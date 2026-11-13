"""Point d'entrée : interface graphique par défaut, ou rapport sur la sortie standard."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from . import __version__, export, fiche, privacy
from .collect import scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas_pc", description="Atlas PC — inventaire matériel Windows.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="imprime l'inventaire en JSON, sans interface")
    group.add_argument("--text", action="store_true", help="imprime le rapport texte, sans interface")
    group.add_argument("--html", action="store_true", help="imprime le rapport HTML, sans interface")
    group.add_argument("--fiche", action="store_true", help="fiche d'intervention HTML imprimable, sans interface")
    parser.add_argument("--anonyme", action="store_true", help="masque nom du poste, numéros de série, MAC et IP")
    parser.add_argument("--technicien", default="", help="nom du technicien sur la fiche")
    parser.add_argument("--client", default="", help="nom du client sur la fiche")
    parser.add_argument("--reference", default="", help="référence de l'intervention sur la fiche")
    parser.add_argument("-o", "--output", metavar="FICHIER", help="écrit le rapport dans ce fichier (.json, .txt ou .html)")
    parser.add_argument("--debug", action="store_true", help="journal détaillé dans le dossier temporaire (atlas-debug.log)")
    parser.add_argument("--version", action="version", version=f"Atlas PC {__version__}")
    return parser


def setup_logging(debug: bool) -> Path | None:
    if not debug:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
        return None
    path = Path(tempfile.gettempdir()) / "atlas-debug.log"
    logging.basicConfig(level=logging.DEBUG, filename=path, filemode="w", encoding="utf-8", format="%(asctime)s %(levelname)s %(message)s")
    return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_path = setup_logging(args.debug)
    if log_path:
        print(f"Journal de débogage : {log_path}", file=sys.stderr)
    if not (args.json or args.text or args.html or args.fiche or args.output):
        try:
            from .gui.app import run  # PySide6 n'est chargé que pour l'interface
        except ImportError as error:
            print(
                f"L'interface demande PySide6 ({error}).\n"
                "Installez-le avec :  python -m pip install -r requirements.txt\n"
                "(lancer_atlas.bat le fait automatiquement)",
                file=sys.stderr,
            )
            return 3
        return run()
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
            print(f"Impossible d'écrire {target} : {error.strerror or error}", file=sys.stderr)
            return 2
        print(f"{'Fiche enregistrée' if args.fiche else 'Rapport enregistré'} : {target}", file=sys.stderr)
    else:
        if sys.stdout is None:  # exécutable sans console : il faut passer par -o
            return 2
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(content(forced).rstrip("\n") + "\n")
    return 1 if data.get("note") and "os" not in data and sys.platform == "win32" else 0


if __name__ == "__main__":
    sys.exit(main())
