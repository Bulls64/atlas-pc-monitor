"""Mode partage : copie de l'inventaire sans les identifiants d'un poste précis.

Masqué : nom du poste, domaine, numéros de série (machine, carte mère, barrettes,
disques, écrans), fin des adresses MAC, fin des adresses IPv4, adresses IPv6.
Conservé : tout ce qui sert au diagnostic (modèles, capacités, versions, états).
"""

from __future__ import annotations

import copy
import ipaddress
import re

from .i18n import N_, _

# Valeurs de remplacement, écrites dans la langue courante au moment du masquage.
MASK = N_("[masqué]")
HOST_MASK = N_("POSTE-MASQUÉ")

# (section, champ) des numéros de série et identifiants à masquer entièrement.
SERIAL_FIELDS = (
    ("bios", "SerialNumber"),
    ("board", "SerialNumber"),
    ("ram", "SerialNumber"),
    ("disks", "SerialNumber"),
    ("monitors", "SerialNumber"),
)
_MAC = re.compile(r"^([0-9A-Fa-f]{2})[-:]([0-9A-Fa-f]{2})[-:]([0-9A-Fa-f]{2})[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}$")


def mask_mac(value) -> str:
    """Garde le préfixe du fabricant (OUI), masque la partie propre à la carte."""
    text = str(value or "").strip()
    match = _MAC.match(text)
    if not match:
        return _(MASK) if text else text
    sep = "-" if "-" in text else ":"
    return sep.join([*match.groups(), "xx", "xx", "xx"])


def mask_ip(value) -> str:
    """IPv4 : dernier octet masqué (le sous-réseau reste lisible). IPv6 : masquée entièrement."""
    masked = []
    for part in str(value or "").split(","):
        address = part.strip()
        if not address:
            continue
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            masked.append(_(MASK))
            continue
        if ip.version == 4:
            masked.append(".".join(address.split(".")[:3] + ["x"]))
        else:
            masked.append("fe80::" + _(MASK) if ip.is_link_local else _(MASK))
    return ", ".join(masked)


def _rows(section) -> list[dict]:
    if isinstance(section, dict):
        return [section]
    return [item for item in section or [] if isinstance(item, dict)]


def anonymize(data: dict) -> dict:
    """Copie masquée de l'inventaire ; l'original n'est pas modifié."""
    if not isinstance(data, dict) or data.get("anonymized"):
        return data
    shared = copy.deepcopy(data)
    shared["anonymized"] = True
    host = shared.get("system")
    if isinstance(host, dict) and host.get("computer"):
        host["computer"] = _(HOST_MASK)
    machine = shared.get("machine")
    if isinstance(machine, dict) and machine.get("PartOfDomain") and machine.get("Domain"):
        machine["Domain"] = _(MASK)
    for section, key in SERIAL_FIELDS:
        for row in _rows(shared.get(section)):
            if str(row.get(key) or "").strip():
                row[key] = _(MASK)
    for adapter in _rows(shared.get("adapters")):
        if adapter.get("MacAddress"):
            adapter["MacAddress"] = mask_mac(adapter["MacAddress"])
    for config in _rows(shared.get("network")):
        for key in ("IPv4", "IPv6", "Gateway", "DNS"):
            if config.get(key):
                config[key] = mask_ip(config[key])
    return shared
