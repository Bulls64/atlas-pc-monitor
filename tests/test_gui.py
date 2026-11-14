"""Essai de bout en bout de l'interface PySide6, sans écran (plateforme Qt « offscreen »)."""

import copy
import json
import os
import time
from pathlib import Path

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
    assert QGuiApplication.clipboard().text().startswith("ATLAS PC MONITOR")
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
    assert (tmp_path / "rapport.txt").read_text(encoding="utf-8").startswith("ATLAS PC MONITOR")


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


def test_tables_show_every_row(win, qtbot):
    """Aucun tableau ne rogne sa dernière ligne, quelle que soit la largeur (retours à la ligne)."""
    from atlas.gui.widgets import CopyTable

    for width in (1320, 1000, 1600):
        win.resize(width, 900)
        for page in ("Mémoire", "Stockage", "Système"):
            win.open_page(page)
            qtbot.wait(50)
            for table in win.scroll.widget().findChildren(CopyTable):
                needed = sum(table.rowHeight(r) for r in range(table.rowCount()))
                if table.horizontalHeader().isVisible():
                    needed += table.horizontalHeader().height()
                assert table.height() >= needed, (width, page, table.height(), needed)


def test_escape_in_fiche_dialog_keeps_the_input(win, qtbot):
    """Échap ferme le dialogue sans passer par closeEvent : la saisie doit quand même être gardée."""
    from PySide6.QtCore import Qt

    from atlas import settings

    win.open_fiche()
    dialog = win.fiche_dialog
    dialog.entries["technician"].setText("Chris")
    dialog.entries["client"].setText("M. Martin")
    qtbot.keyClick(dialog, Qt.Key_Escape)
    assert not dialog.isVisible()
    assert win.fiche_info.client == "M. Martin" and settings.load_config()["technician"] == "Chris"


def test_saved_sharing_mode_is_shown_at_startup(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from atlas import collect, settings
    from atlas.gui import window

    settings.save_config({"sharing": True})
    w = window.MainWindow(scanner=lambda: collect.scan(runner=lambda: (0, json.dumps(PAYLOAD), "")))
    qtbot.addWidget(w)
    assert w.sharing_button.isChecked() and w.sharing_button.text() == "Partage activé"


def test_theme_switch_keeps_narrow_header(win, qtbot):
    """Changer de thème reconstruit l'en-tête : en fenêtre étroite, l'état doit rester masqué."""
    win.resize(1000, 640)
    qtbot.wait(50)
    assert not win.status.isVisible()
    win.toggle_theme()
    qtbot.wait(50)
    assert not win.status.isVisible() and "v3" not in win.brand_sub.text()
    win.toggle_theme()


def test_inventory_text_is_never_rendered_as_html(win):
    """Un nom de périphérique contenant une balise s'affiche tel quel, pas interprété en HTML."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from atlas.findings import analyze

    win.data = copy.deepcopy(win.data)
    win.data["pnp"] = [{"Name": "Carte <b>son</b>", "ConfigManagerErrorCode": 28}]
    win.findings = analyze(win.data)
    win.open_page("Constats")
    shown = [lab for lab in win.scroll.widget().findChildren(QLabel) if "<b>son</b>" in lab.text()]
    assert shown and all(lab.textFormat() == Qt.PlainText for lab in shown)


def test_compare_warns_about_another_machine_without_naming_it_in_sharing_mode(win, monkeypatch, tmp_path):
    from atlas import export
    from atlas.gui import window
    from atlas.gui.dialogs import CompareDialog

    other = copy.deepcopy(win.data)
    other["system"]["computer"] = "PC-VOISIN"
    other["gpu"][0]["DriverVersion"] = "31.0"
    path = tmp_path / "autre.json"
    path.write_text(export.to_json(other), encoding="utf-8")
    monkeypatch.setattr(window.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    win.toggle_sharing()
    win.compare()
    title = win.findChildren(CompareDialog)[-1].findChildren(type(win.status))[1].text()
    assert "autre poste" in title and "PC-VOISIN" not in title
    win.toggle_sharing()


def saved_report(tmp_path, **changes) -> Path:
    """Rapport JSON tel qu'Atlas PC Monitor l'exporte sur un PC Windows."""
    from atlas import collect, export

    on_windows = collect.is_windows
    collect.is_windows = lambda: True  # comme sur le PC Windows qui a produit le rapport
    try:
        data = collect.scan(runner=lambda: (0, json.dumps(PAYLOAD), ""))
    finally:
        collect.is_windows = on_windows
    data.update(changes)
    path = tmp_path / "poste-client.json"
    path.write_text(export.to_json(data), encoding="utf-8")
    return path


@pytest.fixture
def viewer(qtbot, monkeypatch, tmp_path):
    """Fenêtre hors Windows (autouse not_windows) : visionneuse, sans analyse."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from atlas.gui import theme, window

    theme.load_fonts()
    theme.set_theme("dark")
    w = window.MainWindow(scanner=lambda: pytest.fail("aucune analyse hors Windows"))
    qtbot.addWidget(w)
    return w


def test_viewer_starts_on_welcome_without_scanning(viewer):
    from PySide6.QtWidgets import QLabel

    texts = [lab.text() for lab in viewer.scroll.widget().findChildren(QLabel)]
    assert "Ouvrir un rapport Atlas PC Monitor" in texts
    assert viewer.status.text() == "Aucun rapport ouvert"
    assert not viewer.refresh_button.isVisibleTo(viewer)
    assert not any(button.isEnabled() for button in viewer.data_actions)
    viewer.refresh()  # F5 : sans effet hors Windows
    assert not viewer._scanning and not viewer.data


def test_viewer_opens_a_report(viewer, tmp_path):
    path = saved_report(tmp_path)
    assert viewer.open_report(str(path))
    assert viewer.source == "poste-client.json" and viewer.data["system"]["computer"]
    assert viewer.status.text() == "Rapport ouvert : poste-client.json"
    assert viewer.findings and all(button.isEnabled() for button in viewer.data_actions)
    from atlas.pages import PAGES

    for page, _icon in PAGES:
        viewer.open_page(page)  # chaque page se dessine à partir du rapport


def test_viewer_rejects_a_file_that_is_not_a_report(viewer, tmp_path, monkeypatch):
    from atlas.gui import window

    errors = []
    monkeypatch.setattr(window.QMessageBox, "critical", lambda *args: errors.append(args[2]))
    bad = tmp_path / "autre.json"
    bad.write_text('{"name": "pas un rapport"}', encoding="utf-8")
    assert not viewer.open_report(str(bad))
    assert errors and "autre.json" in errors[0] and not viewer.data


def test_viewer_accepts_a_dropped_report(viewer, tmp_path):
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    path = saved_report(tmp_path)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    viewer.dropEvent(event)
    assert viewer.source == "poste-client.json"
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "photo.png"))])
    assert viewer._dropped_report(QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)) == ""


def test_opened_report_on_windows_then_back_to_this_pc(win, qtbot, tmp_path):
    """Sous Windows, un rapport ouvert ne propose pas « Relancer en administrateur » ; F5 revient au poste."""
    path = saved_report(tmp_path, admin=False)
    assert win.open_report(str(path))
    assert win.refresh_button.text() == "Analyser ce poste" and not win.admin_button.isVisibleTo(win)
    win.refresh()
    qtbot.waitUntil(lambda: not win._scanning, timeout=5000)
    assert win.source == "" and win.refresh_button.text() == "Actualiser"


def test_make_icon_writes_a_png(qapp, tmp_path):
    """Icône de l'AppImage (tools/make_icon.py)."""
    import sys

    from PySide6.QtGui import QImage

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import make_icon

    target = tmp_path / "atlas-pc-monitor.png"
    assert make_icon.main([str(target), "128"]) == 0
    image = QImage(str(target))
    assert (image.width(), image.height()) == (128, 128)
    assert make_icon.main([]) == 2


def test_make_icon_writes_a_windows_ico(qapp, tmp_path):
    """Icône de l'exécutable Windows : une image par taille, de 16 à 256 px."""
    image_module = pytest.importorskip("PIL.Image")
    sys_path = str(Path(__file__).resolve().parent.parent / "tools")
    import sys

    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    import make_icon

    target = tmp_path / "icones" / "atlas-pc-monitor.ico"
    assert make_icon.main([str(target)]) == 0
    sizes = image_module.open(target).info["sizes"]
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(sizes)


def test_brand_is_never_cut(win, qtbot):
    """Le nom « Atlas PC Monitor » reste lisible en entier, de la largeur minimale à la pleine largeur."""
    for width in (win.minimumWidth(), 960, 1100, 1400):
        win.resize(width, 700)
        qtbot.wait(30)
        for part in (win.brand, win.brand_sub):
            assert part.width() >= part.fontMetrics().horizontalAdvance(part.text()), (width, part.text())
        assert "MONITOR" in win.brand.text() + win.brand_sub.text()
