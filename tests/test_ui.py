"""Essai de bout en bout de l'interface, avec un inventaire factice.

Sauté automatiquement sans Tkinter ou sans écran (par exemple en CI Linux sans Xvfb).
"""

import copy
import json
import os
import time

import pytest

tk = pytest.importorskip("tkinter")

from conftest import PAYLOAD  # noqa: E402


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from atlas import collect, ui

    monkeypatch.setattr(collect, "is_windows", lambda: True)

    def fake_scan():
        return collect.scan(runner=lambda: (0, json.dumps(PAYLOAD), ""))

    try:
        window = ui.Atlas(scanner=fake_scan)
    except tk.TclError as error:
        pytest.skip(f"pas d'écran disponible : {error}")
    pump(window, 600)
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass  # déjà fermée par le test


def pump(window, ms=300):
    done = []
    window.after(ms, lambda: done.append(True))
    while not done:
        window.update()


def labels(widget):
    found = []
    for child in widget.winfo_children():
        if child.winfo_class() == "Label":
            found.append(child.cget("text"))
        found += labels(child)
    return found


def test_every_page_renders(app):
    from atlas.pages import PAGES

    assert app.data and not app._scanning
    for name, _icon in PAGES:
        app.open_page(name)
        pump(app, 50)
        assert app.inner.winfo_children(), name


def test_findings_page_nav_and_banner(app):
    from atlas.pages import FINDINGS, OVERVIEW

    assert app.findings
    assert app.nav[FINDINGS].cget("text").endswith("(2)")
    app.open_page(OVERVIEW)
    pump(app, 50)
    assert "2 à surveiller" in labels(app.inner)
    app.open_page(FINDINGS)
    pump(app, 50)
    texts = labels(app.inner)
    assert "Barrettes dépareillées" in texts and "À surveiller (2)" in texts
    assert app.subtitle.cget("text").startswith("2 à surveiller")


def test_copy_and_search(app):
    app.open_page("Stockage")
    pump(app, 50)
    tree = app.trees[0]
    first = tree.get_children()[0]
    tree.selection_set(first)
    app.copy_rows(tree)
    assert "SAMSUNG" in app.clipboard_get()
    app.copy_value(tree, item=first)
    assert app.clipboard_get() == "SAMSUNG MZVLB512HBJQ"
    app.copy_report()
    assert app.clipboard_get().startswith("ATLAS PC") and "CONSTATS" in app.clipboard_get()
    app.query.set("nvme")
    pump(app, 400)
    assert app.title_label.cget("text") == "Recherche" and app.trees
    app.query.set("")
    pump(app, 400)
    assert app.title_label.cget("text") == "Stockage"


def test_theme_switch_during_scan_does_not_start_a_second_scan(app):
    from atlas import ui

    calls = []
    original = app.scanner

    def slow():
        calls.append(1)
        time.sleep(0.5)
        return original()

    app.scanner = slow
    app.refresh()
    app.refresh()
    pump(app, 100)
    app.toggle_theme()
    pump(app, 100)
    assert str(app.refresh_button.cget("state")) == "disabled"
    app.refresh()
    pump(app, 1000)
    assert calls == [1]
    assert str(app.refresh_button.cget("state")) == "normal" and app.theme == "light"
    assert json.loads(ui.config_path().read_text())["theme"] == "light"


def test_compare_and_export(app, monkeypatch, tmp_path):
    from atlas import export, ui

    old = copy.deepcopy(app.data)
    old["gpu"][0]["DriverVersion"] = "31.0"
    path = tmp_path / "old.json"
    path.write_text(export.to_json(old), encoding="utf-8")
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **_k: str(path))
    app.compare()
    pump(app, 100)
    assert [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]

    out = tmp_path / "rapport"

    def fake_save(**kwargs):
        kwargs["typevariable"].set("Fichier texte")
        return str(out)

    monkeypatch.setattr(ui.filedialog, "asksaveasfilename", fake_save)
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: None)
    app.export()
    assert os.path.exists(f"{out}.txt")


def test_closing_during_scan_is_clean(app):
    original = app.scanner
    app.scanner = lambda: (time.sleep(0.4), original())[1]
    app.refresh()
    app.destroy()
    time.sleep(0.6)  # le thread de collecte se termine sans toucher à Tk
