import copy

import pytest

from atlas import findings as F

GIB = 1024**3


def titles(found, level=None):
    return [item.title for item in found if level is None or item.level == level]


def test_sample_machine(data):
    found = F.analyze(data)
    assert titles(found, F.WATCH) == ["Barrettes dépareillées", "Disque en alerte : ST1000LM035"]
    assert "Mémoire sous sa vitesse nominale" in titles(found, F.INFO)  # SO-DIMM : simple information — SO-DIMM: information only
    assert "Analyse partielle sans droits administrateur" in titles(found, F.INFO)
    assert "Batterie en bon état" in titles(found, F.OK)
    assert "Aucun périphérique en erreur" in titles(found, F.OK)
    assert [F.ORDER[item.level] for item in found] == sorted(F.ORDER[item.level] for item in found)
    assert F.summary_text(found) == "2 à surveiller"


def test_nothing_without_windows_inventory():
    assert F.analyze({}) == []
    assert F.analyze({"system": {}, "note": "hors Windows"}) == []
    assert F.analyze("pas un dict") == []
    assert F.summary_text([]) == "Aucun constat"


def test_garbage_values_never_raise(data):
    broken = copy.deepcopy(data)
    for section in ("ram", "disks", "volumes", "gpu", "battery", "pnp", "license", "bitlocker"):
        broken[section] = [{"Capacity": "x", "Speed": [], "Size": {}, "DriverDate": 12, "ConfigManagerErrorCode": "z"}]
    broken["os"]["BuildNumber"] = "abc"
    broken["memory"] = {"percent": "beaucoup"}
    broken["captured_at"] = None
    assert isinstance(F.analyze(broken), list)


def test_single_stick_and_same_channel(data):
    one = copy.deepcopy(data)
    one["ram"] = one["ram"][:1]
    found = F.analyze(one)
    assert "Mémoire en mono-canal" in titles(found, F.WATCH)
    assert "1 emplacement(s) libre(s)" in next(i.detail for i in found if i.title == "Mémoire en mono-canal")
    one["memoryarray"]["MemoryDevices"] = 1
    assert "Une seule barrette, un seul emplacement" in titles(F.analyze(one), F.INFO)

    same = copy.deepcopy(data)
    for stick in same["ram"]:
        stick["BankLabel"] = "P0 CHANNEL A"
    assert "Barrettes probablement sur le même canal" in titles(F.analyze(same), F.WATCH)


@pytest.mark.parametrize(
    ("bank", "locator", "channel"),
    [("P0 CHANNEL B", "DIMM 0", "B"), ("BANK 0", "ChannelA-DIMM0", "A"), ("", "DIMM_B2", "B"), ("BANK 1", "DIMM 1", None)],
)
def test_memory_channel(bank, locator, channel):
    assert F.memory_channel({"BankLabel": bank, "DeviceLocator": locator}) == channel


def test_desktop_memory_below_rated_speed(data):
    desktop = copy.deepcopy(data)
    for stick in desktop["ram"]:
        stick.update(FormFactor=8, PartNumber="F4-3600C16", Speed=3600, ConfiguredClockSpeed=2133)
    found = F.analyze(desktop)
    item = next(i for i in found if i.title == "Mémoire sous sa vitesse nominale")
    assert item.level == F.WATCH and "3600 MT/s annoncés, 2133 MT/s configurés" in item.detail and "XMP" in item.advice
    assert "Barrettes dépareillées" not in titles(found)
    assert "Mémoire : rien à signaler" not in titles(found)


def test_storage_rules(data):
    bad = copy.deepcopy(data)
    bad["disks"][0].update(Health="Unhealthy", Wear=85, Temperature=67)
    bad["volumes"] = [
        {"DeviceID": "C:", "Size": 500 * 1000**3, "FreeSpace": 15 * 1000**3},  # 3 %
        {"DeviceID": "D:", "Size": 1000 * 1000**3, "FreeSpace": 80 * 1000**3},  # 8 %
        {"DeviceID": "E:", "Size": 1 * 1000**3, "FreeSpace": 0},  # petite partition ignorée — small partition ignored
    ]
    bad["bitlocker"] = [{"MountPoint": "C:", "Protection": "Off"}]
    found = F.analyze(bad)
    assert {"Disque défaillant : SAMSUNG MZVLB512HBJQ", "SSD très usé : SAMSUNG MZVLB512HBJQ", "Volume C: presque plein"} <= set(
        titles(found, F.FIX)
    )
    assert {"Disque chaud : SAMSUNG MZVLB512HBJQ", "Volume D: bien rempli"} <= set(titles(found, F.WATCH))
    assert "Volume système C: non chiffré" in titles(found, F.INFO)
    assert not any("E:" in t for t in titles(found))
    assert "Stockage : rien à signaler" not in titles(found)

    smart = copy.deepcopy(data)
    smart["disks"] = [{"Model": "WDC WD10", "Status": "Pred Fail", "Size": 10**12}]
    assert "Disque défaillant : WDC WD10" in titles(F.analyze(smart), F.FIX)


def test_windows10_and_eligibility(data):
    old = copy.deepcopy(data)
    old["os"].update(Caption="Microsoft Windows 10 Professionnel", BuildNumber="19045", FirmwareType="Legacy")
    old["tpm"] = {"SpecVersion": "1.2, 2, 3"}
    found = F.analyze(old)
    assert "Windows 10 n'est plus pris en charge" in titles(found, F.FIX)
    eligible = next(i for i in found if i.title == "Non éligible à Windows 11 en l'état")
    assert eligible.detail == "Manque : TPM 2.0, démarrage UEFI."

    old["tpm"] = {}
    old["os"]["FirmwareType"] = "UEFI"
    found = F.analyze(old)
    assert "Éligibilité à Windows 11 à confirmer" in titles(found, F.INFO)

    old["tpm"] = {"SpecVersion": "2.0, 0, 1.38"}
    assert "Configuration minimale de Windows 11 respectée" in titles(F.analyze(old), F.OK)

    before_end = copy.deepcopy(old)
    before_end["captured_at"] = "2025-06-01T10:00:00+02:00"
    before_end["os"]["LastBootUpTime"] = "2025-05-31T10:00:00"
    assert "Fin de prise en charge de Windows 10 proche" in titles(F.analyze(before_end), F.WATCH)


def test_windows_misc(data):
    misc = copy.deepcopy(data)
    misc["license"] = [{"LicenseStatus": 5}]
    misc["secureboot"] = {"Enabled": False}
    misc["os"]["LastBootUpTime"] = "2026-10-01T08:00:00"
    misc["memory"]["percent"] = 94
    found = F.analyze(misc)
    assert "Windows n'est pas activé" in titles(found, F.FIX)
    assert {"Démarrage sécurisé désactivé", "Pas de redémarrage depuis 41 jours", "Mémoire presque saturée"} <= set(titles(found, F.WATCH))


def test_drivers_and_devices(data):
    dev = copy.deepcopy(data)
    dev["gpu"] = [
        {"Name": "Microsoft Basic Display Adapter"},
        {"Name": "NVIDIA GeForce GTX 1060", "DriverDate": "2024-03-01"},
        {"Name": "Parsec Virtual Display Adapter", "DriverDate": "2019-01-01"},
    ]
    dev["pnp"] = [
        {"Name": "Contrôleur SM Bus", "ConfigManagerErrorCode": 28},
        {"Name": "Webcam", "ConfigManagerErrorCode": 22},
        {"Name": "Clé USB débranchée", "ConfigManagerErrorCode": 45},
    ]
    found = F.analyze(dev)
    assert {"Pilote graphique générique", "1 périphérique(s) en erreur"} <= set(titles(found, F.FIX))
    old_driver = [i for i in found if i.title == "Pilote graphique ancien"]
    assert len(old_driver) == 1 and "GTX 1060" in old_driver[0].detail
    broken = next(i for i in found if i.title == "1 périphérique(s) en erreur")
    assert broken.detail == "Contrôleur SM Bus — code 28 : pilote non installé"
    assert "1 périphérique(s) désactivé(s)" in titles(found, F.INFO)
    assert "Aucun périphérique en erreur" not in titles(found)


def test_no_all_clear_for_devices_when_query_failed(data):
    failed = copy.deepcopy(data)
    failed["errors"]["pnp"] = "Accès refusé."
    assert "Aucun périphérique en erreur" not in titles(F.analyze(failed))


@pytest.mark.parametrize(("full", "level", "title"), [(36000, F.FIX, "Batterie à remplacer"), (52000, F.WATCH, "Batterie usée")])
def test_battery(data, full, level, title):
    worn = copy.deepcopy(data)
    worn["battery"][0]["FullCapacity"] = full
    assert title in titles(F.analyze(worn), level)


def test_findings_in_exports_and_system_page(data):
    from atlas import export, pages

    dev = copy.deepcopy(data)
    dev["pnp"] = [{"Name": "Contrôleur SM Bus", "ConfigManagerErrorCode": 28}]
    dev["os"]["FirmwareType"] = "UEFI"
    text = export.to_text(dev)
    assert "CONSTATS — 1 À CORRIGER · 2 À SURVEILLER" in text
    assert "[À corriger] 1 périphérique(s) en erreur" in text
    page = export.to_html(dev)
    assert 'class="finding fix"' in page and "Constats — 1 à corriger" in page
    system = pages.page_system(dev)
    errors = next(s for s in system if s.title == "Périphériques en erreur")
    assert errors.rows[0].value == "Code 28 : pilote non installé"
    security = {r.label: r.value for r in next(s for s in system if s.title == "Sécurité").rows}
    assert security["Mode de démarrage"] == "UEFI"
    assert pages.FINDINGS not in pages.DETAIL_PAGES


@pytest.mark.parametrize(
    ("caption", "build", "when", "level", "title"),
    [
        ("Microsoft Windows 10 Entreprise LTSC", "17763", "2026-11-13", F.INFO, "Windows 10 pris en charge jusqu'en 2029"),
        ("Microsoft Windows 10 IoT Entreprise LTSC", "19044", "2026-11-13", F.INFO, "Windows 10 pris en charge jusqu'en 2032"),
        ("Microsoft Windows 10 Entreprise LTSC", "19044", "2026-11-13", F.WATCH, "Fin de prise en charge de Windows 10 proche"),
        ("Microsoft Windows 10 Entreprise 2016 LTSB", "14393", "2026-11-13", F.FIX, "Windows 10 n'est plus pris en charge"),
        ("Microsoft Windows 10 Professionnel", "19045", "2026-11-13", F.FIX, "Windows 10 n'est plus pris en charge"),
    ],
)
def test_windows10_ltsc_has_its_own_calendar(data, caption, build, when, level, title):
    """Les éditions LTSC ne s'arrêtent pas en octobre 2025 : pas d'alerte rouge sur un poste encore suivi.

    LTSC editions do not end in October 2025: no red alert on a computer that is still supported.
    """
    ltsc = copy.deepcopy(data)
    ltsc["captured_at"] = f"{when}T10:00:00+01:00"
    ltsc["os"].update(Caption=caption, BuildNumber=build, LastBootUpTime=f"{when}T08:00:00")
    assert title in titles(F.analyze(ltsc), level)


def test_predictive_failure_from_get_physicaldisk(data):
    """Get-PhysicalDisk écrit « Predictive Failure » en toutes lettres, Win32_DiskDrive « Pred Fail ».

    Get-PhysicalDisk writes "Predictive Failure" in full, Win32_DiskDrive "Pred Fail".
    """
    failing = copy.deepcopy(data)
    failing["disks"] = [{"Model": "ST1000", "Health": "Warning", "Status": "Predictive Failure", "Size": 10**12}]
    assert "Disque défaillant : ST1000" in titles(F.analyze(failing), F.FIX)


def hyperv(data):
    """Ce que renvoie une vraie VM Hyper-V (relevé de la CI Windows, 13/11/2026).

    What a real Hyper-V VM returns (reading from the Windows CI, 13 November 2026).
    """
    vm = copy.deepcopy(data)
    vm["machine"].update(Manufacturer="Microsoft Corporation", Model="Virtual Machine")
    vm["ram"] = [
        {"Capacity": 1 * GIB, "Manufacturer": "Microsoft Corporation", "PartNumber": "None", "SMBIOSMemoryType": 24},
        {"Capacity": 7 * GIB, "Manufacturer": "Microsoft Corporation", "PartNumber": "None", "SMBIOSMemoryType": 24},
    ]
    vm["gpu"] = [{"Name": "Microsoft Hyper-V Video", "DriverDate": "2006-06-21T00:00:00"}]
    vm["pnp"] = [{"Name": None, "PNPClass": None, "ConfigManagerErrorCode": 28}]
    return vm


def test_real_hyperv_inventory(data):
    found = F.analyze(hyperv(data))
    assert not [i for i in found if i.topic == "Mémoire" and i.level != F.OK], "pas de règle de barrettes sur une VM"
    assert "Pilote graphique ancien" not in titles(found)
    broken = next(i for i in found if i.title == "1 périphérique(s) en erreur")
    assert broken.detail == "Périphérique inconnu — code 28 : pilote non installé"


def test_inbox_driver_date_is_ignored_on_real_hardware(data):
    """Le pilote intégré à Windows est daté du 21/06/2006 par convention : pas un pilote vieux de 20 ans.

    The driver built into Windows is dated 21 June 2006 by convention: not a 20-year-old driver.
    """
    inbox = copy.deepcopy(data)
    inbox["gpu"] = [{"Name": "Intel(R) UHD Graphics", "DriverDate": "2006-06-21T00:00:00"}]
    assert "Pilote graphique ancien" not in titles(F.analyze(inbox))
    inbox["gpu"][0]["DriverDate"] = "2019-03-01T00:00:00"
    assert "Pilote graphique ancien" in titles(F.analyze(inbox))


def test_smbios_placeholders_do_not_make_sticks_look_different(data):
    sticks = copy.deepcopy(data)
    for stick in sticks["ram"]:
        stick["PartNumber"] = "None"
    sticks["ram"][1]["PartNumber"] = "To Be Filled By O.E.M."
    assert "Barrettes dépareillées" not in titles(F.analyze(sticks))
