import copy
import json

from atlas import export, pages
from atlas.formatting import EMPTY


def rows_of(sections, title):
    section = next(s for s in sections if s.title.startswith(title))
    return {row.label: row.value for row in section.rows}


def test_every_page_builds(data):
    built = pages.build_all(data)
    assert list(built) == pages.DETAIL_PAGES
    for sections in built.values():
        assert sections
        for section in sections:
            assert all(row.value and row.value != EMPTY for row in section.rows)


def test_every_page_builds_without_data():
    minimal = {"system": {"computer": "pc", "platform": "Linux", "architecture": "x86_64"}, "note": "x"}
    for sections in pages.build_all(minimal).values():
        assert sections
    assert export.to_text(minimal) and export.to_html(minimal)


def test_memory_page(data):
    sections = pages.page_memory(data)
    summary = rows_of(sections, "Synthèse")
    assert summary["Mémoire installée"] == "16 Go"
    assert summary["Mémoire utilisable par Windows"] == "15,9 Go"
    assert summary["Emplacements occupés"] == "2 sur 2"
    assert summary["Capacité maximale de la carte mère"] == "64 Go"
    stick = rows_of(sections, "Barrette 2")
    assert stick["Capacité"] == "8 Go" and stick["Type"] == "DDR4" and stick["Format"] == "SO-DIMM"
    assert stick["Vitesse nominale"] == "3200 MT/s" and stick["Vitesse configurée"] == "2933 MT/s"


def test_graphics_page(data):
    sections = pages.page_graphics(data)
    assert rows_of(sections, "Carte graphique 1")["Mémoire dédiée"] == "6 Go"
    assert "plafonnée" in rows_of(sections, "Carte graphique 2")["Mémoire dédiée"]
    assert rows_of(sections, "Écran")["Diagonale"].startswith("15,3 pouces")


def test_storage_page(data):
    sections = pages.page_storage(data)
    ssd = rows_of(sections, "Disque 1")
    assert ssd["Type"] == "SSD" and ssd["Interface"] == "NVMe" and ssd["Capacité"] == "512,1 Go"
    assert ssd["État de santé"] == "Sain" and ssd["Heures de fonctionnement"] == "5120 h"
    hdd_section = next(s for s in sections if s.title.startswith("Disque 2"))
    hdd = {row.label: row.value for row in hdd_section.rows}
    assert hdd["Type"] == "Disque dur (HDD)" and hdd["Interface"] == "SATA" and hdd["État de santé"] == "Avertissement"
    assert "administrateur" in hdd_section.note
    assert "libres" in rows_of(sections, "Volumes")["Volume C:"]
    assert "administrateur" in next(s for s in sections if s.title == "BitLocker").note


def test_system_and_network_pages(data):
    system = pages.page_system(data)
    assert rows_of(system, "Ordinateur")["Modèle"] == "82JU"
    windows = rows_of(system, "Windows")
    assert windows["Version"] == "24H2" and windows["Activation"] == "Activé" and windows["Allumé depuis"] == "2 j 2 h"
    assert "administrateur" in next(s for s in system if s.title == "Sécurité").note
    wifi = rows_of(pages.page_network(data), "Wi-Fi")
    assert wifi["État"] == "Connecté" and wifi["Passerelle"] == "192.168.1.1" and wifi["Adresse IPv6"] == "fe80::1"
    battery = rows_of(pages.page_battery(data), "Batterie")
    assert battery["Usure"] == "15 %" and battery["État"] == "Sur secteur"


def test_search_ignores_accents_and_case(data):
    assert any(row.label == "Modèle" for _p, _s, row in pages.search(data, "modele ryzen"))
    assert pages.search(data, "NVME")[0][0] == "Stockage"
    assert pages.search(data, "   ") == []
    assert pages.search(data, "introuvablexyz") == []


def test_diff_ignores_volatile_and_reports_changes(data):
    assert pages.diff_reports(data, copy.deepcopy(data)) == []
    after = copy.deepcopy(data)
    after["os"]["FreePhysicalMemory"] = 1024  # volatile : ignoré — volatile: ignored
    after["cpu"][0]["LoadPercentage"] = 99
    assert pages.diff_reports(data, after) == []
    after["ram"].pop()  # barrette retirée — module removed
    after["gpu"][0]["DriverVersion"] = "32.0.15.7000"
    after["memory"] = {**after["memory"], "installed": 8 * 1024**3}
    changes = {(where, label): (old, new) for where, label, old, new in pages.diff_reports(data, after)}
    assert changes[("Graphiques › Carte graphique 1", "Version du pilote")] == ("32.0.15.6094", "32.0.15.7000")
    assert changes[("Mémoire › Synthèse", "Mémoire installée")] == ("16 Go", "8 Go")
    assert changes[("Mémoire › Barrette 2 — DIMM 1", "Capacité")] == ("8 Go", EMPTY)


def test_exports(data, tmp_path):
    text = export.to_text(data)
    assert "STOCKAGE" in text and "Mémoire Générique" in text and "Accès refusé" in text
    page = export.to_html({**data, "note": "<script>alert(1)</script>"})
    assert page.startswith("<!DOCTYPE html>") and "<script>" not in page and "&lt;script&gt;" in page
    assert json.loads(export.to_json(data))["ram"][1]["Manufacturer"] == "Mémoire Générique"

    assert export.resolve_path("rapport", "Fichier texte").name == "rapport.txt"
    assert export.resolve_path("rapport", "Page HTML").name == "rapport.html"
    assert export.resolve_path("rapport", "").name == "rapport.json"
    assert export.resolve_path("rapport.TXT", "Rapport JSON").name == "rapport.TXT"
    assert export.resolve_path("pc.v2", "Page HTML").name == "pc.v2.html"

    saved = export.save(data, str(tmp_path / "poste"), "Fichier texte")
    assert saved.suffix == ".txt" and saved.read_text(encoding="utf-8").startswith("ATLAS PC MONITOR")
    saved = export.save(data, str(tmp_path / "poste.json"))
    assert export.load(str(saved))["machine"]["Model"] == "82JU"


def test_load_rejects_foreign_json(tmp_path):
    import pytest

    path = tmp_path / "autre.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        export.load(str(path))


def test_cli(capsys, tmp_path):
    from atlas.__main__ import main

    assert main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["atlas_version"]
    assert main(["--text"]) == 0
    assert capsys.readouterr().out.startswith("ATLAS PC MONITOR")
    target = tmp_path / "r.html"
    assert main(["-o", str(target)]) == 0
    assert target.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_diff_keeps_devices_with_the_same_name(data):
    """Deux périphériques audio du même nom : le changement du second n'est pas écrasé par le premier.

    Two audio devices with the same name: the change to the second one is not overwritten by the first.
    """
    before = copy.deepcopy(data)
    before["audio"] = [{"Name": "Périphérique audio HD", "Status": "OK"}, {"Name": "Périphérique audio HD", "Status": "OK"}]
    after = copy.deepcopy(before)
    after["audio"][1]["Status"] = "Error"
    assert pages.diff_reports(before, after) == [("Audio › Périphériques audio", "Périphérique audio HD (2)", "OK", "Error")]


def test_cli_reports_unwritable_output(capsys, tmp_path):
    from atlas.__main__ import main

    assert main(["--json", "-o", str(tmp_path / "absent" / "rapport.json")]) == 2
    assert "Impossible d'écrire" in capsys.readouterr().err


def test_cli_exit_code_on_failed_windows_scan(monkeypatch, capsys):
    """Code 1 seulement si la collecte a échoué sous Windows ; hors Windows, l'inventaire réduit est normal.

    Exit code 1 only if the collection failed on Windows; outside Windows, the reduced inventory is normal.
    """
    from atlas import collect
    from atlas.__main__ import main

    assert main(["--json"]) == 0
    monkeypatch.setattr(collect, "is_windows", lambda: True)
    monkeypatch.setattr("atlas.__main__.scan", lambda: collect.scan(runner=lambda: (1, "", "accès refusé")))
    assert main(["--json"]) == 1


def test_cli_converts_a_saved_report(tmp_path, capsys, data):
    """Hors Windows, la ligne de commande transforme un rapport JSON en texte, HTML ou fiche.

    Outside Windows, the command line turns a JSON report into text, HTML or a sheet.
    """
    from atlas.__main__ import main

    path = tmp_path / "rapport.json"
    path.write_text(export.to_json(data), encoding="utf-8")
    assert main(["--text", str(path)]) == 0
    assert data["system"]["computer"] in capsys.readouterr().out
    target = tmp_path / "fiche.html"
    assert main(["--fiche", "--anonyme", "--technicien", "Chris", str(path), "-o", str(target)]) == 0
    html = target.read_text(encoding="utf-8")
    assert "Chris" in html and data["system"]["computer"] not in html
    assert main(["--json", str(tmp_path / "absent.json")]) == 2
    assert "Rapport illisible" in capsys.readouterr().err
