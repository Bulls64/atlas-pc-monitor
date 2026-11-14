# Recette PyInstaller, sous Windows comme sous Linux (où tools/build_appimage.sh en fait une AppImage).
#   pip install -r requirements-dev.txt
#   pyinstaller atlas_pc.spec --noconfirm                            → dossier dist/AtlasPCMonitor/ (« onedir »)
#   set "ATLAS_ONEFILE=1" && pyinstaller atlas_pc.spec --noconfirm   → fichier unique dist/AtlasPCMonitor.exe
# Le dossier démarre plus vite et alerte moins les antivirus ; le fichier unique est plus simple à
# transporter (il se décompresse dans le dossier temporaire à chaque lancement).
# Icône Windows : python tools/make_icon.py build/atlas-pc-monitor.ico (Pillow), reprise si elle existe.
# L'exécutable est fenêtré : en ligne de commande, utiliser -o, par exemple
#   AtlasPCMonitor.exe --json -o rapport.json
# PyInstaller recipe, on Windows as on Linux (where tools/build_appimage.sh turns it into an AppImage).
# The commands above build the dist/AtlasPCMonitor/ folder ("onedir") or, with ATLAS_ONEFILE=1,
# the single file dist/AtlasPCMonitor.exe. The folder starts faster and triggers fewer antivirus
# alerts; the single file is easier to carry around (it unpacks itself into the temporary folder
# at every launch).
# Windows icon: python tools/make_icon.py build/atlas-pc-monitor.ico (Pillow), used if it exists.
# The executable is windowed: on the command line, use -o, for example
#   AtlasPCMonitor.exe --json -o report.json

import os

a = Analysis(
    ["atlas_pc.py"],
    pathex=[],
    binaries=[],
    datas=[("atlas/gui/fonts", "atlas/gui/fonts")],  # polices OFL et leurs licences — OFL fonts and their licenses
    hiddenimports=["atlas.locale_en"],  # catalogue anglais, importé seulement à la demande — English catalog, imported only on demand
    excludes=["pytest", "pytestqt", "tkinter"],
)

# Modules Qt tirés par des greffons mais inutiles ici (QML, Quick, clavier virtuel, PDF, Wayland :
# sous Linux l'AppImage passe par X11/XWayland) : les retirer allège nettement le dossier.
# Seule la traduction française de Qt est gardée.
# Qt modules pulled in by plugins but useless here (QML, Quick, virtual keyboard, PDF, Wayland:
# on Linux the AppImage goes through X11/XWayland): removing them makes the folder much lighter.
# Only Qt's French translation is kept.
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
