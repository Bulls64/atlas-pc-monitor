#!/bin/sh
# Essai d'Atlas PC Monitor installé par un paquet .deb ou .rpm (CI) : commande, rapport texte,
# PDF sans écran, entrée de menu, et interface ouverte sous Xvfb.
#   sh tests/check_linux_package.sh exemple.json
#
# Check of Atlas PC Monitor installed by a .deb or .rpm package (CI): command, text report,
# PDF without a display, menu entry, and interface opened under Xvfb.
set -eu
report=$1
atlas-pc-monitor --version
atlas-pc-monitor --lang fr --text "$report" | grep -q "CONSTATS"
env -u DISPLAY -u WAYLAND_DISPLAY atlas-pc-monitor "$report" --pdf -o /tmp/atlas-pc-monitor-essai.pdf
head -c 4 /tmp/atlas-pc-monitor-essai.pdf | grep -q "%PDF"
test -f /usr/share/applications/atlas-pc-monitor.desktop
grep -q "^Exec=atlas-pc-monitor %f" /usr/share/applications/atlas-pc-monitor.desktop
test -f /usr/share/icons/hicolor/256x256/apps/atlas-pc-monitor.png
xvfb-run -a sh -c 'atlas-pc-monitor "$1" & pid=$!; sleep 10; kill -0 $pid && kill $pid' sh "$report"
echo "Paquet installé : OK"
