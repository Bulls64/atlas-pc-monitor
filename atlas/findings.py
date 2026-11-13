"""Constats : transforme l'inventaire en verdicts (à corriger, à surveiller, à noter, OK).

Module pur, sans interface : chaque règle lit le dictionnaire produit par collect.scan()
et renvoie des constats. Une règle qui rencontre une donnée inattendue est ignorée
(et journalisée) au lieu de faire tomber l'analyse.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

from . import formatting as f
from .collect import ADMIN_SECTIONS

log = logging.getLogger("atlas")

FIX, WATCH, INFO, OK = "fix", "watch", "info", "ok"
LEVELS = {FIX: "À corriger", WATCH: "À surveiller", INFO: "À noter", OK: "OK"}
ORDER = {level: rank for rank, level in enumerate(LEVELS)}

# Seuils : ce sont des choix d'atelier, pas des normes. Les ajuster ici.
DISK_WEAR_FIX = 80  # % d'usure SSD
DISK_TEMP_WATCH = 60  # °C
VOLUME_FREE_WATCH = 10  # % d'espace libre
VOLUME_FREE_FIX = 5  # % d'espace libre
VOLUME_FREE_FIX_BYTES = 5 * 1024**3  # en dessous, Windows Update échoue souvent
VOLUME_MIN_SIZE = 20 * 1000**3  # ignore les petites partitions (récupération, OEM)
BATTERY_WEAR_WATCH = 30  # %
BATTERY_WEAR_FIX = 50  # %
DRIVER_AGE_DAYS = 365
UPTIME_WATCH_DAYS = 14
MEMORY_PRESSURE = 90  # % utilisé au moment de l'analyse
SPEED_TOLERANCE = 0.95  # vitesse configurée / nominale

WIN10_END = date(2025, 10, 14)
# Les éditions LTSB/LTSC ont leur propre calendrier (source : Microsoft, « Windows release health »).
WIN10_LTSC_END = {10240: date(2025, 10, 14), 14393: date(2026, 10, 13), 17763: date(2029, 1, 9), 19044: date(2027, 1, 12)}
WIN10_IOT_LTSC_2021_END = date(2032, 1, 13)
SUPPORT_WATCH_DAYS = 365  # fin de prise en charge « proche »
WIN11_MIN_RAM = 4 * 1024**3
WIN11_MIN_DISK = 64 * 1000**3
GENERIC_GPU = ("microsoft basic display", "microsoft basic render")
VIRTUAL_GPU = ("virtual", "remote display", "indirect display", "parsec", "dummy")


@dataclass(frozen=True)
class Finding:
    level: str  # FIX, WATCH, INFO ou OK
    topic: str  # regroupement affiché : Mémoire, Stockage...
    title: str
    detail: str = ""
    advice: str = ""
    page: str = ""  # page de l'application où se trouve le détail

    @property
    def label(self) -> str:
        return LEVELS[self.level]


def _num(value) -> float | None:
    return f.to_number(value)


def _int(value) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _today(data: dict) -> date:
    try:
        return datetime.fromisoformat(str(data.get("captured_at"))).date()
    except ValueError:
        return date.today()


def _parse_day(value) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _build(data: dict) -> int | None:
    return _int((data.get("os") or {}).get("BuildNumber"))


def windows10_end(caption: str, build: int | None) -> date:
    """Fin de prise en charge de cette édition de Windows 10 (les LTSC durent plus longtemps)."""
    lowered = caption.lower()
    if "ltsc" not in lowered and "ltsb" not in lowered:
        return WIN10_END
    if build == 19044 and "iot" in lowered:
        return WIN10_IOT_LTSC_2021_END
    return WIN10_LTSC_END.get(build or 0, WIN10_END)


# ---------------------------------------------------------------------- mémoire


_CHANNEL = re.compile(r"CHANNEL\s*([A-H])\b", re.IGNORECASE)
_DIMM_SLOT = re.compile(r"DIMM[_\s-]?([A-H])\d", re.IGNORECASE)


def memory_channel(stick: dict) -> str | None:
    """Lettre du canal mémoire déduite des libellés SMBIOS, si le fabricant l'indique."""
    for text in (stick.get("BankLabel"), stick.get("DeviceLocator")):
        match = _CHANNEL.search(str(text or ""))
        if match:
            return match.group(1).upper()
    match = _DIMM_SLOT.search(str(stick.get("DeviceLocator") or ""))
    return match.group(1).upper() if match else None


def _stick_name(stick: dict) -> str:
    parts = [f.fmt_binary(stick.get("Capacity")), f.clean(stick.get("Manufacturer")), f.clean(stick.get("PartNumber"))]
    return " ".join(p for p in parts if p != f.EMPTY)


def rule_memory(data: dict) -> list[Finding]:
    sticks = data.get("ram") or []
    if not sticks:
        return []
    found = []
    slots = _int((data.get("memoryarray") or {}).get("MemoryDevices"))
    if len(sticks) == 1:
        if slots == 1:
            found.append(
                Finding(
                    INFO, "Mémoire", "Une seule barrette, un seul emplacement", "Pas d'extension possible en double canal.", page="Mémoire"
                )
            )
        else:
            free = f" ({slots - 1} emplacement(s) libre(s))" if slots and slots > 1 else ""
            found.append(
                Finding(
                    WATCH,
                    "Mémoire",
                    "Mémoire en mono-canal",
                    f"Une seule barrette installée{free}.",
                    "Ajouter une barrette identique double la bande passante mémoire : gain net en jeu et avec une puce graphique intégrée.",
                    "Mémoire",
                )
            )
    else:
        channels = [memory_channel(stick) for stick in sticks]
        known = {c for c in channels if c}
        if len(known) == 1 and all(channels):
            found.append(
                Finding(
                    WATCH,
                    "Mémoire",
                    "Barrettes probablement sur le même canal",
                    f"Les {len(sticks)} barrettes sont déclarées sur le canal {known.pop()}.",
                    "Vérifier les emplacements conseillés dans le manuel de la carte mère (souvent A2 et B2).",
                    "Mémoire",
                )
            )

    capacities = {_int(s.get("Capacity")) for s in sticks if _int(s.get("Capacity"))}
    parts = {str(s.get("PartNumber") or "").strip().upper() for s in sticks} - {""}
    if len(sticks) > 1 and (len(capacities) > 1 or len(parts) > 1):
        found.append(
            Finding(
                WATCH,
                "Mémoire",
                "Barrettes dépareillées",
                " · ".join(_stick_name(s) for s in sticks),
                "Des barrettes différentes fonctionnent, mais s'alignent sur la plus lente et peuvent être instables avec un profil XMP/EXPO.",
                "Mémoire",
            )
        )

    for stick in sticks:
        rated, configured = _num(stick.get("Speed")), _num(stick.get("ConfiguredClockSpeed"))
        if rated and configured and configured < rated * SPEED_TOLERANCE:
            laptop = _int(stick.get("FormFactor")) == 12
            where = f.clean(stick.get("DeviceLocator"))
            found.append(
                Finding(
                    INFO if laptop else WATCH,
                    "Mémoire",
                    "Mémoire sous sa vitesse nominale",
                    f"{where} : {f.fmt_mts(rated)} annoncés, {f.fmt_mts(configured)} configurés.",
                    "Sur portable, la vitesse est souvent bridée par le processeur ou le BIOS."
                    if laptop
                    else "Vérifier le profil XMP/EXPO dans le BIOS. Des barrettes mélangées ou quatre barrettes peuvent aussi imposer une vitesse plus basse.",
                    "Mémoire",
                )
            )
            break  # la vitesse est commune à toutes les barrettes : un seul constat suffit

    percent = _num((data.get("memory") or {}).get("percent"))
    if percent is not None and percent >= MEMORY_PRESSURE:
        found.append(
            Finding(
                WATCH,
                "Mémoire",
                "Mémoire presque saturée",
                f"{int(percent)} % utilisés au moment de l'analyse.",
                "Repérer les programmes gourmands dans le Gestionnaire des tâches ; ajouter de la mémoire si c'est habituel.",
                "Mémoire",
            )
        )
    return found


# ---------------------------------------------------------------------- stockage


def rule_storage(data: dict) -> list[Finding]:
    found = []
    for disk in data.get("disks") or []:
        name = f.clean(disk.get("Model"))
        health = str(disk.get("Health") or "").strip().lower()
        status = str(disk.get("Status") or "").strip().lower()
        if health == "unhealthy" or "pred fail" in status or "predictive failure" in status:
            found.append(
                Finding(
                    FIX,
                    "Stockage",
                    f"Disque défaillant : {name}",
                    "Windows signale une panne imminente (SMART).",
                    "Sauvegarder les données sans attendre, puis remplacer le disque.",
                    "Stockage",
                )
            )
        elif health == "warning":
            found.append(
                Finding(
                    WATCH,
                    "Stockage",
                    f"Disque en alerte : {name}",
                    "État de santé « Avertissement » selon Windows.",
                    "Faire une sauvegarde et contrôler les attributs SMART avec l'outil du fabricant.",
                    "Stockage",
                )
            )
        wear = _num(disk.get("Wear"))
        if wear is not None and wear >= DISK_WEAR_FIX:
            found.append(
                Finding(
                    FIX,
                    "Stockage",
                    f"SSD très usé : {name}",
                    f"Usure de {int(wear)} %.",
                    "Prévoir le remplacement et vérifier les sauvegardes.",
                    "Stockage",
                )
            )
        temperature = _num(disk.get("Temperature"))
        if temperature and DISK_TEMP_WATCH <= temperature <= 120:
            found.append(
                Finding(
                    WATCH,
                    "Stockage",
                    f"Disque chaud : {name}",
                    f"{int(temperature)} °C au moment de l'analyse.",
                    "Vérifier la ventilation, ou ajouter un dissipateur sur un SSD NVMe.",
                    "Stockage",
                )
            )

    for volume in data.get("volumes") or []:
        size, free = _num(volume.get("Size")), _num(volume.get("FreeSpace"))
        if not size or free is None or size < VOLUME_MIN_SIZE:
            continue
        percent = free * 100 / size
        letter = f.clean(volume.get("DeviceID"))
        detail = f"{f.fmt_decimal(free)} libres sur {f.fmt_decimal(size)} ({f.fmt_number(percent)} %)."
        if percent < VOLUME_FREE_FIX or free < VOLUME_FREE_FIX_BYTES:
            found.append(
                Finding(
                    FIX,
                    "Stockage",
                    f"Volume {letter} presque plein",
                    detail,
                    "Libérer de l'espace (Nettoyage de disque, fichiers temporaires) : les mises à jour Windows risquent d'échouer.",
                    "Stockage",
                )
            )
        elif percent < VOLUME_FREE_WATCH:
            found.append(
                Finding(
                    WATCH,
                    "Stockage",
                    f"Volume {letter} bien rempli",
                    detail,
                    "Prévoir un nettoyage ou plus d'espace de stockage.",
                    "Stockage",
                )
            )

    system = data.get("os") or {}
    drive = str(system.get("SystemDrive") or "C:").upper()
    for volume in data.get("bitlocker") or []:
        if str(volume.get("MountPoint") or "").upper() == drive and str(volume.get("Protection") or "").lower() == "off":
            found.append(
                Finding(
                    INFO,
                    "Stockage",
                    f"Volume système {drive} non chiffré",
                    "BitLocker n'est pas actif.",
                    "Sur un portable, le chiffrement protège les données en cas de vol.",
                    "Stockage",
                )
            )
    return found


# ---------------------------------------------------------------------- Windows


def windows11_checks(data: dict) -> list[tuple[str, bool | None]]:
    """Critères matériels de Windows 11 : (libellé, respecté / non / inconnu)."""
    tpm = data.get("tpm") or {}
    system = data.get("os") or {}
    memory = data.get("memory") or {}
    cpu = (data.get("cpu") or [{}])[0]
    checks: list[tuple[str, bool | None]] = []

    spec = str(tpm.get("SpecVersion") or "")
    checks.append(("TPM 2.0", spec.startswith("2.0") if tpm else None))
    firmware = str(system.get("FirmwareType") or "").lower()
    checks.append(("démarrage UEFI", True if firmware == "uefi" else False if firmware == "legacy" else None))
    installed = _num(memory.get("installed"))
    checks.append(("4 Go de mémoire", installed >= WIN11_MIN_RAM if installed else None))
    sizes = [_num(d.get("Size")) or 0 for d in data.get("disks") or []]
    checks.append(("64 Go de stockage", max(sizes) >= WIN11_MIN_DISK if sizes else None))
    cores, clock = _num(cpu.get("NumberOfCores")), _num(cpu.get("MaxClockSpeed"))
    arch = str(system.get("OSArchitecture") or (data.get("machine") or {}).get("SystemType") or "")
    if cores and clock:
        checks.append(("processeur 64 bits, 2 cœurs, 1 GHz", cores >= 2 and clock >= 1000 and "64" in arch))
    else:
        checks.append(("processeur 64 bits, 2 cœurs, 1 GHz", None))
    return checks


def rule_windows(data: dict) -> list[Finding]:
    system = data.get("os") or {}
    if not system:
        return []
    found = []
    caption = str(system.get("Caption") or "")
    build = _build(data)
    if build and build < 22000 and "windows 10" in caption.lower():
        end = windows10_end(caption, build)
        left = (end - _today(data)).days
        if left <= 0:
            level, title = FIX, "Windows 10 n'est plus pris en charge"
        elif left <= SUPPORT_WATCH_DAYS:
            level, title = WATCH, "Fin de prise en charge de Windows 10 proche"
        else:
            level, title = INFO, f"Windows 10 pris en charge jusqu'en {end.year}"
        found.append(
            Finding(
                level,
                "Windows",
                title,
                f"Fin du support le {end:%d/%m/%Y} : ensuite, plus de correctifs de sécurité hors programme ESU.",
                "Passer à Windows 11 si la machine est éligible, sinon envisager le programme ESU ou un remplacement.",
                "Système",
            )
        )
        checks = windows11_checks(data)
        failed = [label for label, ok in checks if ok is False]
        unknown = [label for label, ok in checks if ok is None]
        if failed:
            found.append(
                Finding(
                    WATCH,
                    "Windows",
                    "Non éligible à Windows 11 en l'état",
                    "Manque : " + ", ".join(failed) + ".",
                    "Le TPM et l'UEFI s'activent souvent dans le BIOS (fTPM, PTT, mode UEFI) avant de conclure à un remplacement.",
                    "Système",
                )
            )
        elif unknown:
            found.append(
                Finding(
                    INFO,
                    "Windows",
                    "Éligibilité à Windows 11 à confirmer",
                    "Non vérifiable ici : " + ", ".join(unknown) + ".",
                    "Relancer en administrateur pour lire le TPM.",
                    "Système",
                )
            )
        else:
            found.append(
                Finding(
                    OK,
                    "Windows",
                    "Configuration minimale de Windows 11 respectée",
                    "TPM 2.0, UEFI, mémoire, stockage et processeur conformes.",
                    "Vérifier encore que le processeur figure dans la liste de Microsoft.",
                    "Système",
                )
            )

    for product in data.get("license") or []:
        status = _int(product.get("LicenseStatus"))
        if status is not None and status != 1:
            found.append(
                Finding(
                    FIX,
                    "Windows",
                    "Windows n'est pas activé",
                    f.fmt_code(status, f.LICENSE_STATUS) + ".",
                    "Paramètres › Système › Activation.",
                    "Système",
                )
            )
        break

    boot = data.get("secureboot") or {}
    if boot.get("Enabled") is False:
        found.append(
            Finding(
                WATCH,
                "Windows",
                "Démarrage sécurisé désactivé",
                "Secure Boot est coupé dans le firmware.",
                "Le réactiver dans le BIOS sauf besoin particulier (autre système, pilote non signé).",
                "Système",
            )
        )

    boot_time = system.get("LastBootUpTime")
    try:
        days = (
            datetime.fromisoformat(str(data.get("captured_at"))).replace(tzinfo=None)
            - datetime.fromisoformat(str(boot_time)).replace(tzinfo=None)
        ).days
    except ValueError:
        days = None
    if days is not None and days >= UPTIME_WATCH_DAYS:
        found.append(
            Finding(
                WATCH,
                "Windows",
                f"Pas de redémarrage depuis {days} jours",
                "Des mises à jour peuvent attendre un redémarrage.",
                "Utiliser « Redémarrer » : avec le démarrage rapide, « Arrêter » ne remet pas ce compteur à zéro.",
                "Système",
            )
        )
    return found


# ---------------------------------------------------------------------- pilotes et périphériques


def rule_devices(data: dict) -> list[Finding]:
    found = []
    today = _today(data)
    for gpu in data.get("gpu") or []:
        name = str(gpu.get("Name") or "")
        lowered = name.lower()
        if any(word in lowered for word in GENERIC_GPU):
            found.append(
                Finding(
                    FIX,
                    "Pilotes",
                    "Pilote graphique générique",
                    f"{name} : aucun pilote du fabricant installé.",
                    "Installer le pilote NVIDIA, AMD ou Intel : sans lui, ni accélération 3D ni bonne résolution.",
                    "Graphiques",
                )
            )
            continue
        if any(word in lowered for word in VIRTUAL_GPU):
            continue
        released = _parse_day(gpu.get("DriverDate"))
        if released and (today - released).days > DRIVER_AGE_DAYS:
            months = (today - released).days // 30
            found.append(
                Finding(
                    WATCH,
                    "Pilotes",
                    "Pilote graphique ancien",
                    f"{name} : pilote du {released:%d/%m/%Y} (environ {months} mois).",
                    "Mettre à jour depuis le site du fabricant de la carte ou de l'ordinateur.",
                    "Graphiques",
                )
            )

    broken, disabled = [], []
    for device in data.get("pnp") or []:
        code = _int(device.get("ConfigManagerErrorCode"))
        if not code or code == 45:  # 45 : simplement débranché
            continue
        line = f"{f.clean(device.get('Name'))} — code {code} : {f.PNP_ERRORS.get(code, 'erreur inconnue')}"
        (disabled if code == 22 else broken).append(line)
    if broken:
        found.append(
            Finding(
                FIX,
                "Pilotes",
                f"{len(broken)} périphérique(s) en erreur",
                "\n".join(broken),
                "Ouvrir le Gestionnaire de périphériques (devmgmt.msc) : réinstaller le pilote ou le mettre à jour.",
                "Système",
            )
        )
    if disabled:
        found.append(
            Finding(
                INFO,
                "Pilotes",
                f"{len(disabled)} périphérique(s) désactivé(s)",
                "\n".join(disabled),
                "Normal s'ils ont été coupés volontairement.",
                "Système",
            )
        )
    return found


# ---------------------------------------------------------------------- batterie


def battery_wear(battery: dict) -> float | None:
    full, design = _num(battery.get("FullCapacity")), _num(battery.get("DesignCapacity"))
    if not full or not design:
        return None
    return max(0.0, 100 - full * 100 / design)


def rule_battery(data: dict) -> list[Finding]:
    found = []
    for battery in data.get("battery") or []:
        wear = battery_wear(battery)
        if wear is None:
            continue
        detail = f"Usure de {int(round(wear))} % : capacité ramenée à {int(round(100 - wear))} % de l'origine."
        if wear >= BATTERY_WEAR_FIX:
            found.append(
                Finding(
                    FIX,
                    "Batterie",
                    "Batterie à remplacer",
                    detail,
                    "L'autonomie a fortement baissé ; une batterie très usée peut aussi gonfler.",
                    "Batterie",
                )
            )
        elif wear >= BATTERY_WEAR_WATCH:
            found.append(
                Finding(WATCH, "Batterie", "Batterie usée", detail, "Générer un rapport détaillé avec powercfg /batteryreport.", "Batterie")
            )
    return found


# ---------------------------------------------------------------------- portée de l'analyse


def rule_scope(data: dict) -> list[Finding]:
    errors = data.get("errors") or {}
    if data.get("admin") or not any(key in errors for key in ADMIN_SECTIONS):
        return []
    return [
        Finding(
            INFO,
            "Analyse",
            "Analyse partielle sans droits administrateur",
            "TPM, démarrage sécurisé, BitLocker et compteurs de fiabilité des disques ne sont pas lus.",
            "Relancer en administrateur pour des constats complets.",
            "Système",
        )
    ]


RULES = (rule_windows, rule_memory, rule_storage, rule_devices, rule_battery, rule_scope)


# ---------------------------------------------------------------------- synthèse « tout va bien »


def _all_clear(data: dict, found: list[Finding]) -> list[Finding]:
    """Une ligne OK par thème analysé sans problème, pour distinguer « rien à signaler » de « pas vérifié »."""
    flagged = {item.topic for item in found if item.level in (FIX, WATCH)}
    errors = data.get("errors") or {}
    sticks = data.get("ram") or []
    disks = data.get("disks") or []
    clear = []
    if sticks and "Mémoire" not in flagged:
        detail = " · ".join(
            [f.fmt_binary((data.get("memory") or {}).get("installed")), f"{len(sticks)} barrette(s)", *f.memory_types(sticks)]
        )
        clear.append(Finding(OK, "Mémoire", "Mémoire : rien à signaler", detail, page="Mémoire"))
    if disks and "Stockage" not in flagged:
        clear.append(
            Finding(
                OK, "Stockage", "Stockage : rien à signaler", f"{len(disks)} disque(s) sain(s), espace libre suffisant.", page="Stockage"
            )
        )
    if data.get("os") and "Windows" not in flagged:
        clear.append(Finding(OK, "Windows", "Windows : rien à signaler", f.clean((data.get("os") or {}).get("Caption")), page="Système"))
    if data.get("os") and "pnp" not in errors and "Pilotes" not in flagged:
        clear.append(
            Finding(OK, "Pilotes", "Aucun périphérique en erreur", "Gestionnaire de périphériques sans point jaune.", page="Système")
        )
    wears = [w for w in (battery_wear(b) for b in data.get("battery") or []) if w is not None]
    if wears and "Batterie" not in flagged:
        clear.append(Finding(OK, "Batterie", "Batterie en bon état", f"Usure de {int(round(max(wears)))} %.", page="Batterie"))
    return clear


def analyze(data: dict) -> list[Finding]:
    """Tous les constats, du plus urgent au plus anodin. Ne lève jamais."""
    if not isinstance(data, dict) or not data.get("os"):
        return []
    found: list[Finding] = []
    for rule in RULES:
        try:
            found.extend(rule(data))
        except Exception:  # une donnée inattendue ne doit pas masquer les autres constats
            log.exception("Règle %s ignorée", rule.__name__)
    try:
        found.extend(_all_clear(data, found))
    except Exception:
        log.exception("Synthèse des constats ignorée")
    return sorted(found, key=lambda item: ORDER[item.level])


def summary(found: list[Finding]) -> dict[str, int]:
    counts = dict.fromkeys(LEVELS, 0)
    for item in found:
        counts[item.level] += 1
    return counts


def summary_text(found: list[Finding]) -> str:
    counts = summary(found)
    if not found:
        return "Aucun constat"
    if not counts[FIX] and not counts[WATCH]:
        return "Rien à corriger"
    parts = [f"{counts[FIX]} à corriger" if counts[FIX] else "", f"{counts[WATCH]} à surveiller" if counts[WATCH] else ""]
    return " · ".join(p for p in parts if p)
