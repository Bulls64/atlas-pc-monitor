"""Plan de la carte : les composants du poste dessinés comme des puces sur un circuit imprimé.

Chaque piste prend la couleur de l'état de son composant ; cliquer une puce ouvre sa page.
Le dessin est conçu sur 944 × 448 et mis à l'échelle de la largeur disponible.

Board map: the computer's components drawn as chips on a printed circuit board.

Each trace takes the color of its component's status; clicking a chip opens its page.
The drawing is designed at 944 × 448 and scaled to the available width.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..i18n import _
from . import theme
from .model import Chip
from .widgets import draw_glow, draw_via

BASE_W, BASE_H = 944, 448
MAX_SCALE = 1.25

RECTS = {
    "ram": QRectF(40, 64, 232, 96), "disks": QRectF(40, 280, 232, 96), "gpu": QRectF(672, 64, 232, 96),
    "net": QRectF(672, 280, 232, 96), "battery": QRectF(372, 344, 200, 72), "bios": QRectF(392, 32, 160, 56),
    "cpu": QRectF(372, 140, 200, 160),
}  # fmt: skip
TRACES = {
    "ram": [(272, 112), (320, 112), (320, 172), (360, 172)],
    "disks": [(272, 328), (320, 328), (320, 268), (360, 268)],
    "gpu": [(672, 112), (624, 112), (624, 172), (584, 172)],
    "net": [(672, 328), (624, 328), (624, 268), (584, 268)],
    "battery": [(472, 344), (472, 312)],
    "bios": [(472, 88), (472, 128)],
}


def _font(family: str, px: float, weight: int = 400, spacing: float = 0.0) -> QFont:
    font = QFont(family)
    font.setPixelSize(round(px))
    font.setWeight(QFont.Weight(weight))
    if spacing:
        font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return font


class BoardMap(QWidget):
    pageRequested = Signal(str)

    def __init__(self, chips: dict[str, Chip], labels: tuple[str, str]):
        super().__init__()
        self.chips, self.labels = chips, labels
        self.hover: str | None = None
        self.setMouseTracking(True)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumWidth(560)
        self.setAccessibleName(_("Plan de la carte : composants détectés et leur état"))

    # ---------------------------------------------------------------- géométrie / geometry

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(BASE_H * min(width / BASE_W, MAX_SCALE))

    def sizeHint(self) -> QSize:
        return QSize(BASE_W, BASE_H)

    def _transform(self) -> tuple[float, float]:
        scale = min(self.width() / BASE_W, MAX_SCALE)
        return scale, (self.width() - BASE_W * scale) / 2

    def chip_at(self, pos: QPointF) -> str | None:
        scale, dx = self._transform()
        point = QPointF((pos.x() - dx) / scale, pos.y() / scale)
        for key, rect in RECTS.items():
            if rect.contains(point) and key in self.chips and self.chips[key].page:
                return key
        return None

    # ---------------------------------------------------------------- souris / mouse

    def mouseMoveEvent(self, event) -> None:
        key = self.chip_at(event.position())
        if key != self.hover:
            self.hover = key
            self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)
            chip = self.chips.get(key) if key else None
            self.setToolTip(
                _("{0}\nOuvrir la page {1}", chip.issue, _(chip.page))
                if chip and chip.issue
                else (_("Ouvrir la page {0}", _(chip.page)) if chip else "")
            )
            self.update()

    def leaveEvent(self, _event) -> None:
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        key = self.chip_at(event.position())
        if key and event.button() == Qt.LeftButton:
            self.pageRequested.emit(self.chips[key].page)

    # ---------------------------------------------------------------- dessin / drawing

    def _color(self, level: str | None) -> QColor:
        return theme.qcolor(theme.P.via_off if level is None else theme.level_color(level))

    def paintEvent(self, _event) -> None:
        p = theme.P
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        scale, dx = self._transform()
        painter.translate(dx, 0)
        painter.scale(scale, scale)

        # traces, puis points de soudure aux coudes
        # traces, then solder points at the bends
        for key, points in TRACES.items():
            chip = self.chips.get(key)
            level = chip.level if chip else None
            color = self._color(level)
            path = QPainterPath(QPointF(*points[0]))
            for point in points[1:]:
                path.lineTo(QPointF(*point))
            if level is not None and theme.GLOW and p.name == "dark":
                glow = QColor(color)
                glow.setAlphaF(0.22)
                painter.strokePath(path, QPen(glow, 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.strokePath(path, QPen(color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for point in points[1:-1]:
                if level is not None:
                    draw_glow(painter, QPointF(*point), 12, color, 0.45)
                draw_via(painter, QPointF(*point), color, False)

        # broches du processeur (masquées au centre par la puce)
        # processor pins (hidden in the middle by the chip)
        copper = theme.qcolor(p.copper)
        painter.setPen(Qt.NoPen)
        painter.setBrush(copper)
        for y in range(148, 292, 11):
            painter.drawRect(QRectF(360, y, 224, 3))
        for x in range(380, 564, 11):
            painter.drawRect(QRectF(x, 128, 3, 184))

        for key, rect in RECTS.items():
            if key in self.chips:
                self._chip(painter, self.chips[key], rect, key == "cpu")

        painter.setFont(_font(theme.MONO, 10.5, 500, 1.4))
        painter.setPen(copper)
        painter.drawText(QRectF(20, 12, 500, 16), Qt.AlignLeft | Qt.AlignVCenter, self.labels[0])
        painter.setPen(theme.qcolor(p.dim))
        painter.drawText(QRectF(BASE_W - 520, BASE_H - 28, 500, 16), Qt.AlignRight | Qt.AlignVCenter, self.labels[1])

    def _chip(self, painter: QPainter, chip: Chip, rect: QRectF, is_cpu: bool) -> None:
        p = theme.P
        hovered = self.hover == chip.key
        missing = chip.level is None
        border = theme.qcolor(p.bright if hovered else ("rgba(233,164,61,0.5)" if is_cpu and p.name == "dark" else p.border2))
        pen = QPen(border, 1.5 if hovered else 1)
        if missing:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(theme.qcolor(p.panel2 if is_cpu else p.panel))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6 if is_cpu else 8, 6 if is_cpu else 8)

        dim, silk = theme.qcolor(p.dim), theme.qcolor(p.dim if missing else p.silk)
        des_font = _font(theme.MONO, 10.5, 500, 1.6)
        title_font = _font(theme.DISPLAY, 19 if is_cpu else 17, 600)
        line_font = _font(theme.MONO, 11.5)
        pad = 16
        if is_cpu:
            inner = rect.adjusted(14, 16, -14, -12)
            painter.setFont(des_font)
            painter.setPen(theme.qcolor(p.copper))
            painter.drawText(QRectF(inner.left(), inner.top(), inner.width(), 16), Qt.AlignHCenter, chip.designator)
            painter.setFont(title_font)
            painter.setPen(silk)
            title_rect = QRectF(inner.left(), inner.top() + 22, inner.width(), 52)
            painter.drawText(title_rect, Qt.AlignHCenter | Qt.TextWordWrap, chip.title)
            painter.setFont(line_font)
            painter.setPen(dim)
            painter.drawText(QRectF(inner.left(), inner.top() + 80, inner.width(), 40), Qt.AlignHCenter, "\n".join(chip.lines))
            painter.setPen(QPen(theme.qcolor(p.copper), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(rect.left() + 13, rect.top() + 13), 3.5, 3.5)
            return

        y = rect.top() + (12 if rect.height() < 80 else 14)
        width = rect.width() - pad * 2 - 18
        painter.setFont(des_font)
        painter.setPen(theme.qcolor(p.copper))
        painter.drawText(QRectF(rect.left() + pad, y, width + 18, 15), Qt.AlignLeft, chip.designator)
        y += 17
        painter.setFont(title_font)
        painter.setPen(silk)
        title = QFontMetrics(title_font).elidedText(chip.title, Qt.ElideRight, int(width + 18))
        painter.drawText(QRectF(rect.left() + pad, y, width + 18, 22), Qt.AlignLeft, title)
        y += 23
        metrics = QFontMetrics(line_font)
        painter.setFont(line_font)
        for text, color in [(line, dim) for line in chip.lines] + (
            [(chip.issue, theme.qcolor(theme.text_color(chip.level)))] if chip.issue else []
        ):
            if y + 15 > rect.bottom() - 4:
                break
            painter.setPen(color)
            painter.drawText(
                QRectF(rect.left() + pad, y, width + 18, 16), Qt.AlignLeft, metrics.elidedText(text, Qt.ElideRight, int(width + 18))
            )
            y += 16

        center = QPointF(rect.right() - 20, rect.top() + 20)
        color = self._color(chip.level)
        if missing:
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 4, 4)
        else:
            draw_glow(painter, center, 11, color)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(center, 5, 5)
