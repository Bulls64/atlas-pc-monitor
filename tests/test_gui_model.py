"""Modèle d'affichage de l'interface PySide6 (sans Qt).

Display model of the PySide6 interface (without Qt).
"""

import copy

from atlas import findings
from atlas.gui import model


def test_board_chips_levels(data):
    chips = model.board_chips(data, findings.analyze(data))
    assert chips["ram"].title == "16 Go DDR4" and chips["ram"].lines == ["2 × 8 Go SO-DIMM"]
    assert chips["ram"].level == "watch" and chips["ram"].issue == "Barrettes dépareillées"
    assert chips["disks"].level == "watch" and chips["disks"].title == "1,5 To"
    assert chips["gpu"].title == "RTX 3060 Laptop" and chips["gpu"].level == "ok"
    assert chips["net"].title == "Wi-Fi 6 AX200" and "connecté" in chips["net"].lines[0]
    assert chips["battery"].title == "83 % · usure 15 %"
    assert chips["cpu"].title == "AMD Ryzen 7 5800H" and chips["cpu"].lines[0] == "8 cœurs · 16 threads"
    assert {c.page for c in chips.values()} <= {"Mémoire", "Stockage", "Graphiques", "Réseau", "Batterie", "Carte mère", "Processeur"}


def test_board_chips_missing_and_fix(data):
    desktop = copy.deepcopy(data)
    desktop["battery"] = []
    desktop["gpu"] = [{"Name": "Microsoft Basic Display Adapter"}]
    desktop["adapters"] = []
    chips = model.board_chips(desktop, findings.analyze(desktop))
    assert chips["battery"].level is None and chips["battery"].title == "Sur secteur"
    assert chips["net"].level is None
    assert chips["gpu"].level == "fix"  # pilote générique — generic driver
    empty = model.board_chips({}, [])
    assert all(chip.level is None for key, chip in empty.items() if key != "cpu")


def test_headings(data):
    assert model.page_heading(data, "Mémoire") == ("16 Go DDR4 SO-DIMM", "2 emplacement(s) sur 2 occupé(s)")
    assert model.page_heading(data, "Système")[0] == "LENOVO 82JU"
    assert model.page_heading(data, "Stockage") == ("1,5 To de stockage", "2 disque(s) · 1 volume(s)")
    assert model.page_heading({}, "Audio") == ("Audio", "")


def test_sticks_and_routes(data):
    views = model.stick_views(data)
    assert [v.odd for v in views] == [False, True]
    assert "2933 MT/s configurés" in views[1].spec
    headers, rows = model.stick_table(data)
    assert headers == ["Propriété", "DIMM 0", "DIMM 1"] and ("Fabricant", "Samsung", "Mémoire Générique") in rows
    advice, routes = model.upgrade_routes(data)
    assert routes == [("16 Go", "32 Go", "Remplacer par 2 × 16 Go"), ("16 Go", "64 Go", "Remplacer par 2 × 32 Go")]
    assert model.upgrade_routes({}) is None
