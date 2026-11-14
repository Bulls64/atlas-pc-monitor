"""Fenêtre « Nouveautés » : section du CHANGELOG pour la version, affichée après une mise à jour.

"What's new" window: the version's CHANGELOG section, shown after an update.
"""

from atlas import __version__, changelog, settings

SAMPLE = """# Changelog

## [Unreleased]

### English

- Coming soon

## [2.0.0] - 2027-01-10

### English

#### Added

- Updates

### Français

#### Ajouts

- Mises à jour

## [1.0.0] - 2026-11-14

- Première version

[2.0.0]: https://github.com/Bulls64/atlas-pc-monitor/releases/tag/v2.0.0
"""


def test_section_of_a_version():
    assert changelog.section(SAMPLE, "1.0.0") == "- Première version"
    assert changelog.section(SAMPLE, "3.0.0") == ""
    assert changelog.notes("fr", "2.0.0", SAMPLE) == "#### Ajouts\n\n- Mises à jour"
    assert changelog.notes("en", "2.0.0", SAMPLE) == "#### Added\n\n- Updates"
    # Depuis les sources, une version absente retombe sur « Unreleased ».
    # From source, a missing version falls back on "Unreleased".
    assert changelog.notes("en", "3.0.0", SAMPLE) == "- Coming soon"


def test_the_shipped_changelog_describes_this_version():
    assert changelog.path().is_file()
    for language in ("fr", "en"):
        text = changelog.notes(language)
        assert text and "###" not in text.replace("####", "")


def test_shown_once_after_an_update_never_at_first_install():
    config = {}
    assert not changelog.should_show(config, "1.0.0") and config["last_version"] == "1.0.0"
    assert not changelog.should_show(config, "1.0.0")
    assert changelog.should_show(config, "1.1.0")
    assert not changelog.should_show(config, "1.1.0")


def test_window_after_an_update(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings.save_config({"last_version": "0.9.0"})
    from atlas.gui import window

    w = window.MainWindow(scanner=lambda: {})
    qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.whats_new_dialog is not None)
    dialog = w.whats_new_dialog
    labels = [child.text() for child in dialog.findChildren(type(w.status))]
    assert f"Nouveautés de la v{__version__}" in labels
    assert dialog.text.toPlainText().startswith("Ajouts")
    assert settings.load_config()["last_version"] == __version__

    # Relancée dans la même version : plus de fenêtre.
    # Restarted in the same version: no window any more.
    w2 = window.MainWindow(scanner=lambda: {})
    qtbot.addWidget(w2)
    qtbot.wait(50)
    assert w2.whats_new_dialog is None


def test_window_from_the_settings_in_english(win, qtbot):
    from atlas import i18n

    i18n.set_language("en")
    win.open_settings()
    win.settings_dialog.whats_new_button.click()
    dialog = win.whats_new_dialog
    labels = [child.text() for child in dialog.findChildren(type(win.settings_dialog.update_status))]
    assert f"What's new in v{__version__}" in labels
    assert dialog.text.toPlainText().startswith("Added")
