"""Écrit l'icône d'Atlas PC en PNG (AppImage, raccourcis) à partir du logo dessiné par l'interface.

QT_QPA_PLATFORM=offscreen python tools/make_icon.py atlas-pc.png 256
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from atlas.gui.widgets import logo_pixmap  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print("usage : make_icon.py FICHIER.png [TAILLE]", file=sys.stderr)
        return 2
    size = int(argv[1]) if len(argv) > 1 else 256
    app = QApplication.instance() or QApplication([])  # noqa: F841 — QPixmap exige une application
    if not logo_pixmap(size, ratio=1.0).save(argv[0], "PNG"):  # taille exacte, pas de double résolution
        print(f"Impossible d'écrire {argv[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
