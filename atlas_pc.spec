# Recette PyInstaller : produit le dossier dist/AtlasPC/ (mode « onedir »).
#   pip install pyinstaller
#   pyinstaller atlas_pc.spec --noconfirm
# Distribuer le dossier entier (zippé). Le mode onedir est préféré au fichier unique
# (onefile), dont l'extraction temporaire déclenche plus souvent antivirus et SmartScreen.
# L'exécutable est fenêtré : en ligne de commande, utiliser -o, par exemple
#   AtlasPC.exe --json -o rapport.json

a = Analysis(["atlas_pc.py"], pathex=[], binaries=[], datas=[], hiddenimports=[], excludes=["pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AtlasPC", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="AtlasPC")
