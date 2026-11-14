"""Atlas PC Monitor — inventaire matériel Windows, interface en français et en anglais.

Lanceur : tout le code vit dans le paquet « atlas ».
    python atlas_pc.py            interface graphique
    python atlas_pc.py --json     inventaire JSON sur la sortie standard
    python atlas_pc.py --help     toutes les options

Atlas PC Monitor — Windows hardware inventory, interface in French and English.

Launcher: all the code lives in the "atlas" package.
    python atlas_pc.py            graphical interface
    python atlas_pc.py --json     JSON inventory on standard output
    python atlas_pc.py --help     all the options
"""

import sys

from atlas.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
