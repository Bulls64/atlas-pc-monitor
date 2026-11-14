"""Démarrage de l'interface PySide6.

Starts the PySide6 interface.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .. import i18n, update
from . import qtlang, theme
from .window import MainWindow


def run(report: str | None = None) -> int:
    """Ouvre la fenêtre : analyse de ce poste, ou le rapport JSON donné (visionneuse).

    Opens the window: analysis of this computer, or the given JSON report (viewer).
    """
    # Échelle d'affichage exacte (125 %, 150 %…) plutôt qu'arrondie à l'entier.
    # Exact display scaling (125%, 150%…) rather than rounded to a whole number.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Atlas PC Monitor")
    app.setOrganizationName("Bulls64")
    theme.load_fonts()
    update.cleanup()
    # boutons des dialogues Qt (Enregistrer, Annuler…) dans la langue choisie
    # Qt dialog buttons (Save, Cancel…) in the chosen language
    qtlang.apply(i18n.language())
    if sys.platform == "win32":  # icône propre dans la barre des tâches — own icon in the taskbar
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
