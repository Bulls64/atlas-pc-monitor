"""Nouveautés d'une version, lues dans le CHANGELOG.md livré avec l'application.

Module sans interface. Le CHANGELOG est embarqué dans l'exe, le dossier et l'AppImage (atlas_pc.spec) ;
depuis les sources, c'est celui du dépôt. La fenêtre « Nouveautés » s'ouvre au premier lancement qui suit
une mise à jour : la dernière version vue est mémorisée dans les préférences (« last_version »).

What's new in a version, read from the CHANGELOG.md shipped with the application.

Module with no interface. The CHANGELOG is embedded in the exe, the folder and the AppImage
(atlas_pc.spec); from source, it is the repository's. The "What's new" window opens at the first launch
after an update: the last version seen is kept in the preferences ("last_version").
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from . import __version__
from .update import notes_for

UNRELEASED = "Unreleased"


def path() -> Path:
    """CHANGELOG.md : dans le paquet PyInstaller, sinon à la racine du dépôt.

    CHANGELOG.md: inside the PyInstaller bundle, otherwise at the root of the repository.
    """
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "CHANGELOG.md" if base else Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def read() -> str:
    try:
        return path().read_text(encoding="utf-8")
    except OSError:
        return ""


def section(text: str, version: str) -> str:
    """Section « ## [version] » du CHANGELOG, sans son titre ni les liens de fin de fichier.

    "## [version]" section of the CHANGELOG, without its heading or the end-of-file links.
    """
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("## ["):
            if inside:
                break
            inside = line.startswith(f"## [{version}]")
        elif inside and not re.match(r"^\[[^\]]+\]:\s", line):
            lines.append(line)
    return "\n".join(lines).strip()


def notes(language: str, version: str = __version__, text: str | None = None) -> str:
    """Nouveautés de la version dans la langue voulue ; depuis les sources, « Unreleased » à défaut.

    What's new in the version, in the requested language; from source, "Unreleased" as a fallback.
    """
    text = read() if text is None else text
    body = section(text, version) or (section(text, UNRELEASED) if not getattr(sys, "frozen", False) else "")
    return notes_for(body, language) if body else ""


def should_show(config: dict, version: str = __version__) -> bool:
    """Vrai au premier lancement d'une nouvelle version ; mémorise la version vue dans config.

    Une première installation ne montre rien : il n'y a pas encore de « nouveautés » pour l'utilisateur.

    True at the first launch of a new version; records the version seen in config.

    A first installation shows nothing: there is nothing "new" for the user yet.
    """
    previous = config.get("last_version")
    config["last_version"] = version
    return bool(previous) and previous != version
