# Essais sur de vrais PC Windows

La CI vérifie le script sur une machine virtuelle GitHub, sans batterie, capteurs
ni vraies barrettes. Ces essais complètent ce qu'elle ne peut pas voir.

## Machines

| Poste | Pourquoi | Fait |
| --- | --- | --- |
| Un portable récent | batterie, écran interne, SO-DIMM ou mémoire soudée, Wi-Fi | ☐ |
| Un PC fixe | DIMM, plusieurs disques, carte graphique dédiée, profil XMP/EXPO | ☐ |
| Un vieux poste ou une machine virtuelle | Windows 10, BIOS hérité, matériel atypique | ☐ |

## Sur chaque poste

1. Lancer `lancer_atlas.bat` en session normale, puis avec « Relancer en administrateur ».
2. Noter la durée affichée sur la page Système (section Analyse) et la source la plus lente.
3. Comparer avec Windows :
   - modèle, processeur, mémoire installée : `msinfo32` ;
   - barrettes et vitesse configurée : Gestionnaire des tâches › Performances › Mémoire ;
   - type SSD ou HDD des disques : Gestionnaire des tâches › Performances ;
   - périphériques en erreur : `devmgmt.msc` ;
   - TPM et démarrage sécurisé : `tpm.msc` et `msinfo32` (session administrateur).
4. Relire la page Constats : chaque constat est-il juste ? En manque-t-il un évident ?
5. Mise à l'échelle : tester à 100, 125 et 150 % (Paramètres › Affichage) ; rien ne doit
   être coupé, la barre latérale doit défiler si besoin.
6. Imprimer une fiche d'intervention en PDF : une seule page pour un poste courant ?
7. Activer le mode partage, faire une capture : plus aucun numéro de série visible ?

## Ce qu'il faut me renvoyer

Dans un terminal, à côté de `atlas_pc.py` :

```
python atlas_pc.py --json --anonyme -o atlas-poste.json --debug
```

Joindre `atlas-poste.json` (identifiants masqués) et une courte liste de ce qui est faux.
Le journal `%TEMP%\atlas-debug.log` aide en cas d'erreur, **mais contient l'inventaire
brut non masqué** (numéros de série, MAC) : ne le joindre que s'il le faut.
