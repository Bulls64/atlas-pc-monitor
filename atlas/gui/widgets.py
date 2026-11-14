"""Composants dessinés à la manière d'une carte électronique : LED, pistes, points de soudure.

Components drawn like a circuit board: LEDs, traces, solder points.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..formatting import fmt_percent
from ..i18n import _
from . import theme

ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    "share": '<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M9 12h6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "print": '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
    "export": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    "copy": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
    "compare": '<path d="M7 4v16"/><path d="M3 8l4-4 4 4"/><path d="M17 20V4"/><path d="M13 16l4 4 4-4"/>',
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5"/><path d="M9.5 13.5L12 11l2.5 2.5"/>',
    "arrow": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "admin": '<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
}


def svg_pixmap(svg: str, size: int, ratio: float = 2.0) -> QPixmap:
    """Image d'un SVG, en double résolution par défaut (nette sur les écrans HiDPI ; 1.0 pour un fichier).

    Image of an SVG, at double resolution by default (sharp on HiDPI screens; 1.0 for a file).
    """
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon(name: str, color: str, size: int = 16) -> QIcon:
    color = theme.qcolor(color).name()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')  # fmt: skip
    return QIcon(svg_pixmap(svg, size))


def logo_pixmap(size: int = 40, ratio: float = 2.0) -> QPixmap:
    p = theme.P
    pins = "".join(f'<path d="M{x} 3v4M{x} 33v4M3 {x}h4M33 {x}h4"/>' for x in (13, 20, 27))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" fill="none">'
           f'<g stroke="{p.copper}" stroke-width="2" stroke-linecap="round">{pins}</g>'
           f'<rect x="8" y="8" width="24" height="24" rx="4" fill="{p.panel2}" stroke="{p.bright}" stroke-width="2"/>'
           f'<path d="M20 13l7 7-7 7-7-7z" fill="{p.solder}"/><circle cx="12.5" cy="12.5" r="1.6" fill="{p.bright}"/></svg>')  # fmt: skip
    return svg_pixmap(svg, size, ratio)


def label(text: str = "", role: str = "body", wrap: bool = False, selectable: bool = False, rich: bool = False) -> QLabel:
    """Libellé du thème. En texte brut sauf `rich` : une valeur lue sur le poste n'est jamais interprétée comme du HTML.

    Theme label. Plain text unless `rich`: a value read from the computer is never interpreted as HTML.
    """
    widget = QLabel(text)
    widget.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    if selectable:
        widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def card(kind: str = "true", margins=(22, 20, 22, 20), spacing: int = 12) -> tuple[QFrame, QVBoxLayout]:
    """Carte du thème (« true », « result », « map » ou un niveau : fix, watch, info, ok).

    Theme card ("true", "result", "map" or a level: fix, watch, info, ok).
    """
    frame = QFrame()
    frame.setProperty("card", kind)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("separator")
    return line


def draw_glow(painter: QPainter, center: QPointF, radius: float, color: QColor, strength: float = 0.7) -> None:
    if not theme.GLOW or theme.P.name == "light":
        return
    halo = QColor(color)
    gradient = QRadialGradient(center, radius)
    halo.setAlphaF(strength)
    gradient.setColorAt(0.0, halo)
    halo.setAlphaF(0.0)
    gradient.setColorAt(1.0, halo)
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(center, radius, radius)


def draw_via(painter: QPainter, center: QPointF, color: QColor, filled: bool, radius: float = 6.5) -> None:
    painter.setPen(QPen(color, 3))
    painter.setBrush(color if filled else theme.qcolor(theme.P.board2))
    painter.drawEllipse(center, radius - 1.5, radius - 1.5)


class Led(QWidget):
    """LED d'état. `level` : fix, watch, info, ok ; `off` : simple anneau (compteur à zéro).

    Status LED. `level`: fix, watch, info, ok; `off`: plain ring (counter at zero).
    """

    def __init__(self, level: str | None = "ok", size: int = 10, off: bool = False):
        super().__init__()
        self.level, self.diameter, self.off = level, size, off
        self.setFixedSize(size + 10, size + 10)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = theme.qcolor(theme.level_color(self.level))
        center = QPointF(self.width() / 2, self.height() / 2)
        r = self.diameter / 2
        if self.off:
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, r - 1, r - 1)
            return
        if self.level in ("ok", "watch", "fix"):
            draw_glow(painter, center, r + 5, color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(center, r, r)


class BusLine(QWidget):
    """Séparateur en piste de circuit, sous l'en-tête.

    Circuit-trace separator, under the header.
    """

    def __init__(self):
        super().__init__()
        self.setFixedHeight(14)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:
        p = theme.P
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        painter.fillRect(QRectF(0, 6, w, 2), theme.qcolor(p.border2))
        solder = theme.qcolor(p.solder)
        solder.setAlphaF(0.55)
        painter.fillRect(QRectF(w * 0.14, 6, w * 0.33, 2), solder)
        for x, color in ((0.14, p.copper), (0.47, p.solder), (0.83, p.copper)):
            painter.setPen(QPen(theme.qcolor(color), 3))
            painter.setBrush(theme.qcolor(p.board))
            painter.drawEllipse(QPointF(w * x, 7), 4.5, 4.5)


class TraceMeter(QWidget):
    """Jauge en piste : un point de soudure s'allume à chaque palier franchi (25, 50, 75 %).

    Trace gauge: a solder point lights up at each step reached (25, 50, 75%).
    """

    def __init__(self, percent: float | None):
        super().__init__()
        self.percent = max(0.0, min(100.0, percent or 0.0))
        self.setFixedHeight(42)
        self.setMinimumWidth(160)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:
        p = theme.P
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, y = self.width() - 2, 12
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor(p.rail))
        painter.drawRoundedRect(QRectF(1, y - 1.5, w, 3), 1.5, 1.5)
        solder = theme.qcolor(p.solder)
        end = 1 + w * self.percent / 100
        if theme.GLOW and p.name == "dark":
            glow = QColor(solder)
            glow.setAlphaF(0.25)
            painter.setBrush(glow)
            painter.drawRoundedRect(QRectF(1, y - 4, end - 1, 8), 4, 4)
        painter.setBrush(solder)
        painter.drawRoundedRect(QRectF(1, y - 1.5, end - 1, 3), 1.5, 1.5)
        for step in (25, 50, 75):
            on = self.percent >= step
            center = QPointF(1 + w * step / 100, y)
            if on:
                draw_glow(painter, center, 11, solder, 0.5)
            draw_via(painter, center, solder if on else theme.qcolor(p.via_off), on)
        painter.setPen(theme.qcolor(p.dim))
        font = painter.font()
        font.setFamily(theme.MONO)
        font.setPixelSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(0, 26, 60, 14), Qt.AlignLeft, "0")
        painter.drawText(QRectF(w / 2 - 30, 26, 60, 14), Qt.AlignCenter, fmt_percent(50))
        painter.drawText(QRectF(w - 60, 26, 60, 14), Qt.AlignRight, fmt_percent(100))


class DotBackground(QWidget):
    """Fond « board » avec une trame de points, comme le site.

    "Board" background with a dot grid, like the website.
    """

    def paintEvent(self, _event) -> None:
        p = theme.P
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.qcolor(p.board))
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor(p.dot))
        painter.setRenderHint(QPainter.Antialiasing)
        for x in range(12, self.width(), 24):
            for y in range(12, self.height(), 24):
                painter.drawEllipse(QPointF(x, y), 1.1, 1.1)


class CopyTable(QTableWidget):
    """Tableau en lecture seule, sans ascenseur propre : Ctrl+C, double-clic ou clic droit pour copier.

    Read-only table, with no scroll bar of its own: Ctrl+C, double-click or right-click to copy.
    """

    copied = Signal(str)

    def __init__(self, headers: list[str], rows: list[tuple], show_header: bool = False):
        super().__init__(len(rows), len(headers))
        self.setHorizontalHeaderLabels([h.upper() for h in headers])
        self.horizontalHeader().setVisible(show_header)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setWordWrap(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for column in range(len(headers)):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        if len(headers) == 2:
            header.setSectionResizeMode(0, QHeaderView.Interactive)
            self.setColumnWidth(0, 260)
        mono = self.font()
        mono.setFamily(theme.MONO)
        mono.setPixelSize(12)
        dim = theme.qcolor(theme.P.dim)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setForeground(dim)
                elif _looks_technical(item.text()):
                    item.setFont(mono)
                self.setItem(r, c, item)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.cellDoubleClicked.connect(lambda r, _c: self.copy_value(r))
        # La hauteur dépend de la largeur des colonnes (retours à la ligne) : on la recalcule
        # après chaque redimensionnement, une fois les colonnes posées.
        # The height depends on the column widths (line wrapping): it is recomputed
        # after each resize, once the columns are laid out.
        self._fit_timer = QTimer(self, singleShot=True, interval=0, timeout=self._fit)
        header.sectionResized.connect(lambda *_: self._fit_timer.start())
        self._fit()

    def _fit(self) -> None:
        self.resizeRowsToContents()
        height = sum(self.rowHeight(r) for r in range(self.rowCount())) + 2
        if self.horizontalHeader().isVisible():
            height += self.horizontalHeader().height()
        self.setFixedHeight(max(height, 8))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_timer.start()

    def wheelEvent(self, event) -> None:
        event.ignore()  # la page entière défile, pas le tableau — the whole page scrolls, not the table

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_rows()
            return
        super().keyPressEvent(event)

    def _put(self, text: str, message: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.copied.emit(message)

    def copy_rows(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()})
        lines = ["\t".join(self.item(r, c).text() for c in range(self.columnCount())) for r in rows]
        if lines:
            self._put("\n".join(lines), _("{0} ligne(s) copiée(s)", len(lines)))

    def copy_value(self, row: int) -> None:
        self._put(self.item(row, self.columnCount() - 1).text(), _("Valeur copiée"))

    def _menu(self, position) -> None:
        row = self.rowAt(position.y())
        if row < 0:
            return
        if not self.item(row, 0).isSelected():
            self.selectRow(row)
        menu = QMenu(self)
        menu.addAction(_("Copier la valeur"), lambda: self.copy_value(row))
        menu.addAction(_("Copier la ligne"), self.copy_rows)
        menu.exec(self.viewport().mapToGlobal(position))


def _looks_technical(text: str) -> bool:
    """Références, numéros et adresses en police mono ; phrases en police de texte.

    References, numbers and addresses in the monospace font; sentences in the text font.
    """
    letters = sum(ch.isalpha() for ch in text)
    return bool(text) and (letters < len(text) * 0.6 or (" " not in text and any(ch.isdigit() for ch in text)))


def hbox(*widgets, spacing: int = 10, margins=(0, 0, 0, 0), stretch_at: int | None = None) -> QWidget:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for index, widget in enumerate(widgets):
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, int):
            layout.addSpacing(widget)
        else:
            layout.addWidget(widget, 1 if index == stretch_at else 0)
    return box


def screen_size() -> QSize:
    screen = QApplication.primaryScreen()
    return screen.availableGeometry().size() if screen else QSize(1366, 768)


class Responsive(QWidget):
    """Rangée qui passe sur moins de colonnes quand la largeur manque (ex. 2 colonnes, puis 1).

    Row that moves to fewer columns when the width runs short (e.g. 2 columns, then 1).
    """

    def __init__(self, widgets: list[QWidget], breakpoints: tuple = ((720, 2), (0, 1)), spacing: int = 20, stretches: tuple | None = None):
        super().__init__()
        self.setObjectName("inner")
        self.items, self.breakpoints, self.stretches = widgets, breakpoints, stretches
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.columns = 0
        self._layout(min(self.breakpoints[0][1], len(widgets)))

    def _layout(self, columns: int) -> None:
        if columns == self.columns:
            return
        self.columns = columns
        for widget in self.items:
            self.grid.removeWidget(widget)
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        for index, widget in enumerate(self.items):
            self.grid.addWidget(widget, index // columns, index % columns)
        for c in range(columns):
            stretch = self.stretches[c] if self.stretches and columns == len(self.stretches) else 1
            self.grid.setColumnStretch(c, stretch)

    def resizeEvent(self, event) -> None:
        width = event.size().width()
        for minimum, columns in self.breakpoints:
            if width >= minimum:
                self._layout(min(columns, len(self.items)))
                break
        super().resizeEvent(event)
