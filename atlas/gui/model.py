"""Ce que les écrans affichent, calculé sans Qt (donc testable seul) à partir de l'inventaire.

What the screens display, computed from the inventory without Qt (so it can be tested on its own).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import formatting as f
from ..findings import FIX, WATCH, Finding, battery_wear
from ..formatting import EMPTY
from ..i18n import _, is_english
from ..upgrade import gib_text, memory_advice

# Repères de sérigraphie de la navigation (comme sur une vraie carte électronique).
# Silkscreen markings of the navigation (as on a real circuit board).
DESIGNATORS = {
    "Vue d'ensemble": "TOP", "Constats": "TP", "Système": "U0", "Processeur": "U1", "Mémoire": "J1", "Carte mère": "PCB",
    "Graphiques": "U2", "Stockage": "J2", "Réseau": "J3", "Audio": "LS1", "Batterie": "BT1",
}  # fmt: skip


def worst(found: list[Finding], *topics: str, page: str = "") -> str:
    """Niveau à afficher pour un composant (constats d'un thème, ou d'une page) : à corriger, à surveiller, sinon OK.

    Level to display for a component (findings of a topic, or of a page): to fix, to watch, otherwise OK.
    """
    levels = {item.level for item in found if item.topic in topics or (page and item.page == page)}
    return FIX if FIX in levels else WATCH if WATCH in levels else "ok"


def first_issue(found: list[Finding], *topics: str) -> str:
    for item in found:
        if item.topic in topics and item.level in (FIX, WATCH):
            return item.title
    return ""


@dataclass
class Chip:
    key: str
    designator: str
    title: str
    lines: list[str] = field(default_factory=list)
    issue: str = ""
    level: str | None = "ok"  # None : composant absent — None: component missing
    page: str = ""


def _short_gpu(name: str) -> str:
    for prefix in ("NVIDIA GeForce ", "NVIDIA ", "AMD Radeon ", "Intel(R) ", "Intel "):
        if name.startswith(prefix):
            return name[len(prefix) :].replace(" GPU", "")
    return name


def _short_nic(text: str) -> str:
    return text.replace("Intel(R) ", "").replace("(R)", "").replace("Realtek ", "").replace(" Network Adapter", "").strip()


def board_chips(data: dict, found: list[Finding]) -> dict[str, Chip]:
    """Les puces du plan de carte de la vue d'ensemble.

    The chips of the board map on the overview.
    """
    chips: dict[str, Chip] = {}
    memory = data.get("memory") or {}
    sticks = data.get("ram") or []
    types, forms = f.memory_types(sticks), f.memory_forms(sticks)
    sizes = sorted({f.fmt_binary(s.get("Capacity")) for s in sticks})
    layout = _("{0} × {1}", len(sticks), sizes[0]) if len(sizes) == 1 and sticks else _("{0} barrette(s)", len(sticks))
    chips["ram"] = Chip("ram", _("J1 · MÉMOIRE"), " ".join([f.fmt_binary(memory.get("installed")), *types[:1]]),
                        [" ".join([layout, *forms[:1]])] if sticks else [], first_issue(found, "Mémoire"),
                        worst(found, "Mémoire") if sticks else None, "Mémoire")  # fmt: skip

    disks = data.get("disks") or []
    total = sum(f.to_number(d.get("Size")) or 0 for d in disks)
    kinds = []
    for disk in disks:
        kind = f.fmt_media(disk.get("MediaType")) if disk.get("MediaType") not in (None, "") else _("Disque")
        kind = {_("Disque dur (HDD)"): "HDD", _("Non précisé"): _("Disque")}.get(kind, kind)
        kinds.append(f"{kind} {f.fmt_decimal(disk.get('Size'))}")
    chips["disks"] = Chip("disks", _("J2 · STOCKAGE"), f.fmt_decimal(total) if total else EMPTY, [" + ".join(kinds[:2])] if kinds else [],
                          first_issue(found, "Stockage"), worst(found, "Stockage") if disks else None, "Stockage")  # fmt: skip

    gpus = data.get("gpu") or []
    if gpus:
        from ..pages import vram_text

        gpu = gpus[0]
        sub = " · ".join(
            x
            for x in (vram_text(gpu), _("pilote du {0}", f.fmt_date(gpu.get("DriverDate"))) if gpu.get("DriverDate") else "")
            if x and x != EMPTY
        )
        level = worst(found, page="Graphiques")
        chips["gpu"] = Chip(
            "gpu", _("U2 · GRAPHIQUES"), _short_gpu(f.clean(gpu.get("Name"))), [sub] if sub else [], "", level, "Graphiques"
        )
    else:
        chips["gpu"] = Chip("gpu", _("U2 · GRAPHIQUES"), _("Non détectée"), [], "", None, "Graphiques")

    adapters = data.get("adapters") or []
    up = [a for a in adapters if str(a.get("Status") or "").lower() == "up"]
    nic = (up or adapters or [{}])[0]
    if adapters:
        state = _("connecté") if up else _("déconnecté")
        speed = f.clean(nic.get("LinkSpeed")).replace("bps", "b/s")
        speed = speed if is_english() else speed.replace(".", ",")
        line = " · ".join(x for x in (speed if up else "", state) if x and x != EMPTY)
        title = _short_nic(f.clean(nic.get("InterfaceDescription") or nic.get("Name")))
        chips["net"] = Chip("net", _("J3 · RÉSEAU"), title, [line], "", "ok" if up else None, "Réseau")
    else:
        chips["net"] = Chip("net", _("J3 · RÉSEAU"), _("Non détecté"), [], "", None, "Réseau")

    batteries = data.get("battery") or []
    if batteries:
        battery = batteries[0]
        wear = battery_wear(battery)
        parts = [f.fmt_percent(battery.get("Charge")), _("usure {0} %", round(wear)) if wear is not None else EMPTY]
        chips["battery"] = Chip(
            "battery", _("BT1 · BATTERIE"), " · ".join(p for p in parts if p != EMPTY), [], "", worst(found, "Batterie"), "Batterie"
        )
    else:
        chips["battery"] = Chip("battery", _("BT1 · BATTERIE"), _("Sur secteur") if data.get("os") else EMPTY, [], "", None, "Batterie")

    bios = data.get("bios") or {}
    chips["bios"] = Chip("bios", _("U3 · BIOS"), f.clean(bios.get("Version")), [], "", "ok" if bios else None, "Carte mère")

    cpu = (data.get("cpu") or [{}])[0]
    name = f.clean(cpu.get("Name")).replace(" with Radeon Graphics", "").replace("(R)", "").replace("(TM)", "").replace(" Processor", "")
    cores, threads = cpu.get("NumberOfCores"), cpu.get("NumberOfLogicalProcessors")
    lines = []
    if cores:
        lines.append(_("{0} cœurs · {1} threads", cores, threads) if threads else _("{0} cœurs", cores))
    if f.to_number(cpu.get("MaxClockSpeed")):
        lines.append(_("{0} max.", f.fmt_mhz(cpu.get("MaxClockSpeed"))))
    chips["cpu"] = Chip("cpu", _("U1 · PROCESSEUR"), name, lines, "", "ok" if cpu else None, "Processeur")
    return chips


def board_labels(data: dict) -> tuple[str, str]:
    board = data.get("board") or {}
    left = " ".join(p for p in (f.clean(board.get("Manufacturer")), f.clean(board.get("Product"))) if p != EMPTY)
    right = f.clean(board.get("Version"))
    return (f"PCB · {left}" if left else "PCB"), (f"REV {right}" if right != EMPTY else "")


def page_heading(data: dict, page: str) -> tuple[str, str]:
    """Titre et sous-titre d'une page de détail.

    Title and subtitle of a detail page.
    """
    machine = data.get("machine") or {}
    system = data.get("os") or {}
    host = data.get("system") or {}
    title, sub = _(page), ""
    if page == "Système":
        title = " ".join(p for p in (f.clean(machine.get("Manufacturer")), f.clean(machine.get("Model"))) if p != EMPTY) or f.clean(
            host.get("computer")
        )
        sub = " · ".join(p for p in (f.clean(system.get("Caption")), f.clean(system.get("DisplayVersion"))) if p != EMPTY) or f.clean(
            host.get("platform")
        )
    elif page == "Processeur":
        cpu = (data.get("cpu") or [{}])[0]
        title = f.clean(cpu.get("Name"))
        sub = _("{0} cœurs · {1} threads", cpu.get("NumberOfCores", "?"), cpu.get("NumberOfLogicalProcessors", "?")) if cpu else ""
    elif page == "Mémoire":
        sticks = data.get("ram") or []
        title = " ".join([board_chips(data, [])["ram"].title, *f.memory_forms(sticks)[:1]])
        slots = f.to_number((data.get("memoryarray") or {}).get("MemoryDevices"))
        n = len(sticks)
        sub = _("{0} emplacement(s) sur {1} occupé(s)", n, int(slots)) if slots else _("{0} barrette(s)", n)
    elif page == "Carte mère":
        board = data.get("board") or {}
        title = " ".join(p for p in (f.clean(board.get("Manufacturer")), f.clean(board.get("Product"))) if p != EMPTY) or _(page)
        sub = f"BIOS {f.clean((data.get('bios') or {}).get('Version'))}"
    elif page == "Graphiques":
        gpus = data.get("gpu") or []
        title = f.clean(gpus[0].get("Name")) if gpus else _(page)
        sub = _("{0} adaptateur(s) · {1} écran(s)", len(gpus), len(data.get("monitors") or []))
    elif page == "Stockage":
        chip = board_chips(data, [])["disks"]
        title = _("{0} de stockage", chip.title) if chip.title != EMPTY else _(page)
        sub = _("{0} disque(s) · {1} volume(s)", len(data.get("disks") or []), len(data.get("volumes") or []))
    elif page == "Réseau":
        title = board_chips(data, [])["net"].title
        sub = _("{0} carte(s) réseau", len(data.get("adapters") or []))
    elif page == "Audio":
        n = len(data.get("audio") or [])
        title, sub = (_("{0} périphérique(s) audio", n) if n else _(page)), ""
    elif page == "Batterie":
        title = board_chips(data, [])["battery"].title
    if not title or title == EMPTY:
        title = _(page)
    return title, ("" if sub == EMPTY else sub)


@dataclass
class StickView:
    slot: str
    bank: str
    spec: str
    odd: bool  # différente de la première barrette — different from the first module


def stick_views(data: dict) -> list[StickView]:
    sticks = [s for s in data.get("ram") or [] if isinstance(s, dict)]
    if not sticks:
        return []
    ref = (str(sticks[0].get("PartNumber") or "").strip().upper(), f.to_number(sticks[0].get("Capacity")))
    views = []
    for stick in sticks:
        rated, configured = f.to_number(stick.get("Speed")), f.to_number(stick.get("ConfiguredClockSpeed"))
        speed = f.fmt_mts(rated)
        if configured and rated and configured != rated:
            speed = _("{0} annoncés, {1} configurés", f.fmt_mts(rated), f.fmt_mts(configured))
        parts = [f.clean(stick.get("Manufacturer")), f.clean(stick.get("PartNumber")), f.fmt_binary(stick.get("Capacity")), speed]
        mine = (str(stick.get("PartNumber") or "").strip().upper(), f.to_number(stick.get("Capacity")))
        views.append(StickView(f.clean(stick.get("DeviceLocator")), f.clean(stick.get("BankLabel")),
                               " · ".join(p for p in parts if p and p != EMPTY), mine != ref))  # fmt: skip
    return views


def stick_table(data: dict) -> tuple[list[str], list[tuple]]:
    """Comparatif des barrettes : une colonne par barrette.

    Module comparison: one column per module.
    """
    sticks = [s for s in data.get("ram") or [] if isinstance(s, dict)]
    headers = [_("Propriété"), *[f.clean(s.get("DeviceLocator")) for s in sticks]]
    spec = [
        (_("Type"), lambda s: f.fmt_memory_type(s.get("SMBIOSMemoryType"))),
        (_("Format"), lambda s: f.fmt_code(s.get("FormFactor"), f.FORM_FACTORS) if f.to_number(s.get("FormFactor")) else EMPTY),
        (_("Capacité"), lambda s: f.fmt_binary(s.get("Capacity"))),
        (_("Vitesse nominale"), lambda s: f.fmt_mts(s.get("Speed"))),
        (_("Vitesse configurée"), lambda s: f.fmt_mts(s.get("ConfiguredClockSpeed"))),
        (_("Fabricant"), lambda s: f.clean(s.get("Manufacturer"))),
        (_("Référence"), lambda s: f.clean(s.get("PartNumber"))),
        (_("Numéro de série"), lambda s: f.clean(s.get("SerialNumber"))),
        (_("Banque"), lambda s: f.clean(s.get("BankLabel"))),
    ]
    rows = [(label, *[get(s) for s in sticks]) for label, get in spec]
    return headers, [row for row in rows if any(v != EMPTY for v in row[1:])]


def upgrade_routes(data: dict):
    """(conseil, [(départ, cible, action)]) pour le conseiller d'évolution, ou None.

    (advice, [(start, target, action)]) for the upgrade advisor, or None.
    """
    advice = memory_advice(data)
    if not advice:
        return None
    start = gib_text(advice.installed_gib)
    return advice, [(start, gib_text(goal), way[:1].upper() + way[1:]) for goal, way in advice.options]
