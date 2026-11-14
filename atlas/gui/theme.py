"""Thème BAUSTECH PC : palettes sombre et claire, polices embarquées, feuille de style Qt.

Les couleurs reprennent celles du site (board, cuivre, soudure, sérigraphie). Le thème
courant est `theme.P` ; les widgets dessinés à la main le lisent au moment de peindre.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication

FONT_DIR = Path(__file__).with_name("fonts")
DISPLAY = "Space Grotesk"
BODY = "Inter"
MONO = "IBM Plex Mono"


@dataclass(frozen=True)
class Palette:
    name: str
    board: str  # fond
    board2: str  # fond du plan de carte
    panel: str  # cartes
    panel2: str  # cartes relevées, champs
    silk: str  # texte (sérigraphie)
    dim: str  # texte discret
    copper: str  # repères, broches
    bright: str  # cuivre vif : action principale, gros chiffres, « à surveiller »
    solder: str  # soudure : état OK, pistes allumées
    led: str  # LED rouge : « à corriger »
    link: str  # liens et étiquettes de champ
    eyebrow: str  # petites étiquettes en capitales
    border: str
    border2: str
    dot: str  # trame de points du fond
    primary_text: str
    badge: str
    rail: str  # partie éteinte d'une piste
    via_off: str
    warn_text: str  # « à surveiller » en petit texte (l'orange vif ne suffit pas sur fond clair)


DARK = Palette(
    name="dark", board="#0c1512", board2="#101c17", panel="#142520", panel2="#1a2f28", silk="#eef4f0", dim="#a9bdb4",
    copper="#c98a4b", bright="#e8a33d", solder="#52d6c2", led="#ff4a3d", link="#52d6c2", eyebrow="#e8a33d",
    border="rgba(233,164,61,0.18)", border2="rgba(233,164,61,0.30)", dot="rgba(238,244,240,0.05)", primary_text="#16110a",
    badge="rgba(232,163,61,0.14)", rail="rgba(233,164,61,0.22)", via_off="rgba(233,164,61,0.35)", warn_text="#e8a33d",
)  # fmt: skip

# Thème clair du site, avec deux couleurs foncées pour que le petit texte reste lisible (contraste ≥ 4,5:1).
# Le turquoise sombre distingue l'état OK de l'orange « à surveiller ».
LIGHT = Palette(
    name="light", board="#f7f6f3", board2="#ffffff", panel="#ffffff", panel2="#fbfaf8", silk="#17140f", dim="#6b6459",
    copper="#a3480f", bright="#ff5500", solder="#0f7a6c", led="#c1272d", link="#b8460e", eyebrow="#b8460e",
    border="rgba(23,20,15,0.14)", border2="rgba(23,20,15,0.22)", dot="rgba(23,20,15,0.06)", primary_text="#17140f",
    badge="rgba(255,85,0,0.10)", rail="rgba(23,20,15,0.12)", via_off="rgba(23,20,15,0.25)", warn_text="#b8460e",
)  # fmt: skip

PALETTES = {"dark": DARK, "light": LIGHT}
P: Palette = DARK
GLOW = True  # halos lumineux autour des LED et des pistes


def set_theme(name: str) -> Palette:
    global P
    P = PALETTES.get(name, DARK)
    return P


def qcolor(value: str) -> QColor:
    """QColor depuis « #rrggbb » ou « rgba(r,g,b,a) »."""
    value = value.strip()
    if value.startswith("rgba"):
        r, g, b, a = (float(x) for x in value[value.index("(") + 1 : value.index(")")].split(","))
        color = QColor(int(r), int(g), int(b))
        color.setAlphaF(a)
        return color
    return QColor(value)


def level_color(level: str | None) -> str:
    """Couleur d'un niveau de constat : à corriger, à surveiller, à noter, OK (None : sans objet)."""
    return {"fix": P.led, "watch": P.bright, "info": P.silk, "ok": P.solder}.get(level or "", P.dim)


def text_color(level: str | None) -> str:
    """Couleur d'un niveau pour du petit texte (contraste suffisant dans les deux thèmes)."""
    return P.warn_text if level == "watch" else level_color(level)


def load_fonts() -> list[str]:
    """Charge les polices embarquées (licence OFL) ; renvoie les familles disponibles."""
    if QGuiApplication.instance() is None:  # Qt exige une application avant d'enregistrer des polices
        return []
    families: set[str] = set()
    for path in sorted(FONT_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(families)


def qss() -> str:
    """Feuille de style Qt du thème courant."""
    p = P
    # Cartes surmontées d'un filet de couleur : résultat, puis un par niveau de constat.
    accents = {"result": p.bright, "fix": p.led, "watch": p.bright, "info": p.silk, "ok": p.solder}
    cards = "\n".join(
        f'QFrame[card="{kind}"] {{ background: {p.panel}; border: 1px solid {p.border}; border-top: 3px solid {color}; border-radius: 10px; }}'
        for kind, color in accents.items()
    )
    return f"""
* {{ font-family: "{BODY}", "Segoe UI", sans-serif; font-size: 14px; color: {p.silk}; }}
QMainWindow, QDialog {{ background: {p.board}; }}
QWidget#board, QWidget#content {{ background: transparent; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {p.panel2}; color: {p.silk}; border: 1px solid {p.border2}; padding: 6px; }}

QLabel[role="brand"] {{ font-family: "{DISPLAY}"; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
QLabel[role="brandSub"] {{ font-family: "{MONO}"; font-size: 10px; letter-spacing: 1px; color: {p.solder}; }}
QLabel[role="eyebrow"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 500; letter-spacing: 1.2px; color: {p.eyebrow}; }}
QLabel[role="eyebrowDim"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 500; letter-spacing: 1.2px; color: {p.dim}; }}
QLabel[role="h1"] {{ font-family: "{DISPLAY}"; font-size: 34px; font-weight: 600; }}
QLabel[role="h2"] {{ font-family: "{DISPLAY}"; font-size: 22px; font-weight: 600; }}
QLabel[role="h3"] {{ font-family: "{DISPLAY}"; font-size: 18px; font-weight: 600; }}
QLabel[role="sub"] {{ font-size: 15px; color: {p.dim}; }}
QLabel[role="body"] {{ font-size: 14px; }}
QLabel[role="dim"] {{ font-size: 13px; color: {p.dim}; }}
QLabel[role="small"] {{ font-size: 12px; color: {p.dim}; }}
QLabel[role="mono"] {{ font-family: "{MONO}"; font-size: 12px; color: {p.dim}; }}
QLabel[role="monoStrong"] {{ font-family: "{MONO}"; font-size: 12px; color: {p.silk}; }}
QLabel[role="big"] {{ font-family: "{DISPLAY}"; font-size: 30px; font-weight: 700; color: {p.bright}; }}
QLabel[role="bigger"] {{ font-family: "{DISPLAY}"; font-size: 40px; font-weight: 700; color: {p.bright}; }}
QLabel[role="stat"] {{ font-family: "{DISPLAY}"; font-size: 26px; font-weight: 700; }}
QLabel[role="note"] {{ font-size: 13px; color: {p.warn_text}; }}
QLabel[role="status"] {{ font-family: "{MONO}"; font-size: 11px; letter-spacing: 0.5px; color: {p.solder}; }}
QLabel[role="statusWarn"] {{ font-family: "{MONO}"; font-size: 11px; letter-spacing: 0.5px; color: {p.warn_text}; }}
QLabel[role="badge"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 600; color: {p.warn_text}; background: {p.badge};
    border-radius: 9px; padding: 1px 8px; }}
QLabel[role="tag"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; color: {p.warn_text};
    background: {p.badge}; border-radius: 10px; padding: 3px 10px; }}
QLabel[role="tagOk"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; color: {p.link};
    background: {p.badge}; border-radius: 10px; padding: 3px 10px; }}
QLabel[role="designator"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 500; letter-spacing: 1px; color: {p.copper}; }}
QLabel[role="level"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 600; letter-spacing: 1.2px; }}
QLabel[role="counter"] {{ font-family: "{DISPLAY}"; font-size: 40px; font-weight: 700; }}

QFrame[card="true"] {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 10px; }}
{cards}
QFrame[card="map"] {{ background: {p.board2}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame[card] QLabel, QFrame[card] QWidget#inner {{ background: transparent; border: none; }}
QLabel[level="fix"] {{ color: {p.led}; }}
QLabel[level="watch"] {{ color: {p.warn_text}; }}
QLabel[level="info"] {{ color: {p.silk}; }}
QLabel[level="ok"] {{ color: {p.solder}; }}
QLabel[level="off"] {{ color: {p.dim}; }}
QLabel[role="field"] {{ font-family: "{MONO}"; font-size: 11px; font-weight: 500; letter-spacing: 1.5px; color: {p.link}; }}
QFrame#separator {{ background: {p.border2}; border: none; max-height: 1px; min-height: 1px; }}

QPushButton {{ background: transparent; color: {p.silk}; border: 1px solid {p.border2}; border-radius: 8px;
    padding: 9px 14px; font-size: 13px; font-weight: 500; text-align: left; }}
QPushButton:hover {{ border-color: {p.bright}; }}
QPushButton:pressed {{ background: {p.panel2}; }}
QPushButton:disabled {{ color: {p.dim}; border-color: {p.border}; }}
QPushButton:focus {{ outline: none; border-color: {p.link}; }}
QPushButton[kind="primary"] {{ background: {p.bright}; color: {p.primary_text}; border: none; font-family: "{DISPLAY}";
    font-size: 14px; font-weight: 600; padding: 10px 16px; text-align: center; }}
QPushButton[kind="primary"]:hover {{ background: {p.copper if p.name == "light" else "#f0b152"}; }}
QPushButton[kind="primary"]:disabled {{ background: {p.panel2}; color: {p.dim}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid {p.silk}; }}
QPushButton[kind="icon"] {{ padding: 0; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; text-align: center; }}
QPushButton[kind="language"] {{ padding: 0 10px; min-height: 40px; max-height: 40px; text-align: center; font-family: "{MONO}";
    font-size: 12px; font-weight: 600; letter-spacing: 1px; }}
QPushButton[kind="sharing"]:checked {{ background: {p.bright}; color: {p.primary_text}; border-color: {p.bright}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {p.link}; padding: 2px 0; font-family: "{MONO}";
    font-size: 12px; letter-spacing: 1px; }}
QPushButton[kind="link"]:hover {{ color: {p.silk}; }}
QPushButton[kind="nav"] {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 0; min-height: 38px; }}
QPushButton[kind="nav"]:hover {{ background: {p.panel}; }}
QPushButton[kind="nav"]:checked {{ background: {p.panel}; border-color: {p.border}; }}
QLabel[role="navName"] {{ font-size: 14px; font-weight: 500; color: {p.dim}; }}
QLabel[role="navName"][active="true"] {{ font-weight: 600; color: {p.silk}; }}
QLabel[role="designator"][active="true"] {{ color: {p.bright}; }}

QLineEdit {{ background: {p.panel2}; border: 1px solid {p.border2}; border-radius: 8px; padding: 0 10px; min-height: 38px;
    selection-background-color: {p.solder}; selection-color: {p.board}; }}
QLineEdit:focus {{ border-color: {p.link}; }}
QPlainTextEdit {{ background: {p.panel2}; border: 1px solid {p.border2}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {p.solder}; selection-color: {p.board}; }}
QPlainTextEdit:focus {{ border-color: {p.link}; }}

QTableWidget {{ background: transparent; border: none; gridline-color: transparent; font-size: 13px;
    selection-background-color: {p.badge}; selection-color: {p.silk}; outline: none; }}
QTableWidget::item {{ padding: 8px 12px; border-bottom: 1px solid {p.border}; }}
QTableWidget::item:selected {{ background: {p.badge}; color: {p.silk}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {p.dim}; border: none; border-bottom: 1px solid {p.border2};
    padding: 8px 12px; font-family: "{MONO}"; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border2}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.copper}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border2}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {p.panel2}; border: 1px solid {p.border2}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.badge}; }}
QMessageBox QLabel {{ font-size: 14px; }}
"""
