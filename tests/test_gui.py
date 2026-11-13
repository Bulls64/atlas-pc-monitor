"""Essai de bout en bout de l'interface PySide6, sans écran (plateforme Qt « offscreen »)."""

import copy
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from conftest import PAYLOAD  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402


@pytest.fixture
def win(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from atlas import collect
    from atlas.gui import theme, window

    monkeypatch.setattr(collect, "is_windows", lambda: True)
    theme.load_fonts()
    theme.set_theme("dark")

    def fake_scan():
        return collect.scan(runner=lambda: (0, json.dumps(PAYLOAD), ""))

    w = window.MainWindow(scanner=fake_scan)
    qtbot.addWidget(w)
    w.resize(1320, 900)
    w.show()
    qtbot.waitUntil(lambda: bool(w.data) and not w._scanning, timeout=5000)
    return w


def texts(widget):
    from PySide6.QtWidgets import QLabel

    return [label.text() for label in widget.findChildren(QLabel)]


def table_values(widget):
    from atlas.gui.widgets import CopyTable

    return [t.item(r, c).text() for t in widget.findChildren(CopyTable) for r in range(t.rowCount()) for c in range(t.columnCount())]


def test_fonts_are_bundled(qapp):
    from PySide6.QtGui import QFontDatabase

    from atlas.gui import theme

    theme.load_fonts()
    families = set(QFontDatabase.families())
    assert {"Space Grotesk", "Inter", "IBM Plex Mono"} <= families


def test_every_page_renders(win, qtbot):
    from atlas.pages import PAGES

    for name, _icon in PAGES:
        win.open_page(name)
        assert win.scroll.widget().findChildren(type(win.scroll.widget())), name
        assert win.nav[name].isChecked()
        assert sum(button.isChecked() for button in win.nav.values()) == 1


def test_overview_board_and_nav_badge(win, qtbot):
    from atlas.gui.boardmap import BoardMap

    assert win.nav["Constats"].badge.text() == "2" and win.nav["Constats"].badge.isVisible()
    assert "2 à surveiller" in texts(win.scroll.widget())
    board = win.scroll.widget().findChild(BoardMap)
    assert board.chips["ram"].level == "watch"
    with qtbot.waitSignal(board.pageRequested) as signal:
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        scale, dx = board._transform()
        point = QPointF(dx + 150 * scale, 110 * scale)  # puce mémoire
        event = QMouseEvent(
            QMouseEvent.MouseButtonRelease,
            point,
            board.mapToGlobal(QPoint(int(point.x()), int(point.y()))),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        board.mouseReleaseEvent(event)
    assert signal.args == ["Mémoire"]
    assert win.page == "Mémoire"


def test_findings_and_memory_pages(win):
    from atlas.gui.dimm import DimmStick, RouteTrace

    win.open_page("Constats")
    page_texts = texts(win.scroll.widget())
    assert "Barrettes dépareillées" in page_texts and "Disque en alerte : ST1000LM035" in page_texts
    win.open_page("Mémoire")
    assert len(win.scroll.widget().findChildren(DimmStick)) == 2
    assert len(win.scroll.widget().findChildren(RouteTrace)) == 2
    assert "Mémoire Générique" in table_values(win.scroll.widget())


def test_copy_and_search(win, qtbot):
    from atlas.gui.widgets import CopyTable

    win.open_page("Stockage")
    table = win.scroll.widget().findChildren(CopyTable)[0]
    table.selectRow(0)
    table.copy_rows()
    assert "SAMSUNG MZVLB512HBJQ" in QGuiApplication.clipboard().text()
    table.copy_value(0)
    assert QGuiApplication.clipboard().text() == "SAMSUNG MZVLB512HBJQ"
    win.copy_report()
    assert QGuiApplication.clipboard().text().startswith("ATLAS PC")
    win.search.setText("nvme")
    qtbot.waitUntil(lambda: win.query == "nvme", timeout=2000)
    assert "NVMe" in table_values(win.scroll.widget())
    assert not any(button.isChecked() for button in win.nav.values())
    win.search.clear()
    qtbot.waitUntil(lambda: win.query == "", timeout=2000)
    assert win.nav["Stockage"].isChecked()


def test_theme_switch_during_scan_does_not_start_a_second_scan(win, qtbot):
    from atlas import settings
    from atlas.gui import theme

    calls = []
    original = win.scanner

    def slow():
        calls.append(1)
        time.sleep(0.4)
        return original()

    win.scanner = slow
    win.refresh()
    win.refresh()
    win.toggle_theme()
    assert not win.refresh_button.isEnabled() and theme.P.name == "light"
    win.refresh()
    qtbot.waitUntil(lambda: not win._scanning, timeout=5000)
    assert calls == [1] and win.refresh_button.isEnabled()
    assert settings.load_config()["theme"] == "light"
    win.toggle_theme()


def test_sharing_mode(win, monkeypatch, tmp_path):
    from atlas import settings
    from atlas.gui import window
    from atlas.privacy import HOST_MASK

    win.open_page("Carte mère")
    assert "PF3ABCDE" in table_values(win.scroll.widget())
    win.toggle_sharing()
    assert win.sharing and win.sharing_button.isChecked() and settings.load_config()["sharing"] is True
    assert "PF3ABCDE" not in table_values(win.scroll.widget()) and "[masqué]" in table_values(win.scroll.widget())
    assert win.data["bios"]["SerialNumber"] == "PF3ABCDE"
    win.copy_report()
    assert HOST_MASK in QGuiApplication.clipboard().text() and "PF3ABCDE" not in QGuiApplication.clipboard().text()
    assert "PF3ABCDE" not in win.fiche_html(win.fiche_info)
    target = tmp_path / "partage"
    monkeypatch.setattr(window.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "Rapport JSON (*.json)"))
    win.export()
    saved = json.loads((tmp_path / "partage.json").read_text(encoding="utf-8"))
    assert saved["anonymized"] is True and saved["bios"]["SerialNumber"] == "[masqué]"

    win.toggle_sharing()
    shown = []
    monkeypatch.setattr(window.QFileDialog, "getOpenFileName", lambda *a, **k: (str(tmp_path / "partage.json"), ""))
    monkeypatch.setattr(window.QMessageBox, "information", lambda _parent, _title, message: shown.append(message))
    win.compare()
    assert shown and "Aucune différence" in shown[0]


def test_export_follows_chosen_filter(win, monkeypatch, tmp_path):
    from atlas.gui import window

    monkeypatch.setattr(window.QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "rapport"), "Fichier texte (*.txt)"))
    win.export()
    assert (tmp_path / "rapport.txt").read_text(encoding="utf-8").startswith("ATLAS PC")


def test_compare_shows_differences(win, monkeypatch, tmp_path):
    from atlas import export
    from atlas.gui import window
    from atlas.gui.dialogs import CompareDialog

    old = copy.deepcopy(win.data)
    old["gpu"][0]["DriverVersion"] = "31.0"
    path = tmp_path / "old.json"
    path.write_text(export.to_json(old), encoding="utf-8")
    monkeypatch.setattr(window.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    win.compare()
    dialogs = win.findChildren(CompareDialog)
    assert dialogs and "31.0" in [dialogs[0].table.item(r, 2).text() for r in range(dialogs[0].table.rowCount())]


def test_fiche_dialog(win, monkeypatch, tmp_path):
    from atlas import settings
    from atlas.gui import window

    opened = []
    monkeypatch.setattr(window.webbrowser, "open", lambda uri: opened.append(uri) or True)
    monkeypatch.setattr(window.tempfile, "gettempdir", lambda: str(tmp_path))
    win.open_fiche()
    dialog = win.fiche_dialog
    assert dialog.entries["reference"].text().startswith("INT-")
    dialog.entries["technician"].setText("Chris")
    dialog.entries["client"].setText("Mme Dupont")
    dialog.texts["request"].setPlainText("Lenteurs")
    dialog.insert_advice(dialog.texts["recommendations"])
    dialog.insert_advice(dialog.texts["recommendations"])  # pas de doublon
    assert dialog.texts["recommendations"].toPlainText().count("- Barrettes dépareillées") == 1
    win.open_fiche()  # déjà ouverte : pas de second dialogue
    assert win.fiche_dialog is dialog
    dialog.close()
    assert win.fiche_info.client == "Mme Dupont" and win.fiche_info.request == "Lenteurs"
    assert settings.load_config()["technician"] == "Chris"
    target = win.print_fiche(win.fiche_info)
    assert opened == [target.as_uri()] and "Mme Dupont" in target.read_text(encoding="utf-8")
    monkeypatch.setattr(window.QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "ma-fiche"), ""))
    saved = win.save_fiche(win.fiche_info)
    assert saved.name == "ma-fiche.html" and "Lenteurs" in saved.read_text(encoding="utf-8")


def test_narrow_window_stacks_rows(win, qtbot):
    from atlas.gui.widgets import Responsive

    win.resize(1000, 640)
    win.open_page("Vue d'ensemble")
    qtbot.wait(100)
    rows = win.scroll.widget().findChildren(Responsive)
    assert rows and rows[0].columns == 1
    assert not win.status.isVisible()
    win.resize(1320, 900)
    qtbot.wait(100)
    assert win.scroll.widget().findChildren(Responsive)[0].columns == 2


def test_closing_during_scan_is_clean(qapp, qtbot, monkeypatch, tmp_path):
    """Fenêtre fermée et détruite pendant l'analyse : le thread de collecte se termine sans erreur."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from atlas import collect
    from atlas.gui import window

    def slow():
        time.sleep(0.3)
        return collect.scan(runner=lambda: (0, json.dumps(PAYLOAD), ""))

    w = window.MainWindow(scanner=slow)  # non suivie par qtbot : on la détruit nous-mêmes
    w.show()
    w.close()
    w.deleteLater()
    qtbot.wait(700)
