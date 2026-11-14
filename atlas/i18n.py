"""Langue de l'interface : français (langue du code source) ou anglais.

Chaque texte affiché passe par `_()` : en anglais, il est remplacé par sa traduction du catalogue
`atlas/locale_en.py` ; en français, il est rendu tel quel. Les textes définis au chargement d'un
module (tables de codes, noms de pages) sont seulement marqués par `N_()` et traduits à l'affichage,
car la langue peut changer pendant que l'application tourne.

    _("Mémoire")                          → « Memory » en anglais
    _("{0} barrette(s)", 2)               → « 2 module(s) »
    N_("pilote non installé")             → marqué pour le catalogue, traduit plus tard par _()
"""

from __future__ import annotations

import locale
import os

LANGUAGES = {"fr": "Français", "en": "English"}
DEFAULT = "fr"

_current = DEFAULT
_catalog: dict[str, str] | None = None


def language() -> str:
    return _current


def set_language(code: str | None) -> str:
    """Change la langue (code inconnu → français). Renvoie la langue retenue."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT
    return _current


def is_english() -> bool:
    return _current == "en"


def _english() -> dict[str, str]:
    global _catalog
    if _catalog is None:
        from .locale_en import EN

        _catalog = EN
    return _catalog


def _(text: str, *args, **kwargs) -> str:
    """Texte dans la langue courante, puis complété par format() s'il reçoit des valeurs."""
    if _current == "en":
        text = _english().get(text, text)
    return text.format(*args, **kwargs) if args or kwargs else text


def N_(text: str) -> str:
    """Marque un texte pour le catalogue sans le traduire (il le sera à l'affichage)."""
    return text


def system_language() -> str:
    """Langue du système : français si l'interface de Windows (ou la locale) est en français, sinon anglais."""
    names = [os.environ.get(name, "") for name in ("LC_ALL", "LC_MESSAGES", "LANG")]
    if os.name == "nt":
        try:
            import ctypes

            names.append(locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), ""))
        except (AttributeError, OSError):
            pass
    try:
        names.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    for name in names:
        name = name.lower()
        if name and name not in ("c", "posix") and not name.startswith("c."):
            return "fr" if name.startswith(("fr", "french")) else "en"
    return DEFAULT
