"""Fiche d'intervention : une page HTML au format A4, prête à imprimer ou à enregistrer en PDF.

Module pur : il reçoit l'inventaire et les champs saisis, et renvoie le HTML.
Les champs laissés vides sont imprimés comme des zones à remplir à la main.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from . import __version__
from . import formatting as f
from .findings import FIX, INFO, OK, WATCH, Finding, analyze, battery_wear, summary, summary_text
from .formatting import EMPTY


@dataclass
class FicheInfo:
    """Champs saisis par le technicien. Tous facultatifs."""

    technician: str = ""
    client: str = ""
    contact: str = ""
    reference: str = ""
    request: str = ""  # demande du client, motif de l'intervention
    work: str = ""  # travaux réalisés
    recommendations: str = ""


def default_reference(data: dict) -> str:
    """Référence proposée par défaut : date et heure de l'analyse."""
    try:
        moment = datetime.fromisoformat(str(data.get("captured_at")))
    except ValueError:
        moment = datetime.now()
    return f"INT-{moment:%Y%m%d-%H%M}"


def _join(*parts) -> str:
    """Valeurs renseignées séparées par « · » (vides, None et tirets ignorés)."""
    texts = (str(part).strip() for part in parts if part is not None)
    return " · ".join(text for text in texts if text and text != EMPTY)


def machine_rows(data: dict) -> list[tuple[str, str]]:
    """Identité du poste, en lignes courtes faites pour tenir sur une page."""
    host = data.get("system") or {}
    machine = data.get("machine") or {}
    bios = data.get("bios") or {}
    system = data.get("os") or {}
    memory = data.get("memory") or {}
    sticks = data.get("ram") or []
    rows: list[tuple[str, str]] = []

    def add(label: str, value: str) -> None:
        if value and value != EMPTY:
            rows.append((label, value))

    add("Nom du poste", f.clean(host.get("computer")))
    add("Fabricant et modèle", _join(machine.get("Manufacturer"), machine.get("Model"), machine.get("SystemFamily")))
    add("Numéro de série", f.clean(bios.get("SerialNumber")))
    windows = _join(
        system.get("Caption"), system.get("DisplayVersion"), f"build {system['BuildNumber']}" if system.get("BuildNumber") else ""
    )
    product = next(iter(data.get("license") or []), None)
    if product:
        windows = _join(windows, f.fmt_code(product.get("LicenseStatus"), f.LICENSE_STATUS))
    add("Windows", windows or f.clean(host.get("platform")))
    for cpu in (data.get("cpu") or [])[:1]:
        add("Processeur", _join(cpu.get("Name"), f"{cpu['NumberOfCores']} cœurs" if cpu.get("NumberOfCores") else ""))
    add("Mémoire", _join(f.fmt_binary(memory.get("installed")), f"{len(sticks)} barrette(s)" if sticks else "", *f.memory_types(sticks)))
    for disk in data.get("disks") or []:
        kind = f.fmt_media(disk.get("MediaType")) if disk.get("MediaType") not in (None, "") else ""
        health = {"healthy": "sain", "warning": "en alerte", "unhealthy": "défaillant"}.get(str(disk.get("Health") or "").lower(), "")
        add("Disque", _join(disk.get("Model"), f.fmt_decimal(disk.get("Size")), kind, health))
    gpus = [f.clean(gpu.get("Name")) for gpu in data.get("gpu") or []]
    add("Carte graphique" if len(gpus) < 2 else "Cartes graphiques", " + ".join(g for g in gpus if g != EMPTY))
    for battery in data.get("battery") or []:
        wear = battery_wear(battery)
        if wear is not None:
            add("Batterie", f"usure {int(round(wear))} %")
    add("BIOS / UEFI", _join(bios.get("Version"), f.fmt_date(bios.get("ReleaseDate"))))
    return rows


_CSS = """
@page { size: A4; margin: 14mm 14mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; font-size: 10pt; color: #172333; margin: 0; background: #e9eef4; }
.sheet { background: #fff; max-width: 210mm; margin: 12px auto; padding: 12mm 14mm; box-shadow: 0 2px 10px rgba(0,0,0,.12); }
header { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #13865f; padding-bottom: 6px; }
h1 { font-size: 17pt; margin: 0; }
.meta { text-align: right; color: #637386; font-size: 9pt; line-height: 1.5; }
.meta strong { color: #172333; }
h2 { font-size: 9.5pt; text-transform: uppercase; letter-spacing: .04em; color: #13865f; margin: 10px 0 4px; }
.parties { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px; }
.box { border: 1px solid #d5dee8; border-radius: 4px; padding: 5px 9px; min-height: 40px; }
.parties .box { min-height: 13mm; }
.box .label { font-size: 8pt; text-transform: uppercase; color: #637386; display: block; margin-bottom: 2px; }
table { width: 100%; border-collapse: collapse; }
td { padding: 1.5px 6px; border-bottom: 1px solid #e5ebf2; vertical-align: top; font-size: 9pt; }
td:first-child { width: 26%; color: #637386; }
.finding { border-left: 4px solid #13865f; padding: 2px 0 2px 8px; margin: 3px 0; break-inside: avoid; }
.finding .chip { font-size: 7.5pt; font-weight: 700; text-transform: uppercase; margin-right: 6px; }
.finding .detail, .finding .advice { color: #4a5a6c; font-size: 9pt; }
.finding.fix { border-color: #c0392b; } .finding.fix .chip { color: #c0392b; }
.finding.watch { border-color: #b87410; } .finding.watch .chip { color: #98620a; }
.finding.info { border-color: #2766b2; } .finding.info .chip { color: #2766b2; }
.ok-line { color: #13865f; font-size: 9pt; margin: 4px 0 0; }
.notes { color: #2766b2; font-size: 9pt; margin: 4px 0 0; }
.free { border: 1px solid #d5dee8; border-radius: 4px; padding: 5px 9px; white-space: pre-wrap; min-height: 10mm; }
.free.blank { background: repeating-linear-gradient(#fff 0 6.5mm, #dfe5ec 6.5mm calc(6.5mm + 1px)); min-height: 19.5mm; }
.signatures { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; break-inside: avoid; }
.signatures .box { min-height: 22mm; }
footer { margin-top: 8px; color: #8c9bad; font-size: 7.5pt; text-align: center; }
.toolbar { max-width: 210mm; margin: 12px auto 0; text-align: right; }
.toolbar button { font: inherit; font-weight: 600; padding: 7px 14px; border: 0; border-radius: 4px;
  background: #13865f; color: #fff; cursor: pointer; }
@media print {
  body { background: #fff; }
  .sheet { box-shadow: none; margin: 0; padding: 0; max-width: none; }
  .toolbar { display: none; }
}
"""


def _text_block(value: str) -> str:
    """Zone de texte libre : le contenu saisi, ou des lignes à remplir à la main."""
    if value.strip():
        return f'<div class="free">{html.escape(value.strip())}</div>'
    return '<div class="free blank"></div>'


def _finding(item: Finding) -> str:
    esc = html.escape
    detail = "<br>".join(esc(line) for line in item.detail.splitlines())
    advice = f'<div class="advice">→ {esc(item.advice)}</div>' if item.advice else ""
    return (
        f'<div class="finding {item.level}"><span class="chip">{esc(item.label)}</span><strong>{esc(item.title)}</strong>'
        f'<div class="detail">{detail}</div>{advice}</div>'
    )


def to_html(data: dict, info: FicheInfo | None = None, found: list[Finding] | None = None) -> str:
    """Fiche d'intervention complète, en un seul fichier HTML autonome."""
    info = info or FicheInfo()
    found = analyze(data) if found is None else found
    esc = html.escape
    stamp = f.fmt_stamp(data.get("captured_at"))
    reference = info.reference.strip() or default_reference(data)
    computer = (data.get("system") or {}).get("computer", "")

    def party(label: str, *values: str) -> str:
        text = "<br>".join(esc(v.strip()) for v in values if v and v.strip())
        return f'<div class="box"><span class="label">{label}</span>{text}</div>'

    machine = "".join(f"<tr><td>{esc(label)}</td><td>{esc(value)}</td></tr>" for label, value in machine_rows(data))
    alerts = [item for item in found if item.level in (FIX, WATCH)]
    notes = [item.title for item in found if item.level == INFO]
    oks = [item.title for item in found if item.level == OK]
    if alerts:
        findings_html = "".join(_finding(item) for item in alerts)
    elif found:
        findings_html = '<p class="ok-line">Aucun point à corriger ni à surveiller.</p>'
    else:
        findings_html = '<p class="ok-line" style="color:#637386">Diagnostic automatique indisponible (inventaire Windows non lu).</p>'
    if notes:
        findings_html += f'<p class="notes">À noter : {esc(" · ".join(notes))}</p>'
    if oks:
        findings_html += f'<p class="ok-line">✓ {esc(" · ".join(oks))}</p>'

    counts = summary(found)
    verdict_text = summary_text(found) if counts[FIX] or counts[WATCH] else ("Rien à signaler" if found else "")
    note = f'<p class="ok-line" style="color:#98620a">{esc(data["note"])}</p>' if data.get("note") else ""

    masked = "<br>Identifiants masqués" if data.get("anonymized") else ""
    title = f"Fiche d'intervention {reference}"
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>{esc(title)} — {esc(computer)}</title><style>{_CSS}</style></head>
<body>
<div class="toolbar"><button onclick="window.print()">Imprimer ou enregistrer en PDF</button></div>
<div class="sheet">
<header>
  <h1>Fiche d'intervention</h1>
  <div class="meta">Référence <strong>{esc(reference)}</strong><br>Diagnostic du <strong>{esc(stamp)}</strong>{masked}</div>
</header>
<div class="parties">
  {party("Client", info.client, info.contact)}
  {party("Technicien", info.technician)}
</div>
<h2>Demande du client</h2>
{_text_block(info.request)}
<h2>Poste diagnostiqué</h2>
<table>{machine}</table>
<h2>Diagnostic automatique{f" — {esc(verdict_text)}" if verdict_text else ""}</h2>
{note}{findings_html}
<h2>Travaux réalisés</h2>
{_text_block(info.work)}
<h2>Recommandations</h2>
{_text_block(info.recommendations)}
<div class="signatures">
  <div class="box"><span class="label">Signature du technicien</span></div>
  <div class="box"><span class="label">Signature du client</span></div>
</div>
<footer>Généré par Atlas PC Monitor {esc(__version__)} le {datetime.now():%d/%m/%Y à %H:%M}</footer>
</div>
</body></html>
"""
