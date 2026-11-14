"""Fenêtres secondaires : fiche d'intervention, comparaison de rapports et paramètres.

Secondary windows: intervention sheet, report comparison and settings.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import webbrowser

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, fiche, i18n, settings, update
from .. import findings as F
from ..i18n import N_, _
from . import theme
from .widgets import CopyTable, card, icon, label

log = logging.getLogger("atlas")


class FicheDialog(QDialog):
    """Saisie de la fiche ; laissés vides, les champs s'impriment comme des lignes à remplir à la main.

    Sheet entry; fields left empty print as lines to fill in by hand.
    """

    FIELDS = (("technician", N_("Technicien")), ("client", N_("Client")), ("contact", N_("Contact")), ("reference", N_("Référence")))
    TEXTS = (("request", N_("Demande du client")), ("work", N_("Travaux réalisés")), ("recommendations", N_("Recommandations")))

    def __init__(self, win, info: fiche.FicheInfo):
        super().__init__(win)
        self.win, self.info = win, info
        self.setWindowTitle(_("Atlas PC Monitor — Fiche d'intervention"))
        self.setWindowIcon(win.windowIcon())
        self.resize(660, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)
        layout.addWidget(label(_("FICHE D'INTERVENTION"), "eyebrow"))
        layout.addWidget(label(_("Préparer la fiche"), "h2"))
        layout.addWidget(
            label(
                _("Tous les champs sont facultatifs : laissés vides, ils s'impriment comme des lignes à remplir à la main."),
                "dim",
                wrap=True,
            )
        )
        layout.addSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.entries: dict[str, QLineEdit] = {}
        for row, (key, text) in enumerate(self.FIELDS):
            entry = QLineEdit(getattr(info, key))
            name = label(_(text).upper(), "field")
            name.setBuddy(entry)
            grid.addWidget(name, row, 0)
            grid.addWidget(entry, row, 1)
            self.entries[key] = entry
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.texts: dict[str, QPlainTextEdit] = {}
        for key, text in self.TEXTS:
            head = QHBoxLayout()
            head.addWidget(label(_(text).upper(), "field"))
            head.addStretch(1)
            box = QPlainTextEdit(getattr(info, key))
            box.setTabChangesFocus(True)
            box.setMinimumHeight(84)
            if key == "recommendations":
                link = QPushButton(_("Reprendre les conseils des constats"))
                link.setProperty("kind", "link")
                link.clicked.connect(lambda checked=False, target=box: self.insert_advice(target))
                head.addWidget(link)
            layout.addSpacing(6)
            layout.addLayout(head)
            layout.addWidget(box, 1)
            self.texts[key] = box
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 12, 0, 0)
        close = QPushButton(_("Fermer"))
        close.clicked.connect(self.close)
        save = QPushButton(_("Enregistrer…"))
        save.clicked.connect(lambda: self.win.save_fiche(self.collect(), self))
        printing = QPushButton(_("Ouvrir pour imprimer"))
        printing.setProperty("kind", "primary")
        printing.setIcon(icon("print", theme.P.primary_text))
        printing.clicked.connect(lambda: self.win.print_fiche(self.collect()))
        printing.setDefault(True)
        bar.addWidget(close)
        bar.addStretch(1)
        bar.addWidget(save)
        bar.addWidget(printing)
        layout.addLayout(bar)
        self.entries["client"].setFocus()

    def insert_advice(self, box: QPlainTextEdit) -> None:
        """Ajoute les conseils des constats à corriger et à surveiller, sans doublon.

        Adds the advice from the findings to fix and to watch, without duplicates.
        """
        current = box.toPlainText()
        lines = [_("- {0} : {1}", i.title, i.advice) for i in self.win.findings if i.level in (F.FIX, F.WATCH) and i.advice]
        new = [line for line in lines if line not in current]
        if not new:
            self.win.flash(_("Aucun conseil à ajouter"))
            return
        box.setPlainText((current.rstrip() + "\n" if current.strip() else "") + "\n".join(new))

    def collect(self) -> fiche.FicheInfo:
        for key, entry in self.entries.items():
            setattr(self.info, key, entry.text().strip())
        for key, box in self.texts.items():
            setattr(self.info, key, box.toPlainText().strip())
        self.win.remember_technician(self.info.technician)
        return self.info

    def hideEvent(self, event) -> None:
        # Fermer, Échap ou la croix : dans tous les cas la saisie est gardée pour la prochaine ouverture.
        # Close, Esc or the window's close button: in every case the entry is kept for the next opening.
        self.collect()
        super().hideEvent(event)


class CompareDialog(QDialog):
    def __init__(self, win, title: str, changes: list[tuple]):
        super().__init__(win)
        self.setWindowTitle(_("Atlas PC Monitor — Comparaison de rapports"))
        self.setWindowIcon(win.windowIcon())
        self.resize(1000, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(label(_("COMPARAISON"), "eyebrow"))
        layout.addWidget(label(title, "h3", wrap=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        frame, fl = card("true", (8, 12, 8, 12), 0)
        self.table = CopyTable([_("Emplacement"), _("Propriété"), _("Avant"), _("Maintenant")], changes, show_header=True)
        self.table.copied.connect(win.flash)
        fl.addWidget(self.table)
        il.addWidget(frame)
        il.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        close = QPushButton(_("Fermer"))
        close.clicked.connect(self.close)
        layout.addWidget(close, 0, Qt.AlignRight)


class _UpdateBridge(QObject):
    checked = Signal(object)
    progress = Signal(int, int)
    installed = Signal(object)


class SettingsDialog(QDialog):
    """Paramètres : langue, thème et mises à jour depuis les releases GitHub.

    Settings: language, theme and updates from the GitHub releases.
    """

    MODES = {
        update.EXE: N_("fichier unique Windows"),
        update.FOLDER: N_("dossier Windows"),
        update.APPIMAGE: N_("AppImage Linux"),
        update.SOURCE: N_("sources Python"),
    }

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowIcon(win.windowIcon())
        self.resize(620, 640)
        self.error = ""
        self.busy = False
        self.bridge = _UpdateBridge(self)
        self.bridge.checked.connect(self._on_checked)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.installed.connect(self._on_installed)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(24, 22, 24, 22)
        self.body: QWidget | None = None
        self.build()

    # ------------------------------------------------------------------ construction / building

    def build(self) -> None:
        """(Re)construit le contenu, par exemple après un changement de langue ou de thème.

        (Re)builds the content, for example after a change of language or theme.
        """
        self.setWindowTitle(_("Atlas PC Monitor — Paramètres"))
        if self.body is not None:
            self.outer.removeWidget(self.body)
            self.body.deleteLater()
        self.body = QWidget()
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label(_("PARAMÈTRES"), "eyebrow"))
        layout.addWidget(label(_("Paramètres"), "h2"))

        frame, fl = card("true")
        fl.addWidget(label(_("AFFICHAGE"), "eyebrow"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.addWidget(label(_("Langue"), "body"), 0, 0)
        grid.addLayout(self._choices([("fr", "Français"), ("en", "English")], i18n.language(), self._set_language), 0, 1)
        grid.addWidget(label(_("Thème"), "body"), 1, 0)
        grid.addLayout(self._choices([("dark", _("Sombre")), ("light", _("Clair"))], theme.P.name, self._set_theme), 1, 1)
        grid.setColumnStretch(2, 1)
        fl.addLayout(grid)
        layout.addWidget(frame)

        frame, ul = card("true")
        ul.addWidget(label(_("MISES À JOUR"), "eyebrow"))
        mode = self.win.updater.install_mode()
        ul.addWidget(label(_("Version installée : {0} ({1})", __version__, _(self.MODES.get(mode, mode))), "body"))
        self.update_status = label("", "dim", wrap=True, selectable=True)
        ul.addWidget(self.update_status)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMaximumHeight(170)
        self.notes.hide()
        ul.addWidget(self.notes)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        ul.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.check_button = QPushButton(_("Rechercher une mise à jour"))
        self.check_button.setIcon(icon("refresh", theme.P.silk))
        self.check_button.clicked.connect(self.check)
        buttons.addWidget(self.check_button)
        self.install_button = QPushButton(_("Installer et redémarrer"))
        self.install_button.setProperty("kind", "primary")
        self.install_button.clicked.connect(self.install)
        buttons.addWidget(self.install_button)
        self.page_button = QPushButton(_("Voir la release"))
        self.page_button.setIcon(icon("arrow", theme.P.silk))
        self.page_button.clicked.connect(self.open_page)
        buttons.addWidget(self.page_button)
        buttons.addStretch(1)
        ul.addLayout(buttons)
        self.auto_check = QCheckBox(_("Rechercher une mise à jour au démarrage"))
        self.auto_check.setChecked(bool(self.win.config.get("check_updates", False)))
        self.auto_check.toggled.connect(self._set_auto_check)
        ul.addWidget(self.auto_check)
        privacy = _("La recherche interroge GitHub (api.github.com) : aucune donnée de l'inventaire n'est envoyée.")
        ul.addWidget(label(privacy, "small", wrap=True))
        layout.addWidget(frame)
        layout.addStretch(1)
        close = QPushButton(_("Fermer"))
        close.clicked.connect(self.close)
        layout.addWidget(close, 0, Qt.AlignRight)
        self.outer.addWidget(self.body)
        self._show_release()

    def _choices(self, options: list[tuple[str, str]], current: str, slot) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        for code, text in options:
            button = QPushButton(text)
            button.setProperty("kind", "choice")
            button.setCheckable(True)
            button.setChecked(code == current)
            button.clicked.connect(lambda _checked=False, value=code: slot(value))
            row.addWidget(button)
        row.addStretch(1)
        return row

    # ------------------------------------------------------------------ affichage / display

    def _set_language(self, code: str) -> None:
        if code != i18n.language():
            self.win.toggle_language()
        self.build()

    def _set_theme(self, name: str) -> None:
        if name != theme.P.name:
            self.win.toggle_theme()
        self.build()

    def _set_auto_check(self, checked: bool) -> None:
        self.win.config["check_updates"] = bool(checked)
        settings.save_config(self.win.config)

    # ------------------------------------------------------------------ mises à jour / updates

    def _show_release(self) -> None:
        release = self.win.available_release
        newer = release is not None and release.is_newer
        installable = newer and self.win.updater.install_mode() != update.SOURCE
        if self.busy:
            pass
        elif self.error:
            self.update_status.setText(self.error)
        elif release is None:
            self.update_status.setText(_("Aucune recherche faite pour l'instant."))
        elif not newer:
            self.update_status.setText(_("Atlas PC Monitor est à jour (dernière version : {0}).", release.version))
        elif installable:
            restart = _("L'application se fermera puis redémarrera dans la nouvelle version.")
            self.update_status.setText(f"{_('Version {0} disponible.', release.version)} {restart}")
        else:
            self.update_status.setText(f"{_('Version {0} disponible.', release.version)} {_(update.FROM_SOURCE)}")
        self.update_status.setProperty("role", "note" if self.error else "dim")
        self.update_status.style().unpolish(self.update_status)
        self.update_status.style().polish(self.update_status)
        self.notes.setVisible(newer and bool(release.notes.strip()) and not self.busy)
        if newer:
            self.notes.setMarkdown(update.notes_for(release.notes, i18n.language()))
        self.check_button.setEnabled(not self.busy)
        self.install_button.setVisible(installable)
        self.install_button.setEnabled(not self.busy)
        self.page_button.setVisible(newer)

    def check(self) -> None:
        if self.busy:
            return
        self.busy, self.error = True, ""
        self.update_status.setText(_("Recherche en cours…"))
        self._show_release()
        threading.Thread(target=self._check_work, daemon=True).start()

    def _check_work(self) -> None:
        try:
            result = self.win.updater.check()
        except update.UpdateError as error:
            result = error
        except Exception as error:
            log.exception("Recherche de mise à jour interrompue")
            result = update.UpdateError(_("Recherche impossible : {0}", error))
        with contextlib.suppress(RuntimeError):  # fenêtre déjà fermée — window already closed
            self.bridge.checked.emit(result)

    def _on_checked(self, result) -> None:
        self.busy = False
        if isinstance(result, update.Release):
            self.win.set_available_release(result)
        else:
            self.error = str(result)
        self._show_release()

    def install(self) -> None:
        release = self.win.available_release
        if self.busy or release is None:
            return
        self.busy, self.error = True, ""
        self.update_status.setText(_("Téléchargement de la version {0}…", release.version))
        self.progress.setRange(0, 0)
        self.progress.show()
        self._show_release()
        threading.Thread(target=self._install_work, args=(release,), daemon=True).start()

    def _install_work(self, release) -> None:
        def progress(done: int, total: int) -> None:
            with contextlib.suppress(RuntimeError):
                self.bridge.progress.emit(done, total)

        try:
            result = self.win.updater.install(release, progress)
        except update.UpdateError as error:
            result = error
        except Exception as error:
            log.exception("Mise à jour interrompue")
            result = update.UpdateError(_("Mise à jour impossible : {0}", error))
        with contextlib.suppress(RuntimeError):
            self.bridge.installed.emit(result)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, done * 1000 // total))

    def _on_installed(self, result) -> None:
        self.busy = False
        self.progress.hide()
        if isinstance(result, update.UpdateError):
            self.error = str(result)
            self._show_release()
            return
        self.update_status.setText(_("Mise à jour installée : redémarrage…"))
        self.win.updater.launch(result)
        self.win.quit_for_update()

    def open_page(self) -> None:
        release = self.win.available_release
        webbrowser.open(release.page if release is not None else update.RELEASES_PAGE)
