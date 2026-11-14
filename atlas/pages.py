"""Modèle des pages : transforme l'inventaire en sections de lignes « libellé / valeur ».

Module pur (aucune dépendance graphique) : il sert à l'interface, aux exports,
à la recherche et à la comparaison de rapports.

Page model: turns the inventory into sections of "label / value" rows.

Pure module (no graphical dependency): it serves the interface, the exports,
the search and the report comparison.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from . import formatting as f
from .collect import ADMIN_SECTIONS
from .findings import battery_wear, device_name
from .formatting import EMPTY
from .i18n import N_, _
from .upgrade import gib_text, memory_advice

OVERVIEW = N_("Vue d'ensemble")
FINDINGS = N_("Constats")
# (nom de la page, icône) : ajouter une page ici suffit à l'ajouter à la navigation.
# (page name, icon): adding a page here is enough to add it to the navigation.
PAGES: list[tuple[str, str]] = [
    (OVERVIEW, "⌂"),
    (FINDINGS, "✓"),
    (N_("Système"), "▣"),
    (N_("Processeur"), "◉"),
    (N_("Mémoire"), "▤"),
    (N_("Carte mère"), "▥"),
    (N_("Graphiques"), "▰"),
    (N_("Stockage"), "▱"),
    (N_("Réseau"), "⌁"),
    (N_("Audio"), "♪"),
    (N_("Batterie"), "▮"),
]
DETAIL_PAGES = [name for name, _icon in PAGES if name not in (OVERVIEW, FINDINGS)]

HEALTH = {"healthy": N_("Sain"), "warning": N_("Avertissement"), "unhealthy": N_("Défaillant"), "unknown": N_("Inconnu")}
NET_STATUS = {"up": N_("Connecté"), "disconnected": N_("Déconnecté"), "disabled": N_("Désactivé"), "not present": N_("Absent")}
PROTECTION = {"on": N_("Protection activée"), "off": N_("Protection désactivée"), "unknown": N_("État inconnu")}
# AdapterRAM est un entier 32 bits : à partir de ce seuil, la valeur est plafonnée par Windows.
# AdapterRAM is a 32-bit integer: from this threshold on, the value is capped by Windows.
ADAPTER_RAM_CAP = 4 * 1024**3 - 2 * 1024**2


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    # change d'une analyse à l'autre : ignoré par la comparaison
    # changes from one analysis to the next: ignored by the comparison
    volatile: bool = False


@dataclass
class Section:
    title: str
    rows: list[Row] = field(default_factory=list)
    note: str = ""
    # remarque neutre (conseil), par opposition à note (problème de collecte)
    # neutral remark (advice), as opposed to note (collection problem)
    tip: str = ""


def _add(rows: list[Row], label: str, value: str, volatile: bool = False) -> None:
    """Ajoute la ligne seulement si la valeur est renseignée.

    Adds the row only if the value is provided.
    """
    if value and value != EMPTY:
        rows.append(Row(label, value, volatile))


def _error_note(data: dict, *keys: str) -> str:
    """Explique pourquoi une source n'a rien renvoyé.

    Explains why a source returned nothing.
    """
    errors = data.get("errors") or {}
    for key in keys:
        if key in errors:
            if key in ADMIN_SECTIONS and not data.get("admin"):
                return _("Source indisponible sans droits administrateur ({0})", errors[key])
            return _("Source indisponible : {0}", errors[key])
    return ""


def _numbered(title: str, index: int, total: int, detail: str = "") -> str:
    text = f"{title} {index}" if total > 1 else title
    return f"{text} — {detail}" if detail and detail != EMPTY else text


def _kb(value) -> str:
    number = f.to_number(value)
    return f.fmt_binary(number * 1024) if number else EMPTY


def page_system(data: dict) -> list[Section]:
    host = data.get("system") or {}
    machine = data.get("machine") or {}
    system = data.get("os") or {}
    rows: list[Row] = []
    _add(rows, _("Nom de l'ordinateur"), f.clean(host.get("computer")))
    _add(rows, _("Fabricant"), f.clean(machine.get("Manufacturer")))
    _add(rows, _("Modèle"), f.clean(machine.get("Model")))
    _add(rows, _("Famille"), f.clean(machine.get("SystemFamily")))
    _add(rows, _("Type de système"), f.clean(machine.get("SystemType")))
    if machine.get("PartOfDomain"):
        _add(rows, _("Domaine"), f.clean(machine.get("Domain")))
    if "HypervisorPresent" in machine:
        _add(rows, _("Hyperviseur détecté"), f.fmt_bool(machine.get("HypervisorPresent")))
    if not machine:
        _add(rows, _("Plateforme"), f.clean(host.get("platform")))
        _add(rows, _("Architecture"), f.clean(host.get("architecture")))
    sections = [Section(_("Ordinateur"), rows, _error_note(data, "machine"))]

    rows = []
    _add(rows, _("Édition"), f.clean(system.get("Caption")))
    _add(rows, _("Version"), f.clean(system.get("DisplayVersion")))
    _add(rows, _("Numéro de version"), f.clean(system.get("Version")))
    _add(rows, _("Build"), f.clean(system.get("BuildNumber")))
    _add(rows, _("Architecture"), f.clean(system.get("OSArchitecture")))
    _add(rows, _("Installé le"), f.fmt_date(system.get("InstallDate")))
    _add(rows, _("Dernier démarrage"), f.fmt_date(system.get("LastBootUpTime")), volatile=True)
    _add(rows, _("Allumé depuis"), f.fmt_uptime(system.get("LastBootUpTime"), data.get("captured_at")), volatile=True)
    product = next(iter(data.get("license") or []), None)
    if product:
        _add(rows, _("Activation"), f.fmt_code(product.get("LicenseStatus"), f.LICENSE_STATUS))
        _add(rows, _("Licence"), f.clean(product.get("Description")))
    if rows or data.get("errors"):
        sections.append(Section(_("Windows"), rows, _error_note(data, "os", "license")))

    if system or data.get("errors"):
        rows = []
        boot = data.get("secureboot") or {}
        tpm = data.get("tpm") or {}
        firmware = str(system.get("FirmwareType") or "")
        _add(rows, _("Mode de démarrage"), {"uefi": "UEFI", "legacy": _("BIOS hérité (Legacy)")}.get(firmware.lower(), firmware))
        if "Enabled" in boot:
            _add(rows, _("Démarrage sécurisé"), _("Activé") if boot.get("Enabled") else _("Désactivé"))
        if tpm:
            _add(rows, _("TPM activé"), f.fmt_bool(tpm.get("IsEnabled_InitialValue")))
            _add(rows, _("Version de la spécification TPM"), f.clean(tpm.get("SpecVersion")))
        if "admin" in data:
            _add(rows, _("Session administrateur"), f.fmt_bool(data.get("admin")))
        sections.append(Section(_("Sécurité"), rows, _error_note(data, "secureboot", "tpm")))
    seconds = f.to_number(data.get("scan_seconds"))
    if seconds is not None:
        rows = [Row(_("Durée de l'analyse"), _("{0} s", f.fmt_number(seconds)), volatile=True)]
        timings = data.get("timings") or {}
        if timings:
            name, ms = max(timings.items(), key=lambda item: item[1])
            slowest = _("{0} ({1} s)", _(SOURCE_LABELS.get(name, name)), f.fmt_number(ms / 1000))
            rows.append(Row(_("Source la plus lente"), slowest, volatile=True))
        sections.append(Section(_("Analyse"), rows))
    rows = []
    for device in data.get("pnp") or []:
        code = f.to_number(device.get("ConfigManagerErrorCode"))
        if code and int(code) != 45:
            text = _("Code {0} : {1}", int(code), _(f.PNP_ERRORS.get(int(code), N_("erreur inconnue"))))
            _add(rows, device_name(device), text)
    note = _error_note(data, "pnp")
    if rows or note:
        sections.append(Section(_("Périphériques en erreur"), rows, note))
    return sections


def page_cpu(data: dict) -> list[Section]:
    cpus = data.get("cpu") or []
    sections = []
    for index, cpu in enumerate(cpus, 1):
        rows: list[Row] = []
        _add(rows, _("Modèle"), f.clean(cpu.get("Name")))
        _add(rows, _("Fabricant"), f.clean(cpu.get("Manufacturer")))
        _add(rows, _("Socket"), f.clean(cpu.get("SocketDesignation")))
        _add(rows, _("Cœurs"), f.clean(cpu.get("NumberOfCores")))
        _add(rows, _("Threads"), f.clean(cpu.get("NumberOfLogicalProcessors")))
        _add(rows, _("Fréquence maximale"), f.fmt_mhz(cpu.get("MaxClockSpeed")))
        _add(rows, _("Fréquence actuelle"), f.fmt_mhz(cpu.get("CurrentClockSpeed")), volatile=True)
        _add(rows, _("Cache L2"), _kb(cpu.get("L2CacheSize")))
        _add(rows, _("Cache L3"), _kb(cpu.get("L3CacheSize")))
        if cpu.get("VirtualizationFirmwareEnabled") is not None:
            _add(rows, _("Virtualisation activée dans le firmware"), f.fmt_bool(cpu.get("VirtualizationFirmwareEnabled")))
        _add(rows, _("Charge"), f.fmt_percent(cpu.get("LoadPercentage")), volatile=True)
        sections.append(Section(_numbered(_("Processeur"), index, len(cpus)), rows))
    return sections or [Section(_("Processeur"), [], _error_note(data, "cpu"))]


def page_memory(data: dict) -> list[Section]:
    memory = data.get("memory") or {}
    sticks = data.get("ram") or []
    array = data.get("memoryarray") or {}
    rows: list[Row] = []
    _add(rows, _("Mémoire installée"), f.fmt_binary(memory.get("installed")))
    _add(rows, _("Mémoire utilisable par Windows"), f.fmt_binary(memory.get("total")))
    _add(rows, _("Utilisée"), f.fmt_binary(memory.get("used")), volatile=True)
    _add(rows, _("Disponible"), f.fmt_binary(memory.get("free")), volatile=True)
    slots = f.to_number(array.get("MemoryDevices"))
    if slots and sticks:
        _add(rows, _("Emplacements occupés"), _("{0} sur {1}", len(sticks), int(slots)))
    _add(rows, _("Capacité maximale de la carte mère"), _kb(array.get("MaxCapacity")))
    sections = [Section(_("Synthèse"), rows, _error_note(data, "ram", "os"))]
    advice = memory_advice(data)
    if advice:
        rows = [Row(_("Configuration actuelle"), advice.current)]
        if advice.upgradable:
            _add(rows, _("Barrettes à acheter"), advice.spec)
            rows += [Row(_("Passer à {0}", gib_text(goal)), way[:1].upper() + way[1:]) for goal, way in advice.options]
        sections.append(Section(_("Évolution possible"), rows, tip=" ".join(advice.notes)))
    for index, stick in enumerate(sticks, 1):
        rows = []
        _add(rows, _("Emplacement"), f.clean(stick.get("DeviceLocator")))
        _add(rows, _("Banque"), f.clean(stick.get("BankLabel")))
        if f.to_number(stick.get("SMBIOSMemoryType")):
            _add(rows, _("Type"), f.fmt_memory_type(stick.get("SMBIOSMemoryType")))
        if f.to_number(stick.get("FormFactor")):
            _add(rows, _("Format"), f.fmt_code(stick.get("FormFactor"), f.FORM_FACTORS))
        _add(rows, _("Capacité"), f.fmt_binary(stick.get("Capacity")))
        _add(rows, _("Vitesse nominale"), f.fmt_mts(stick.get("Speed")))
        _add(rows, _("Vitesse configurée"), f.fmt_mts(stick.get("ConfiguredClockSpeed")))
        _add(rows, _("Fabricant"), f.clean(stick.get("Manufacturer")))
        _add(rows, _("Référence"), f.clean(stick.get("PartNumber")))
        _add(rows, _("Numéro de série"), f.clean(stick.get("SerialNumber")))
        sections.append(Section(_numbered(_("Barrette"), index, max(len(sticks), 2), f.clean(stick.get("DeviceLocator"))), rows))
    return sections


def page_board(data: dict) -> list[Section]:
    board = data.get("board") or {}
    bios = data.get("bios") or {}
    rows: list[Row] = []
    _add(rows, _("Fabricant"), f.clean(board.get("Manufacturer")))
    _add(rows, _("Modèle"), f.clean(board.get("Product")))
    _add(rows, _("Révision"), f.clean(board.get("Version")))
    _add(rows, _("Numéro de série"), f.clean(board.get("SerialNumber")))
    sections = [Section(_("Carte mère"), rows, _error_note(data, "board"))]
    rows = []
    _add(rows, _("Fabricant"), f.clean(bios.get("Manufacturer")))
    _add(rows, _("Version"), f.clean(bios.get("Version")))
    _add(rows, _("Date"), f.fmt_date(bios.get("ReleaseDate")))
    _add(rows, _("Numéro de série de la machine"), f.clean(bios.get("SerialNumber")))
    sections.append(Section(_("BIOS / UEFI"), rows, _error_note(data, "bios")))
    rows = [Row(f.clean(zone.get("Name")), f.fmt_celsius(zone.get("Celsius")), volatile=True) for zone in data.get("temperatures") or []]
    note = _error_note(data, "temperatures")
    if not rows and not note and data.get("os"):
        note = _("Aucune zone thermique ACPI exposée par ce matériel.")
    sections.append(Section(_("Zones thermiques ACPI"), rows, note))
    return sections


def vram_text(gpu: dict) -> str:
    amount = f.to_number(gpu.get("VRAM"))
    if not amount or amount <= 0:
        return EMPTY
    if gpu.get("VRAMSource") != "registre" and amount >= ADAPTER_RAM_CAP:
        return _("4 Go ou plus (valeur plafonnée par Windows)")
    return f.fmt_binary(amount)


def page_graphics(data: dict) -> list[Section]:
    gpus = data.get("gpu") or []
    monitors = data.get("monitors") or []
    sections = []
    for index, gpu in enumerate(gpus, 1):
        rows: list[Row] = []
        _add(rows, _("Modèle"), f.clean(gpu.get("Name")))
        _add(rows, _("Mémoire dédiée"), vram_text(gpu))
        _add(rows, _("Version du pilote"), f.clean(gpu.get("DriverVersion")))
        _add(rows, _("Date du pilote"), f.fmt_date(gpu.get("DriverDate")))
        _add(rows, _("Mode vidéo"), f.clean(gpu.get("VideoModeDescription")), volatile=True)
        if f.to_number(gpu.get("RefreshRate")):
            _add(rows, _("Fréquence de rafraîchissement"), _("{0} Hz", int(f.to_number(gpu.get("RefreshRate")))), volatile=True)
        sections.append(Section(_numbered(_("Carte graphique"), index, len(gpus)), rows))
    if not gpus:
        sections.append(Section(_("Carte graphique"), [], _error_note(data, "gpu")))
    for index, monitor in enumerate(monitors, 1):
        rows = []
        _add(rows, _("Nom"), f.clean(monitor.get("Name")))
        _add(rows, _("Code fabricant"), f.clean(monitor.get("Manufacturer")))
        _add(rows, _("Diagonale"), f.fmt_diagonal(monitor.get("WidthCm"), monitor.get("HeightCm")))
        if f.to_number(monitor.get("Year")):
            _add(rows, _("Année de fabrication"), str(int(f.to_number(monitor.get("Year")))))
        _add(rows, _("Numéro de série"), f.clean(monitor.get("SerialNumber")))
        sections.append(Section(_numbered(_("Écran"), index, len(monitors)), rows))
    if not monitors and (note := _error_note(data, "monitors")):
        sections.append(Section(_("Écrans"), [], note))
    return sections


def volume_text(volume: dict) -> str:
    parts = [
        f.clean(volume.get("VolumeName")) if volume.get("VolumeName") else _("Disque local"),
        f.fmt_decimal(volume.get("Size")),
        _("{0} libres", f.fmt_decimal(volume.get("FreeSpace"))),
        f.clean(volume.get("FileSystem")),
    ]
    return " · ".join(part for part in parts if part != EMPTY)


def page_storage(data: dict) -> list[Section]:
    disks = data.get("disks") or []
    sections = []
    for index, disk in enumerate(disks, 1):
        rows: list[Row] = []
        _add(rows, _("Modèle"), f.clean(disk.get("Model")))
        if disk.get("MediaType") not in (None, ""):
            _add(rows, _("Type"), f.fmt_media(disk.get("MediaType")))
        _add(rows, _("Interface"), f.fmt_bus(disk.get("BusType")))
        _add(rows, _("Capacité"), f.fmt_decimal(disk.get("Size")))
        health = f.clean(disk.get("Health"))
        _add(rows, _("État de santé"), _(HEALTH.get(health.lower(), health)))
        _add(rows, _("État opérationnel"), f.clean(disk.get("Status")))
        temperature = f.to_number(disk.get("Temperature"))
        if temperature and 0 < temperature <= 120:
            _add(rows, _("Température"), f.fmt_celsius(temperature), volatile=True)
        if f.to_number(disk.get("PowerOnHours")) is not None:
            _add(rows, _("Heures de fonctionnement"), _("{0} h", int(f.to_number(disk.get("PowerOnHours")))), volatile=True)
        if f.to_number(disk.get("Wear")) is not None:
            _add(rows, _("Usure"), f.fmt_percent(disk.get("Wear")), volatile=True)
        if f.to_number(disk.get("ReadErrors")) is not None:
            _add(rows, _("Erreurs de lecture"), str(int(f.to_number(disk.get("ReadErrors")))), volatile=True)
        _add(rows, _("Firmware"), f.clean(disk.get("Firmware")))
        _add(rows, _("Numéro de série"), f.clean(disk.get("SerialNumber")))
        note = ""
        if "PowerOnHours" in disk and disk.get("PowerOnHours") is None and not data.get("admin"):
            note = _("Compteurs de fiabilité (heures, usure, température) disponibles en session administrateur.")
        sections.append(Section(_numbered(_("Disque"), index, len(disks), f.clean(disk.get("Model"))), rows, note))
    if not disks:
        sections.append(Section(_("Disques physiques"), [], _error_note(data, "disks", "disks_fallback")))
    rows = [Row(_("Volume {0}", f.clean(v.get("DeviceID"))), volume_text(v), volatile=True) for v in data.get("volumes") or []]
    if rows or data.get("errors"):
        sections.append(Section(_("Volumes"), rows, _error_note(data, "volumes")))
    rows = []
    for volume in data.get("bitlocker") or []:
        state = _(PROTECTION.get(f.clean(volume.get("Protection")).lower(), f.clean(volume.get("Protection"))))
        percent = f.to_number(volume.get("Percent"))
        text = _("{0} · chiffré à {1} %", state, int(percent)) if percent is not None else state
        _add(rows, _("Volume {0}", f.clean(volume.get("MountPoint"))), text)
    note = _error_note(data, "bitlocker")
    if rows or note:
        sections.append(Section(_("BitLocker"), rows, note))
    return sections


def _add_ip(rows: list[Row], ip: dict) -> None:
    for label, key in ((_("Adresse IPv4"), "IPv4"), (_("Adresse IPv6"), "IPv6"), (_("Passerelle"), "Gateway"), (_("Serveurs DNS"), "DNS")):
        _add(rows, label, f.clean(ip.get(key)), volatile=True)


def page_network(data: dict) -> list[Section]:
    adapters = data.get("adapters") or []
    config = {str(item.get("Name")): item for item in data.get("network") or []}
    sections = []
    for adapter in adapters:
        name = f.clean(adapter.get("Name"))
        rows: list[Row] = []
        _add(rows, _("Description"), f.clean(adapter.get("InterfaceDescription")))
        status = f.clean(adapter.get("Status"))
        _add(rows, _("État"), _(NET_STATUS.get(status.lower(), status)), volatile=True)
        _add(rows, _("Débit"), f.clean(adapter.get("LinkSpeed")), volatile=True)
        _add(rows, _("Adresse MAC"), f.clean(adapter.get("MacAddress")))
        _add_ip(rows, config.pop(name, {}))
        sections.append(Section(name, rows))
    for name, ip in config.items():  # interfaces actives non physiques (VPN, virtuelles) — active non-physical interfaces (VPN, virtual)
        rows = []
        _add_ip(rows, ip)
        if rows:
            sections.append(Section(_("{0} (interface virtuelle)", name), rows))
    return sections or [Section(_("Interfaces réseau"), [], _error_note(data, "adapters", "network"))]


def page_audio(data: dict) -> list[Section]:
    rows: list[Row] = []
    for device in data.get("audio") or []:
        parts = [f.clean(device.get("Manufacturer")), f.clean(device.get("Status"))]
        _add(rows, f.clean(device.get("Name")), " · ".join(p for p in parts if p != EMPTY) or _("Détecté"))
    return [Section(_("Périphériques audio"), rows, _error_note(data, "audio"))]


def page_battery(data: dict) -> list[Section]:
    batteries = data.get("battery") or []
    sections = []
    for index, battery in enumerate(batteries, 1):
        rows: list[Row] = []
        _add(rows, _("Nom"), f.clean(battery.get("Name")))
        _add(rows, _("Charge"), f.fmt_percent(battery.get("Charge")), volatile=True)
        if f.to_number(battery.get("Status")):
            _add(rows, _("État"), f.fmt_code(battery.get("Status"), f.BATTERY_STATUS), volatile=True)
        full, design = f.to_number(battery.get("FullCapacity")), f.to_number(battery.get("DesignCapacity"))
        if design:
            _add(rows, _("Capacité d'origine"), _("{0} mWh", int(design)))
        if full:
            _add(rows, _("Capacité à pleine charge"), _("{0} mWh", int(full)), volatile=True)
        wear = battery_wear(battery)
        if wear is not None:
            _add(rows, _("Usure"), f.fmt_percent(wear), volatile=True)
        sections.append(Section(_numbered(_("Batterie"), index, len(batteries)), rows))
    if not sections:
        note = _error_note(data, "battery") or (_("Aucune batterie détectée.") if data.get("os") else "")
        sections.append(Section(_("Batterie"), [], note))
    return sections


SOURCE_LABELS = {
    "machine": N_("modèle de l'ordinateur"), "bios": N_("BIOS"), "secureboot": N_("démarrage sécurisé"), "os": N_("Windows"),
    "cpu": N_("processeur"), "board": N_("carte mère"), "ram": N_("mémoire"), "memoryarray": N_("emplacements mémoire"),
    "vram": N_("mémoire vidéo"), "gpu": N_("carte graphique"), "disks": N_("disques"), "disks_fallback": N_("disques"),
    "volumes": N_("volumes"), "bitlocker": N_("BitLocker"), "adapters": N_("cartes réseau"), "network": N_("configuration IP"),
    "temperatures": N_("températures"), "battery": N_("batterie"), "monitors": N_("écrans"), "audio": N_("audio"), "tpm": N_("TPM"),
    "pnp": N_("périphériques en erreur"), "license": N_("activation Windows"),
}  # fmt: skip


_BUILDERS = {
    "Système": page_system,
    "Processeur": page_cpu,
    "Mémoire": page_memory,
    "Carte mère": page_board,
    "Graphiques": page_graphics,
    "Stockage": page_storage,
    "Réseau": page_network,
    "Audio": page_audio,
    "Batterie": page_battery,
}


def build_page(data: dict, page: str) -> list[Section]:
    return _BUILDERS[page](data)


def build_all(data: dict) -> dict[str, list[Section]]:
    """Toutes les pages de détail, dans l'ordre de la navigation.

    All the detail pages, in navigation order.
    """
    return {page: build_page(data, page) for page in DETAIL_PAGES}


def fold(text: str) -> str:
    """Minuscules sans accents, pour une recherche tolérante.

    Lowercase without accents, for a forgiving search.
    """
    decomposed = unicodedata.normalize("NFD", str(text).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def search(data: dict, query: str) -> list[tuple[str, str, Row]]:
    """Lignes dont la page, la section, le libellé ou la valeur contiennent tous les mots cherchés.

    Rows whose page, section, label or value contain all the words searched for.
    """
    words = fold(query).split()
    if not words:
        return []
    hits = []
    for page, sections in build_all(data).items():
        for section in sections:
            for row in section.rows:
                haystack = fold(f"{_(page)} {section.title} {row.label} {row.value}")
                if all(word in haystack for word in words):
                    hits.append((page, section.title, row))
    return hits


def diff_reports(before: dict, after: dict) -> list[tuple[str, str, str, str]]:
    """Différences stables entre deux inventaires : (page › section, libellé, avant, après).

    Stable differences between two inventories: (page › section, label, before, after).
    """

    def index(data: dict) -> dict[tuple[str, str, str], str]:
        found: dict[tuple[str, str, str], str] = {}
        for page, sections in build_all(data).items():
            for section in sections:
                for row in section.rows:
                    if row.volatile:
                        continue
                    # Deux périphériques du même nom (audio, points jaunes) : numérotés, sinon le second écrase le premier.
                    # Two devices with the same name (audio, yellow marks): numbered, otherwise the second overwrites the first.
                    key, rank = (page, section.title, row.label), 1
                    while key in found:
                        rank += 1
                        key = (page, section.title, f"{row.label} ({rank})")
                    found[key] = row.value
        return found

    old, new = index(before), index(after)
    changes = []
    for key in [*old, *(k for k in new if k not in old)]:
        if old.get(key) != new.get(key):
            page, section, label = key
            changes.append((f"{_(page)} › {section}", label, old.get(key, EMPTY), new.get(key, EMPTY)))
    return changes
