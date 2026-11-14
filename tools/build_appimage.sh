#!/usr/bin/env bash
# Construit dist/AtlasPCMonitor-<version>-x86_64.AppImage : Atlas PC Monitor en visionneuse de rapports pour Linux.
#
#   pip install -r requirements-dev.txt
#   sudo apt install libxcb-cursor0 squashfs-tools
#   tools/build_appimage.sh
#
# Une AppImage = le « runtime » AppImage (petit lanceur qui monte l'image) suivi d'une image
# squashfs du dossier de l'application. On l'assemble ici sans appimagetool : mksquashfs vient
# des paquets de la distribution, et le runtime officiel est épinglé à une version datée dont
# l'empreinte SHA-256 est vérifiée. Il n'est jamais exécuté pendant la construction.
#
# Une AppImage tourne sur les distributions dont la glibc est au moins celle de la machine
# de construction : la CI la construit sur Ubuntu 22.04 (glibc 2.35) pour en couvrir le plus.
#
# Builds dist/AtlasPCMonitor-<version>-x86_64.AppImage: Atlas PC Monitor as a report viewer for Linux
# (commands above).
#
# An AppImage = the AppImage "runtime" (a small launcher that mounts the image) followed by a
# squashfs image of the application folder. It is assembled here without appimagetool: mksquashfs
# comes from the distribution's packages, and the official runtime is pinned to a dated version
# whose SHA-256 fingerprint is checked. It is never run during the build.
#
# An AppImage runs on distributions whose glibc is at least that of the build machine: the CI
# builds it on Ubuntu 22.04 (glibc 2.35) to cover as many as possible.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH=x86_64
RUNTIME_VERSION=20251108
RUNTIME_SHA256=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d
RUNTIME_URL=https://github.com/AppImage/type2-runtime/releases/download/$RUNTIME_VERSION/runtime-$ARCH

VERSION=$(python3 -c "import atlas; print(atlas.__version__)")
APPDIR=build/AtlasPCMonitor.AppDir
RUNTIME=build/runtime-$ARCH-$RUNTIME_VERSION
TARGET="dist/AtlasPCMonitor-$VERSION-$ARCH.AppImage"

for need in mksquashfs pyinstaller; do
    command -v "$need" >/dev/null || { echo "$need manque (voir l'en-tête de ce script)." >&2; exit 1; }
done
if ! ldconfig -p | grep -q libxcb-cursor.so.0; then
    echo "libxcb-cursor0 manque : l'AppImage ne s'ouvrirait pas sur les postes qui n'en ont pas." >&2
    echo "Installez-le (sudo apt install libxcb-cursor0) puis relancez." >&2
    exit 1
fi

mkdir -p build dist
if [ ! -f "$RUNTIME" ]; then
    echo "Téléchargement du runtime AppImage $RUNTIME_VERSION…"
    curl -fsSL -o "$RUNTIME.part" "$RUNTIME_URL"
    mv "$RUNTIME.part" "$RUNTIME"
fi
if ! echo "$RUNTIME_SHA256  $RUNTIME" | sha256sum --check --status; then
    echo "Empreinte inattendue pour $RUNTIME : fichier supprimé, relancez pour le retélécharger." >&2
    rm -f -- "$RUNTIME"
    exit 1
fi

echo "1/3 PyInstaller…"
pyinstaller atlas_pc.spec --noconfirm --log-level WARN

echo "2/3 Dossier de l'application…"
rm -rf -- "$APPDIR"  # dossier de construction de ce script uniquement — this script's build folder only
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a dist/AtlasPCMonitor "$APPDIR/usr/lib/atlas-pc-monitor"
install -m 755 packaging/linux/AppRun "$APPDIR/AppRun"
install -m 644 packaging/linux/atlas-pc-monitor.desktop "$APPDIR/atlas-pc-monitor.desktop"
cp "$APPDIR/atlas-pc-monitor.desktop" "$APPDIR/usr/share/applications/"
QT_QPA_PLATFORM=offscreen python3 tools/make_icon.py "$APPDIR/atlas-pc-monitor.png" 256
cp "$APPDIR/atlas-pc-monitor.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
ln -sf atlas-pc-monitor.png "$APPDIR/.DirIcon"

echo "3/3 Image squashfs + runtime…"
image=build/AtlasPCMonitor.squashfs
rm -f -- "$image"
mksquashfs "$APPDIR" "$image" -root-owned -noappend -comp zstd -Xcompression-level 19 -quiet
cat "$RUNTIME" "$image" > "$TARGET.part"
chmod +x "$TARGET.part"
mv "$TARGET.part" "$TARGET"
echo "AppImage : $TARGET ($(du -h "$TARGET" | cut -f1))"
