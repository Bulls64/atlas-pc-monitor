"""Barrettes mémoire dessinées (vue de face) et pistes du conseiller d'évolution."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme
from .widgets import draw_via

CHIP, GOLD = "#0c1512", "#c98a4b"
# Vert de circuit imprimé, plus clair que les cartes en thème sombre pour que la barrette s'en détache.
PCB = {"dark": "#24493c", "light": "#142520"}
STICK_W, STICK_H = 680, 104


class DimmStick(QWidget):
    def __init__(self, accessible: str):
        super().__init__()
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMaximumWidth(STICK_W)
        self.setMinimumWidth(300)
        self.setAccessibleName(accessible)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(STICK_H * min(width, STICK_W) / STICK_W)

    def sizeHint(self) -> QSize:
        return QSize(STICK_W, STICK_H)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width(), STICK_W) / STICK_W
        painter.scale(scale, scale)
        body = QPainterPath()
        body.addRoundedRect(QRectF(4, 4, 672, 68), 4, 4)
        painter.setPen(QPen(QColor(201, 138, 75, 90), 1))
        painter.setBrush(QColor(PCB[theme.P.name]))
        painter.drawPath(body)
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRectF(4, 66, 536, 14))
        painter.drawRect(QRectF(556, 66, 120, 14))
        painter.setBrush(theme.qcolor(theme.P.panel))  # encoches latérales
        painter.drawEllipse(QPointF(4, 40), 6, 6)
        painter.drawEllipse(QPointF(676, 40), 6, 6)
        painter.setPen(QPen(QColor(238, 244, 240, 30), 1))
        painter.setBrush(QColor(CHIP))
        for x in (56, 176, 296, 416):
            painter.drawRoundedRect(QRectF(x, 14, 96, 44), 3, 3)
        dash = QPen(QColor(238, 244, 240, 46), 1, Qt.DashLine)
        painter.setPen(dash)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(540, 16, 110, 40), 3, 3)
        painter.setPen(QPen(QColor(201, 138, 75, 115), 1.5))
        painter.drawLine(QPointF(20, 64), QPointF(520, 64))
        painter.drawLine(QPointF(560, 64), QPointF(656, 64))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(GOLD))
        for start, end in ((16, 540), (556, 664)):
            x = start + 1
            while x + 6 <= end:
                painter.drawRoundedRect(QRectF(x, 78, 6, 20), 1, 1)
                x += 9


class RouteTrace(QWidget):
    """Piste du conseiller : de la capacité actuelle (point creux) à la cible (point plein)."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(18)
        self.setMinimumWidth(80)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = theme.qcolor(theme.P.bright)
        y = self.height() / 2
        painter.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(8, y), QPointF(self.width() - 8, y))
        draw_via(painter, QPointF(8, y), color, False)
        draw_via(painter, QPointF(self.width() - 8, y), color, True)
