# Changelog · Journal des versions

All notable changes to Atlas PC Monitor are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

Toutes les évolutions notables d'Atlas PC Monitor sont décrites ici. Le format suit
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et les numéros de version suivent
[le versionnage sémantique](https://semver.org/lang/fr/).

## [Unreleased]

### English

#### Added

- Settings window (⚙ button in the header): language, theme and updates.
- Updates from the GitHub releases: check, then install and restart in one click; the download is checked against `SHA256SUMS.txt`. Works for the single file, the folder and the AppImage; optional check at startup, off by default.

### Français

#### Ajouts

- Fenêtre Paramètres (bouton ⚙ de l'en-tête) : langue, thème et mises à jour.
- Mises à jour depuis les releases GitHub : recherche, puis installation et redémarrage en un clic ; le téléchargement est vérifié avec `SHA256SUMS.txt`. Fonctionne pour le fichier unique, le dossier et l'AppImage ; recherche au démarrage en option, désactivée par défaut.

## [1.0.0] - 2026-11-14

### English

First public release. Atlas PC Monitor takes over from Atlas PC, an in-house tool whose versions 2.x and 3.0 were never published: with the new name, numbering starts again at 1.0.0.

#### Added

- Full hardware inventory of a Windows 10 or 11 PC in a single PowerShell/CIM query: machine, BIOS/UEFI, processor, memory, graphics cards and monitors, disks and their health, volumes and BitLocker, network, audio, battery, TPM, Secure Boot, Windows activation.
- Automatic findings (to fix, to watch, to note, OK), each with a piece of advice: memory, storage, Windows 10 end of support and Windows 11 eligibility, drivers and devices in error, battery.
- Printable A4 intervention sheet, ready to save as PDF.
- Memory upgrade advisor: which modules to buy to reach the next capacity.
- Sharing mode, which hides the computer's identifiers before a screenshot or an export.
- Comparison with an earlier report, search across every page, JSON, text and HTML exports.
- Command line (`--json`, `--text`, `--html`, `--fiche`, `--lang`…) to do everything without the interface.
- PySide6 interface with the BAUSTECH PC look, dark and light themes, board map of the components.
- Interface, findings, reports and sheet in English and French, switched with the EN/FR button or `--lang`.
- Report viewer, on Windows and on Linux (AppImage).
- Windows executables (single file and folder) with file properties, and a Linux AppImage, built and checked by the CI on a real Windows inventory.
- Third-party notices and license texts shipped with every build (Qt and PySide6 under the LGPL-3.0).

### Français

Première version publique. Atlas PC Monitor prend la suite d'Atlas PC, un outil interne dont les versions 2.x et 3.0 n'ont jamais été publiées : avec le nouveau nom, la numérotation repart de 1.0.0.

#### Ajouts

- Inventaire matériel complet d'un PC sous Windows 10 ou 11 en une seule requête PowerShell/CIM : machine, BIOS/UEFI, processeur, mémoire, cartes graphiques et écrans, disques et leur santé, volumes et BitLocker, réseau, audio, batterie, TPM, démarrage sécurisé, activation de Windows.
- Constats automatiques (à corriger, à surveiller, à noter, OK), chacun avec un conseil : mémoire, stockage, fin de prise en charge de Windows 10 et compatibilité Windows 11, pilotes et périphériques en erreur, batterie.
- Fiche d'intervention A4 prête à imprimer ou à enregistrer en PDF.
- Conseiller d'évolution mémoire : quelles barrettes acheter pour passer à la capacité suivante.
- Mode partage, qui masque les identifiants du poste avant une capture ou un export.
- Comparaison avec un rapport antérieur, recherche dans toutes les pages, exports JSON, texte et HTML.
- Ligne de commande (`--json`, `--text`, `--html`, `--fiche`, `--lang`…) pour tout faire sans l'interface.
- Interface PySide6 au look BAUSTECH PC, thèmes sombre et clair, plan de carte des composants.
- Interface, constats, rapports et fiche en français et en anglais, au choix avec le bouton FR/EN ou `--lang`.
- Visionneuse de rapports, sous Windows comme sous Linux (AppImage).
- Exécutables Windows (fichier unique et dossier) avec leurs propriétés de fichier, et AppImage Linux, construits et vérifiés par la CI sur un vrai inventaire Windows.
- Mentions tierces et textes de licence livrés avec chaque version (Qt et PySide6 sous LGPL-3.0).

[1.0.0]: https://github.com/Bulls64/atlas-pc-monitor/releases/tag/v1.0.0
