"""Atlas PC Monitor — inventaire matériel Windows, interface française.

Lanceur : tout le code vit dans le paquet « atlas ».
    python atlas_pc.py            interface graphique
    python atlas_pc.py --json     inventaire JSON sur la sortie standard
    python atlas_pc.py --help     toutes les options
"""

import sys

from atlas.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
