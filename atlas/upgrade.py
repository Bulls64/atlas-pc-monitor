"""Conseiller d'évolution mémoire : ce qu'on peut acheter pour augmenter la RAM.

Module pur. Il s'appuie sur les barrettes installées, le nombre d'emplacements et la
capacité maximale déclarés par le SMBIOS. Ces deux dernières valeurs sont parfois
fausses ou prudentes : chaque conseil le rappelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import formatting as f
from .collect import is_virtual
from .i18n import _

GIB = 1024**3
TARGETS_GIB = (8, 16, 32, 48, 64, 96, 128, 192, 256)

# Tailles de barrette courantes dans le commerce, par type (Go).
STICK_SIZES = {
    "DDR3": (2, 4, 8),
    "DDR4": (4, 8, 16, 32),
    "DDR5": (8, 16, 24, 32, 48, 64),
}
SODIMM_MAX = {"DDR5": 48}  # au-delà, pas de SO-DIMM courante
SOLDERED_TYPES = {"LPDDR", "LPDDR2", "LPDDR3", "LPDDR4", "LPDDR5"}
SOCKETED_FORMS = (8, 12)  # DIMM, SO-DIMM


@dataclass
class MemoryAdvice:
    current: str  # résumé de la configuration actuelle
    spec: str = ""  # barrettes à acheter : type, format, vitesse
    options: list[tuple[int, str]] = field(default_factory=list)  # (capacité visée en Go, comment l'atteindre)
    notes: list[str] = field(default_factory=list)
    upgradable: bool = True
    installed_gib: int = 0


def _gib(stick: dict) -> int:
    value = f.to_number(stick.get("Capacity")) or 0
    return int(round(value / GIB))


def _form(stick: dict) -> int:
    return int(f.to_number(stick.get("FormFactor")) or 0)


def _type(stick: dict) -> str:
    kind = f.fmt_memory_type(stick.get("SMBIOSMemoryType"))
    return kind if kind in f.MEMORY_TYPES.values() else ""


def gib_text(size: int) -> str:
    """Capacité entière en Go (« 16 Go », « 16 GB »)."""
    return _("{0} Go", size)


def _plural(count: int, size: int) -> str:
    return f"{count} × {gib_text(size)}"


def memory_advice(data: dict) -> MemoryAdvice | None:
    """Conseil d'évolution, ou None si l'inventaire mémoire est absent."""
    sticks = [s for s in data.get("ram") or [] if isinstance(s, dict) and _gib(s)]
    if not sticks:
        return None
    array = data.get("memoryarray") or {}
    slots = int(f.to_number(array.get("MemoryDevices")) or 0)
    max_kb = f.to_number(array.get("MaxCapacity"))
    max_gib = int(max_kb * 1024 / GIB) if max_kb else 0
    installed = sum(_gib(s) for s in sticks)

    types = {_type(s) for s in sticks} - {""}
    kind = next(iter(types)) if len(types) == 1 else ""
    forms = {_form(s) for s in sticks}
    socketed = [s for s in sticks if _form(s) in SOCKETED_FORMS]
    socket_forms = {_form(s) for s in socketed} or forms
    form = "SO-DIMM" if socket_forms == {12} else "DIMM" if socket_forms == {8} else ""
    speed = max((int(f.to_number(s.get("Speed")) or 0) for s in sticks), default=0)
    sizes = sorted({_gib(s) for s in sticks})
    layout = " + ".join(_plural(sum(1 for s in sticks if _gib(s) == size), size) for size in sorted(sizes, reverse=True))
    occupancy = _(" ; emplacements occupés : {0} sur {1}", len(sticks), slots) if slots >= len(sticks) else ""
    current = _("{0} installés : {1}{2}.", gib_text(installed), " ".join(p for p in (layout, kind, form) if p), occupancy)
    advice = MemoryAdvice(current, installed_gib=installed)

    if is_virtual(data):
        advice.upgradable = False
        advice.notes.append(_("Machine virtuelle : la mémoire se règle dans l'hyperviseur, pas en achetant des barrettes."))
        return advice
    if kind in SOLDERED_TYPES:
        advice.upgradable = False
        advice.notes.append(_("Mémoire {0} soudée à la carte mère : aucune évolution possible.", kind))
        return advice
    if not socketed and forms - {0}:
        advice.upgradable = False
        advice.notes.append(_("Aucune barrette amovible détectée (format non DIMM/SO-DIMM) : mémoire probablement soudée."))
        return advice
    if len(socketed) < len(sticks):
        soldered = sum(_gib(s) for s in sticks if s not in socketed)
        advice.notes.append(_("{0} semblent soudés à la carte mère : seules les barrettes amovibles se remplacent.", gib_text(soldered)))
    else:
        soldered = 0

    spec = " ".join(p for p in (kind, form, f"{speed} MT/s" if speed else "") if p)
    advice.spec = spec or _("même type et même format que les barrettes actuelles")
    # Un SMBIOS incohérent (moins d'emplacements que de barrettes) : on s'en tient aux barrettes vues.
    usable_slots = max(slots - (len(sticks) - len(socketed)) if slots else 0, len(socketed))
    free = usable_slots - len(socketed)
    available = STICK_SIZES.get(kind, (4, 8, 16, 32))
    if form == "SO-DIMM" and kind in SODIMM_MAX:
        available = tuple(size for size in available if size <= SODIMM_MAX[kind])
    ceiling = max_gib if max_gib >= installed else 0
    hardware_max = soldered + usable_slots * max(available) if usable_slots else 0
    limit = min(x for x in (ceiling, hardware_max) if x) if (ceiling or hardware_max) else 0

    socket_sizes = {_gib(s) for s in socketed}
    targets = set(TARGETS_GIB)
    if soldered:  # partie soudée + barrette(s) amovible(s) : les totaux courants sont décalés (8 + 16 = 24 Go...)
        targets |= {soldered + usable_slots * size for size in available}
        advice.notes.append(_("Avec une partie soudée, des capacités différentes de chaque côté donnent un double canal partiel."))
    for target in sorted(targets):
        if target <= installed or (limit and target > limit):
            continue
        need = target - soldered
        ways = []
        # 1. Compléter avec des barrettes identiques aux actuelles (rien à jeter).
        if free and len(socket_sizes) == 1:
            size = next(iter(socket_sizes))
            extra = need - len(socketed) * size
            total = len(socketed) + extra // size if size else 0
            # Seulement si l'on aboutit à un nombre pair de barrettes : double canal équilibré.
            if extra > 0 and extra % size == 0 and extra // size <= free and (total % 2 == 0 or usable_slots == 1):
                count = extra // size
                note = _(" (4 barrettes DDR5 : vitesse souvent réduite)") if kind == "DDR5" and total >= 4 else ""
                same = _("ajouter {0} identique") if count == 1 else _("ajouter {0} identiques")
                ways.append(same.format(_plural(count, size)) + note)
        # 2. Kit complet de 2 (ou 4) barrettes, en remplaçant l'existant.
        for count in (2, 4) if usable_slots >= 2 else (1,):
            if count > usable_slots or need % count:
                continue
            size = need // count
            if size in available:
                if soldered and count == 1:
                    way = _("remplacer la barrette amovible par {0}")
                else:
                    way = _("remplacer par {0}") if socketed else _("installer {0}")
                ways.append(way.format(_plural(count, size)))
                break
        if ways:
            advice.options.append((target, _(" ; ou ").join(ways)))
        if len(advice.options) >= 3:
            break

    if not advice.options:
        advice.notes.append(_("Aucune évolution courante trouvée dans les limites déclarées par la carte mère."))
    if max_gib:
        advice.notes.append(
            _("Maximum déclaré par la carte mère : {0}. Valeur souvent prudente : vérifier la fiche du fabricant.", gib_text(max_gib))
        )
    if not slots:
        advice.notes.append(_("Nombre d'emplacements inconnu : vérifier le manuel avant d'acheter."))
    advice.notes.append(_("Pour un double canal stable avec un profil XMP/EXPO, préférer un kit de barrettes identiques."))
    return advice
