"""Export du rapport en PDF (A4), mis en page par Qt (QTextDocument + QPdfWriter, sans outil externe).

Le moteur de texte de Qt ne lit qu'une partie du CSS : la page est donc écrite pour lui, avec des
tableaux et des styles en ligne, plutôt que de reprendre le rapport HTML. Nécessite PySide6, comme
l'interface ; en ligne de commande, Qt tourne sans fenêtre.

Report export to PDF (A4), laid out by Qt (QTextDocument + QPdfWriter, no external tool).

Qt's text engine only reads part of CSS: the page is therefore written for it, with tables and inline
styles, rather than reusing the HTML report. Requires PySide6, like the interface; on the command line,
Qt runs without a window.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

from . import __version__
from .export import _header
from .findings import analyze, summary_text
from .i18n import _
from .pages import build_all

# Couleurs d'impression : texte foncé sur fond blanc, une teinte par niveau de constat.
# Print colors: dark text on white, one tint per finding level.
INK, DIM, RULE, ZEBRA, ACCENT = "#172333", "#5b6b7d", "#d5dee8", "#f4f6f9", "#13865f"
LEVELS = {
    "fix": ("#b42318", "#fbebeb"),
    "watch": ("#8a5a06", "#fdf3e1"),
    "info": ("#2766b2", "#e7f1fb"),
    "ok": ("#13865f", "#e5f4e4"),
}


def to_document_html(data: dict) -> str:
    """Page du rapport pour le moteur de texte de Qt (tableaux, styles en ligne).

    Report page for Qt's text engine (tables, inline styles).
    """
    esc = html.escape
    title, subtitle = _header(data)
    parts = [
        f'<h1 style="color:{INK}; font-size:20pt; margin-bottom:2px;">{esc(title)}</h1>',
        f'<p style="color:{DIM}; margin-top:0;">{esc(subtitle)}</p>',
    ]
    if data.get("note"):
        parts.append(f'<p style="color:{LEVELS["fix"][0]};">{esc(data["note"])}</p>')
    found = analyze(data)
    if found:
        parts.append(_heading(_("Constats — {0}", summary_text(found))))
        rows = []
        for item in found:
            ink, tint = LEVELS.get(item.level, (INK, ZEBRA))
            detail = "<br>".join(esc(line) for line in item.detail.splitlines())
            advice = f'<br><span style="color:{DIM};">→ {esc(item.advice)}</span>' if item.advice else ""
            rows.append(
                f'<tr><td width="18%" bgcolor="{tint}" style="color:{ink}; font-weight:700; font-size:8pt;">'
                f'{esc(item.label).upper()}</td><td bgcolor="{tint}"><b>{esc(item.title)}</b><br>{detail}{advice}</td></tr>'
            )
        parts.append(_table(rows, spacing=3))
    for page, sections in build_all(data).items():
        parts.append(_heading(_(page)))
        for section in sections:
            parts.append(f'<h3 style="color:{INK}; font-size:10.5pt; margin-top:10px; margin-bottom:4px;">{esc(section.title)}</h3>')
            if section.rows:
                rows = []
                for index, row in enumerate(section.rows):
                    shade = f' bgcolor="{ZEBRA}"' if index % 2 else ""
                    rows.append(f'<tr{shade}><td width="36%" style="color:{DIM};">{esc(row.label)}</td><td>{esc(row.value)}</td></tr>')
                parts.append(_table(rows))
            if section.note or not section.rows:
                parts.append(f'<p style="color:{DIM};">{esc(section.note or _("Aucune information détectée."))}</p>')
            if section.tip:
                parts.append(f'<p style="color:{DIM}; font-size:8.5pt;">{esc(section.tip)}</p>')
    parts.append(f'<p style="color:{DIM}; font-size:8pt; margin-top:16px;">{esc(_("Généré par Atlas PC Monitor {0}", __version__))}</p>')
    return f'<html><body style="color:{INK}; font-size:9pt;">' + "\n".join(parts) + "</body></html>"


def _heading(text: str) -> str:
    return (
        f'<h2 style="color:{ACCENT}; font-size:14pt; margin-top:18px; margin-bottom:6px;">{html.escape(text)}</h2>'
        f'<hr style="background-color:{ACCENT}; height:1px;">'
    )


def _table(rows: list[str], spacing: int = 0) -> str:
    return (
        f'<table width="100%" cellspacing="{spacing}" cellpadding="4" '
        f'style="border-collapse:collapse; border: 1px solid {RULE};">' + "".join(rows) + "</table>"
    )


def _application():
    """Application Qt pour la mise en page : celle de l'interface, sinon une sans fenêtre.

    Qt application for the layout: the interface's one, otherwise one without a window.
    """
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    if app is None:
        # Sous Linux, le PDF n'a jamais besoin d'écran : le lanceur de l'AppImage ou des paquets impose
        # pourtant X11 (xcb), qui échoue dans une session sans affichage (SSH, cron).
        # On Linux, the PDF never needs a display: the AppImage or package launcher still forces X11
        # (xcb), which fails in a session without a display (SSH, cron).
        if sys.platform.startswith("linux"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QGuiApplication(sys.argv[:1])
    return app


def write(data: dict, path: str | Path) -> Path:
    """Écrit le rapport en PDF A4 ; renvoie le chemin écrit.

    Writes the report as an A4 PDF; returns the path written.
    """
    _application()
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    from .gui import theme

    theme.load_fonts()
    target = Path(path)
    writer = QPdfWriter(str(target))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Millimeter)
    writer.setResolution(96)
    writer.setTitle(_header(data)[0])
    writer.setCreator(f"Atlas PC Monitor {__version__}")
    document = QTextDocument()
    document.setDefaultFont(QFont(theme.BODY, 9))
    document.setDocumentMargin(0)
    document.setHtml(to_document_html(data))
    layout = writer.pageLayout()
    rect = layout.paintRectPixels(writer.resolution())
    document.setPageSize(QSizeF(rect.width(), rect.height()))
    document.print_(writer)
    del writer  # termine le fichier — finishes the file
    if not target.is_file() or target.stat().st_size == 0:
        raise OSError(_("Le PDF n'a pas pu être écrit : {0}", target))
    return target
