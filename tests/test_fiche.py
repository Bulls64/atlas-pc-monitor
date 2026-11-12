import copy
import re

from atlas import fiche
from atlas.findings import analyze


def test_fiche_with_all_fields(data):
    info = fiche.FicheInfo(
        technician="Chris", client="Mme Dupont <SARL & Fils>", contact="06 00 00 00 00", reference="INT-42",
        request="Le PC rame au démarrage.", work="Nettoyage\nMise à jour du pilote", recommendations="Ajouter 8 Go",
    )  # fmt: skip
    page = fiche.to_html(data, info)
    assert page.startswith("<!DOCTYPE html>") and "@page { size: A4" in page
    assert "Mme Dupont &lt;SARL &amp; Fils&gt;" in page and "<SARL" not in page
    assert "INT-42" in page and "Chris" in page and "Le PC rame au démarrage." in page
    assert "Nettoyage\nMise à jour du pilote" in page  # retours à la ligne conservés (pre-wrap)
    assert "LENOVO · 82JU" in page and "PF3ABCDE" in page and "AMD Ryzen 7 5800H" in page
    assert "Diagnostic automatique — 2 à surveiller" in page
    assert page.count('class="finding watch"') == 2 and "Barrettes dépareillées" in page
    assert "✓ " in page and "Batterie en bon état" in page
    assert "À noter : Mémoire sous sa vitesse nominale · Analyse partielle sans droits administrateur" in page
    assert 'class="finding info"' not in page  # les points « à noter » tiennent sur une ligne
    assert 'class="free blank"' not in page
    assert "Signature du client" in page and "window.print()" in page


def test_blank_fiche_has_handwriting_zones(data):
    page = fiche.to_html(data)
    assert page.count('class="free blank"') == 3
    assert re.search(r"Référence <strong>INT-20261111-1030</strong>", page)


def test_machine_rows(data):
    rows = dict(fiche.machine_rows(data))
    assert rows["Fabricant et modèle"] == "LENOVO · 82JU · Legion 5 15ACH6H"
    assert rows["Windows"] == "Microsoft Windows 11 Famille · 24H2 · build 26100 · Activé"
    assert rows["Mémoire"] == "16 Go · 2 barrette(s) · DDR4"
    assert rows["Batterie"] == "usure 15 %"
    disks = [value for label, value in fiche.machine_rows(data) if label == "Disque"]
    assert disks == ["SAMSUNG MZVLB512HBJQ · 512,1 Go · SSD · sain", "ST1000LM035 · 1 To · Disque dur (HDD) · en alerte"]


def test_fiche_states(data):
    clean = copy.deepcopy(data)
    clean["ram"] = clean["ram"][:1] + [dict(clean["ram"][0], DeviceLocator="DIMM 1", BankLabel="P0 CHANNEL B")]
    clean["disks"][1]["Health"] = "Healthy"
    clean["errors"] = {}
    clean["admin"] = True
    found = analyze(clean)
    page = fiche.to_html(clean, found=[item for item in found if item.level == "ok"])
    assert "Aucun point à corriger ni à surveiller." in page and "Rien à signaler" in page

    outside = {"system": {"computer": "pc", "platform": "Linux"}, "note": "Hors Windows", "captured_at": "2026-11-12T09:00:00"}
    page = fiche.to_html(outside)
    assert "Diagnostic automatique indisponible" in page and "Hors Windows" in page and "INT-20261112-0900" in page


def test_cli_fiche(tmp_path, capsys):
    from atlas.__main__ import main

    target = tmp_path / "fiche.html"
    assert main(["--fiche", "--client", "Dupont", "--technicien", "Chris", "-o", str(target)]) == 0
    page = target.read_text(encoding="utf-8")
    assert "Fiche d'intervention" in page and "Dupont" in page and "Chris" in page
    assert main(["--fiche"]) == 0
    assert "Fiche d'intervention" in capsys.readouterr().out
