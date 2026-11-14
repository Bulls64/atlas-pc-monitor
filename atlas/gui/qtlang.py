"""Langue des éléments fournis par Qt (boutons Enregistrer / Annuler des dialogues, menus contextuels).

Language of the elements provided by Qt (Save / Cancel buttons of the dialogs, context menus).
"""

from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

_translator: QTranslator | None = None


def apply(code: str) -> None:
    """Français : traduction qtbase_fr de Qt ; anglais : textes d'origine de Qt.

    French: Qt's qtbase_fr translation; English: Qt's original texts.
    """
    global _translator
    app = QApplication.instance()
    if app is None:
        return
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator = None
    if code == "fr":
        QLocale.setDefault(QLocale(QLocale.French, QLocale.France))
        translator = QTranslator(app)
        if translator.load(QLocale(QLocale.French), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(translator)
            _translator = translator
    else:
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
