import copy
import json

import pytest

from atlas import export, fiche, pages, privacy, upgrade

GIB = 1024**3


# ---------------------------------------------------------------------- mode partage


@pytest.mark.parametrize(
    ("mac", "masked"),
    [("AA-BB-CC-DD-EE-FF", "AA-BB-CC-xx-xx-xx"), ("aa:bb:cc:dd:ee:ff", "aa:bb:cc:xx:xx:xx"), ("bizarre", "[masqué]"), ("", "")],
)
def test_mask_mac(mac, masked):
    assert privacy.mask_mac(mac) == masked


@pytest.mark.parametrize(
    ("ip", "masked"),
    [
        ("192.168.1.42", "192.168.1.x"),
        ("192.168.1.1, 1.1.1.1", "192.168.1.x, 1.1.1.x"),
        ("fe80::1%12", "fe80::[masqué]"),
        ("2a01:e0a:1:2::5", "[masqué]"),
        ("pas une ip", "[masqué]"),
    ],
)
def test_mask_ip(ip, masked):
    assert privacy.mask_ip(ip) == masked


def test_anonymize_masks_identifiers_only(data):
    original = copy.deepcopy(data)
    data["machine"].update(PartOfDomain=True, Domain="ENTREPRISE.LOCAL")
    shared = privacy.anonymize(data)
    assert data["bios"]["SerialNumber"] == "PF3ABCDE"  # l'original n'est pas touché
    assert shared["anonymized"] is True and privacy.anonymize(shared) is shared
    text = json.dumps(shared, ensure_ascii=False)
    for secret in ("PF3ABCDE", "1234ABCD", "S4EWNX0R", "WL1ABCDE", "DD-EE-FF", "192.168.1.42", "fe80::1", "ENTREPRISE", '"vm"'):
        assert secret not in text, secret
    assert shared["system"]["computer"] == privacy.HOST_MASK
    # le diagnostic reste intact
    assert shared["machine"]["Model"] == "82JU" and shared["disks"][0]["Model"] == "SAMSUNG MZVLB512HBJQ"
    assert shared["ram"][0]["PartNumber"] == original["ram"][0]["PartNumber"]
    assert shared["gpu"] == original["gpu"]


def test_shared_exports_say_so(data):
    shared = privacy.anonymize(data)
    assert "identifiants masqués (mode partage)" in export.to_text(shared)
    assert "PF3ABCDE" not in export.to_html(shared)
    page = fiche.to_html(shared)
    assert "Identifiants masqués" in page and "PF3ABCDE" not in page and "[masqué]" in page


def test_anonymize_tolerates_odd_shapes():
    assert privacy.anonymize({}) == {"anonymized": True}
    assert privacy.anonymize("x") == "x"
    odd = privacy.anonymize({"bios": [{"SerialNumber": "A"}], "network": {"IPv4": "10.0.0.5"}, "adapters": None})
    assert odd["bios"][0]["SerialNumber"] == privacy.MASK and odd["network"]["IPv4"] == "10.0.0.x"


def test_cli_anonyme(capsys):
    from atlas.__main__ import main

    assert main(["--json", "--anonyme"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["anonymized"] is True and report["system"]["computer"] == privacy.HOST_MASK


# ---------------------------------------------------------------------- conseiller d'évolution


def advice_for(data, sticks=None, slots=None, max_gib=None, **stick_fields):
    d = copy.deepcopy(data)
    if sticks is not None:
        d["ram"] = [dict(d["ram"][0], DeviceLocator=f"DIMM {i}", **stick_fields) for i in range(sticks)]
    elif stick_fields:
        for stick in d["ram"]:
            stick.update(stick_fields)
    if slots is not None:
        d["memoryarray"]["MemoryDevices"] = slots
    if max_gib is not None:
        d["memoryarray"]["MaxCapacity"] = max_gib * 1024 * 1024
    return upgrade.memory_advice(d)


def test_sample_laptop(data):
    advice = upgrade.memory_advice(data)
    assert advice.current == "16 Go installés : 2 × 8 Go DDR4 SO-DIMM ; emplacements occupés : 2 sur 2."
    assert advice.spec == "DDR4 SO-DIMM 3200 MT/s"
    assert advice.options == [("Passer à 32 Go", "remplacer par 2 × 16 Go"), ("Passer à 64 Go", "remplacer par 2 × 32 Go")]
    assert any("64 Go" in note and "prudente" in note for note in advice.notes)


def test_single_stick_with_free_slot(data):
    advice = advice_for(data, sticks=1)
    goal, way = advice.options[0]
    assert goal == "Passer à 16 Go" and way == "ajouter 1 × 8 Go identique ; ou remplacer par 2 × 8 Go"


def test_no_odd_number_of_sticks_and_ddr5_four_dimm_warning(data):
    advice = advice_for(data, sticks=2, slots=4, max_gib=192, SMBIOSMemoryType=34, FormFactor=8, Speed=6000, Capacity=16 * GIB)
    options = dict(advice.options)
    assert options["Passer à 48 Go"] == "remplacer par 2 × 24 Go"  # pas de 3e barrette
    assert options["Passer à 64 Go"].startswith("ajouter 2 × 16 Go identiques (4 barrettes DDR5 : vitesse souvent réduite)")
    assert options["Passer à 96 Go"] == "remplacer par 2 × 48 Go"
    assert len(advice.options) == 3


def test_limits(data):
    capped = advice_for(data, max_gib=32)
    assert [goal for goal, _ in capped.options] == ["Passer à 32 Go"]
    full = advice_for(data, max_gib=16)
    assert full.options == [] or all("16" not in goal for goal, _ in full.options)
    one_slot = advice_for(data, sticks=1, slots=1)
    assert dict(one_slot.options)["Passer à 16 Go"] == "remplacer par 1 × 16 Go"


def test_soldered_memory(data):
    lp = advice_for(data, SMBIOSMemoryType=35, FormFactor=0)
    assert not lp.upgradable and lp.options == [] and "soudée" in lp.notes[0]
    bga = advice_for(data, FormFactor=21)
    assert not bga.upgradable and "soudée" in bga.notes[0]
    mixed = copy.deepcopy(data)
    mixed["ram"][0]["FormFactor"] = 21  # 8 Go soudés + 1 emplacement SO-DIMM
    advice = upgrade.memory_advice(mixed)
    assert advice.upgradable and any("8 Go semblent soudés" in note for note in advice.notes)
    assert advice.spec == "DDR4 SO-DIMM 3200 MT/s"
    assert advice.options == [
        ("Passer à 24 Go", "remplacer la barrette amovible par 1 × 16 Go"),
        ("Passer à 40 Go", "remplacer la barrette amovible par 1 × 32 Go"),
    ]


def test_no_ram_no_advice():
    assert upgrade.memory_advice({}) is None
    assert upgrade.memory_advice({"ram": [{"Capacity": "x"}]}) is None


def test_memory_page_section(data):
    section = next(s for s in pages.page_memory(data) if s.title == "Évolution possible")
    rows = {row.label: row.value for row in section.rows}
    assert rows["Barrettes à acheter"] == "DDR4 SO-DIMM 3200 MT/s" and rows["Passer à 32 Go"] == "Remplacer par 2 × 16 Go"
    assert "prudente" in section.tip and not section.note


def test_no_memory_upgrade_advice_on_a_virtual_machine(data):
    vm = copy.deepcopy(data)
    vm["machine"].update(Manufacturer="VMware, Inc.", Model="VMware20,1")
    advice = upgrade.memory_advice(vm)
    assert not advice.upgradable and "hyperviseur" in advice.notes[0]
