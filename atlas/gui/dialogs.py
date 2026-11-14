"""Fenêtres secondaires : fiche d'intervention et comparaison de rapports."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import fiche
from .. import findings as F
from . import theme
from .widgets import CopyTable, card, icon, label


class FicheDialog(QDialog):
    """Saisie de la fiche ; laissés vides, les champs s'impriment comme des lignes à remplir à la main."""

    FIELDS = (("technician", "Technicien"), ("client", "Client"), ("contact", "Contact"), ("reference", "Référence"))
    TEXTS = (("request", "Demande du client"), ("work", "Travaux réalisés"), ("recommendations", "Recommandations"))

    def __init__(self, win, info: fiche.FicheInfo):
        super().__init__(win)
        self.win, self.info = win, info
        self.setWindowTitle("Atlas PC Monitor — Fiche d'intervention")
        self.setWindowIcon(win.windowIcon())
        self.resize(660, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)
        layout.addWidget(label("FICHE D'INTERVENTION", "eyebrow"))
        layout.addWidget(label("Préparer la fiche", "h2"))
        layout.addWidget(
            label(
                "Tous les champs sont facultatifs : laissés vides, ils s'impriment comme des lignes à remplir à la main.", "dim", wrap=True
            )
        )
        layout.addSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.entries: dict[str, QLineEdit] = {}
        for row, (key, text) in enumerate(self.FIELDS):
            entry = QLineEdit(getattr(info, key))
            name = label(text.upper(), "field")
            name.setBuddy(entry)
            grid.addWidget(name, row, 0)
            grid.addWidget(entry, row, 1)
            self.entries[key] = entry
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.texts: dict[str, QPlainTextEdit] = {}
        for key, text in self.TEXTS:
            head = QHBoxLayout()
            head.addWidget(label(text.upper(), "field"))
            head.addStretch(1)
            box = QPlainTextEdit(getattr(info, key))
            box.setTabChangesFocus(True)
            box.setMinimumHeight(84)
            if key == "recommendations":
                link = QPushButton("Reprendre les conseils des constats")
                link.setProperty("kind", "link")
                link.clicked.connect(lambda _=False, target=box: self.insert_advice(target))
                head.addWidget(link)
            layout.addSpacing(6)
            layout.addLayout(head)
            layout.addWidget(box, 1)
            self.texts[key] = box
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 12, 0, 0)
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        save = QPushButton("Enregistrer…")
        save.clicked.connect(lambda: self.win.save_fiche(self.collect(), self))
        printing = QPushButton("Ouvrir pour imprimer")
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
        """Ajoute les conseils des constats à corriger et à surveiller, sans doublon."""
        current = box.toPlainText()
        lines = [f"- {i.title} : {i.advice}" for i in self.win.findings if i.level in (F.FIX, F.WATCH) and i.advice]
        new = [line for line in lines if line not in current]
        if not new:
            self.win.flash("Aucun conseil à ajouter")
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
        self.collect()
        super().hideEvent(event)


class CompareDialog(QDialog):
    def __init__(self, win, title: str, changes: list[tuple]):
        super().__init__(win)
        self.setWindowTitle("Atlas PC Monitor — Comparaison de rapports")
        self.setWindowIcon(win.windowIcon())
        self.resize(1000, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(label("COMPARAISON", "eyebrow"))
        layout.addWidget(label(title, "h3", wrap=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        frame, fl = card("true", (8, 12, 8, 12), 0)
        self.table = CopyTable(["Emplacement", "Propriété", "Avant", "Maintenant"], changes, show_header=True)
        self.table.copied.connect(win.flash)
        fl.addWidget(self.table)
        il.addWidget(frame)
        il.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        layout.addWidget(close, 0, Qt.AlignRight)
