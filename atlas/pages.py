"""Modèle des pages : transforme l'inventaire en sections de lignes « libellé / valeur ».

Module pur (aucune dépendance à Tkinter) : il sert à l'interface, aux exports,
à la recherche et à la comparaison de rapports.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from . import formatting as f
from .collect import ADMIN_SECTIONS
from .formatting import EMPTY
from .upgrade import memory_advice

OVERVIEW = "Vue d'ensemble"
FINDINGS = "Constats"
# (nom de la page, icône) : ajouter une page ici suffit à l'ajouter à la navigation.
PAGES: list[tuple[str, str]] = [
    (OVERVIEW, "⌂"),
    (FINDINGS, "✓"),
    ("Système", "▣"),
    ("Processeur", "◉"),
    ("Mémoire", "▤"),
    ("Carte mère", "▥"),
    ("Graphiques", "▰"),
    ("Stockage", "▱"),
    ("Réseau", "⌁"),
    ("Audio", "♪"),
    ("Batterie", "▮"),
]
DETAIL_PAGES = [name for name, _icon in PAGES if name not in (OVERVIEW, FINDINGS)]

HEALTH = {"healthy": "Sain", "warning": "Avertissement", "unhealthy": "Défaillant", "unknown": "Inconnu"}
NET_STATUS = {"up": "Connecté", "disconnected": "Déconnecté", "disabled": "Désactivé", "not present": "Absent"}
PROTECTION = {"on": "Protection activée", "off": "Protection désactivée", "unknown": "État inconnu"}
# AdapterRAM est un entier 32 bits : à partir de ce seuil, la valeur est plafonnée par Windows.
ADAPTER_RAM_CAP = 4 * 1024**3 - 2 * 1024**2


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    volatile: bool = False  # change d'une analyse à l'autre : ignoré par la comparaison


@dataclass
class Section:
    title: str
    rows: list[Row] = field(default_factory=list)
    note: str = ""
    tip: str = ""  # remarque neutre (conseil), par opposition à note (problème de collecte)


def _add(rows: list[Row], label: str, value: str, volatile: bool = False) -> None:
    """Ajoute la ligne seulement si la valeur est renseignée."""
    if value and value != EMPTY:
        rows.append(Row(label, value, volatile))


def _error_note(data: dict, *keys: str) -> str:
    """Explique pourquoi une source n'a rien renvoyé."""
    errors = data.get("errors") or {}
    for key in keys:
        if key in errors:
            if key in ADMIN_SECTIONS and not data.get("admin"):
                return f"Source indisponible sans droits administrateur ({errors[key]})"
            return f"Source indisponible : {errors[key]}"
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
    _add(rows, "Nom de l'ordinateur", f.clean(host.get("computer")))
    _add(rows, "Fabricant", f.clean(machine.get("Manufacturer")))
    _add(rows, "Modèle", f.clean(machine.get("Model")))
    _add(rows, "Famille", f.clean(machine.get("SystemFamily")))
    _add(rows, "Type de système", f.clean(machine.get("SystemType")))
    if machine.get("PartOfDomain"):
        _add(rows, "Domaine", f.clean(machine.get("Domain")))
    if "HypervisorPresent" in machine:
        _add(rows, "Hyperviseur détecté", f.fmt_bool(machine.get("HypervisorPresent")))
    if not machine:
        _add(rows, "Plateforme", f.clean(host.get("platform")))
        _add(rows, "Architecture", f.clean(host.get("architecture")))
    sections = [Section("Ordinateur", rows, _error_note(data, "machine"))]

    rows = []
    _add(rows, "Édition", f.clean(system.get("Caption")))
    _add(rows, "Version", f.clean(system.get("DisplayVersion")))
    _add(rows, "Numéro de version", f.clean(system.get("Version")))
    _add(rows, "Build", f.clean(system.get("BuildNumber")))
    _add(rows, "Architecture", f.clean(system.get("OSArchitecture")))
    _add(rows, "Installé le", f.fmt_date(system.get("InstallDate")))
    _add(rows, "Dernier démarrage", f.fmt_date(system.get("LastBootUpTime")), volatile=True)
    _add(rows, "Allumé depuis", f.fmt_uptime(system.get("LastBootUpTime"), data.get("captured_at")), volatile=True)
    for product in data.get("license") or []:
        _add(rows, "Activation", f.fmt_code(product.get("LicenseStatus"), f.LICENSE_STATUS))
        _add(rows, "Licence", f.clean(product.get("Description")))
        break
    if rows or data.get("errors"):
        sections.append(Section("Windows", rows, _error_note(data, "os", "license")))

    if system or data.get("errors"):
        rows = []
        boot = data.get("secureboot") or {}
        tpm = data.get("tpm") or {}
        firmware = str(system.get("FirmwareType") or "")
        _add(rows, "Mode de démarrage", {"uefi": "UEFI", "legacy": "BIOS hérité (Legacy)"}.get(firmware.lower(), firmware))
        if "Enabled" in boot:
            _add(rows, "Démarrage sécurisé", "Activé" if boot.get("Enabled") else "Désactivé")
        if tpm:
            _add(rows, "TPM activé", f.fmt_bool(tpm.get("IsEnabled_InitialValue")))
            _add(rows, "Version de la spécification TPM", f.clean(tpm.get("SpecVersion")))
        if "admin" in data:
            _add(rows, "Session administrateur", f.fmt_bool(data.get("admin")))
        sections.append(Section("Sécurité", rows, _error_note(data, "secureboot", "tpm")))
    seconds = f.to_number(data.get("scan_seconds"))
    if seconds is not None:
        rows = [Row("Durée de l'analyse", f"{f._decimal(seconds)} s", volatile=True)]
        timings = data.get("timings") or {}
        if timings:
            name, ms = max(timings.items(), key=lambda item: item[1])
            rows.append(Row("Source la plus lente", f"{SOURCE_LABELS.get(name, name)} ({f._decimal(ms / 1000)} s)", volatile=True))
        sections.append(Section("Analyse", rows))
    rows = []
    for device in data.get("pnp") or []:
        code = f.to_number(device.get("ConfigManagerErrorCode"))
        if code and int(code) != 45:
            text = f"Code {int(code)} : {f.PNP_ERRORS.get(int(code), 'erreur inconnue')}"
            _add(rows, f.clean(device.get("Name")), text)
    note = _error_note(data, "pnp")
    if rows or note:
        sections.append(Section("Périphériques en erreur", rows, note))
    return sections


def page_cpu(data: dict) -> list[Section]:
    cpus = data.get("cpu") or []
    sections = []
    for index, cpu in enumerate(cpus, 1):
        rows: list[Row] = []
        _add(rows, "Modèle", f.clean(cpu.get("Name")))
        _add(rows, "Fabricant", f.clean(cpu.get("Manufacturer")))
        _add(rows, "Socket", f.clean(cpu.get("SocketDesignation")))
        _add(rows, "Cœurs", f.clean(cpu.get("NumberOfCores")))
        _add(rows, "Threads", f.clean(cpu.get("NumberOfLogicalProcessors")))
        _add(rows, "Fréquence maximale", f.fmt_mhz(cpu.get("MaxClockSpeed")))
        _add(rows, "Fréquence actuelle", f.fmt_mhz(cpu.get("CurrentClockSpeed")), volatile=True)
        _add(rows, "Cache L2", _kb(cpu.get("L2CacheSize")))
        _add(rows, "Cache L3", _kb(cpu.get("L3CacheSize")))
        if cpu.get("VirtualizationFirmwareEnabled") is not None:
            _add(rows, "Virtualisation activée dans le firmware", f.fmt_bool(cpu.get("VirtualizationFirmwareEnabled")))
        _add(rows, "Charge", f.fmt_percent(cpu.get("LoadPercentage")), volatile=True)
        sections.append(Section(_numbered("Processeur", index, len(cpus)), rows))
    return sections or [Section("Processeur", [], _error_note(data, "cpu"))]


def page_memory(data: dict) -> list[Section]:
    memory = data.get("memory") or {}
    sticks = data.get("ram") or []
    array = data.get("memoryarray") or {}
    rows: list[Row] = []
    _add(rows, "Mémoire installée", f.fmt_binary(memory.get("installed")))
    _add(rows, "Mémoire utilisable par Windows", f.fmt_binary(memory.get("total")))
    _add(rows, "Utilisée", f.fmt_binary(memory.get("used")), volatile=True)
    _add(rows, "Disponible", f.fmt_binary(memory.get("free")), volatile=True)
    slots = f.to_number(array.get("MemoryDevices"))
    if slots and sticks:
        _add(rows, "Emplacements occupés", f"{len(sticks)} sur {int(slots)}")
    _add(rows, "Capacité maximale de la carte mère", _kb(array.get("MaxCapacity")))
    sections = [Section("Synthèse", rows, _error_note(data, "ram", "os"))]
    advice = memory_advice(data)
    if advice:
        rows = [Row("Configuration actuelle", advice.current)]
        if advice.upgradable:
            _add(rows, "Barrettes à acheter", advice.spec)
            rows += [Row(goal, way[:1].upper() + way[1:]) for goal, way in advice.options]
        sections.append(Section("Évolution possible", rows, tip=" ".join(advice.notes)))
    for index, stick in enumerate(sticks, 1):
        rows = []
        _add(rows, "Emplacement", f.clean(stick.get("DeviceLocator")))
        _add(rows, "Banque", f.clean(stick.get("BankLabel")))
        if f.to_number(stick.get("SMBIOSMemoryType")):
            _add(rows, "Type", f.fmt_code(stick.get("SMBIOSMemoryType"), f.MEMORY_TYPES))
        if f.to_number(stick.get("FormFactor")):
            _add(rows, "Format", f.fmt_code(stick.get("FormFactor"), f.FORM_FACTORS))
        _add(rows, "Capacité", f.fmt_binary(stick.get("Capacity")))
        _add(rows, "Vitesse nominale", f.fmt_mts(stick.get("Speed")))
        _add(rows, "Vitesse configurée", f.fmt_mts(stick.get("ConfiguredClockSpeed")))
        _add(rows, "Fabricant", f.clean(stick.get("Manufacturer")))
        _add(rows, "Référence", f.clean(stick.get("PartNumber")))
        _add(rows, "Numéro de série", f.clean(stick.get("SerialNumber")))
        sections.append(Section(_numbered("Barrette", index, max(len(sticks), 2), f.clean(stick.get("DeviceLocator"))), rows))
    return sections


def page_board(data: dict) -> list[Section]:
    board = data.get("board") or {}
    bios = data.get("bios") or {}
    rows: list[Row] = []
    _add(rows, "Fabricant", f.clean(board.get("Manufacturer")))
    _add(rows, "Modèle", f.clean(board.get("Product")))
    _add(rows, "Révision", f.clean(board.get("Version")))
    _add(rows, "Numéro de série", f.clean(board.get("SerialNumber")))
    sections = [Section("Carte mère", rows, _error_note(data, "board"))]
    rows = []
    _add(rows, "Fabricant", f.clean(bios.get("Manufacturer")))
    _add(rows, "Version", f.clean(bios.get("Version")))
    _add(rows, "Date", f.fmt_date(bios.get("ReleaseDate")))
    _add(rows, "Numéro de série de la machine", f.clean(bios.get("SerialNumber")))
    sections.append(Section("BIOS / UEFI", rows, _error_note(data, "bios")))
    rows = [Row(f.clean(zone.get("Name")), f.fmt_celsius(zone.get("Celsius")), volatile=True) for zone in data.get("temperatures") or []]
    note = _error_note(data, "temperatures")
    if not rows and not note and data.get("os"):
        note = "Aucune zone thermique ACPI exposée par ce matériel."
    sections.append(Section("Zones thermiques ACPI", rows, note))
    return sections


def vram_text(gpu: dict) -> str:
    amount = f.to_number(gpu.get("VRAM"))
    if not amount or amount <= 0:
        return EMPTY
    if gpu.get("VRAMSource") != "registre" and amount >= ADAPTER_RAM_CAP:
        return "4 Go ou plus (valeur plafonnée par Windows)"
    return f.fmt_binary(amount)


def page_graphics(data: dict) -> list[Section]:
    gpus = data.get("gpu") or []
    monitors = data.get("monitors") or []
    sections = []
    for index, gpu in enumerate(gpus, 1):
        rows: list[Row] = []
        _add(rows, "Modèle", f.clean(gpu.get("Name")))
        _add(rows, "Mémoire dédiée", vram_text(gpu))
        _add(rows, "Version du pilote", f.clean(gpu.get("DriverVersion")))
        _add(rows, "Date du pilote", f.fmt_date(gpu.get("DriverDate")))
        _add(rows, "Mode vidéo", f.clean(gpu.get("VideoModeDescription")), volatile=True)
        if f.to_number(gpu.get("RefreshRate")):
            _add(rows, "Fréquence de rafraîchissement", f"{int(f.to_number(gpu.get('RefreshRate')))} Hz", volatile=True)
        sections.append(Section(_numbered("Carte graphique", index, len(gpus)), rows))
    if not gpus:
        sections.append(Section("Carte graphique", [], _error_note(data, "gpu")))
    for index, monitor in enumerate(monitors, 1):
        rows = []
        _add(rows, "Nom", f.clean(monitor.get("Name")))
        _add(rows, "Code fabricant", f.clean(monitor.get("Manufacturer")))
        _add(rows, "Diagonale", f.fmt_diagonal(monitor.get("WidthCm"), monitor.get("HeightCm")))
        if f.to_number(monitor.get("Year")):
            _add(rows, "Année de fabrication", str(int(f.to_number(monitor.get("Year")))))
        _add(rows, "Numéro de série", f.clean(monitor.get("SerialNumber")))
        sections.append(Section(_numbered("Écran", index, len(monitors)), rows))
    if not monitors and (note := _error_note(data, "monitors")):
        sections.append(Section("Écrans", [], note))
    return sections


def volume_text(volume: dict) -> str:
    parts = [
        f.clean(volume.get("VolumeName")) if volume.get("VolumeName") else "Disque local",
        f.fmt_decimal(volume.get("Size")),
        f"{f.fmt_decimal(volume.get('FreeSpace'))} libres",
        f.clean(volume.get("FileSystem")),
    ]
    return " · ".join(part for part in parts if part != EMPTY)


def page_storage(data: dict) -> list[Section]:
    disks = data.get("disks") or []
    sections = []
    for index, disk in enumerate(disks, 1):
        rows: list[Row] = []
        _add(rows, "Modèle", f.clean(disk.get("Model")))
        if disk.get("MediaType") not in (None, ""):
            _add(rows, "Type", f.fmt_media(disk.get("MediaType")))
        _add(rows, "Interface", f.fmt_bus(disk.get("BusType")))
        _add(rows, "Capacité", f.fmt_decimal(disk.get("Size")))
        health = f.clean(disk.get("Health"))
        _add(rows, "État de santé", HEALTH.get(health.lower(), health))
        _add(rows, "État opérationnel", f.clean(disk.get("Status")))
        temperature = f.to_number(disk.get("Temperature"))
        if temperature and 0 < temperature <= 120:
            _add(rows, "Température", f.fmt_celsius(temperature), volatile=True)
        if f.to_number(disk.get("PowerOnHours")) is not None:
            _add(rows, "Heures de fonctionnement", f"{int(f.to_number(disk.get('PowerOnHours')))} h", volatile=True)
        if f.to_number(disk.get("Wear")) is not None:
            _add(rows, "Usure", f.fmt_percent(disk.get("Wear")), volatile=True)
        if f.to_number(disk.get("ReadErrors")) is not None:
            _add(rows, "Erreurs de lecture", str(int(f.to_number(disk.get("ReadErrors")))), volatile=True)
        _add(rows, "Firmware", f.clean(disk.get("Firmware")))
        _add(rows, "Numéro de série", f.clean(disk.get("SerialNumber")))
        note = ""
        if "PowerOnHours" in disk and disk.get("PowerOnHours") is None and not data.get("admin"):
            note = "Compteurs de fiabilité (heures, usure, température) disponibles en session administrateur."
        sections.append(Section(_numbered("Disque", index, len(disks), f.clean(disk.get("Model"))), rows, note))
    if not disks:
        sections.append(Section("Disques physiques", [], _error_note(data, "disks", "disks_fallback")))
    rows = [Row(f"Volume {f.clean(v.get('DeviceID'))}", volume_text(v), volatile=True) for v in data.get("volumes") or []]
    if rows or data.get("errors"):
        sections.append(Section("Volumes", rows, _error_note(data, "volumes")))
    rows = []
    for volume in data.get("bitlocker") or []:
        state = PROTECTION.get(f.clean(volume.get("Protection")).lower(), f.clean(volume.get("Protection")))
        percent = f.to_number(volume.get("Percent"))
        text = f"{state} · chiffré à {int(percent)} %" if percent is not None else state
        _add(rows, f"Volume {f.clean(volume.get('MountPoint'))}", text)
    note = _error_note(data, "bitlocker")
    if rows or note:
        sections.append(Section("BitLocker", rows, note))
    return sections


def page_network(data: dict) -> list[Section]:
    adapters = data.get("adapters") or []
    config = {str(item.get("Name")): item for item in data.get("network") or []}
    sections = []
    for adapter in adapters:
        name = f.clean(adapter.get("Name"))
        rows: list[Row] = []
        _add(rows, "Description", f.clean(adapter.get("InterfaceDescription")))
        status = f.clean(adapter.get("Status"))
        _add(rows, "État", NET_STATUS.get(status.lower(), status), volatile=True)
        _add(rows, "Débit", f.clean(adapter.get("LinkSpeed")), volatile=True)
        _add(rows, "Adresse MAC", f.clean(adapter.get("MacAddress")))
        ip = config.pop(name, {})
        _add(rows, "Adresse IPv4", f.clean(ip.get("IPv4")), volatile=True)
        _add(rows, "Adresse IPv6", f.clean(ip.get("IPv6")), volatile=True)
        _add(rows, "Passerelle", f.clean(ip.get("Gateway")), volatile=True)
        _add(rows, "Serveurs DNS", f.clean(ip.get("DNS")), volatile=True)
        sections.append(Section(name, rows))
    for name, ip in config.items():  # interfaces actives non physiques (VPN, virtuelles)
        rows = []
        _add(rows, "Adresse IPv4", f.clean(ip.get("IPv4")), volatile=True)
        _add(rows, "Adresse IPv6", f.clean(ip.get("IPv6")), volatile=True)
        _add(rows, "Passerelle", f.clean(ip.get("Gateway")), volatile=True)
        _add(rows, "Serveurs DNS", f.clean(ip.get("DNS")), volatile=True)
        if rows:
            sections.append(Section(f"{name} (interface virtuelle)", rows))
    return sections or [Section("Interfaces réseau", [], _error_note(data, "adapters", "network"))]


def page_audio(data: dict) -> list[Section]:
    rows: list[Row] = []
    for device in data.get("audio") or []:
        parts = [f.clean(device.get("Manufacturer")), f.clean(device.get("Status"))]
        _add(rows, f.clean(device.get("Name")), " · ".join(p for p in parts if p != EMPTY) or "Détecté")
    return [Section("Périphériques audio", rows, _error_note(data, "audio"))]


def page_battery(data: dict) -> list[Section]:
    batteries = data.get("battery") or []
    sections = []
    for index, battery in enumerate(batteries, 1):
        rows: list[Row] = []
        _add(rows, "Nom", f.clean(battery.get("Name")))
        _add(rows, "Charge", f.fmt_percent(battery.get("Charge")), volatile=True)
        if f.to_number(battery.get("Status")):
            _add(rows, "État", f.fmt_code(battery.get("Status"), f.BATTERY_STATUS), volatile=True)
        full, design = f.to_number(battery.get("FullCapacity")), f.to_number(battery.get("DesignCapacity"))
        if design:
            _add(rows, "Capacité d'origine", f"{int(design)} mWh")
        if full:
            _add(rows, "Capacité à pleine charge", f"{int(full)} mWh", volatile=True)
        if full and design:
            _add(rows, "Usure", f.fmt_percent(max(0.0, 100 - full * 100 / design)), volatile=True)
        sections.append(Section(_numbered("Batterie", index, len(batteries)), rows))
    if not sections:
        note = _error_note(data, "battery") or ("Aucune batterie détectée." if data.get("os") else "")
        sections.append(Section("Batterie", [], note))
    return sections


SOURCE_LABELS = {
    "machine": "modèle de l'ordinateur", "bios": "BIOS", "secureboot": "démarrage sécurisé", "os": "Windows",
    "cpu": "processeur", "board": "carte mère", "ram": "mémoire", "memoryarray": "emplacements mémoire",
    "vram": "mémoire vidéo", "gpu": "carte graphique", "disks": "disques", "disks_fallback": "disques",
    "volumes": "volumes", "bitlocker": "BitLocker", "adapters": "cartes réseau", "network": "configuration IP",
    "temperatures": "températures", "battery": "batterie", "monitors": "écrans", "audio": "audio", "tpm": "TPM",
    "pnp": "périphériques en erreur", "license": "activation Windows",
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
    """Toutes les pages de détail, dans l'ordre de la navigation."""
    return {page: build_page(data, page) for page in DETAIL_PAGES}


def fold(text: str) -> str:
    """Minuscules sans accents, pour une recherche tolérante."""
    decomposed = unicodedata.normalize("NFD", str(text).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def search(data: dict, query: str) -> list[tuple[str, str, Row]]:
    """Lignes dont la page, la section, le libellé ou la valeur contiennent tous les mots cherchés."""
    words = fold(query).split()
    if not words:
        return []
    hits = []
    for page, sections in build_all(data).items():
        for section in sections:
            for row in section.rows:
                haystack = fold(f"{page} {section.title} {row.label} {row.value}")
                if all(word in haystack for word in words):
                    hits.append((page, section.title, row))
    return hits


def diff_reports(before: dict, after: dict) -> list[tuple[str, str, str, str]]:
    """Différences stables entre deux inventaires : (page › section, libellé, avant, après)."""

    def index(data: dict) -> dict[tuple[str, str, str], str]:
        found = {}
        for page, sections in build_all(data).items():
            for section in sections:
                for row in section.rows:
                    if not row.volatile:
                        found[(page, section.title, row.label)] = row.value
        return found

    old, new = index(before), index(after)
    changes = []
    for key in list(old) + [k for k in new if k not in old]:
        if old.get(key) != new.get(key):
            page, section, label = key
            changes.append((f"{page} › {section}", label, old.get(key, EMPTY), new.get(key, EMPTY)))
    return changes


def overview_tiles(data: dict) -> list[tuple[str, str, str]]:
    """Tuiles de la vue d'ensemble : (titre, valeur, détail)."""
    cpu = (data.get("cpu") or [{}])[0]
    gpus = data.get("gpu") or []
    board = data.get("board") or {}
    machine = data.get("machine") or {}
    memory = data.get("memory") or {}
    sticks = data.get("ram") or []
    disks = data.get("disks") or []
    kinds = [f.fmt_media(d.get("MediaType")) for d in disks if d.get("MediaType") not in (None, "")]
    total = sum(f.to_number(d.get("Size")) or 0 for d in disks)
    types = sorted({f.fmt_code(s.get("SMBIOSMemoryType"), f.MEMORY_TYPES) for s in sticks if f.to_number(s.get("SMBIOSMemoryType"))})
    return [
        (
            "Modèle",
            " ".join(p for p in (f.clean(machine.get("Manufacturer")), f.clean(machine.get("Model"))) if p != EMPTY),
            f.clean(machine.get("SystemFamily")) if machine.get("SystemFamily") else "Ordinateur",
        ),
        (
            "Processeur",
            f.clean(cpu.get("Name")),
            f"{f.clean(cpu.get('NumberOfCores'))} cœurs · {f.clean(cpu.get('NumberOfLogicalProcessors'))} threads",
        ),
        (
            "Mémoire vive",
            f.fmt_binary(memory.get("installed")),
            " · ".join([f"{len(sticks)} barrette(s)", *types]),
        ),
        (
            "Carte graphique",
            f.clean(gpus[0].get("Name")) if gpus else EMPTY,
            vram_text(gpus[0]) if gpus and vram_text(gpus[0]) != EMPTY else f"{len(gpus)} adaptateur(s)",
        ),
        (
            "Carte mère",
            " ".join(p for p in (f.clean(board.get("Manufacturer")), f.clean(board.get("Product"))) if p != EMPTY),
            f"BIOS {f.clean((data.get('bios') or {}).get('Version'))}",
        ),
        (
            "Stockage",
            f.fmt_decimal(total) if total else EMPTY,
            " · ".join([f"{len(disks)} disque(s)", *sorted(set(kinds))]),
        ),
    ]
