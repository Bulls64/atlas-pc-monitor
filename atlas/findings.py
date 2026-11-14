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
from .collect import ADMIN_SECTIONS, is_virtual
from .i18n import N_, _

log = logging.getLogger("atlas")

FIX, WATCH, INFO, OK = "fix", "watch", "info", "ok"
LEVELS = {FIX: N_("À corriger"), WATCH: N_("À surveiller"), INFO: N_("À noter"), OK: N_("OK")}
ORDER = {level: rank for rank, level in enumerate(LEVELS)}
# Thèmes des constats : identifiants en français, traduits à l'affichage par _(item.topic).
TOPICS = (N_("Mémoire"), N_("Stockage"), N_("Windows"), N_("Pilotes"), N_("Batterie"), N_("Analyse"))

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
VIRTUAL_GPU = ("virtual", "hyper-v", "remote display", "indirect display", "parsec", "dummy")
# Date conventionnelle de tous les pilotes fournis avec Windows : elle ne dit rien de leur âge réel.
INBOX_DRIVER_DATE = date(2006, 6, 21)


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
        return _(LEVELS[self.level])


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
    if is_virtual(data):  # barrettes simulées par l'hyperviseur : seule l'occupation a un sens
        return _memory_pressure(data)
    found = []
    slots = _int((data.get("memoryarray") or {}).get("MemoryDevices"))
    if len(sticks) == 1:
        if slots == 1:
            found.append(
                Finding(
                    INFO,
                    "Mémoire",
                    _("Une seule barrette, un seul emplacement"),
                    _("Pas d'extension possible en double canal."),
                    page="Mémoire",
                )
            )
        else:
            free = _(" ({0} emplacement(s) libre(s))", slots - 1) if slots and slots > 1 else ""
            found.append(
                Finding(
                    WATCH,
                    "Mémoire",
                    _("Mémoire en mono-canal"),
                    _("Une seule barrette installée{0}.", free),
                    _(
                        "Ajouter une barrette identique double la bande passante mémoire : gain net en jeu et avec une puce graphique intégrée."
                    ),
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
                    _("Barrettes probablement sur le même canal"),
                    _("Les {0} barrettes sont déclarées sur le canal {1}.", len(sticks), known.pop()),
                    _("Vérifier les emplacements conseillés dans le manuel de la carte mère (souvent A2 et B2)."),
                    "Mémoire",
                )
            )

    capacities = {_int(s.get("Capacity")) for s in sticks if _int(s.get("Capacity"))}
    parts = {f.clean(s.get("PartNumber")).upper() for s in sticks} - {f.EMPTY}
    if len(sticks) > 1 and (len(capacities) > 1 or len(parts) > 1):
        found.append(
            Finding(
                WATCH,
                "Mémoire",
                _("Barrettes dépareillées"),
                " · ".join(_stick_name(s) for s in sticks),
                _(
                    "Des barrettes différentes fonctionnent, mais s'alignent sur la plus lente et peuvent être instables avec un profil XMP/EXPO."
                ),
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
                    _("Mémoire sous sa vitesse nominale"),
                    _("{0} : {1} annoncés, {2} configurés.", where, f.fmt_mts(rated), f.fmt_mts(configured)),
                    _("Sur portable, la vitesse est souvent bridée par le processeur ou le BIOS.")
                    if laptop
                    else _(
                        "Vérifier le profil XMP/EXPO dans le BIOS. Des barrettes mélangées ou quatre barrettes peuvent aussi imposer une vitesse plus basse."
                    ),
                    "Mémoire",
                )
            )
            break  # la vitesse est commune à toutes les barrettes : un seul constat suffit
    return found + _memory_pressure(data)


def _memory_pressure(data: dict) -> list[Finding]:
    percent = _num((data.get("memory") or {}).get("percent"))
    if percent is None or percent < MEMORY_PRESSURE:
        return []
    return [
        Finding(
            WATCH,
            "Mémoire",
            _("Mémoire presque saturée"),
            _("{0} % utilisés au moment de l'analyse.", int(percent)),
            _("Repérer les programmes gourmands dans le Gestionnaire des tâches ; ajouter de la mémoire si c'est habituel."),
            "Mémoire",
        )
    ]


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
                    _("Disque défaillant : {0}", name),
                    _("Windows signale une panne imminente (SMART)."),
                    _("Sauvegarder les données sans attendre, puis remplacer le disque."),
                    "Stockage",
                )
            )
        elif health == "warning":
            found.append(
                Finding(
                    WATCH,
                    "Stockage",
                    _("Disque en alerte : {0}", name),
                    _("État de santé « Avertissement » selon Windows."),
                    _("Faire une sauvegarde et contrôler les attributs SMART avec l'outil du fabricant."),
                    "Stockage",
                )
            )
        wear = _num(disk.get("Wear"))
        if wear is not None and wear >= DISK_WEAR_FIX:
            found.append(
                Finding(
                    FIX,
                    "Stockage",
                    _("SSD très usé : {0}", name),
                    _("Usure de {0} %.", int(wear)),
                    _("Prévoir le remplacement et vérifier les sauvegardes."),
                    "Stockage",
                )
            )
        temperature = _num(disk.get("Temperature"))
        if temperature and DISK_TEMP_WATCH <= temperature <= 120:
            found.append(
                Finding(
                    WATCH,
                    "Stockage",
                    _("Disque chaud : {0}", name),
                    _("{0} °C au moment de l'analyse.", int(temperature)),
                    _("Vérifier la ventilation, ou ajouter un dissipateur sur un SSD NVMe."),
                    "Stockage",
                )
            )

    for volume in data.get("volumes") or []:
        size, free = _num(volume.get("Size")), _num(volume.get("FreeSpace"))
        if not size or free is None or size < VOLUME_MIN_SIZE:
            continue
        percent = free * 100 / size
        letter = f.clean(volume.get("DeviceID"))
        detail = _("{0} libres sur {1} ({2} %).", f.fmt_decimal(free), f.fmt_decimal(size), f.fmt_number(percent))
        if percent < VOLUME_FREE_FIX or free < VOLUME_FREE_FIX_BYTES:
            found.append(
                Finding(
                    FIX,
                    "Stockage",
                    _("Volume {0} presque plein", letter),
                    detail,
                    _("Libérer de l'espace (Nettoyage de disque, fichiers temporaires) : les mises à jour Windows risquent d'échouer."),
                    "Stockage",
                )
            )
        elif percent < VOLUME_FREE_WATCH:
            found.append(
                Finding(
                    WATCH,
                    "Stockage",
                    _("Volume {0} bien rempli", letter),
                    detail,
                    _("Prévoir un nettoyage ou plus d'espace de stockage."),
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
                    _("Volume système {0} non chiffré", drive),
                    _("BitLocker n'est pas actif."),
                    _("Sur un portable, le chiffrement protège les données en cas de vol."),
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
    checks.append((_("TPM 2.0"), spec.startswith("2.0") if tpm else None))
    firmware = str(system.get("FirmwareType") or "").lower()
    checks.append((_("démarrage UEFI"), True if firmware == "uefi" else False if firmware == "legacy" else None))
    installed = _num(memory.get("installed"))
    checks.append((_("4 Go de mémoire"), installed >= WIN11_MIN_RAM if installed else None))
    sizes = [_num(d.get("Size")) or 0 for d in data.get("disks") or []]
    checks.append((_("64 Go de stockage"), max(sizes) >= WIN11_MIN_DISK if sizes else None))
    cores, clock = _num(cpu.get("NumberOfCores")), _num(cpu.get("MaxClockSpeed"))
    arch = str(system.get("OSArchitecture") or (data.get("machine") or {}).get("SystemType") or "")
    if cores and clock:
        checks.append((_("processeur 64 bits, 2 cœurs, 1 GHz"), cores >= 2 and clock >= 1000 and "64" in arch))
    else:
        checks.append((_("processeur 64 bits, 2 cœurs, 1 GHz"), None))
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
            level, title = FIX, _("Windows 10 n'est plus pris en charge")
        elif left <= SUPPORT_WATCH_DAYS:
            level, title = WATCH, _("Fin de prise en charge de Windows 10 proche")
        else:
            level, title = INFO, _("Windows 10 pris en charge jusqu'en {0}", end.year)
        found.append(
            Finding(
                level,
                "Windows",
                title,
                _("Fin du support le {0} : ensuite, plus de correctifs de sécurité hors programme ESU.", f.fmt_day(end)),
                _("Passer à Windows 11 si la machine est éligible, sinon envisager le programme ESU ou un remplacement."),
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
                    _("Non éligible à Windows 11 en l'état"),
                    _("Manque : ") + ", ".join(failed) + ".",
                    _("Le TPM et l'UEFI s'activent souvent dans le BIOS (fTPM, PTT, mode UEFI) avant de conclure à un remplacement."),
                    "Système",
                )
            )
        elif unknown:
            found.append(
                Finding(
                    INFO,
                    "Windows",
                    _("Éligibilité à Windows 11 à confirmer"),
                    _("Non vérifiable ici : ") + ", ".join(unknown) + ".",
                    _("Relancer en administrateur pour lire le TPM."),
                    "Système",
                )
            )
        else:
            found.append(
                Finding(
                    OK,
                    "Windows",
                    _("Configuration minimale de Windows 11 respectée"),
                    _("TPM 2.0, UEFI, mémoire, stockage et processeur conformes."),
                    _("Vérifier encore que le processeur figure dans la liste de Microsoft."),
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
                    _("Windows n'est pas activé"),
                    f.fmt_code(status, f.LICENSE_STATUS) + ".",
                    _("Paramètres › Système › Activation."),
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
                _("Démarrage sécurisé désactivé"),
                _("Secure Boot est coupé dans le firmware."),
                _("Le réactiver dans le BIOS sauf besoin particulier (autre système, pilote non signé)."),
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
                _("Pas de redémarrage depuis {0} jours", days),
                _("Des mises à jour peuvent attendre un redémarrage."),
                _("Utiliser « Redémarrer » : avec le démarrage rapide, « Arrêter » ne remet pas ce compteur à zéro."),
                "Système",
            )
        )
    return found


# ---------------------------------------------------------------------- pilotes et périphériques


def device_name(device: dict) -> str:
    """Nom du périphérique ; un périphérique sans pilote n'en a souvent pas (« Périphérique inconnu »)."""
    name = f.clean(device.get("Name"))
    if name != f.EMPTY:
        return name
    kind = f.clean(device.get("PNPClass"))
    return _("Périphérique inconnu") + (_(" (classe {0})", kind) if kind != f.EMPTY else "")


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
                    _("Pilote graphique générique"),
                    _("{0} : aucun pilote du fabricant installé.", name),
                    _("Installer le pilote NVIDIA, AMD ou Intel : sans lui, ni accélération 3D ni bonne résolution."),
                    "Graphiques",
                )
            )
            continue
        if any(word in lowered for word in VIRTUAL_GPU):
            continue
        released = _parse_day(gpu.get("DriverDate"))
        if released and released != INBOX_DRIVER_DATE and (today - released).days > DRIVER_AGE_DAYS:
            months = (today - released).days // 30
            found.append(
                Finding(
                    WATCH,
                    "Pilotes",
                    _("Pilote graphique ancien"),
                    _("{0} : pilote du {1} (environ {2} mois).", name, f.fmt_day(released), months),
                    _("Mettre à jour depuis le site du fabricant de la carte ou de l'ordinateur."),
                    "Graphiques",
                )
            )

    broken, disabled = [], []
    for device in data.get("pnp") or []:
        code = _int(device.get("ConfigManagerErrorCode"))
        if not code or code == 45:  # 45 : simplement débranché
            continue
        line = _("{0} — code {1} : {2}", device_name(device), code, _(f.PNP_ERRORS.get(code, N_("erreur inconnue"))))
        (disabled if code == 22 else broken).append(line)
    if broken:
        found.append(
            Finding(
                FIX,
                "Pilotes",
                _("{0} périphérique(s) en erreur", len(broken)),
                "\n".join(broken),
                _("Ouvrir le Gestionnaire de périphériques (devmgmt.msc) : réinstaller le pilote ou le mettre à jour."),
                "Système",
            )
        )
    if disabled:
        found.append(
            Finding(
                INFO,
                "Pilotes",
                _("{0} périphérique(s) désactivé(s)", len(disabled)),
                "\n".join(disabled),
                _("Normal s'ils ont été coupés volontairement."),
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
        detail = _("Usure de {0} % : capacité ramenée à {1} % de l'origine.", int(round(wear)), int(round(100 - wear)))
        if wear >= BATTERY_WEAR_FIX:
            found.append(
                Finding(
                    FIX,
                    "Batterie",
                    _("Batterie à remplacer"),
                    detail,
                    _("L'autonomie a fortement baissé ; une batterie très usée peut aussi gonfler."),
                    "Batterie",
                )
            )
        elif wear >= BATTERY_WEAR_WATCH:
            found.append(
                Finding(
                    WATCH,
                    "Batterie",
                    _("Batterie usée"),
                    detail,
                    _("Générer un rapport détaillé avec powercfg /batteryreport."),
                    "Batterie",
                )
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
            _("Analyse partielle sans droits administrateur"),
            _("TPM, démarrage sécurisé, BitLocker et compteurs de fiabilité des disques ne sont pas lus."),
            _("Relancer en administrateur pour des constats complets."),
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
            [f.fmt_binary((data.get("memory") or {}).get("installed")), _("{0} barrette(s)", len(sticks)), *f.memory_types(sticks)]
        )
        clear.append(Finding(OK, "Mémoire", _("Mémoire : rien à signaler"), detail, page="Mémoire"))
    if disks and "Stockage" not in flagged:
        clear.append(
            Finding(
                OK,
                "Stockage",
                _("Stockage : rien à signaler"),
                _("{0} disque(s) sain(s), espace libre suffisant.", len(disks)),
                page="Stockage",
            )
        )
    if data.get("os") and "Windows" not in flagged:
        clear.append(Finding(OK, "Windows", _("Windows : rien à signaler"), f.clean((data.get("os") or {}).get("Caption")), page="Système"))
    if data.get("os") and "pnp" not in errors and "Pilotes" not in flagged:
        clear.append(
            Finding(OK, "Pilotes", _("Aucun périphérique en erreur"), _("Gestionnaire de périphériques sans point jaune."), page="Système")
        )
    wears = [w for w in (battery_wear(b) for b in data.get("battery") or []) if w is not None]
    if wears and "Batterie" not in flagged:
        clear.append(Finding(OK, "Batterie", _("Batterie en bon état"), _("Usure de {0} %.", int(round(max(wears)))), page="Batterie"))
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
        return _("Aucun constat")
    if not counts[FIX] and not counts[WATCH]:
        return _("Rien à corriger")
    parts = [_("{0} à corriger", counts[FIX]) if counts[FIX] else "", _("{0} à surveiller", counts[WATCH]) if counts[WATCH] else ""]
    return " · ".join(p for p in parts if p)
