"""Point d'entrée : interface graphique par défaut, ou rapport sur la sortie standard."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from . import __version__, collect, export, fiche, i18n, privacy, settings
from .collect import scan
from .i18n import _


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas_pc", description=_("Atlas PC Monitor — inventaire matériel Windows."))
    parser.add_argument(
        "rapport",
        nargs="?",
        help=_("rapport JSON d'Atlas PC Monitor à ouvrir ou à convertir au lieu d'analyser ce poste (seul usage possible hors Windows)"),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help=_("imprime l'inventaire en JSON, sans interface"))
    group.add_argument("--text", action="store_true", help=_("imprime le rapport texte, sans interface"))
    group.add_argument("--html", action="store_true", help=_("imprime le rapport HTML, sans interface"))
    group.add_argument("--fiche", action="store_true", help=_("fiche d'intervention HTML imprimable, sans interface"))
    parser.add_argument("--anonyme", action="store_true", help=_("masque nom du poste, numéros de série, MAC et IP"))
    parser.add_argument("--technicien", default="", help=_("nom du technicien sur la fiche"))
    parser.add_argument("--client", default="", help=_("nom du client sur la fiche"))
    parser.add_argument("--reference", default="", help=_("référence de l'intervention sur la fiche"))
    parser.add_argument("-o", "--output", metavar=_("FICHIER"), help=_("écrit le rapport dans ce fichier (.json, .txt ou .html)"))
    parser.add_argument("--debug", action="store_true", help=_("journal détaillé dans le dossier temporaire (atlas-debug.log)"))
    parser.add_argument(
        "--lang",
        choices=sorted(i18n.LANGUAGES),
        help=_("langue de l'interface et des rapports (par défaut : préférence enregistrée, sinon celle du système)"),
    )
    parser.add_argument("--version", action="version", version=f"Atlas PC Monitor {__version__}")
    return parser


def setup_logging(debug: bool) -> Path | None:
    if not debug:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
        return None
    path = Path(tempfile.gettempdir()) / "atlas-debug.log"
    logging.basicConfig(level=logging.DEBUG, filename=path, filemode="w", encoding="utf-8", format="%(asctime)s %(levelname)s %(message)s")
    return path


def requested_language(argv: list[str]) -> str:
    """Valeur de --lang, lue avant l'analyse des arguments pour que l'aide (--help) soit déjà traduite."""
    for index, arg in enumerate(argv):
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
        if arg == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    i18n.set_language(requested_language(argv) or settings.preferred_language())
    args = build_parser().parse_args(argv)
    log_path = setup_logging(args.debug)
    if log_path:
        print(_("Journal de débogage : {0}", log_path), file=sys.stderr)
    if not (args.json or args.text or args.html or args.fiche or args.output):
        try:
            from .gui.app import run  # PySide6 n'est chargé que pour l'interface
        except ImportError as error:
            print(
                _(
                    "L'interface demande PySide6 ({0}).\n"
                    "Installez-le avec :  python -m pip install -r requirements.txt\n"
                    "(lancer_atlas.bat le fait automatiquement)",
                    error,
                ),
                file=sys.stderr,
            )
            return 3
        return run(args.rapport)
    if args.rapport:
        try:
            data = export.load(args.rapport)
        except (OSError, ValueError) as error:
            print(_("Rapport illisible : {0} ({1})", args.rapport, error), file=sys.stderr)
            return 2
    else:
        data = scan()
    if args.anonyme:
        data = privacy.anonymize(data)
    forced = ".txt" if args.text else ".html" if args.html or args.fiche else ".json" if args.json else ""

    def content(suffix: str) -> str:
        if args.fiche:
            info = fiche.FicheInfo(technician=args.technicien, client=args.client, reference=args.reference)
            return fiche.to_html(data, info)
        return export.render(data, suffix)

    if args.output:
        target = Path(args.output) if forced else export.resolve_path(args.output)
        try:
            target.write_text(content(forced or target.suffix), encoding="utf-8")
        except OSError as error:
            print(_("Impossible d'écrire {0} : {1}", target, error.strerror or error), file=sys.stderr)
            return 2
        saved = _("Fiche enregistrée : {0}") if args.fiche else _("Rapport enregistré : {0}")
        print(saved.format(target), file=sys.stderr)
    else:
        if sys.stdout is None:  # exécutable sans console : il faut passer par -o
            return 2
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(content(forced).rstrip("\n") + "\n")
    # Sous Windows, un inventaire sans section « os » est un échec de collecte : code 1 pour les scripts.
    return 1 if data.get("note") and "os" not in data and collect.is_windows() else 0


if __name__ == "__main__":
    sys.exit(main())
