# Recette PyInstaller, sous Windows comme sous Linux (où tools/build_appimage.sh en fait une AppImage).
#   pip install -r requirements-dev.txt
#   pyinstaller atlas_pc.spec --noconfirm                            → dossier dist/AtlasPCMonitor/ (« onedir »)
#   set "ATLAS_ONEFILE=1" && pyinstaller atlas_pc.spec --noconfirm   → fichier unique dist/AtlasPCMonitor.exe
# Le dossier démarre plus vite et alerte moins les antivirus ; le fichier unique est plus simple à
# transporter (il se décompresse dans le dossier temporaire à chaque lancement).
# Icône Windows : python tools/make_icon.py build/atlas-pc-monitor.ico (Pillow), reprise si elle existe.
# L'exécutable est fenêtré : en ligne de commande, utiliser -o, par exemple
#   AtlasPCMonitor.exe --json -o rapport.json

import os

a = Analysis(
    ["atlas_pc.py"],
    pathex=[],
    binaries=[],
    datas=[("atlas/gui/fonts", "atlas/gui/fonts")],  # polices OFL et leurs licences
    hiddenimports=[],
    excludes=["pytest", "pytestqt", "tkinter"],
)

# Modules Qt tirés par des greffons mais inutiles ici (QML, Quick, clavier virtuel, PDF, Wayland :
# sous Linux l'AppImage passe par X11/XWayland) : les retirer allège nettement le dossier.
# Seule la traduction française de Qt est gardée.
UNUSED = ("qt6qml", "qt6quick", "virtualkeyboard", "qt6pdf", "qpdf", "/qml/", "webengine", "wayland", "eglfs")


def keep(entry):
    name = entry[0].replace("\\", "/").lower()
    if any(word in name for word in UNUSED):
        return False
    if "/translations/" in name and not name.endswith(("qtbase_fr.qm", "qt_fr.qm")):
        return False
    return True


a.binaries = [entry for entry in a.binaries if keep(entry)]
a.datas = [entry for entry in a.datas if keep(entry)]

pyz = PYZ(a.pure)
ICON = "build/atlas-pc-monitor.ico" if os.path.exists("build/atlas-pc-monitor.ico") else None

if os.environ.get("ATLAS_ONEFILE", "").strip() == "1":
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="AtlasPCMonitor", console=False, upx=False, icon=ICON)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AtlasPCMonitor", console=False, upx=False, icon=ICON)
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="AtlasPCMonitor")
