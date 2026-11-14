# Third-party notices · Mentions tierces

[English](#english) · [Français](#français)

## English

Atlas PC Monitor itself is released under the MIT License (see `LICENSE`). The executables
(`AtlasPCMonitor.exe`, `AtlasPCMonitor-windows.zip`) and the Linux AppImage also contain the
following third-party software, each under its own license. The full license texts are in the
`licenses/` folder shipped with each build, and in this repository.

| Component | Use | License | Source code |
| --- | --- | --- | --- |
| [Qt 6](https://www.qt.io/) and [Qt for Python (PySide6, Shiboken6)](https://doc.qt.io/qtforpython-6/) | graphical interface | LGPL-3.0 (`licenses/LGPL-3.0.txt`, which builds on `licenses/GPL-3.0.txt`) | [download.qt.io/official_releases/QtForPython](https://download.qt.io/official_releases/QtForPython/) · [download.qt.io/official_releases/qt](https://download.qt.io/official_releases/qt/) · [code.qt.io](https://code.qt.io/) |
| [Python](https://www.python.org/) | interpreter embedded in the executable | PSF License Agreement (`licenses/Python-PSF.txt`) | [python.org/downloads/source](https://www.python.org/downloads/source/) |
| [PyInstaller](https://pyinstaller.org/) bootloader | starts the executable | GPL-2.0 with the bootloader exception (no restriction on the application) | [github.com/pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller) |
| Inter, IBM Plex Mono, Space Grotesk | interface fonts | SIL Open Font License 1.1 (`atlas/gui/fonts/OFL-*.txt`) | [rsms.me/inter](https://rsms.me/inter/) · [github.com/IBM/plex](https://github.com/IBM/plex) · [github.com/floriankarsten/space-grotesk](https://github.com/floriankarsten/space-grotesk) |
| [AppImage type2 runtime](https://github.com/AppImage/type2-runtime) (AppImage only) | mounts the AppImage | MIT; statically includes libfuse (LGPL-2.1) and squashfuse (BSD-2-Clause) | [github.com/AppImage/type2-runtime](https://github.com/AppImage/type2-runtime) |

Qt itself includes third-party components (FreeType, HarfBuzz, libpng, zlib…), listed in
[Licenses Used in Qt](https://doc.qt.io/qt-6/licenses-used-in-qt.html).

**Qt and PySide6 under the LGPL.** Atlas PC Monitor uses the unmodified Qt and PySide6 libraries
published by The Qt Company. You may replace them with another compatible version:

- in the folder version (`AtlasPCMonitor-windows.zip`), the Qt and PySide6 libraries are separate
  files in `_internal/PySide6/` and can be swapped directly;
- for the single file and the AppImage, rebuild them from the source code of this repository with
  another PySide6 version (`pip install PySide6==<version>`, then `pyinstaller atlas_pc.spec`,
  see the README).

The version of PySide6 used by a build is shown in the properties of the files in
`_internal/PySide6/` (folder version).

## Français

Atlas PC Monitor est publié sous licence MIT (voir `LICENSE`). Les exécutables
(`AtlasPCMonitor.exe`, `AtlasPCMonitor-windows.zip`) et l'AppImage Linux contiennent aussi les
logiciels tiers suivants, chacun sous sa propre licence. Les textes complets des licences sont
dans le dossier `licenses/` livré avec chaque version, et dans ce dépôt.

| Composant | Rôle | Licence | Code source |
| --- | --- | --- | --- |
| [Qt 6](https://www.qt.io/) et [Qt for Python (PySide6, Shiboken6)](https://doc.qt.io/qtforpython-6/) | interface graphique | LGPL-3.0 (`licenses/LGPL-3.0.txt`, qui s'appuie sur `licenses/GPL-3.0.txt`) | [download.qt.io/official_releases/QtForPython](https://download.qt.io/official_releases/QtForPython/) · [download.qt.io/official_releases/qt](https://download.qt.io/official_releases/qt/) · [code.qt.io](https://code.qt.io/) |
| [Python](https://www.python.org/) | interpréteur intégré à l'exécutable | PSF License Agreement (`licenses/Python-PSF.txt`) | [python.org/downloads/source](https://www.python.org/downloads/source/) |
| Chargeur (bootloader) de [PyInstaller](https://pyinstaller.org/) | démarre l'exécutable | GPL-2.0 avec l'exception du chargeur (aucune contrainte sur l'application) | [github.com/pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller) |
| Inter, IBM Plex Mono, Space Grotesk | polices de l'interface | SIL Open Font License 1.1 (`atlas/gui/fonts/OFL-*.txt`) | [rsms.me/inter](https://rsms.me/inter/) · [github.com/IBM/plex](https://github.com/IBM/plex) · [github.com/floriankarsten/space-grotesk](https://github.com/floriankarsten/space-grotesk) |
| [Runtime AppImage type2](https://github.com/AppImage/type2-runtime) (AppImage seulement) | monte l'AppImage | MIT ; inclut libfuse (LGPL-2.1) et squashfuse (BSD-2-Clause) | [github.com/AppImage/type2-runtime](https://github.com/AppImage/type2-runtime) |

Qt intègre lui-même des composants tiers (FreeType, HarfBuzz, libpng, zlib…), listés dans
[Licenses Used in Qt](https://doc.qt.io/qt-6/licenses-used-in-qt.html).

**Qt et PySide6 sous LGPL.** Atlas PC Monitor utilise les bibliothèques Qt et PySide6 publiées par
The Qt Company, sans modification. Vous pouvez les remplacer par une autre version compatible :

- dans la version en dossier (`AtlasPCMonitor-windows.zip`), les bibliothèques Qt et PySide6 sont
  des fichiers séparés, dans `_internal/PySide6/`, que l'on peut remplacer directement ;
- pour le fichier unique et l'AppImage, il suffit de les reconstruire à partir du code source de ce
  dépôt avec une autre version de PySide6 (`pip install PySide6==<version>`, puis
  `pyinstaller atlas_pc.spec`, voir le README).

La version de PySide6 d'une construction figure dans les propriétés des fichiers de
`_internal/PySide6/` (version en dossier).
