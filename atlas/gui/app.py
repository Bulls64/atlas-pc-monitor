"""Démarrage de l'interface PySide6."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .. import i18n
from . import qtlang, theme
from .window import MainWindow


def run(report: str | None = None) -> int:
    """Ouvre la fenêtre : analyse de ce poste, ou le rapport JSON donné (visionneuse)."""
    # Échelle d'affichage exacte (125 %, 150 %…) plutôt qu'arrondie à l'entier.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Atlas PC Monitor")
    app.setOrganizationName("Bulls64")
    theme.load_fonts()
    qtlang.apply(i18n.language())  # boutons des dialogues Qt (Enregistrer, Annuler…) dans la langue choisie
    if sys.platform == "win32":  # icône propre dans la barre des tâches
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Bulls64.AtlasPCMonitor")
        except (AttributeError, OSError):
            pass
    window = MainWindow()
    window.show()
    if report:
        window.open_report(report)
    return app.exec()
