"""Mise en forme des valeurs : fonctions pures, sans interface ni accès système."""

from __future__ import annotations

from datetime import datetime

EMPTY = "—"
_UNITS = ("o", "Ko", "Mo", "Go", "To", "Po")

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
MEDIA_TYPES = {0: "Non précisé", 3: "Disque dur (HDD)", 4: "SSD", 5: "SCM"}
MEDIA_NAMES = {"hdd": "Disque dur (HDD)", "ssd": "SSD", "scm": "SCM", "unspecified": "Non précisé"}
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
    15: "Stockage virtuel",
    16: "Espaces de stockage",
    17: "NVMe",
}
BATTERY_STATUS = {
    1: "Sur batterie",
    2: "Sur secteur",
    3: "Chargée",
    4: "Faible",
    5: "Critique",
    6: "En charge",
    7: "En charge (niveau élevé)",
    8: "En charge (niveau faible)",
    9: "En charge (niveau critique)",
    11: "Partiellement chargée",
}
LICENSE_STATUS = {
    0: "Sans licence",
    1: "Activé",
    2: "Période de grâce initiale",
    3: "Période de grâce (matériel modifié)",
    4: "Période de grâce (copie non authentique)",
    5: "Notification",
    6: "Période de grâce étendue",
}


def to_number(value) -> float | None:
    """Convertit en nombre, ou None si la valeur n'est pas exploitable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _decimal(number: float, digits: int = 1) -> str:
    """Nombre à la française : virgule décimale, sans « ,0 » inutile."""
    text = f"{number:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _fmt_bytes(value, base: int) -> str:
    number = to_number(value)
    if number is None or number < 0:
        return EMPTY
    for unit in _UNITS:
        if number < base or unit == _UNITS[-1]:
            return f"{_decimal(number, 0 if unit == 'o' else 1)} {unit}"
        number /= base
    return EMPTY


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
        return f"{_decimal(number / 1000, 2)} GHz"
    return f"{_decimal(number, 0)} MHz"


def fmt_percent(value) -> str:
    number = to_number(value)
    return EMPTY if number is None else f"{_decimal(number, 0)} %"


def fmt_celsius(value) -> str:
    number = to_number(value)
    return EMPTY if number is None else f"{_decimal(number)} °C"


def fmt_bool(value) -> str:
    if value is None or value == "":
        return EMPTY
    return "Oui" if value else "Non"


def fmt_code(value, table: dict[int, str]) -> str:
    """Traduit un code numérique CIM ; garde la valeur brute si elle est inconnue."""
    number = to_number(value)
    if number is None:
        return str(value).strip() if value not in (None, "") else EMPTY
    return table.get(int(number), f"Code {int(number)}")


def fmt_media(value) -> str:
    if isinstance(value, str) and not value.strip().isdigit():
        return MEDIA_NAMES.get(value.strip().lower(), value.strip() or EMPTY)
    return fmt_code(value, MEDIA_TYPES)


def fmt_bus(value) -> str:
    if isinstance(value, str) and not value.strip().isdigit():
        return value.strip() or EMPTY
    return fmt_code(value, BUS_TYPES)


def fmt_date(value) -> str:
    """Date ISO (AAAA-MM-JJ[THH:MM:SS]) rendue en JJ/MM/AAAA [HH:MM]."""
    if not value or not isinstance(value, str):
        return EMPTY
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if len(value) <= 10:
        return moment.strftime("%d/%m/%Y")
    return moment.strftime("%d/%m/%Y %H:%M")


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
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {mins} min"
    return f"{mins} min"


def fmt_diagonal(width_cm, height_cm) -> str:
    """Diagonale d'écran en pouces à partir des dimensions EDID en centimètres."""
    width, height = to_number(width_cm), to_number(height_cm)
    if not width or not height:
        return EMPTY
    inches = (width**2 + height**2) ** 0.5 / 2.54
    return f"{_decimal(inches)} pouces ({_decimal(width, 0)} × {_decimal(height, 0)} cm)"


def clean(value) -> str:
    """Texte brut nettoyé, ou tiret si vide."""
    if value is None:
        return EMPTY
    text = str(value).strip()
    return text or EMPTY
