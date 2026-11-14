"""Traduction anglaise : catalogue complet, et aucun reste de français à l'écran ni dans les rapports."""

from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path

import pytest

from atlas import export, fiche, i18n, settings
from atlas.locale_en import EN

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
# Mots qui trahissent un texte resté en français (les valeurs lues sur le poste sont exclues à part).
FRENCH = re.compile(
    r"[éèêàùçœ]|\b(le|la|les|des|du|une|aucun|aucune|est|sont|sur|pour|avec|sans|dans|ou|et|pas|ce|cette|à)\b",
    re.IGNORECASE,
)


def marked_texts() -> dict[str, str]:
    """Textes passés à _() ou N_() dans le code, avec leur emplacement."""
    texts = {}
    for path in sorted((ROOT / "atlas").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_", "N_") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    texts.setdefault(first.value, f"{path.relative_to(ROOT)}:{node.lineno}")
    return texts


def test_every_marked_text_has_a_translation_and_none_is_orphan():
    texts = marked_texts()
    assert len(texts) > 400
    missing = {text: where for text, where in texts.items() if text not in EN}
    assert not missing, f"Traductions manquantes dans atlas/locale_en.py : {missing}"
    orphans = [key for key in EN if key not in texts]
    assert not orphans, f"Traductions qui ne servent plus : {orphans}"


def test_translations_keep_their_placeholders():
    for french, english in EN.items():
        assert sorted(PLACEHOLDER.findall(french)) == sorted(PLACEHOLDER.findall(english)), french
        assert english.strip(), french


def test_language_switch_and_number_formats(english):
    from atlas import formatting as f

    assert i18n._("Mémoire") == "Memory"
    assert i18n._("{0} barrette(s)", 2) == "2 module(s)"
    assert f.fmt_binary(17 * 1024**3) == "17 GB" and f.fmt_decimal(512_110_190_592) == "512.1 GB"
    assert f.fmt_percent(62) == "62%" and f.fmt_date("2026-11-13T10:30:00") == "2026-11-13 10:30"
    assert f.fmt_code(28, f.PNP_ERRORS) == "driver not installed"
    i18n.set_language("fr")
    assert f.fmt_decimal(512_110_190_592) == "512,1 Go" and f.fmt_percent(62) == "62 %"
    assert i18n.set_language("de") == "fr"  # langue inconnue : français


def test_saved_language_wins_over_the_system(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(i18n, "system_language", lambda: "en")
    assert settings.preferred_language() == "en"
    settings.save_config({"language": "fr"})
    assert settings.preferred_language() == "fr"


@pytest.mark.parametrize(
    ("environment", "expected"),
    [({"LANG": "fr_FR.UTF-8"}, "fr"), ({"LANG": "en_US.UTF-8"}, "en"), ({"LC_ALL": "de_DE.UTF-8"}, "en"), ({"LANG": "C.UTF-8"}, None)],
)
def test_system_language(monkeypatch, environment, expected):
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    result = i18n.system_language()
    if expected is None:  # locale neutre : on se rabat sur celle de Windows ou de Python, toujours fr ou en
        assert result in i18n.LANGUAGES
    else:
        assert result == expected


def data_words(data) -> set[str]:
    """Toutes les valeurs lues sur le poste (elles peuvent être en français : Windows en français)."""
    found = set()

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            found.add(value)

    walk(data)
    return found


# Textes du catalogue dont l'anglais diffère : affichés tels quels, ils trahissent un oubli de _().
UNTRANSLATED = {key.strip().upper() for key, value in EN.items() if key.strip() != value.strip() and not PLACEHOLDER.search(key)}


def french_leftovers(texts, data) -> list[str]:
    values = data_words(data)
    leftovers = []
    for text in texts:
        if text.strip().upper() in UNTRANSLATED and text not in values:
            leftovers.append(text)
            continue
        cleaned = text
        for value in sorted(values, key=len, reverse=True):
            if len(value) > 2:
                cleaned = cleaned.replace(value, " ")
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)  # balises HTML
        for name in i18n.LANGUAGES.values():  # le nom d'une langue s'écrit dans cette langue (« Français »)
            cleaned = cleaned.replace(name, " ")
        if "{" in cleaned and ":" in cleaned and ";" in cleaned:  # feuille de style CSS
            continue
        if FRENCH.search(cleaned):
            leftovers.append(text)
    return leftovers


def test_text_and_html_reports_in_english(data, english):
    from atlas.findings import analyze

    found = analyze(data)
    assert found and all(not FRENCH.search(item.title) for item in found), [item.title for item in found]
    text = export.to_text(data)
    assert text.startswith("ATLAS PC MONITOR — SYSTEM REPORT FOR") and "FINDINGS —" in text
    assert not french_leftovers(text.splitlines(), data)
    page = export.to_html(data)
    assert '<html lang="en">' in page and not french_leftovers(re.findall(r">([^<]+)<", page), data)
    sheet = fiche.to_html(data, fiche.FicheInfo(technician="Chris"))
    assert "Intervention sheet" in sheet and not french_leftovers(re.findall(r">([^<]+)<", sheet), data)


def test_cli_in_english(capsys, tmp_path, data):
    from atlas.__main__ import main

    path = tmp_path / "report.json"
    path.write_text(export.to_json(data), encoding="utf-8")
    assert main(["--lang", "en", "--text", str(path)]) == 0
    assert "SYSTEM REPORT" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--lang=en", "--help"])
    assert "hide computer name" in capsys.readouterr().out
    i18n.set_language("fr")


def visible_texts(widget) -> list[str]:
    from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QTableWidget

    texts = [w.text() for w in widget.findChildren(QLabel) if w.isVisibleTo(widget)]
    texts += [w.text() for w in widget.findChildren(QAbstractButton) if w.isVisibleTo(widget)]
    texts += [w.toolTip() for w in widget.findChildren(QAbstractButton) if w.toolTip()]
    texts += [w.placeholderText() for w in widget.findChildren(QLineEdit)]
    for table in widget.findChildren(QTableWidget):
        texts += [table.item(r, c).text() for r in range(table.rowCount()) for c in range(table.columnCount()) if table.item(r, c)]
        texts += [table.horizontalHeaderItem(c).text() for c in range(table.columnCount()) if table.horizontalHeaderItem(c)]
    return [t for t in texts if t]


def test_every_screen_in_english(win, qtbot):
    """Toutes les pages, la recherche et la fiche, dessinées en anglais : rien ne doit rester en français."""
    from atlas.pages import PAGES

    win.resize(1400, 900)
    win.toggle_language()
    assert i18n.language() == "en" and win.config["language"] == "en"
    assert win.nav["Mémoire"].title.text() == "Memory" and win.language_button.text() == "EN"
    leftovers = {}
    for page, _icon in PAGES:
        win.open_page(page)
        qtbot.wait(10)
        bad = french_leftovers(visible_texts(win), win.data)
        if bad:
            leftovers[page] = bad
    win.search.setText("memory")
    win._run_search()
    leftovers["search"] = french_leftovers(visible_texts(win), win.data)
    win.search.clear()
    win.open_fiche()
    leftovers["fiche"] = french_leftovers(visible_texts(win.fiche_dialog), win.data)
    win.fiche_dialog.close()
    assert not any(leftovers.values()), {k: v for k, v in leftovers.items() if v}
    win.toggle_language()  # retour au français
    assert i18n.language() == "fr" and win.nav["Mémoire"].title.text() == "Mémoire"


def test_language_switch_reanalyzes_and_keeps_the_fiche_input(win, qtbot):
    win.open_fiche()
    win.fiche_dialog.entries["client"].setText("Jane Smith")
    win.toggle_language()
    assert win.fiche_dialog is None and win.fiche_info.client == "Jane Smith"
    titles = {item.title for item in win.findings}
    assert titles and not any(FRENCH.search(title) for title in titles), titles
    win.open_fiche()
    assert win.fiche_dialog.entries["client"].text() == "Jane Smith"
    assert win.fiche_dialog.windowTitle() == "Atlas PC Monitor — Intervention sheet"
    win.fiche_dialog.close()
    win.toggle_language()


def test_english_masks_in_sharing_mode(data, english):
    from atlas import privacy

    shared = privacy.anonymize(copy.deepcopy(data))
    assert shared["system"]["computer"] == "HIDDEN-PC"
    assert "[hidden]" in json.dumps(shared)
