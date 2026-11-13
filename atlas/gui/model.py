"""Ce que les écrans affichent, calculé sans Qt (donc testable seul) à partir de l'inventaire."""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import formatting as f
from ..findings import FIX, WATCH, Finding, battery_wear
from ..formatting import EMPTY
from ..upgrade import memory_advice

# Repères de sérigraphie de la navigation (comme sur une vraie carte électronique).
DESIGNATORS = {
    "Vue d'ensemble": "TOP", "Constats": "TP", "Système": "U0", "Processeur": "U1", "Mémoire": "J1", "Carte mère": "PCB",
    "Graphiques": "U2", "Stockage": "J2", "Réseau": "J3", "Audio": "LS1", "Batterie": "BT1",
}  # fmt: skip


def worst(found: list[Finding], *topics: str, page: str = "") -> str:
    """Niveau à afficher pour un composant (constats d'un thème, ou d'une page) : à corriger, à surveiller, sinon OK."""
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
    level: str | None = "ok"  # None : composant absent
    page: str = ""


def _short_gpu(name: str) -> str:
    for prefix in ("NVIDIA GeForce ", "NVIDIA ", "AMD Radeon ", "Intel(R) ", "Intel "):
        if name.startswith(prefix):
            return name[len(prefix) :].replace(" GPU", "")
    return name


def _short_nic(text: str) -> str:
    return text.replace("Intel(R) ", "").replace("(R)", "").replace("Realtek ", "").replace(" Network Adapter", "").strip()


def board_chips(data: dict, found: list[Finding]) -> dict[str, Chip]:
    """Les puces du plan de carte de la vue d'ensemble."""
    chips: dict[str, Chip] = {}
    memory = data.get("memory") or {}
    sticks = data.get("ram") or []
    types, forms = f.memory_types(sticks), f.memory_forms(sticks)
    sizes = sorted({f.fmt_binary(s.get("Capacity")) for s in sticks})
    layout = f"{len(sticks)} × {sizes[0]}" if len(sizes) == 1 and sticks else f"{len(sticks)} barrette(s)"
    chips["ram"] = Chip("ram", "J1 · MÉMOIRE", " ".join([f.fmt_binary(memory.get("installed")), *types[:1]]),
                        [" ".join([layout, *forms[:1]])] if sticks else [], first_issue(found, "Mémoire"),
                        worst(found, "Mémoire") if sticks else None, "Mémoire")  # fmt: skip

    disks = data.get("disks") or []
    total = sum(f.to_number(d.get("Size")) or 0 for d in disks)
    kinds = []
    for disk in disks:
        kind = f.fmt_media(disk.get("MediaType")) if disk.get("MediaType") not in (None, "") else "Disque"
        kind = {"Disque dur (HDD)": "HDD", "Non précisé": "Disque"}.get(kind, kind)
        kinds.append(f"{kind} {f.fmt_decimal(disk.get('Size'))}")
    chips["disks"] = Chip("disks", "J2 · STOCKAGE", f.fmt_decimal(total) if total else EMPTY, [" + ".join(kinds[:2])] if kinds else [],
                          first_issue(found, "Stockage"), worst(found, "Stockage") if disks else None, "Stockage")  # fmt: skip

    gpus = data.get("gpu") or []
    if gpus:
        from ..pages import vram_text

        gpu = gpus[0]
        sub = " · ".join(
            x
            for x in (vram_text(gpu), f"pilote du {f.fmt_date(gpu.get('DriverDate'))}" if gpu.get("DriverDate") else "")
            if x and x != EMPTY
        )
        level = worst(found, page="Graphiques")
        chips["gpu"] = Chip("gpu", "U2 · GRAPHIQUES", _short_gpu(f.clean(gpu.get("Name"))), [sub] if sub else [], "", level, "Graphiques")
    else:
        chips["gpu"] = Chip("gpu", "U2 · GRAPHIQUES", "Non détectée", [], "", None, "Graphiques")

    adapters = data.get("adapters") or []
    up = [a for a in adapters if str(a.get("Status") or "").lower() == "up"]
    nic = (up or adapters or [{}])[0]
    if adapters:
        state = "connecté" if up else "déconnecté"
        speed = f.clean(nic.get("LinkSpeed")).replace("bps", "b/s").replace(".", ",")
        line = " · ".join(x for x in (speed if up else "", state) if x and x != EMPTY)
        title = _short_nic(f.clean(nic.get("InterfaceDescription") or nic.get("Name")))
        chips["net"] = Chip("net", "J3 · RÉSEAU", title, [line], "", "ok" if up else None, "Réseau")
    else:
        chips["net"] = Chip("net", "J3 · RÉSEAU", "Non détecté", [], "", None, "Réseau")

    batteries = data.get("battery") or []
    if batteries:
        battery = batteries[0]
        wear = battery_wear(battery)
        parts = [f.fmt_percent(battery.get("Charge")), f"usure {round(wear)} %" if wear is not None else EMPTY]
        chips["battery"] = Chip(
            "battery", "BT1 · BATTERIE", " · ".join(p for p in parts if p != EMPTY), [], "", worst(found, "Batterie"), "Batterie"
        )
    else:
        chips["battery"] = Chip("battery", "BT1 · BATTERIE", "Sur secteur" if data.get("os") else EMPTY, [], "", None, "Batterie")

    bios = data.get("bios") or {}
    chips["bios"] = Chip("bios", "U3 · BIOS", f.clean(bios.get("Version")), [], "", "ok" if bios else None, "Carte mère")

    cpu = (data.get("cpu") or [{}])[0]
    name = f.clean(cpu.get("Name")).replace(" with Radeon Graphics", "").replace("(R)", "").replace("(TM)", "").replace(" Processor", "")
    cores, threads = cpu.get("NumberOfCores"), cpu.get("NumberOfLogicalProcessors")
    lines = []
    if cores:
        lines.append(f"{cores} cœurs · {threads} threads" if threads else f"{cores} cœurs")
    if f.to_number(cpu.get("MaxClockSpeed")):
        lines.append(f"{f.fmt_mhz(cpu.get('MaxClockSpeed'))} max.")
    chips["cpu"] = Chip("cpu", "U1 · PROCESSEUR", name, lines, "", "ok" if cpu else None, "Processeur")
    return chips


def board_labels(data: dict) -> tuple[str, str]:
    board = data.get("board") or {}
    left = " ".join(p for p in (f.clean(board.get("Manufacturer")), f.clean(board.get("Product"))) if p != EMPTY)
    right = f.clean(board.get("Version"))
    return (f"PCB · {left}" if left else "PCB"), (f"REV {right}" if right != EMPTY else "")


def page_heading(data: dict, page: str) -> tuple[str, str]:
    """Titre et sous-titre d'une page de détail."""
    machine = data.get("machine") or {}
    system = data.get("os") or {}
    host = data.get("system") or {}
    title, sub = page, ""
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
        sub = f"{cpu.get('NumberOfCores', '?')} cœurs · {cpu.get('NumberOfLogicalProcessors', '?')} threads" if cpu else ""
    elif page == "Mémoire":
        sticks = data.get("ram") or []
        title = " ".join([board_chips(data, [])["ram"].title, *f.memory_forms(sticks)[:1]])
        slots = f.to_number((data.get("memoryarray") or {}).get("MemoryDevices"))
        n = len(sticks)
        sub = f"{n} emplacement(s) sur {int(slots)} occupé(s)" if slots else f"{n} barrette(s)"
    elif page == "Carte mère":
        board = data.get("board") or {}
        title = " ".join(p for p in (f.clean(board.get("Manufacturer")), f.clean(board.get("Product"))) if p != EMPTY) or page
        sub = f"BIOS {f.clean((data.get('bios') or {}).get('Version'))}"
    elif page == "Graphiques":
        gpus = data.get("gpu") or []
        title = f.clean(gpus[0].get("Name")) if gpus else page
        sub = f"{len(gpus)} adaptateur(s) · {len(data.get('monitors') or [])} écran(s)"
    elif page == "Stockage":
        chip = board_chips(data, [])["disks"]
        title = f"{chip.title} de stockage" if chip.title != EMPTY else page
        sub = f"{len(data.get('disks') or [])} disque(s) · {len(data.get('volumes') or [])} volume(s)"
    elif page == "Réseau":
        title = board_chips(data, [])["net"].title
        sub = f"{len(data.get('adapters') or [])} carte(s) réseau"
    elif page == "Audio":
        n = len(data.get("audio") or [])
        title, sub = (f"{n} périphérique(s) audio" if n else page), ""
    elif page == "Batterie":
        title = board_chips(data, [])["battery"].title
    if not title or title == EMPTY:
        title = page
    return title, ("" if sub == EMPTY else sub)


@dataclass
class StickView:
    slot: str
    bank: str
    spec: str
    odd: bool  # différente de la première barrette


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
            speed = f"{f.fmt_mts(rated)} annoncés, {f.fmt_mts(configured)} configurés"
        parts = [f.clean(stick.get("Manufacturer")), f.clean(stick.get("PartNumber")), f.fmt_binary(stick.get("Capacity")), speed]
        mine = (str(stick.get("PartNumber") or "").strip().upper(), f.to_number(stick.get("Capacity")))
        views.append(StickView(f.clean(stick.get("DeviceLocator")), f.clean(stick.get("BankLabel")),
                               " · ".join(p for p in parts if p and p != EMPTY), mine != ref))  # fmt: skip
    return views


def stick_table(data: dict) -> tuple[list[str], list[tuple]]:
    """Comparatif des barrettes : une colonne par barrette."""
    sticks = [s for s in data.get("ram") or [] if isinstance(s, dict)]
    headers = ["Propriété", *[f.clean(s.get("DeviceLocator")) for s in sticks]]
    spec = [
        ("Type", lambda s: f.fmt_code(s.get("SMBIOSMemoryType"), f.MEMORY_TYPES) if f.to_number(s.get("SMBIOSMemoryType")) else EMPTY),
        ("Format", lambda s: f.fmt_code(s.get("FormFactor"), f.FORM_FACTORS) if f.to_number(s.get("FormFactor")) else EMPTY),
        ("Capacité", lambda s: f.fmt_binary(s.get("Capacity"))),
        ("Vitesse nominale", lambda s: f.fmt_mts(s.get("Speed"))),
        ("Vitesse configurée", lambda s: f.fmt_mts(s.get("ConfiguredClockSpeed"))),
        ("Fabricant", lambda s: f.clean(s.get("Manufacturer"))),
        ("Référence", lambda s: f.clean(s.get("PartNumber"))),
        ("Numéro de série", lambda s: f.clean(s.get("SerialNumber"))),
        ("Banque", lambda s: f.clean(s.get("BankLabel"))),
    ]
    rows = [(label, *[get(s) for s in sticks]) for label, get in spec]
    return headers, [row for row in rows if any(v != EMPTY for v in row[1:])]


def upgrade_routes(data: dict):
    """(conseil, [(départ, cible, action)]) pour le conseiller d'évolution, ou None."""
    advice = memory_advice(data)
    if not advice:
        return None
    start = f"{advice.installed_gib} Go"
    return advice, [(start, goal.replace("Passer à ", ""), way[:1].upper() + way[1:]) for goal, way in advice.options]
