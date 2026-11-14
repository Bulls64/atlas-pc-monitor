"""Les écrans de l'application : vue d'ensemble, constats, pages de détail, recherche."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .. import findings as F
from .. import formatting as fmt
from ..collect import ADMIN_SECTIONS
from ..formatting import EMPTY
from ..i18n import _
from ..pages import FINDINGS, SOURCE_LABELS, build_page, search
from . import model, theme
from .boardmap import BoardMap
from .dimm import DimmStick, RouteTrace
from .widgets import CopyTable, Led, Responsive, TraceMeter, card, hbox, icon, label, separator


def column(spacing: int = 24) -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    widget.setObjectName("inner")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    return widget, layout


def heading(eyebrow: str, title: str, sub: str = "") -> QWidget:
    widget, layout = column(6)
    layout.addWidget(label(eyebrow.upper(), "eyebrow"))
    layout.addSpacing(4)
    title_label = label(title, "h1", wrap=True, selectable=True)
    layout.addWidget(title_label)
    if sub:
        layout.addWidget(label(sub, "sub", wrap=True))
    return widget


def welcome(win) -> QWidget:
    """Accueil hors Windows : Atlas PC Monitor y sert de visionneuse de rapports."""
    widget, layout = column(18)
    layout.addWidget(
        heading(
            _("Visionneuse"),
            _("Ouvrir un rapport Atlas PC Monitor"),
            _(
                "L'inventaire matériel se fait sous Windows. Ici, Atlas PC Monitor affiche, compare et imprime"
                " les rapports JSON faits sur des PC Windows."
            ),
        )
    )
    box, inner = card(spacing=10)
    steps = (
        _("Sur le PC Windows : bouton « Exporter le rapport » au format JSON, ou AtlasPCMonitor.exe --json -o rapport.json."),
        _("Ici : bouton ci-dessous, Ctrl+O, ou glisser le fichier .json sur la fenêtre."),
        _("Constats, fiche d'intervention, mode partage et comparaison fonctionnent comme sous Windows."),
    )
    for number, text in enumerate(steps, 1):
        inner.addWidget(label(f"{number}.  {text}", "dim", wrap=True))
    inner.addSpacing(6)
    button = QPushButton(_("Ouvrir un rapport"))
    button.setProperty("kind", "primary")
    button.setIcon(icon("open", theme.P.primary_text))
    button.clicked.connect(lambda: win.open_report())
    inner.addWidget(button, 0, Qt.AlignLeft)
    layout.addWidget(box)
    return widget


def stamp(data: dict) -> str:
    return fmt.fmt_stamp(data.get("captured_at")).replace(" ", _(" à "), 1)


def legend(level: str, text: str, off: bool = False) -> QWidget:
    return hbox(Led(level, 9, off=off), label(text.upper(), "mono"), spacing=4)


def link_button(text: str, slot) -> QPushButton:
    button = QPushButton(text.upper())
    button.setProperty("kind", "link")
    button.setIcon(icon("arrow", theme.P.link, 14))
    button.setLayoutDirection(Qt.RightToLeft)
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(slot)
    button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return button


def note(text: str, role: str = "note") -> QLabel:
    return label(text, role, wrap=True)


# ====================================================================== vue d'ensemble


def overview(win) -> QWidget:
    data, found = win.shown, win.findings
    page, layout = column()
    host = data.get("system") or {}
    machine = data.get("machine") or {}
    system = data.get("os") or {}
    who = " ".join(
        p for p in (fmt.clean(machine.get("Manufacturer")), fmt.clean(machine.get("SystemFamily") or machine.get("Model"))) if p != EMPTY
    )
    windows = " ".join(p for p in (fmt.clean(system.get("Caption")), fmt.clean(system.get("DisplayVersion"))) if p != EMPTY)
    sub = " · ".join(p for p in (who, windows or host.get("platform", ""), fmt.clean(system.get("OSArchitecture"))) if p and p != EMPTY)
    layout.addWidget(heading(_("Vue d'ensemble · inventaire du {0}", stamp(data)), host.get("computer", ""), sub))

    layout.addWidget(Responsive([_findings_card(win, found), _memory_card(data)], ((700, 2), (0, 1))))

    if data.get("os"):
        section, sl = column(14)
        legend_row = hbox(legend("ok", _("OK")), legend("watch", _("À surveiller")), legend("fix", _("À corriger")), spacing=16)
        titles, tl = column(6)
        tl.addWidget(label(_("PLAN DE LA CARTE"), "eyebrow"))
        tl.addWidget(label(_("Composants détectés"), "h2"))
        legend_box = hbox(None, legend_row)
        sl.addWidget(Responsive([titles, legend_box], ((620, 2), (0, 1)), spacing=8))
        frame, fl = card("map", (12, 12, 12, 12))
        board = BoardMap(model.board_chips(data, found), model.board_labels(data))
        board.pageRequested.connect(win.open_page)
        fl.addWidget(board)
        sl.addWidget(frame)
        sl.addWidget(
            label(_("Chaque piste prend la couleur de l'état de son composant. Cliquer une puce ouvre sa page."), "small", wrap=True)
        )
        layout.addWidget(section)

    errors = data.get("errors") or {}
    if errors:
        names = sorted({_(SOURCE_LABELS.get(key, key)) for key in errors})
        hint = "" if data.get("admin") else _(" Certaines exigent une session administrateur.")
        layout.addWidget(note(_("Sources indisponibles : {0}.{1} Le détail figure sur chaque page.", ", ".join(names), hint)))
    if data.get("note"):
        layout.addWidget(note(data["note"]))
    layout.addStretch(1)
    return page


def _findings_card(win, found) -> QFrame:
    frame, layout = card("result")
    layout.addWidget(label(_("BANC DE TEST · CONSTATS"), "eyebrow"))
    counts = F.summary(found)
    big = F.summary_text(found) if found else _("Diagnostic indisponible")
    level = F.FIX if counts[F.FIX] else F.WATCH if counts[F.WATCH] else F.OK
    big_label = label(big, "big", wrap=True)
    if level != F.WATCH:
        big_label.setProperty("level", level)
    layout.addWidget(big_label)
    row = hbox(
        legend(F.FIX, _("{0} à corriger", counts[F.FIX]), off=not counts[F.FIX]),
        legend(F.WATCH, _("{0} à surveiller", counts[F.WATCH]), off=not counts[F.WATCH]),
        legend(F.INFO, _("{0} à noter", counts[F.INFO])),
        legend(F.OK, _("{0} OK", counts[F.OK]), off=not counts[F.OK]),
        None,
        spacing=14,
    )
    layout.addWidget(row)
    urgent = [item.title for item in found if item.level in (F.FIX, F.WATCH)][:3]
    if urgent:
        layout.addWidget(label(" · ".join(urgent), "dim", wrap=True))
    layout.addWidget(link_button(_("Voir les constats"), lambda: win.open_page(FINDINGS)), 0, Qt.AlignLeft)
    layout.addStretch(1)
    return frame


def _memory_card(data: dict) -> QFrame:
    memory = data.get("memory") or {}
    frame, layout = card("result")
    layout.addWidget(label(_("MÉMOIRE UTILISÉE"), "eyebrow"))
    percent = memory.get("percent")
    layout.addWidget(label(fmt.fmt_percent(percent), "bigger"))
    layout.addWidget(TraceMeter(percent))
    if memory:
        used, total, free = (fmt.fmt_binary(memory.get(key)) for key in ("used", "total", "free"))
        text = _('<span style="color:{0}">{1}</span> utilisés sur {2} · {3} disponibles', theme.P.silk, used, total, free)
        layout.addWidget(label(text, "dim", wrap=True, rich=True))
    layout.addStretch(1)
    return frame


# ====================================================================== constats


def findings_page(win) -> QWidget:
    data, found = win.shown, win.findings
    counts = F.summary(found)
    page, layout = column(22)
    if counts[F.FIX]:
        title = _("{0} point(s) à corriger", counts[F.FIX])
    elif counts[F.WATCH]:
        title = _("{0} point(s) à surveiller", counts[F.WATCH])
    else:
        title = _("Rien à corriger") if found else _("Constats indisponibles")
    sub = _("Diagnostic automatique de l'inventaire.")
    if found and not data.get("admin") and any(k in (data.get("errors") or {}) for k in ADMIN_SECTIONS):
        sub += _(" L'inventaire a été lu sans droits administrateur : quelques sources manquent.")
    if not found:
        sub = _("L'inventaire Windows n'a pas pu être lu.")
    layout.addWidget(heading(_("Constats · banc de test du {0}", stamp(data)), title, sub))

    counters = []
    for level in (F.FIX, F.WATCH, F.INFO, F.OK):
        frame, fl = card(level, (20, 16, 20, 18), 10)
        fl.addWidget(
            hbox(
                Led(level, 10, off=not counts[level] and level != F.INFO), label(_(F.LEVELS[level]).upper(), "eyebrowDim"), None, spacing=4
            )
        )
        number = label(str(counts[level]), "counter")
        number.setProperty("level", level if counts[level] else "off")
        fl.addWidget(number)
        counters.append(frame)
    layout.addWidget(Responsive(counters, ((680, 4), (0, 2)), spacing=16))

    left, ll = column(12)
    for level in (F.FIX, F.WATCH, F.INFO):
        items = [item for item in found if item.level == level]
        if not items:
            continue
        group = label(f"{_(F.LEVELS[level]).upper()} ({len(items)})", "level")
        group.setProperty("level", level)
        ll.addSpacing(6)
        ll.addWidget(group)
        for item in items:
            ll.addWidget(_finding_card(win, item))
    oks = [item for item in found if item.level == F.OK]
    if oks:
        group = label(_("OK ({0})", len(oks)), "level")
        group.setProperty("level", F.OK)
        ll.addSpacing(6)
        ll.addWidget(group)
        chips = []
        for item in oks:
            frame, fl = card("true", (14, 12, 16, 12), 10)
            fl.addWidget(
                hbox(
                    Led(F.OK, 10),
                    label(item.title, "body", wrap=True),
                    label(model.DESIGNATORS.get(item.page, ""), "mono"),
                    spacing=8,
                    stretch_at=1,
                )
            )
            frame.setToolTip(item.detail)
            chips.append(frame)
        ll.addWidget(Responsive(chips, ((640, 3), (0, 1)), spacing=10))
    ll.addStretch(1)
    aside = _fiche_aside(win)
    holder, hl = column(0)
    hl.addWidget(aside)
    hl.addStretch(1)
    layout.addWidget(Responsive([left, holder], ((900, 2), (0, 1)), spacing=24, stretches=(1, 0)))
    return page


class _RingLed(QWidget):
    def __init__(self, level: str):
        super().__init__()
        self.level = level
        self.setFixedSize(36, 36)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(Led(level, 14), 0, Qt.AlignCenter)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(theme.qcolor(theme.level_color(self.level)), 1.5))
        painter.drawEllipse(QPointF(18, 18), 16, 16)


def _finding_card(win, item: F.Finding) -> QFrame:
    frame, layout = card("true", (20, 18, 20, 18), 0)
    row = QHBoxLayout()
    row.setSpacing(18)
    row.addWidget(_RingLed(item.level), 0, Qt.AlignTop)
    text, tl = column(6)
    topic = f'<span style="color:{theme.P.dim}; font-weight:400"> · {escape(_(item.topic).upper())}</span>'
    tag = label(escape(item.label.upper()) + topic, "level", rich=True)
    tag.setProperty("level", item.level)
    top = QHBoxLayout()
    top.addWidget(tag)
    top.addStretch(1)
    if item.page:
        top.addWidget(link_button(_(item.page), lambda checked=False, page=item.page: win.open_page(page)))
    tl.addLayout(top)
    tl.addWidget(label(item.title, "h3", wrap=True, selectable=True))
    if item.detail:
        tl.addWidget(label(item.detail, "body", wrap=True, selectable=True))
    if item.advice:
        tl.addWidget(label(f'<span style="color:{theme.P.link}">→</span> {escape(item.advice)}', "dim", wrap=True, rich=True))
    row.addWidget(text, 1)
    layout.addLayout(row)
    text_copy = "\n".join(filter(None, [f"[{item.label}] {item.title}", item.detail, item.advice and f"→ {item.advice}"]))
    frame.setContextMenuPolicy(Qt.CustomContextMenu)
    frame.customContextMenuRequested.connect(lambda pos, f=frame, t=text_copy: win.copy_menu(f, pos, t))
    return frame


def _fiche_aside(win) -> QFrame:
    frame, layout = card("result")
    frame.setMinimumWidth(270)
    frame.setMaximumWidth(320)
    layout.addWidget(label(_("FICHE D'INTERVENTION"), "eyebrow"))
    layout.addWidget(label(_("Les points à surveiller et à corriger, avec leurs conseils, partent sur la fiche A4."), "body", wrap=True))
    button = QPushButton(_("Préparer la fiche"))
    button.setProperty("kind", "primary")
    button.setIcon(icon("print", theme.P.primary_text))
    button.clicked.connect(win.open_fiche)
    layout.addWidget(button)
    layout.addWidget(separator())
    thresholds = "\n".join(
        [
            _("SEUILS · atlas/findings.py"),
            _("usure SSD ≥ {0} %", F.DISK_WEAR_FIX),
            _("volume libre < {0} %", F.VOLUME_FREE_WATCH),
            _("usure batterie ≥ {0} %", F.BATTERY_WEAR_WATCH),
            _("pilote graphique > 1 an"),
            _("sans redémarrage ≥ {0} j", F.UPTIME_WATCH_DAYS),
        ]
    )
    layout.addWidget(label(thresholds, "mono"))
    return frame


# ====================================================================== pages de détail


def detail_page(win, page_name: str) -> QWidget:
    data = win.shown
    page, layout = column(22)
    title, sub = model.page_heading(data, page_name)
    layout.addWidget(heading(f"{model.DESIGNATORS.get(page_name, '')} · {_(page_name)}", title, sub))
    sections = build_page(data, page_name)
    if page_name == "Mémoire" and data.get("ram"):
        _memory_extras(win, layout)
        shown_apart = (_("Synthèse"), _("Évolution possible"))  # déjà dessinés au-dessus
        sections = [s for s in sections if s.title not in shown_apart and not s.title.startswith(_("Barrette"))]
    for section in sections:
        layout.addWidget(section_card(win, section))
    if data.get("note"):
        layout.addWidget(note(data["note"]))
    layout.addStretch(1)
    return page


def section_card(win, section) -> QFrame:
    frame, layout = card("true", (8, 18, 8, 12), 8)
    layout.addWidget(hbox(label(section.title.upper(), "eyebrow"), margins=(14, 0, 14, 4)))
    if section.rows:
        table = CopyTable([_("Propriété"), _("Valeur")], [(row.label, row.value) for row in section.rows])
        table.copied.connect(win.flash)
        layout.addWidget(table)
    if section.note or not section.rows:
        layout.addWidget(
            hbox(
                note(section.note or _("Aucune information détectée."), "note" if section.note else "dim"),
                margins=(14, 0, 14, 4),
                stretch_at=0,
            )
        )
    if section.tip:
        layout.addWidget(hbox(note(section.tip, "small"), margins=(14, 4, 14, 4), stretch_at=0))
    return frame


def _stat(title: str, value: str, sub: str) -> QFrame:
    frame, layout = card("true", (18, 16, 18, 16), 6)
    layout.addWidget(label(title.upper(), "eyebrowDim"))
    layout.addWidget(label(value, "stat"))
    layout.addWidget(label(sub, "small", wrap=True))
    return frame


def _memory_extras(win, layout: QVBoxLayout) -> None:
    data = win.shown
    memory = data.get("memory") or {}
    max_kb = fmt.to_number((data.get("memoryarray") or {}).get("MaxCapacity"))
    stats = [
        (_("Installée"), fmt.fmt_binary(memory.get("installed")), _("{0} barrette(s)", len(data.get("ram") or []))),
        (_("Utilisable"), fmt.fmt_binary(memory.get("total")), _("vue par Windows")),
        (_("Utilisée"), fmt.fmt_binary(memory.get("used")), _("{0} au moment de l'analyse", fmt.fmt_percent(memory.get("percent")))),
        (_("Max. déclaré"), fmt.fmt_binary(max_kb * 1024) if max_kb else EMPTY, _("par la carte mère")),
    ]
    layout.addWidget(Responsive([_stat(*item) for item in stats], ((680, 4), (0, 2)), spacing=14))

    frame, fl = card("true", (24, 22, 24, 22), 20)
    titles, tl = column(6)
    tl.addWidget(label(_("EMPLACEMENTS"), "eyebrow"))
    tl.addWidget(label(_("Barrettes installées"), "h2"))
    top = QHBoxLayout()
    top.addWidget(titles)
    top.addStretch(1)
    top.addWidget(label(_("vue de face · échelle indicative"), "mono"), 0, Qt.AlignBottom)
    fl.addLayout(top)
    for view in model.stick_views(data):
        block, bl = column(10)
        tag = label(_("DÉPAREILLÉE") if view.odd else _("RÉFÉRENCE"), "tag" if view.odd else "tagOk")
        bl.addWidget(hbox(label(view.slot, "monoStrong"), label(view.bank, "mono"), tag, None, spacing=10))
        bl.addWidget(DimmStick(_("Barrette {0}", view.slot)))
        bl.addWidget(label(view.spec, "mono", wrap=True, selectable=True))
        fl.addWidget(block)
    layout.addWidget(frame)

    pair = []
    routes = model.upgrade_routes(data)
    if routes:
        advice, items = routes
        frame, fl = card("result", (22, 20, 22, 20), 10)
        fl.addWidget(label(_("CONSEILLER D'ÉVOLUTION"), "eyebrow"))
        fl.addWidget(label(_("Évolution possible"), "h3"))
        if advice.upgradable:
            fl.addWidget(
                label(
                    _(
                        'Barrettes à acheter : <span style="color:{0}; font-family:{1}">{2}</span>',
                        theme.P.silk,
                        theme.MONO,
                        escape(advice.spec),
                    ),
                    "dim",
                    wrap=True,
                    rich=True,
                )
            )
            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(4)
            for index, (start, target, action) in enumerate(items):
                grid.addWidget(label(start, "mono"), index * 2, 0)
                grid.addWidget(RouteTrace(), index * 2, 1)
                big = label(target, "big")
                big.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                grid.addWidget(big, index * 2, 2)
                grid.addWidget(label(action, "body", wrap=True), index * 2 + 1, 1, 1, 2)
            grid.setColumnStretch(1, 1)
            fl.addSpacing(8)
            fl.addLayout(grid)
        fl.addSpacing(6)
        fl.addWidget(separator())
        fl.addWidget(label(" ".join(advice.notes), "small", wrap=True))
        fl.addStretch(1)
        pair.append(frame)
    headers, rows = model.stick_table(data)
    frame, fl = card("true", (8, 20, 8, 12), 8)
    fl.addWidget(hbox(label(_("DÉTAIL PAR BARRETTE"), "eyebrow"), margins=(14, 0, 14, 4)))
    table = CopyTable(headers, rows, show_header=True)
    table.copied.connect(win.flash)
    fl.addWidget(table)
    fl.addStretch(1)
    pair.append(frame)
    layout.addWidget(Responsive(pair, ((820, 2), (0, 1))))


# ====================================================================== recherche


def search_page(win, query: str) -> QWidget:
    data = win.shown
    hits = search(data, query) if data else []
    page, layout = column(18)
    layout.addWidget(
        heading(
            _("Recherche"),
            _("{0} résultat(s) pour « {1} »", len(hits), query),
            _("Recherche dans toutes les pages, sans tenir compte des accents. Échap pour revenir."),
        )
    )
    if hits:
        frame, fl = card("true", (8, 12, 8, 12), 0)
        table = CopyTable(
            [_("Emplacement"), _("Propriété"), _("Valeur")],
            [(f"{_(p)} › {s}", row.label, row.value) for p, s, row in hits],
            show_header=True,
        )
        table.copied.connect(win.flash)
        fl.addWidget(table)
        layout.addWidget(frame)
    layout.addStretch(1)
    return page
