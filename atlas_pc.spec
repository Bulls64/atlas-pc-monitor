# Recette PyInstaller : produit dist/AtlasPC.exe, autonome, sans Python installé.
#   pip install pyinstaller
#   pyinstaller atlas_pc.spec
# L'exécutable est fenêtré (pas de console) : en ligne de commande, utilisez -o,
# par exemple  AtlasPC.exe --json -o rapport.json

a = Analysis(["atlas_pc.py"], pathex=[], binaries=[], datas=[], hiddenimports=[], excludes=["pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="AtlasPC", console=False, upx=False)
