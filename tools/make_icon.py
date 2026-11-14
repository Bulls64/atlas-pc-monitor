"""Écrit l'icône d'Atlas PC Monitor à partir du logo dessiné par l'interface.

QT_QPA_PLATFORM=offscreen python tools/make_icon.py atlas-pc-monitor.png 256   PNG (AppImage)
QT_QPA_PLATFORM=offscreen python tools/make_icon.py atlas-pc-monitor.ico       ICO multi-tailles (Windows, Pillow)
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
    target = Path(argv[0])
    size = int(argv[1]) if len(argv) > 1 else 256
    app = QApplication.instance() or QApplication([])  # noqa: F841 — QPixmap exige une application
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".ico":
        return _write_ico(target)
    if not logo_pixmap(size, ratio=1.0).save(str(target), "PNG"):  # taille exacte, pas de double résolution
        print(f"Impossible d'écrire {target}", file=sys.stderr)
        return 1
    return 0


ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _write_ico(target: Path) -> int:
    """Une image par taille, chacune dessinée à sa taille (net en petit, contrairement à une réduction)."""
    import io

    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice

    images = []
    for size in ICO_SIZES:
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        logo_pixmap(size, ratio=1.0).save(buffer, "PNG")
        images.append(Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA"))
    images[-1].save(target, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=images[:-1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
