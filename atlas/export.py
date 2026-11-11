"""Exports du rapport : JSON (réimportable), texte et HTML autonome."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .formatting import fmt_date
from .pages import build_all

FORMATS = {".json": "Rapport JSON", ".txt": "Fichier texte", ".html": "Page HTML"}


def to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _header(data: dict) -> tuple[str, str]:
    computer = (data.get("system") or {}).get("computer", "")
    stamp = fmt_date(data.get("captured_at", "")[:19])
    return f"Atlas PC — rapport système de {computer}", f"Généré le {stamp} · Atlas PC {data.get('atlas_version', '')}"


def to_text(data: dict) -> str:
    title, subtitle = _header(data)
    lines = [title.upper(), subtitle]
    if data.get("note"):
        lines += ["", f"Remarque : {data['note']}"]
    for page, sections in build_all(data).items():
        lines += ["", "=" * 60, page.upper(), "=" * 60]
        for section in sections:
            lines += ["", section.title, "-" * len(section.title)]
            width = max((len(row.label) for row in section.rows), default=0)
            lines += [f"{row.label.ljust(width)} : {row.value}" for row in section.rows]
            if section.note:
                lines.append(f"({section.note})")
            elif not section.rows:
                lines.append("(Aucune information détectée.)")
    return "\n".join(lines) + "\n"


_CSS = (
    "body{font-family:'Segoe UI',system-ui,sans-serif;margin:2rem auto;max-width:60rem;padding:0 1rem;"
    "color:#172333;background:#f3f6fa}h1{font-size:1.5rem;margin-bottom:.2rem}h2{margin-top:2rem;"
    "border-bottom:2px solid #13865f;padding-bottom:.3rem}h3{margin:1.2rem 0 .4rem;font-size:1rem}"
    "p.meta,p.note{color:#637386}table{width:100%;border-collapse:collapse;background:#fff;"
    "border:1px solid #d5dee8}td{padding:.45rem .8rem;border-top:1px solid #e5ebf2;vertical-align:top}"
    "td:first-child{width:38%;color:#637386}@media print{body{background:#fff;margin:0}}"
)


def to_html(data: dict) -> str:
    esc = html.escape
    title, subtitle = _header(data)
    parts = [
        "<!DOCTYPE html>",
        f'<html lang="fr"><head><meta charset="utf-8"><title>{esc(title)}</title><style>{_CSS}</style></head><body>',
        f'<h1>{esc(title)}</h1><p class="meta">{esc(subtitle)}</p>',
    ]
    if data.get("note"):
        parts.append(f'<p class="note">{esc(data["note"])}</p>')
    for page, sections in build_all(data).items():
        parts.append(f"<h2>{esc(page)}</h2>")
        for section in sections:
            parts.append(f"<h3>{esc(section.title)}</h3>")
            if section.rows:
                cells = "".join(f"<tr><td>{esc(r.label)}</td><td>{esc(r.value)}</td></tr>" for r in section.rows)
                parts.append(f"<table>{cells}</table>")
            if section.note or not section.rows:
                parts.append(f'<p class="note">{esc(section.note or "Aucune information détectée.")}</p>')
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def render(data: dict, suffix: str) -> str:
    """Contenu du rapport pour une extension donnée (.json par défaut)."""
    suffix = suffix.lower()
    if suffix == ".txt":
        return to_text(data)
    if suffix in (".html", ".htm"):
        return to_html(data)
    return to_json(data)


def resolve_path(path: str, chosen_filter: str = "") -> Path:
    """Complète l'extension d'après le type choisi dans la boîte de dialogue."""
    target = Path(path)
    if target.suffix.lower() in (*FORMATS, ".htm"):
        return target
    for suffix, label in FORMATS.items():
        if chosen_filter and label in chosen_filter:
            return target.with_name(target.name + suffix)
    return target.with_name(target.name + ".json")


def save(data: dict, path: str, chosen_filter: str = "") -> Path:
    target = resolve_path(path, chosen_filter)
    target.write_text(render(data, target.suffix), encoding="utf-8")
    return target


def load(path: str) -> dict:
    """Relit un export JSON d'Atlas PC pour la comparaison."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "system" not in data:
        raise ValueError("ce fichier n'est pas un rapport JSON d'Atlas PC")
    return data
