"""Fenêtre principale d'Atlas PC Monitor (PySide6), au look BAUSTECH PC.

Main window of Atlas PC Monitor (PySide6), with the BAUSTECH PC look.
"""

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

from .. import __version__, collect, export, fiche, i18n, privacy, settings, update
from ..collect import base_report, scan
from ..findings import FIX, WATCH, Finding, analyze, summary
from ..formatting import fmt_number, fmt_stamp, to_number
from ..i18n import _
from ..pages import FINDINGS, OVERVIEW, PAGES, diff_reports
from . import model, qtlang, screens, theme
from .dialogs import CompareDialog, FicheDialog, SettingsDialog
from .widgets import BusLine, DotBackground, Led, icon, label, logo_pixmap, screen_size, separator

log = logging.getLogger("atlas")
# Largeur à partir de laquelle l'en-tête affiche le nom complet et les libellés des boutons.
# Width from which the header shows the full name and the button labels.
WIDE = 1010


class _Bridge(QObject):
    done = Signal(object)


class NavButton(QPushButton):
    """Entrée de navigation : repère de sérigraphie, nom de la page, compteur ou point actif.

    Navigation entry: silkscreen marking, page name, counter or active dot.
    """

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.setProperty("kind", "nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(_(name))
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        self.designator = designator = label(model.DESIGNATORS.get(name, ""), "designator")
        designator.setFixedWidth(32)
        self.title = label(_(name), "navName")
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
        self.settings_dialog: SettingsDialog | None = None
        # module de mise à jour (remplaçable dans les tests) et dernière release trouvée
        # update module (replaceable in tests) and latest release found
        self.updater = update
        self.available_release: update.Release | None = None
        self._shown: tuple | None = None
        # nom du rapport JSON affiché ; vide = inventaire de ce poste
        # name of the JSON report shown; empty = inventory of this computer
        self.source = ""
        self._scanning = False
        self._closing = False
        self.bridge = _Bridge(self)
        self.bridge.done.connect(self._on_scanned)
        self.update_bridge = _Bridge(self)
        self.update_bridge.done.connect(self._on_update_checked)
        self._flash_timer = QTimer(self, singleShot=True, interval=2500, timeout=self._update_status)
        self._search_timer = QTimer(self, singleShot=True, interval=200, timeout=self._run_search)

        self.setWindowTitle(_("Atlas PC Monitor — Informations système"))
        self.setWindowIcon(QIcon(logo_pixmap(64)))
        available = screen_size()
        self.resize(min(1320, available.width() - 60), min(900, available.height() - 60))
        self.setMinimumSize(min(980, available.width() - 40), min(620, available.height() - 40))
        QShortcut(QKeySequence.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)
        QShortcut(QKeySequence.Open, self, activated=self.open_report)
        self.setAcceptDrops(True)
        self.build()
        if collect.is_windows():
            self.refresh()
        else:
            # rien à analyser ici : visionneuse de rapports faits sur des PC Windows
            # nothing to analyze here: viewer for reports made on Windows PCs
            self._update_status()
            self.render()
        if self.config.get("check_updates"):
            threading.Thread(target=self._check_update_work, daemon=True).start()

    def _focus_search(self) -> None:
        self.search.setFocus()
        # Ctrl+F sur une recherche en cours : on retape directement
        # Ctrl+F during a search: typing goes straight in
        self.search.selectAll()

    # ------------------------------------------------------------------ données affichées / displayed data

    @property
    def shown(self) -> dict:
        """Inventaire tel qu'il est affiché et partagé : masqué quand le mode partage est actif.

        Inventory as it is displayed and shared: masked when sharing mode is on.
        """
        if not self.sharing or not self.data:
            return self.data
        if self._shown is None or self._shown[0] is not self.data:
            self._shown = (self.data, privacy.anonymize(self.data))
        return self._shown[1]

    # ------------------------------------------------------------------ construction / building

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
        self.scroll.setFocus()  # pas le champ de recherche au démarrage — not the search field at startup

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
        self.brand = label("ATLAS PC MONITOR", "brand")
        bl.addWidget(self.brand)
        self.brand_sub = label(_("INVENTAIRE · DIAGNOSTIC · v{0}", __version__), "brandSub")
        bl.addWidget(self.brand_sub)
        row.addWidget(brand)
        row.addStretch(1)
        self.status_led = Led("ok", 8)
        self.status = label("", "status")
        row.addWidget(self.status_led)
        row.addWidget(self.status)
        row.addSpacing(8)
        self.search = QLineEdit(self.query)
        self.search.setPlaceholderText(_("Rechercher…   Ctrl+F"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", p.dim), QLineEdit.LeadingPosition)
        self.search.setMinimumWidth(205)
        self.search.setMaximumWidth(260)
        self.search.setAccessibleName(_("Rechercher dans l'inventaire"))
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
            _("Masque nom du poste, numéros de série, MAC et IP à l'écran, dans les copies, les exports et la fiche")
        )
        self.sharing_button.clicked.connect(self.toggle_sharing)
        row.addWidget(self.sharing_button)
        dark = p.name == "dark"
        self.theme_button = QPushButton()
        self.theme_button.setProperty("kind", "icon")
        self.theme_button.setIcon(icon("sun" if dark else "moon", p.silk, 18))
        self.theme_button.setToolTip(_("Passer en thème clair") if dark else _("Passer en thème sombre"))
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        self.theme_button.clicked.connect(self.toggle_theme)
        row.addWidget(self.theme_button)
        self.language_button = QPushButton(i18n.language().upper())
        self.language_button.setProperty("kind", "language")
        self.language_button.setIcon(icon("globe", p.silk, 16))
        self.language_button.setToolTip(_("Langue : français. Passer en anglais (English)"))
        self.language_button.setAccessibleName(self.language_button.toolTip())
        self.language_button.clicked.connect(self.toggle_language)
        row.addWidget(self.language_button)
        self.settings_button = QPushButton()
        self.settings_button.setIcon(icon("settings", p.silk, 18))
        self.settings_button.clicked.connect(self.open_settings)
        row.addWidget(self.settings_button)
        self._show_update_badge()
        self.refresh_button = QPushButton(_("Actualiser"))
        self.refresh_button.setProperty("kind", "primary")
        self.refresh_button.setIcon(icon("refresh", p.primary_text))
        self.refresh_button.clicked.connect(self.refresh)
        # hors Windows, pas de collecte possible
        # outside Windows, no collection is possible
        self.refresh_button.setVisible(collect.is_windows())
        row.addWidget(self.refresh_button)
        return header

    def _sidebar(self) -> QWidget:
        p = theme.P
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 10, 16)
        layout.setSpacing(3)
        layout.addWidget(label(_("MATÉRIEL"), "eyebrowDim"))
        layout.addSpacing(6)
        self.nav: dict[str, NavButton] = {}
        for name, _icon in PAGES:
            button = NavButton(name)
            button.clicked.connect(lambda checked=False, page=name: self.open_page(page))
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

        self.data_actions = [action(_("Fiche d'intervention"), "print", self.open_fiche, primary=True)]
        layout.addSpacing(4)
        self.data_actions += [
            action(_("Exporter le rapport"), "export", self.export),
            action(_("Copier le rapport"), "copy", self.copy_report),
            action(_("Comparer à un rapport"), "compare", self.compare),
        ]
        action(_("Ouvrir un rapport"), "open", self.open_report).setToolTip(_("Afficher un rapport JSON d'Atlas PC Monitor (Ctrl+O)"))
        self.admin_button = action(_("Relancer en administrateur"), "admin", self.relaunch_as_admin)
        self.admin_button.hide()
        layout.addStretch(1)
        return side

    # ------------------------------------------------------------------ état / state

    def _update_status(self) -> None:
        if self._closing:
            return
        if self._scanning:
            text, level = _("Analyse en cours…"), "watch"
        elif self.source:
            text, level = _("Rapport ouvert : {0}", self.source), "info"
        elif self.data.get("note") and not self.data.get("os"):
            text, level = _("Inventaire partiel"), "watch"
        elif self.data:
            seconds = to_number(self.data.get("scan_seconds"))
            text = _("Analyse terminée") + (f" · {fmt_number(seconds, 2)} s" if seconds else "")
            level = "ok"
        elif collect.is_windows():
            text, level = _("Analyse en attente"), None
        else:
            text, level = _("Aucun rapport ouvert"), None
        self.status.setText(text)
        self.status.setProperty("role", "status" if level in ("ok", "info") else "statusWarn")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status_led.level = level
        self.status_led.update()
        self.refresh_button.setEnabled(not self._scanning)
        self.refresh_button.setText(_("Analyser ce poste") if self.source else _("Actualiser"))
        self.refresh_button.setToolTip(_("Revenir à l'inventaire de ce poste (F5)") if self.source else _("Relancer l'analyse (F5)"))
        for button in self.data_actions:
            button.setEnabled(bool(self.data))
        # un rapport ouvert ne se relance pas en administrateur
        # an opened report is not restarted as administrator
        live = collect.is_windows() and not self.source
        self.admin_button.setVisible(live and "admin" in self.data and not self.data["admin"])

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

    # ------------------------------------------------------------------ rendu / rendering

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
        if not self.data and (self._scanning or collect.is_windows()):
            layout.addWidget(
                screens.heading("Atlas PC Monitor", _("Analyse en cours…"), _("L'inventaire du poste est en cours de lecture."))
            )
            layout.addStretch(1)
        elif not self.data:
            layout.addWidget(screens.welcome(self))
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

    # ------------------------------------------------------------------ collecte / collection

    def refresh(self) -> None:
        if self._scanning or not collect.is_windows():
            return
        self._scanning = True
        self._update_status()
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            result = self.scanner()
        except Exception as error:
            # la collecte ne doit jamais faire tomber l'interface
            # the collection must never bring the interface down
            log.exception("Collecte interrompue")
            result = base_report(_("Erreur inattendue pendant la collecte : {0}", error))
        with contextlib.suppress(RuntimeError):  # fenêtre déjà fermée — window already closed
            self.bridge.done.emit(result)

    def _on_scanned(self, result: dict) -> None:
        self.source = ""
        self._show(result)
        self._scanning = False
        self._update_status()

    def _show(self, data: dict) -> None:
        self.data = data
        self.findings = analyze(data)
        self.page = OVERVIEW
        self.render()

    # ------------------------------------------------------------------ visionneuse / viewer

    def open_report(self, path: str | Path | None = None) -> bool:
        """Affiche un rapport JSON fait par Atlas PC Monitor sur un autre poste (ou plus tôt sur celui-ci).

        Shows a JSON report made by Atlas PC Monitor on another computer (or earlier on this one).
        """
        if self._scanning:
            return False
        if not path:
            path, _chosen = QFileDialog.getOpenFileName(
                self, _("Ouvrir un rapport JSON d'Atlas PC Monitor"), "", _("Rapport JSON (*.json)")
            )
            if not path:
                return False
        try:
            data = export.load(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, _("Rapport illisible"), f"{Path(path).name} : {error}")
            return False
        self.source = Path(path).name
        self._show(data)
        self._update_status()
        return True

    @staticmethod
    def _dropped_report(event) -> str:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        local = [url.toLocalFile() for url in urls if url.isLocalFile()]
        return local[0] if len(local) == 1 and local[0].lower().endswith(".json") else ""

    def dragEnterEvent(self, event) -> None:
        if self._dropped_report(event) and not self._scanning:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        path = self._dropped_report(event)
        if path:
            event.acceptProposedAction()
            self.open_report(path)

    # ------------------------------------------------------------------ thème et partage / theme and sharing

    def toggle_theme(self) -> None:
        name = "light" if theme.P.name == "dark" else "dark"
        theme.set_theme(name)
        self.config["theme"] = name
        settings.save_config(self.config)
        self.query = self.search.text().strip()
        self.build()
        if self.settings_dialog is not None:
            self.settings_dialog.build()

    def toggle_language(self) -> None:
        """Bascule français ↔ anglais : tout est reconstruit, constats compris (ils sont rédigés à l'analyse).

        Switches French ↔ English: everything is rebuilt, findings included (they are written at analysis time).
        """
        code = i18n.set_language("en" if i18n.language() == "fr" else "fr")
        self.config["language"] = code
        settings.save_config(self.config)
        qtlang.apply(code)
        self.setWindowTitle(_("Atlas PC Monitor — Informations système"))
        if self.fiche_dialog is not None:
            # ses libellés sont figés : on le refera à la prochaine ouverture
            # its labels are fixed: it will be rebuilt at the next opening
            self.fiche_dialog.collect()
            self.fiche_dialog.close()
            self.fiche_dialog.deleteLater()
            self.fiche_dialog = None
        self.findings = analyze(self.data) if self.data else []
        self.query = self.search.text().strip()
        self.build()
        if self.settings_dialog is not None:
            self.settings_dialog.build()
        self.flash(_("Interface en français") if code == "fr" else _("Interface en anglais"))

    def toggle_sharing(self) -> None:
        self.sharing = not self.sharing
        self.config["sharing"] = self.sharing
        settings.save_config(self.config)
        self._show_sharing()
        self.flash(_("Identifiants masqués") if self.sharing else _("Identifiants affichés"))
        if self.data:
            self.render()

    def _show_sharing(self) -> None:
        p = theme.P
        self.sharing_button.setChecked(self.sharing)
        self.sharing_button.setIcon(icon("share", p.primary_text if self.sharing else p.bright))
        wide = self.width() >= WIDE  # en fenêtre étroite, icône seule (voir _fit_header) — in a narrow window, icon only (see _fit_header)
        self.sharing_button.setText((_("Partage activé") if self.sharing else _("Mode partage")) if wide else "")

    # ------------------------------------------------------------------ copie, export, comparaison / copy, export, comparison

    def copy_menu(self, widget: QWidget, position, text: str) -> None:
        menu = QMenu(self)
        menu.addAction(_("Copier ce constat"), lambda: self._to_clipboard(text, _("Constat copié")))
        menu.exec(widget.mapToGlobal(position))

    def _to_clipboard(self, text: str, message: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.flash(message)

    def copy_report(self) -> None:
        if self.data:
            self._to_clipboard(export.to_text(self.shown), _("Rapport copié"))

    def export(self) -> None:
        if not self.data:
            return
        filters = ";;".join(f"{_(name)} (*{suffix})" for suffix, name in export.FORMATS.items())
        path, chosen = QFileDialog.getSaveFileName(
            self, _("Exporter le rapport"), f"atlas-pc-monitor-{datetime.now():%Y%m%d-%H%M}", filters
        )
        if not path:
            return
        try:
            target = export.save(self.shown, path, chosen)
        except OSError as error:
            QMessageBox.critical(self, _("Export impossible"), str(error))
            return
        self.flash(_("Rapport enregistré : {0}", target.name))

    def compare(self) -> None:
        if not self.data:
            return
        path, _chosen = QFileDialog.getOpenFileName(self, _("Choisir un rapport JSON d'Atlas PC Monitor"), "", _("Rapport JSON (*.json)"))
        if not path:
            return
        try:
            previous = export.load(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, _("Rapport illisible"), str(error))
            return
        other = (previous.get("system") or {}).get("computer") or ""
        # Un rapport anonymisé ne dit plus de quel poste il vient : on ne peut pas prévenir.
        # An anonymized report no longer says which computer it comes from: no warning is possible.
        elsewhere = not previous.get("anonymized") and other != (self.data.get("system") or {}).get("computer")
        current = self.data
        if self.sharing or previous.get("anonymized"):  # comparer à masquage égal — compare with the same masking
            previous, current = privacy.anonymize(previous), privacy.anonymize(current)
        changes = diff_reports(previous, current)
        when = fmt_stamp(previous.get("captured_at"))
        if not changes:
            QMessageBox.information(self, _("Comparaison"), _("Aucune différence matérielle avec le rapport du {0}.", when))
            return
        title = _("{0} différence(s) entre le rapport du {1} et l'inventaire actuel", len(changes), when)
        if other and elsewhere:
            title += _(" — attention, ce rapport vient d'un autre poste") + ("" if self.sharing else f" ({other})")
        CompareDialog(self, title, changes).show()

    # ------------------------------------------------------------------ fiche d'intervention / intervention sheet

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
        """Écrit la fiche dans le dossier temporaire et l'ouvre dans le navigateur (Ctrl+P pour imprimer ou faire un PDF).

        Writes the sheet to the temporary folder and opens it in the browser (Ctrl+P to print it or make a PDF).
        """
        folder = Path(tempfile.gettempdir()) / "AtlasPCMonitor"
        target = folder / f"fiche-{self._safe(info.reference)}.html"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target.write_text(self.fiche_html(info), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, _("Fiche impossible"), str(error))
            return None
        if not webbrowser.open(target.as_uri()):
            QMessageBox.information(
                self, _("Fiche d'intervention"), _("Ouvrez ce fichier dans un navigateur pour l'imprimer :\n{0}", target)
            )
        self.flash(_("Fiche ouverte dans le navigateur"))
        return target

    def save_fiche(self, info: fiche.FicheInfo, parent=None) -> Path | None:
        path, _chosen = QFileDialog.getSaveFileName(
            parent or self, _("Enregistrer la fiche d'intervention"), f"fiche-{self._safe(info.reference)}.html", _("Page HTML (*.html)")
        )
        if not path:
            return None
        target = Path(path) if Path(path).suffix.lower() in (".html", ".htm") else Path(f"{path}.html")
        try:
            target.write_text(self.fiche_html(info), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(parent or self, _("Enregistrement impossible"), str(error))
            return None
        self.flash(_("Fiche enregistrée"))
        return target

    # ------------------------------------------------------------------ élévation et fermeture / elevation and closing

    # ------------------------------------------------------------------ paramètres et mises à jour / settings and updates

    def open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _check_update_work(self) -> None:
        """Recherche au démarrage (option des paramètres) : silencieuse en cas d'échec.

        Check at startup (settings option): silent on failure.
        """
        try:
            result = self.updater.check()
        except Exception as error:
            log.info("Recherche de mise à jour au démarrage : %s", error)
            return
        with contextlib.suppress(RuntimeError):  # fenêtre déjà fermée — window already closed
            self.update_bridge.done.emit(result)

    def _on_update_checked(self, release) -> None:
        self.set_available_release(release)
        if release.is_newer:
            self.flash(_("Mise à jour disponible : version {0}", release.version))

    def set_available_release(self, release) -> None:
        self.available_release = release
        self._show_update_badge()

    def _show_update_badge(self) -> None:
        """Bouton des paramètres : roue seule, ou « v1.1.0 » quand une mise à jour attend.

        Settings button: gear only, or "v1.1.0" when an update is waiting.
        """
        release = self.available_release
        waiting = release is not None and release.is_newer
        self.settings_button.setProperty("kind", "language" if waiting else "icon")
        self.settings_button.setText(f"v{release.version}" if waiting else "")
        tip = _("Paramètres · mise à jour {0} disponible", release.version) if waiting else _("Paramètres")
        self.settings_button.setToolTip(tip)
        self.settings_button.setAccessibleName(tip)
        self.settings_button.style().unpolish(self.settings_button)
        self.settings_button.style().polish(self.settings_button)

    def quit_for_update(self) -> None:
        """Ferme l'application pour laisser la nouvelle version démarrer.

        Closes the application so the new version can start.
        """
        self.close()
        QApplication.quit()

    def relaunch_as_admin(self) -> None:
        if settings.relaunch_as_admin():
            self.close()
        else:
            self.flash(_("Élévation annulée"))

    def _fit_header(self, width: int) -> None:
        """En fenêtre étroite, l'en-tête se resserre : le message d'état cède la place en premier,
        puis le sous-titre, puis le nom passe sur deux lignes (« ATLAS PC » / « MONITOR »).

        In a narrow window, the header tightens: the status message gives way first,
        then the subtitle, then the name moves onto two lines ("ATLAS PC" / "MONITOR").
        """
        self.status.setVisible(width >= WIDE + 220)
        self.status_led.setVisible(width >= WIDE + 220)
        wide = width >= WIDE
        # Bouton « Mode partage » réduit à son icône (l'info-bulle reste) quand la place manque.
        # "Sharing mode" button reduced to its icon (the tooltip remains) when space runs short.
        self.sharing_button.setText((_("Partage activé") if self.sharing else _("Mode partage")) if wide else "")
        self.brand.setText("ATLAS PC MONITOR" if wide else "ATLAS PC")
        if not wide:
            self.brand_sub.setText("MONITOR")
        else:
            self.brand_sub.setText(_("INVENTAIRE · DIAGNOSTIC{0}", " · v" + __version__ if width >= WIDE + 140 else ""))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "status"):  # un redimensionnement peut précéder la construction — a resize can come before the window is built
            self._fit_header(event.size().width())

    def closeEvent(self, event) -> None:
        self._closing = True
        super().closeEvent(event)
