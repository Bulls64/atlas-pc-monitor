"""Vérifie un inventaire réel produit sous Windows (atlas_pc.py --json -o scan.json).

Usage : python tools/check_scan.py scan.json [--strict]

Écrit un résumé Markdown sur la sortie standard (adapté à $GITHUB_STEP_SUMMARY)
et sort en erreur si une vérification bloquante échoue :
- la collecte PowerShell a abouti (pas de note d'échec) ;
- les sources indispensables sont présentes ;
- toutes les pages, les constats, les exports et la fiche se construisent ;
- le mode partage ne laisse fuir aucun numéro de série ni adresse MAC complète.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlas import export, fiche, findings, pages, privacy  # noqa: E402

# Sans elles, l'outil n'a pas de sens : bloquant.
REQUIRED = ("os", "cpu", "disks", "volumes", "machine", "board")
# Souvent absentes sur une machine virtuelle (runner CI) : simple avertissement.
OPTIONAL = ("bios", "ram", "memoryarray", "gpu", "adapters", "network", "monitors", "audio", "battery", "tpm", "secureboot", "license")


def secrets_of(data: dict) -> list[str]:
    """Valeurs que le mode partage doit faire disparaître."""
    found = []
    for section, key in privacy.SERIAL_FIELDS:
        value = data.get(section)
        for row in value if isinstance(value, list) else [value] if isinstance(value, dict) else []:
            text = str(row.get(key) or "").strip()
            if len(text) >= 4 and text.lower() not in ("none", "to be filled by o.e.m.", "default string", "0"):
                found.append(text)
    for adapter in data.get("adapters") or []:
        if adapter.get("MacAddress"):
            found.append(str(adapter["MacAddress"]))
    computer = (data.get("system") or {}).get("computer")
    if computer:
        found.append(str(computer))
    return found


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    problems: list[str] = []
    warnings: list[str] = []
    out = ["## Inventaire Windows réel", ""]

    if data.get("note"):
        problems.append(f"Collecte en échec : {data['note']}")
    for key in REQUIRED:
        if not data.get(key):
            problems.append(f"Source indispensable vide : {key}")
    for key in OPTIONAL:
        if not data.get(key):
            warnings.append(key)

    system = data.get("os") or {}
    out += [
        f"- Windows : {system.get('Caption', '?')} {system.get('DisplayVersion', '')} (build {system.get('BuildNumber', '?')})",
        f"- Session administrateur : {data.get('admin')}",
        f"- Durée totale : {data.get('scan_seconds', '?')} s, dont PowerShell {data.get('powershell_ms', '?')} ms",
        "",
        "| Source | Durée (ms) | Éléments | Erreur |",
        "| --- | ---: | ---: | --- |",
    ]
    timings = data.get("timings") or {}
    errors = data.get("errors") or {}
    if not timings:
        problems.append("Aucun chronométrage dans le JSON")
    for name, ms in sorted(timings.items(), key=lambda item: -item[1]):
        value = data.get(name)
        count = len(value) if isinstance(value, list) else int(bool(value)) if name in data else "—"
        out.append(f"| {name} | {ms} | {count} | {errors.get(name, '')} |")
    out.append("")

    # Tout ce que l'application construit à partir de l'inventaire doit fonctionner sur des données réelles.
    try:
        built = pages.build_all(data)
        rows = sum(len(section.rows) for sections in built.values() for section in sections)
        out.append(f"- Pages : {len(built)} construites, {rows} lignes")
        found = findings.analyze(data)
        out.append(f"- Constats : {findings.summary_text(found)} ({len(found)} au total)")
        out += [f"  - [{item.label}] {item.title}" for item in found]
        for suffix in (".json", ".txt", ".html"):
            export.render(data, suffix)
        fiche.to_html(data, fiche.FicheInfo(client="CI"))
        out.append("- Exports JSON, texte, HTML et fiche : OK")
        shared = privacy.anonymize(data)
        dumped = json.dumps(shared, ensure_ascii=False) + export.to_text(shared) + fiche.to_html(shared)
        leaks = [secret for secret in secrets_of(data) if secret in dumped]
        if leaks:
            problems.append(f"Mode partage : {len(leaks)} identifiant(s) encore visibles")
        else:
            out.append(f"- Mode partage : {len(secrets_of(data))} identifiant(s) masqué(s), aucune fuite")
    except Exception as error:  # le but est justement d'attraper ce qui casse sur des données réelles
        problems.append(f"Construction des pages ou exports : {type(error).__name__}: {error}")

    if warnings:
        out += ["", f"Sources vides (normal sur une machine virtuelle) : {', '.join(warnings)}"]
    if errors:
        out += ["", "Erreurs remontées par PowerShell :", *[f"- `{k}` : {v}" for k, v in errors.items()]]
    out += ["", "### Résultat", *(f"- ÉCHEC : {p}" for p in problems)] if problems else ["", "### Résultat : OK"]
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
