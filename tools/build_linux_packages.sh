#!/bin/sh
# Construit les paquets Linux d'Atlas PC Monitor (visionneuse de rapports, comme l'AppImage) :
#   dist/atlas-pc-monitor_<version>-1_amd64.deb      Debian, Ubuntu, Linux Mint…
#   dist/atlas-pc-monitor-<version>-1.x86_64.rpm     Fedora, openSUSE, RHEL/Alma/Rocky 10…
#
#   tools/build_linux_packages.sh          (relance PyInstaller si dist/AtlasPCMonitor/ manque)
#
# Outils : dpkg-deb et rpmbuild (sur Debian/Ubuntu : sudo apt install rpm), PyInstaller.
# Les paquets installent l'application dans /opt/atlas-pc-monitor, la commande atlas-pc-monitor,
# une entrée de menu, son icône, et la licence avec les mentions tierces dans /usr/share/doc.
#
# Dépendances : la version empaquetée embarque Qt et la plupart des bibliothèques ; celles qu'elle
# prend au système (OpenGL/EGL, xcb, wayland, libc…) sont relevées avec ldd sur la machine de
# construction, puis déclarées par paquet Debian (.deb) ou par nom de bibliothèque (.rpm), ce qui
# vaut pour toutes les distributions RPM. Construire sur Ubuntu 22.04 (glibc 2.35), comme la CI.
#
# Builds the Atlas PC Monitor Linux packages (report viewer, like the AppImage):
#   dist/atlas-pc-monitor_<version>-1_amd64.deb      Debian, Ubuntu, Linux Mint…
#   dist/atlas-pc-monitor-<version>-1.x86_64.rpm     Fedora, openSUSE, RHEL/Alma/Rocky 10…
#
#   tools/build_linux_packages.sh          (reruns PyInstaller if dist/AtlasPCMonitor/ is missing)
#
# Tools: dpkg-deb and rpmbuild (on Debian/Ubuntu: sudo apt install rpm), PyInstaller.
# The packages install the application in /opt/atlas-pc-monitor, the atlas-pc-monitor command,
# a menu entry, its icon, and the license with the third-party notices in /usr/share/doc.
#
# Dependencies: the packaged version embeds Qt and most libraries; the ones it takes from the system
# (OpenGL/EGL, xcb, wayland, libc…) are found with ldd on the build machine, then declared by Debian
# package (.deb) or by library name (.rpm), which works on every RPM distribution. Build on Ubuntu
# 22.04 (glibc 2.35), like the CI.
set -eu
cd "$(dirname "$0")/.."

NAME=atlas-pc-monitor
VERSION=$(python3 -c "import atlas; print(atlas.__version__)")
RELEASE=1
BUNDLE=dist/AtlasPCMonitor
ROOT=build/linux-packages/root
DEB="dist/${NAME}_${VERSION}-${RELEASE}_amd64.deb"
RPM="dist/${NAME}-${VERSION}-${RELEASE}.x86_64.rpm"
SUMMARY="Hardware inventory viewer for Atlas PC Monitor reports"
HOMEPAGE=https://github.com/Bulls64/atlas-pc-monitor
MAINTAINER="Bulls64 <45872843+Bulls64@users.noreply.github.com>"

for need in dpkg-deb dpkg-query rpmbuild ldd; do
    command -v "$need" >/dev/null || { echo "$need manque (voir l'en-tête de ce script)." >&2; exit 1; }
done
if [ ! -x "$BUNDLE/AtlasPCMonitor" ]; then
    echo "PyInstaller…"
    pyinstaller atlas_pc.spec --noconfirm --log-level WARN
fi

echo "1/4 Arborescence du paquet…"
rm -rf -- build/linux-packages  # dossier de construction de ce script uniquement — this script's build folder only
mkdir -p "$ROOT/opt" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
    "$ROOT/usr/share/icons/hicolor/256x256/apps" "$ROOT/usr/share/doc/$NAME"
cp -a "$BUNDLE" "$ROOT/opt/$NAME"
install -m 755 packaging/linux/atlas-pc-monitor "$ROOT/usr/bin/$NAME"
# Même entrée de menu que l'AppImage, lancée par la commande installée.
# Same menu entry as the AppImage, started by the installed command.
sed "s|^Exec=.*|Exec=$NAME %f|" packaging/linux/atlas-pc-monitor.desktop > "$ROOT/usr/share/applications/$NAME.desktop"
QT_QPA_PLATFORM=offscreen python3 tools/make_icon.py "$ROOT/usr/share/icons/hicolor/256x256/apps/$NAME.png" 256
cp -a THIRD-PARTY-NOTICES.md CHANGELOG.md licenses "$ROOT/usr/share/doc/$NAME/"
cp LICENSE "$ROOT/usr/share/doc/$NAME/copyright"
find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT/usr/share" -type f -exec chmod 644 {} +

echo "2/4 Bibliothèques prises au système…"
# Chemins des bibliothèques embarquées : leurs dépendances internes ne comptent pas.
# Paths of the embedded libraries: their internal dependencies do not count.
libpath=$(find "$ROOT/opt/$NAME" -name '*.so*' -printf '%h\n' | sort -u | tr '\n' ':')
find "$ROOT/opt/$NAME" -type f \( -name '*.so*' -o -name AtlasPCMonitor \) | while read -r file; do
    LD_LIBRARY_PATH="$libpath" ldd "$file" 2>/dev/null || true
done | awk '$2 == "=>" && $3 ~ /^\// {print $1, $3}' | grep -v "$ROOT" | sort -u > build/linux-packages/system-libs.txt
debdeps=$(awk '{print $2}' build/linux-packages/system-libs.txt | while read -r lib; do
    dpkg-query -S "$lib" 2>/dev/null || dpkg-query -S "$(readlink -f "$lib")" 2>/dev/null || dpkg-query -S "/usr$lib" 2>/dev/null || true
done | cut -d: -f1 | sort -u | grep -v '^$' | paste -sd, - | sed 's/,/, /g')
[ -n "$debdeps" ] || { echo "Dépendances Debian introuvables (dpkg-query)." >&2; exit 1; }
# glibc minimale : celle de la machine de construction.
# Minimum glibc: the build machine's one.
glibc=$(ldd --version | awk 'NR == 1 {print $NF}')
debdeps=$(echo "$debdeps" | sed "s/\blibc6\b/libc6 (>= $glibc)/")
rpmreqs=$(awk '{print $1}' build/linux-packages/system-libs.txt | sed 's/$/()(64bit)/' | paste -sd' ' -)
echo "   .deb : $debdeps"
echo "   .rpm : $rpmreqs"

echo "3/4 Paquet .deb…"
DEBROOT=build/linux-packages/deb
cp -a "$ROOT" "$DEBROOT"
mkdir -p "$DEBROOT/DEBIAN"
size=$(du -sk "$DEBROOT" | cut -f1)
cat > "$DEBROOT/DEBIAN/control" <<EOF
Package: $NAME
Version: $VERSION-$RELEASE
Architecture: amd64
Maintainer: $MAINTAINER
Installed-Size: $size
Depends: $debdeps
Section: utils
Priority: optional
Homepage: $HOMEPAGE
Description: $SUMMARY
 Atlas PC Monitor inventories the hardware of Windows PCs and turns it into
 findings, upgrade advice and a printable intervention sheet. On Linux, it opens,
 compares, prints and exports (PDF, HTML, text) the JSON reports made on Windows.
EOF
dpkg-deb --root-owner-group -Zxz --build "$DEBROOT" "$DEB" >/dev/null

echo "4/4 Paquet .rpm…"
RPMTOP="$(pwd)/build/linux-packages/rpm"
mkdir -p "$RPMTOP/SPECS"
cat > "$RPMTOP/SPECS/$NAME.spec" <<EOF
Name:           $NAME
Version:        $VERSION
Release:        $RELEASE
Summary:        $SUMMARY
License:        MIT AND LGPL-3.0-only AND PSF-2.0 AND OFL-1.1
URL:            $HOMEPAGE
BuildArch:      x86_64
# Dépendances déclarées à la main (bibliothèques du système) : sans ça, rpm ajouterait toutes les
# bibliothèques embarquées comme dépendances et comme « fournies » par le paquet.
# Dependencies declared by hand (system libraries): otherwise rpm would add every embedded library as
# a dependency and as "provided" by the package.
AutoReqProv:    no
Requires:       $rpmreqs
%global debug_package %{nil}
%global __os_install_post %{nil}
%global _build_id_links none

%description
Atlas PC Monitor inventories the hardware of Windows PCs and turns it into
findings, upgrade advice and a printable intervention sheet. On Linux, it opens,
compares, prints and exports (PDF, HTML, text) the JSON reports made on Windows.

%install
cp -a "$(pwd)/$ROOT/." %{buildroot}/

%files
/opt/$NAME
/usr/bin/$NAME
/usr/share/applications/$NAME.desktop
/usr/share/icons/hicolor/256x256/apps/$NAME.png
%doc /usr/share/doc/$NAME
EOF
rpmbuild --quiet --define "_topdir $RPMTOP" --define "_binary_payload w9.xzdio" -bb "$RPMTOP/SPECS/$NAME.spec"
cp "$RPMTOP/RPMS/x86_64/$NAME-$VERSION-$RELEASE.x86_64.rpm" "$RPM"

echo "Paquets : $DEB ($(du -h "$DEB" | cut -f1)), $RPM ($(du -h "$RPM" | cut -f1))"
