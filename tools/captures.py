"""Régénère les captures d'écran du README à partir de l'inventaire d'exemple des tests.

Usage : python tools/captures.py [dossier]   (par défaut docs/captures)

Fonctionne sans écran (plateforme Qt « offscreen »). Les données sont celles de
tests/conftest.py : aucune information d'un vrai poste ne finit dans le dépôt.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp()  # préférences jetables : thème sombre au départ

from conftest import PAYLOAD  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from atlas import collect, fiche  # noqa: E402

WIDTH, HEIGHT = 1320, 900
HOST = "POSTE-CLIENT-01"


def sample_scan() -> dict:
    payload = copy.deepcopy(PAYLOAD)
    payload["pnp"] = []
    data = collect.scan(runner=lambda: (0, json.dumps(payload), ""))
    data["system"]["computer"] = HOST
    data["captured_at"] = "2026-11-13T10:30:00+01:00"
    data["scan_seconds"] = 4.1
    return data


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def save(widget, path: Path, full: bool = False) -> None:
    """Capture la fenêtre ; « full » l'agrandit pour montrer toute la page."""
    window = widget.window()
    if full:
        window.resize(WIDTH, max(HEIGHT, window.scroll.widget().sizeHint().height() + 200))
        wait(300)
    image = widget.grab().toImage()
    if full:  # recadre sous le dernier élément de la page
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QWidget

        widgets = window.scroll.widget().findChildren(QWidget)
        leaves = [w for w in widgets if w.isVisible() and (not w.findChildren(QWidget) or w.property("card"))]
        bottom = max((w.mapTo(window, QPoint(0, w.height())).y() for w in leaves), default=image.height())
        image = image.copy(0, 0, image.width(), min(image.height(), bottom + 40))
    tmp = path.with_suffix(".tmp.png")
    image.save(str(tmp))
    window.resize(WIDTH, HEIGHT)
    # Couleurs complètes : une palette réduite confond le rouge « à corriger » et l'orange « à surveiller ».
    Image.open(tmp).convert("RGB").save(path, optimize=True)
    tmp.unlink()
    print(f"{path.name:28} {path.stat().st_size // 1024} Ko")


def fiche_a4(win, info, out: Path) -> None:
    """Fiche imprimée, rendue par Chrome ou Edge s'il est installé (sinon ignorée)."""
    browser = next((b for b in ("google-chrome", "chromium", "chrome", "msedge") if shutil.which(b)), None)
    if not browser:
        print("fiche-a4.png : aucun Chrome/Edge trouvé, capture ignorée")
        return
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "fiche.html"
        page.write_text(
            win.fiche_html(info).replace('<div class="toolbar">', '<div class="toolbar" style="display:none">'), encoding="utf-8"
        )
        shot = Path(tmp) / "fiche.png"
        subprocess.run([browser, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--screenshot={shot}",
                        "--window-size=900,1240", page.as_uri()], check=True, capture_output=True, timeout=60)  # fmt: skip
        image = Image.open(shot).convert("RGB")
        page_box = ImageChops.difference(image, Image.new("RGB", image.size, image.getpixel((2, 2)))).getbbox()
        if page_box:  # recadre sur la feuille, avec une petite marge
            left, top, right, bottom = page_box
            image = image.crop((max(0, left - 24), max(0, top - 24), min(image.width, right + 24), min(image.height, bottom + 24)))
        image.save(out / "fiche-a4.png", optimize=True)
    print(f"{'fiche-a4.png':28} {(out / 'fiche-a4.png').stat().st_size // 1024} Ko")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "captures"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])  # noqa: F841 (doit vivre jusqu'à la fin)
    from atlas.gui import theme, window

    theme.load_fonts()
    collect.is_windows = lambda: True
    win = window.MainWindow(scanner=sample_scan)
    win.resize(WIDTH, HEIGHT)
    win.show()
    wait(800)

    win.open_page("Vue d'ensemble")
    save(win, out / "vue-ensemble.png", full=True)
    win.open_page("Constats")
    save(win, out / "constats.png", full=True)
    win.open_page("Stockage")
    save(win, out / "stockage.png")
    win.toggle_sharing()
    win.open_page("Carte mère")
    wait(200)
    save(win, out / "mode-partage.png")
    win.toggle_sharing()

    win.toggle_theme()
    wait(300)
    win.open_page("Vue d'ensemble")
    save(win, out / "vue-ensemble-clair.png", full=True)
    win.open_page("Mémoire")
    save(win, out / "memoire-clair.png", full=True)
    win.toggle_theme()
    wait(300)

    info = fiche.FicheInfo(
        technician="Chris", client="Mme Dupont", contact="06 12 34 56 78", reference="INT-20261113-1030",
        request="Le PC est lent au démarrage et la batterie tient peu.",
        work="Contrôle SMART du disque ST1000LM035.\nNettoyage des programmes au démarrage.",
    )  # fmt: skip
    win.open_fiche()
    dialog = win.fiche_dialog
    for key, entry in dialog.entries.items():
        entry.setText(getattr(info, key))
    dialog.texts["request"].setPlainText(info.request)
    dialog.texts["work"].setPlainText(info.work)
    dialog.insert_advice(dialog.texts["recommendations"])
    wait(200)
    image = dialog.grab().toImage()
    image.save(str(out / "fiche.tmp.png"))
    Image.open(out / "fiche.tmp.png").convert("RGB").save(out / "fiche.png", optimize=True)
    (out / "fiche.tmp.png").unlink()
    print(f"{'fiche.png':28} {(out / 'fiche.png').stat().st_size // 1024} Ko")
    fiche_a4(win, dialog.collect(), out)
    dialog.close()
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
