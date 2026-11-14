"""Mise en forme des valeurs : fonctions pures, sans interface ni accès système."""

from __future__ import annotations

import math
from datetime import datetime

from .i18n import N_, _, is_english

EMPTY = "—"
_UNITS = {"fr": ("o", "Ko", "Mo", "Go", "To", "Po"), "en": ("B", "KB", "MB", "GB", "TB", "PB")}

MEMORY_TYPES = {
    20: "DDR",
    21: "DDR2",
    24: "DDR3",
    26: "DDR4",
    27: "LPDDR",
    28: "LPDDR2",
    29: "LPDDR3",
    30: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
}
FORM_FACTORS = {8: "DIMM", 12: "SO-DIMM"}
MEDIA_TYPES = {0: N_("Non précisé"), 3: N_("Disque dur (HDD)"), 4: "SSD", 5: "SCM"}
MEDIA_NAMES = {"hdd": N_("Disque dur (HDD)"), "ssd": "SSD", "scm": "SCM", "unspecified": N_("Non précisé")}
BUS_TYPES = {
    1: "SCSI",
    2: "ATAPI",
    3: "ATA",
    6: "Fibre Channel",
    7: "USB",
    8: "RAID",
    9: "iSCSI",
    10: "SAS",
    11: "SATA",
    12: "SD",
    13: "MMC",
    15: N_("Stockage virtuel"),
    16: N_("Espaces de stockage"),
    17: "NVMe",
}
BATTERY_STATUS = {
    1: N_("Sur batterie"),
    2: N_("Sur secteur"),
    3: N_("Chargée"),
    4: N_("Faible"),
    5: N_("Critique"),
    6: N_("En charge"),
    7: N_("En charge (niveau élevé)"),
    8: N_("En charge (niveau faible)"),
    9: N_("En charge (niveau critique)"),
    11: N_("Partiellement chargée"),
}
LICENSE_STATUS = {
    0: N_("Sans licence"),
    1: N_("Activé"),
    2: N_("Période de grâce initiale"),
    3: N_("Période de grâce (matériel modifié)"),
    4: N_("Période de grâce (copie non authentique)"),
    5: N_("Notification"),
    6: N_("Période de grâce étendue"),
}

# Codes ConfigManagerErrorCode (les « points jaunes » du Gestionnaire de périphériques).
PNP_ERRORS = {
    1: N_("mal configuré"),
    3: N_("pilote endommagé ou mémoire insuffisante"),
    10: N_("le périphérique ne peut pas démarrer"),
    12: N_("ressources insuffisantes"),
    14: N_("redémarrage nécessaire"),
    18: N_("pilotes à réinstaller"),
    19: N_("configuration du registre endommagée"),
    21: N_("suppression en cours"),
    22: N_("désactivé"),
    24: N_("absent ou mal détecté"),
    28: N_("pilote non installé"),
    31: N_("Windows ne peut pas charger les pilotes"),
    32: N_("service du pilote désactivé"),
    37: N_("le pilote a signalé un échec"),
    39: N_("pilote endommagé ou manquant"),
    41: N_("pilote chargé mais matériel introuvable"),
    43: N_("arrêté après avoir signalé des problèmes"),
    45: N_("non connecté actuellement"),
    47: N_("préparé pour un retrait sécurisé"),
    48: N_("pilote bloqué (incompatible)"),
    52: N_("signature du pilote non vérifiable"),
}


def to_number(value) -> float | None:
    """Convertit en nombre, ou None si la valeur n'est pas exploitable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fmt_number(number: float, digits: int = 1) -> str:
    """Nombre sans « ,0 » inutile : virgule décimale en français, point en anglais."""
    text = f"{number:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if is_english() else text.replace(".", ",")


def _fmt_bytes(value, base: int) -> str:
    number = to_number(value)
    if number is None or number < 0:
        return EMPTY
    units = _UNITS["en" if is_english() else "fr"]
    unit = 0
    while number >= base and unit < len(units) - 1:
        number /= base
        unit += 1
    return f"{fmt_number(number, 1 if unit else 0)} {units[unit]}"


def fmt_binary(value) -> str:
    """Octets en base 1024 (mémoire vive, VRAM), affichés comme le fait Windows."""
    return _fmt_bytes(value, 1024)


def fmt_decimal(value) -> str:
    """Octets en base 1000 (capacité commerciale des disques)."""
    return _fmt_bytes(value, 1000)


def fmt_mhz(value) -> str:
    number = to_number(value)
    if number is None or number <= 0:
        return EMPTY
    if number >= 1000:
        return f"{fmt_number(number / 1000, 2)} GHz"
    return f"{fmt_number(number, 0)} MHz"


def fmt_mts(value) -> str:
    """Débit mémoire : Windows le rapporte en « MHz », mais c'est le nombre de MT/s (DDR4-3200 → 3200)."""
    number = to_number(value)
    return EMPTY if number is None or number <= 0 else f"{int(number)} MT/s"


def fmt_percent(value) -> str:
    number = to_number(value)
    if number is None:
        return EMPTY
    return f"{fmt_number(number, 0)}%" if is_english() else f"{fmt_number(number, 0)} %"


def fmt_celsius(value) -> str:
    number = to_number(value)
    return EMPTY if number is None else f"{fmt_number(number)} °C"


def fmt_bool(value) -> str:
    if value is None or value == "":
        return EMPTY
    return _("Oui") if value else _("Non")


def fmt_code(value, table: dict[int, str]) -> str:
    """Traduit un code numérique CIM (dans la langue courante) ; garde la valeur brute si elle est inconnue."""
    number = to_number(value)
    if number is None:
        return str(value).strip() if value not in (None, "") else EMPTY
    text = table.get(int(number))
    return _(text) if text else _("Code {0}", int(number))


def fmt_media(value) -> str:
    if isinstance(value, str) and not value.strip().isdigit():
        name = MEDIA_NAMES.get(value.strip().lower())
        return _(name) if name else value.strip() or EMPTY
    return fmt_code(value, MEDIA_TYPES)


def fmt_bus(value) -> str:
    if isinstance(value, str) and not value.strip().isdigit():
        return value.strip() or EMPTY
    return fmt_code(value, BUS_TYPES)


def fmt_date(value) -> str:
    """Date ISO (AAAA-MM-JJ[THH:MM:SS]) rendue en JJ/MM/AAAA [HH:MM] ; en anglais, AAAA-MM-JJ [HH:MM]."""
    if not value or not isinstance(value, str):
        return EMPTY
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    return fmt_day(moment, with_time=len(value) > 10)


def fmt_day(day, with_time: bool = False) -> str:
    """Date (ou date et heure) déjà convertie, au format de la langue courante."""
    pattern = "%Y-%m-%d" if is_english() else "%d/%m/%Y"
    return day.strftime(pattern + (" %H:%M" if with_time else ""))


def fmt_uptime(boot_iso, now_iso) -> str:
    """Durée écoulée depuis le dernier démarrage."""
    try:
        boot = datetime.fromisoformat(boot_iso)
        now = datetime.fromisoformat(now_iso).replace(tzinfo=None)
    except (TypeError, ValueError):
        return EMPTY
    minutes = int((now - boot.replace(tzinfo=None)).total_seconds() // 60)
    if minutes < 0:
        return EMPTY
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return _("{0} j {1} h", days, hours)
    if hours:
        return _("{0} h {1} min", hours, mins)
    return _("{0} min", mins)


def fmt_diagonal(width_cm, height_cm) -> str:
    """Diagonale d'écran en pouces à partir des dimensions EDID en centimètres."""
    width, height = to_number(width_cm), to_number(height_cm)
    if not width or not height:
        return EMPTY
    inches = (width**2 + height**2) ** 0.5 / 2.54
    return _("{0} pouces ({1} × {2} cm)", fmt_number(inches), fmt_number(width, 0), fmt_number(height, 0))


def fmt_stamp(value) -> str:
    """Horodatage ISO d'un inventaire (« captured_at ») en date et heure de la langue courante, fuseau ignoré."""
    return fmt_date(str(value or "")[:19])


def fmt_memory_type(value) -> str:
    """Type d'une barrette (DDR4…). 0, 1 et 2 (« inconnu », « autre ») = non renseigné, fréquent sur une VM."""
    number = to_number(value)
    if number is None or int(number) <= 2:
        return EMPTY
    return fmt_code(number, MEMORY_TYPES)


def memory_types(sticks: list[dict]) -> list[str]:
    """Types de mémoire distincts des barrettes (DDR4, DDR5…), triés ; les types non renseignés sont ignorés."""
    return sorted({fmt_memory_type(s.get("SMBIOSMemoryType")) for s in sticks} - {EMPTY})


def memory_forms(sticks: list[dict]) -> list[str]:
    """Formats amovibles distincts des barrettes (DIMM, SO-DIMM), triés."""
    return sorted({FORM_FACTORS[int(n)] for s in sticks if (n := to_number(s.get("FormFactor"))) in FORM_FACTORS})


# Valeurs bouche-trou du SMBIOS et de WMI : affichées comme une valeur absente.
PLACEHOLDERS = frozenset(
    {"none", "null", "n/a", "not specified", "not available", "not applicable", "to be filled by o.e.m.", "default string", "undefined"}
)


def clean(value) -> str:
    """Texte brut nettoyé, ou tiret si vide ou si c'est une valeur bouche-trou (« None », « To Be Filled By O.E.M. »)."""
    if value is None:
        return EMPTY
    text = str(value).strip()
    return text if text and text.lower() not in PLACEHOLDERS else EMPTY
