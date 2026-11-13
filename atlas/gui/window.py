"""Fenêtre principale d'Atlas PC (PySide6), au look BAUSTECH PC."""

from __future__ import annotations

import contextlib
import logging
import tempfile
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, export, fiche, privacy, settings
from ..collect import base_report, is_windows, scan
from ..findings import FIX, WATCH, Finding, analyze, summary
from ..formatting import fmt_number, fmt_stamp, to_number
from ..pages import FINDINGS, OVERVIEW, PAGES, diff_reports
from . import model, screens, theme
from .dialogs import CompareDialog, FicheDialog
from .widgets import BusLine, DotBackground, Led, icon, label, logo_pixmap, screen_size, separator

log = logging.getLogger("atlas")


class _Bridge(QObject):
    done = Signal(object)


class NavButton(QPushButton):
    """Entrée de navigation : repère de sérigraphie, nom de la page, compteur ou point actif."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.setProperty("kind", "nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(name)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        self.designator = designator = label(model.DESIGNATORS.get(name, ""), "designator")
        designator.setFixedWidth(32)
        self.title = label(name, "navName")
        self.badge = label("", "badge")
        self.badge.setFixedHeight(18)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        self.dot = Led("ok", 8)
        self.dot.hide()
        for widget in (designator, self.title, self.badge, self.dot):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(designator)
        row.addWidget(self.title, 1)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)
        row.addWidget(self.dot)

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        for widget in (self.title, self.designator):
            widget.setProperty("active", active)
            widget.style().unpolish(widget)
            widget.style().polish(widget)


class MainWindow(QMainWindow):
    def __init__(self, scanner=scan):
        super().__init__()
        self.scanner = scanner
        self.config = settings.load_config()
        theme.set_theme(self.config.get("theme", "dark"))
        self.sharing = bool(self.config.get("sharing", False))
        self.data: dict = {}
        self.findings: list[Finding] = []
        self.page = OVERVIEW
        self.query = ""
        self.fiche_info = fiche.FicheInfo(technician=str(self.config.get("technician", "")))
        self.fiche_dialog: FicheDialog | None = None
        self._shown: tuple | None = None
        self._scanning = False
        self._closing = False
        self.bridge = _Bridge(self)
        self.bridge.done.connect(self._on_scanned)
        self._flash_timer = QTimer(self, singleShot=True, interval=2500, timeout=self._update_status)
        self._search_timer = QTimer(self, singleShot=True, interval=200, timeout=self._run_search)

        self.setWindowTitle("Atlas PC — Informations système")
        self.setWindowIcon(QIcon(logo_pixmap(64)))
        available = screen_size()
        self.resize(min(1320, available.width() - 60), min(900, available.height() - 60))
        self.setMinimumSize(min(980, available.width() - 40), min(620, available.height() - 40))
        QShortcut(QKeySequence.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)
        self.build()
        self.refresh()

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()  # Ctrl+F sur une recherche en cours : on retape directement

    # ------------------------------------------------------------------ données affichées

    @property
    def shown(self) -> dict:
        """Inventaire tel qu'il est affiché et partagé : masqué quand le mode partage est actif."""
        if not self.sharing or not self.data:
            return self.data
        if self._shown is None or self._shown[0] is not self.data:
            self._shown = (self.data, privacy.anonymize(self.data))
        return self._shown[1]

    # ------------------------------------------------------------------ construction

    def build(self) -> None:
        QApplication.instance().setStyleSheet(theme.qss())
        root = DotBackground()
        root.setObjectName("board")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header())
        bus = QWidget()
        bl = QHBoxLayout(bus)
        bl.setContentsMargins(32, 0, 32, 0)
        bl.addWidget(BusLine())
        outer.addWidget(bus)

        body = QHBoxLayout()
        body.setContentsMargins(24, 16, 0, 0)
        body.setSpacing(16)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setFixedWidth(262)
        side_scroll.setWidget(self._sidebar())
        body.addWidget(side_scroll)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self.scroll, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(root)
        self._update_status()
        self._fit_header(self.width())
        self.render()
        self.scroll.setFocus()  # pas le champ de recherche au démarrage

    def _header(self) -> QWidget:
        p = theme.P
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(32, 20, 32, 14)
        row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(40))
        row.addWidget(logo)
        brand = QWidget()
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(4, 0, 0, 0)
        bl.setSpacing(4)
        bl.addWidget(label("ATLAS PC", "brand"))
        self.brand_sub = label(f"INVENTAIRE · DIAGNOSTIC · v{__version__}", "brandSub")
        bl.addWidget(self.brand_sub)
        row.addWidget(brand)
        row.addStretch(1)
        self.status_led = Led("ok", 8)
        self.status = label("", "status")
        row.addWidget(self.status_led)
        row.addWidget(self.status)
        row.addSpacing(8)
        self.search = QLineEdit(self.query)
        self.search.setPlaceholderText("Rechercher…   Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", p.dim), QLineEdit.LeadingPosition)
        self.search.setMinimumWidth(170)
        self.search.setMaximumWidth(260)
        self.search.setAccessibleName("Rechercher dans l'inventaire")
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        escape = QAction(self.search)
        escape.setShortcut(QKeySequence("Escape"))
        escape.setShortcutContext(Qt.WidgetShortcut)
        escape.triggered.connect(self.search.clear)
        self.search.addAction(escape)
        row.addWidget(self.search)
        self.sharing_button = QPushButton()
        self.sharing_button.setProperty("kind", "sharing")
        self.sharing_button.setCheckable(True)
        self._show_sharing()
        self.sharing_button.setToolTip(
            "Masque nom du poste, numéros de série, MAC et IP à l'écran, dans les copies, les exports et la fiche"
        )
        self.sharing_button.clicked.connect(self.toggle_sharing)
        row.addWidget(self.sharing_button)
        dark = p.name == "dark"
        self.theme_button = QPushButton()
        self.theme_button.setProperty("kind", "icon")
        self.theme_button.setIcon(icon("sun" if dark else "moon", p.silk, 18))
        self.theme_button.setToolTip("Passer en thème clair" if dark else "Passer en thème sombre")
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        self.theme_button.clicked.connect(self.toggle_theme)
        row.addWidget(self.theme_button)
        self.refresh_button = QPushButton("Actualiser")
        self.refresh_button.setProperty("kind", "primary")
        self.refresh_button.setIcon(icon("refresh", p.primary_text))
        self.refresh_button.setToolTip("Relancer l'analyse (F5)")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        return header

    def _sidebar(self) -> QWidget:
        p = theme.P
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 10, 16)
        layout.setSpacing(3)
        layout.addWidget(label("MATÉRIEL", "eyebrowDim"))
        layout.addSpacing(6)
        self.nav: dict[str, NavButton] = {}
        for name, _icon in PAGES:
            button = NavButton(name)
            button.clicked.connect(lambda _=False, page=name: self.open_page(page))
            layout.addWidget(button)
            self.nav[name] = button
        layout.addSpacing(10)
        layout.addWidget(separator())
        layout.addSpacing(10)

        def action(text: str, icon_name: str, slot, primary: bool = False) -> QPushButton:
            button = QPushButton(text)
            if primary:
                button.setProperty("kind", "primary")
            button.setIcon(icon(icon_name, p.primary_text if primary else p.copper))
            button.clicked.connect(slot)
            layout.addWidget(button)
            return button

        action("Fiche d'intervention", "print", self.open_fiche, primary=True)
        layout.addSpacing(4)
        action("Exporter le rapport", "export", self.export)
        action("Copier le rapport", "copy", self.copy_report)
        action("Comparer à un rapport", "compare", self.compare)
        self.admin_button = action("Relancer en administrateur", "admin", self.relaunch_as_admin)
        self.admin_button.hide()
        layout.addStretch(1)
        return side

    # ------------------------------------------------------------------ état

    def _update_status(self) -> None:
        if self._closing:
            return
        if self._scanning:
            text, level = "Analyse en cours…", "watch"
        elif self.data.get("note") and not self.data.get("os"):
            text, level = "Inventaire partiel", "watch"
        elif self.data:
            seconds = to_number(self.data.get("scan_seconds"))
            text = "Analyse terminée" + (f" · {fmt_number(seconds, 2)} s" if seconds else "")
            level = "ok"
        else:
            text, level = "Analyse en attente", None
        self.status.setText(text)
        self.status.setProperty("role", "status" if level == "ok" else "statusWarn")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status_led.level = level
        self.status_led.update()
        self.refresh_button.setEnabled(not self._scanning)
        self.admin_button.setVisible("admin" in self.data and not self.data["admin"] and is_windows())

    def flash(self, message: str) -> None:
        if self._closing:
            return
        self.status.setText(message)
        self.status_led.level = "ok"
        self.status_led.update()
        self._flash_timer.start()

    def _update_nav(self) -> None:
        counts = summary(self.findings)
        alerts = counts[FIX] + counts[WATCH]
        for name, button in self.nav.items():
            active = name == self.page and not self.query
            button.set_active(active)
            button.dot.setVisible(active and name != FINDINGS)
            if name == FINDINGS:
                button.badge.setText(str(alerts))
                button.badge.setVisible(bool(alerts))

    # ------------------------------------------------------------------ rendu

    def open_page(self, page: str) -> None:
        self.page = page
        if self.query:
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.query = ""
        self.render()

    def _run_search(self) -> None:
        self.query = self.search.text().strip()
        self.render()

    def render(self) -> None:
        if self._closing:
            return
        self._update_nav()
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 8, 32, 40)
        if not self.data:
            layout.addWidget(screens.heading("Atlas PC", "Analyse en cours…", "L'inventaire du poste est en cours de lecture."))
            layout.addStretch(1)
        elif self.query:
            layout.addWidget(screens.search_page(self, self.query))
        elif self.page == OVERVIEW:
            layout.addWidget(screens.overview(self))
        elif self.page == FINDINGS:
            layout.addWidget(screens.findings_page(self))
        else:
            layout.addWidget(screens.detail_page(self, self.page))
        old = self.scroll.takeWidget()
        self.scroll.setWidget(content)
        if old is not None:
            old.deleteLater()

    # ------------------------------------------------------------------ collecte

    def refresh(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._update_status()
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            result = self.scanner()
        except Exception as error:  # la collecte ne doit jamais faire tomber l'interface
            log.exception("Collecte interrompue")
            result = base_report(f"Erreur inattendue pendant la collecte : {error}")
        with contextlib.suppress(RuntimeError):  # fenêtre déjà fermée
            self.bridge.done.emit(result)

    def _on_scanned(self, result: dict) -> None:
        self.data = result
        self.findings = analyze(result)
        self._scanning = False
        self._update_status()
        self.render()

    # ------------------------------------------------------------------ thème et partage

    def toggle_theme(self) -> None:
        name = "light" if theme.P.name == "dark" else "dark"
        theme.set_theme(name)
        self.config["theme"] = name
        settings.save_config(self.config)
        self.query = self.search.text().strip()
        self.build()

    def toggle_sharing(self) -> None:
        self.sharing = not self.sharing
        self.config["sharing"] = self.sharing
        settings.save_config(self.config)
        self._show_sharing()
        self.flash("Identifiants masqués" if self.sharing else "Identifiants affichés")
        if self.data:
            self.render()

    def _show_sharing(self) -> None:
        p = theme.P
        self.sharing_button.setChecked(self.sharing)
        self.sharing_button.setIcon(icon("share", p.primary_text if self.sharing else p.bright))
        self.sharing_button.setText("Partage activé" if self.sharing else "Mode partage")

    # ------------------------------------------------------------------ copie, export, comparaison

    def copy_menu(self, widget: QWidget, position, text: str) -> None:
        menu = QMenu(self)
        menu.addAction("Copier ce constat", lambda: self._to_clipboard(text, "Constat copié"))
        menu.exec(widget.mapToGlobal(position))

    def _to_clipboard(self, text: str, message: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.flash(message)

    def copy_report(self) -> None:
        if self.data:
            self._to_clipboard(export.to_text(self.shown), "Rapport copié")

    def export(self) -> None:
        if not self.data:
            return
        filters = ";;".join(f"{name} (*{suffix})" for suffix, name in export.FORMATS.items())
        path, chosen = QFileDialog.getSaveFileName(self, "Exporter le rapport", f"atlas-pc-{datetime.now():%Y%m%d-%H%M}", filters)
        if not path:
            return
        try:
            target = export.save(self.shown, path, chosen)
        except OSError as error:
            QMessageBox.critical(self, "Export impossible", str(error))
            return
        self.flash(f"Rapport enregistré : {target.name}")

    def compare(self) -> None:
        if not self.data:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un rapport JSON d'Atlas PC", "", "Rapport JSON (*.json)")
        if not path:
            return
        try:
            previous = export.load(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Rapport illisible", str(error))
            return
        other = (previous.get("system") or {}).get("computer") or ""
        # Un rapport anonymisé ne dit plus de quel poste il vient : on ne peut pas prévenir.
        elsewhere = not previous.get("anonymized") and other != (self.data.get("system") or {}).get("computer")
        current = self.data
        if self.sharing or previous.get("anonymized"):  # comparer à masquage égal
            previous, current = privacy.anonymize(previous), privacy.anonymize(current)
        changes = diff_reports(previous, current)
        when = fmt_stamp(previous.get("captured_at"))
        if not changes:
            QMessageBox.information(self, "Comparaison", f"Aucune différence matérielle avec le rapport du {when}.")
            return
        title = f"{len(changes)} différence(s) entre le rapport du {when} et l'inventaire actuel"
        if other and elsewhere:
            title += " — attention, ce rapport vient d'un autre poste" + ("" if self.sharing else f" ({other})")
        CompareDialog(self, title, changes).show()

    # ------------------------------------------------------------------ fiche d'intervention

    def open_fiche(self) -> None:
        if not self.data:
            return
        if self.fiche_dialog is not None and self.fiche_dialog.isVisible():
            self.fiche_dialog.raise_()
            self.fiche_dialog.activateWindow()
            return
        if not self.fiche_info.reference:
            self.fiche_info.reference = fiche.default_reference(self.data)
        self.fiche_dialog = FicheDialog(self, self.fiche_info)
        self.fiche_dialog.show()

    def remember_technician(self, name: str) -> None:
        if name != self.config.get("technician", ""):
            self.config["technician"] = name
            settings.save_config(self.config)

    def fiche_html(self, info: fiche.FicheInfo) -> str:
        return fiche.to_html(self.shown, info, self.findings)

    @staticmethod
    def _safe(reference: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (reference or "fiche"))

    def print_fiche(self, info: fiche.FicheInfo) -> Path | None:
        """Écrit la fiche dans le dossier temporaire et l'ouvre dans le navigateur (Ctrl+P pour imprimer ou faire un PDF)."""
        folder = Path(tempfile.gettempdir()) / "AtlasPC"
        target = folder / f"fiche-{self._safe(info.reference)}.html"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target.write_text(self.fiche_html(info), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Fiche impossible", str(error))
            return None
        if not webbrowser.open(target.as_uri()):
            QMessageBox.information(self, "Fiche d'intervention", f"Ouvrez ce fichier dans un navigateur pour l'imprimer :\n{target}")
        self.flash("Fiche ouverte dans le navigateur")
        return target

    def save_fiche(self, info: fiche.FicheInfo, parent=None) -> Path | None:
        path, _ = QFileDialog.getSaveFileName(
            parent or self, "Enregistrer la fiche d'intervention", f"fiche-{self._safe(info.reference)}.html", "Page HTML (*.html)"
        )
        if not path:
            return None
        target = Path(path) if Path(path).suffix.lower() in (".html", ".htm") else Path(f"{path}.html")
        try:
            target.write_text(self.fiche_html(info), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(parent or self, "Enregistrement impossible", str(error))
            return None
        self.flash("Fiche enregistrée")
        return target

    # ------------------------------------------------------------------ élévation et fermeture

    def relaunch_as_admin(self) -> None:
        if settings.relaunch_as_admin():
            self.close()
        else:
            self.flash("Élévation annulée")

    def _fit_header(self, width: int) -> None:
        """En fenêtre étroite, l'en-tête se resserre : le message d'état cède la place en premier."""
        self.status.setVisible(width >= 1180)
        self.status_led.setVisible(width >= 1180)
        self.brand_sub.setText(f"INVENTAIRE · DIAGNOSTIC{' · v' + __version__ if width >= 1100 else ''}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "status"):  # un redimensionnement peut précéder la construction
            self._fit_header(event.size().width())

    def closeEvent(self, event) -> None:
        self._closing = True
        super().closeEvent(event)
