# Recette PyInstaller : produit le dossier dist/AtlasPC/ (mode « onedir »), sous Windows comme
# sous Linux (où tools/build_appimage.sh en fait une AppImage).
#   pip install -r requirements-dev.txt
#   pyinstaller atlas_pc.spec --noconfirm
# Distribuer le dossier entier (zippé). Le mode onedir est préféré au fichier unique
# (onefile), dont l'extraction temporaire déclenche plus souvent antivirus et SmartScreen.
# L'exécutable est fenêtré : en ligne de commande, utiliser -o, par exemple
#   AtlasPC.exe --json -o rapport.json

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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AtlasPC", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="AtlasPC")
