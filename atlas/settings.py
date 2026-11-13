"""Préférences de l'utilisateur et relance de l'application (sans dépendance graphique)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("atlas")


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "AtlasPC" / "config.json"


def load_config() -> dict:
    try:
        config = json.loads(config_path().read_text(encoding="utf-8"))
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    try:
        config_path().parent.mkdir(parents=True, exist_ok=True)
        config_path().write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        log.warning("Préférences non enregistrées : %s", error)


def relaunch_command() -> tuple[str, list[str]]:
    """Exécutable et arguments pour relancer l'application à l'identique."""
    if getattr(sys, "frozen", False):
        return sys.executable, sys.argv[1:]
    executable = sys.executable
    windowed = Path(executable).with_name("pythonw.exe")
    if windowed.is_file():
        executable = str(windowed)
    main_module = sys.modules.get("__main__")
    if getattr(main_module, "__spec__", None) is not None:  # lancé par « python -m atlas »
        return executable, ["-m", "atlas", *sys.argv[1:]]
    return executable, [os.path.abspath(sys.argv[0]), *sys.argv[1:]]


def relaunch_as_admin() -> bool:
    """Relance l'application élevée (invite UAC). Vrai si la nouvelle instance a démarré."""
    if os.name != "nt":
        return False
    import ctypes

    executable, arguments = relaunch_command()
    code = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, subprocess.list2cmdline(arguments), os.getcwd(), 1)
    return code > 32
