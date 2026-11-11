"""Interface Tkinter d'Atlas PC."""

from __future__ import annotations

import json
import logging
import os
import platform
import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, export
from .collect import scan
from .formatting import EMPTY, fmt_binary, fmt_celsius, fmt_date
from .pages import OVERVIEW, PAGES, Section, build_page, diff_reports, overview_tiles, search

log = logging.getLogger("atlas")
FONT = "Segoe UI"

SOURCE_NAMES = {
    "machine": "modèle de l'ordinateur",
    "bios": "BIOS",
    "secureboot": "démarrage sécurisé",
    "os": "Windows",
    "cpu": "processeur",
    "board": "carte mère",
    "ram": "mémoire",
    "memoryarray": "emplacements mémoire",
    "gpu": "carte graphique",
    "disks": "disques",
    "disks_fallback": "disques",
    "volumes": "volumes",
    "bitlocker": "BitLocker",
    "adapters": "cartes réseau",
    "network": "configuration IP",
    "temperatures": "températures",
    "battery": "batterie",
    "monitors": "écrans",
    "audio": "audio",
    "tpm": "TPM",
    "license": "activation Windows",
}


@dataclass(frozen=True)
class Palette:
    bg: str
    card: str
    alt: str
    line: str
    fg: str
    dim: str
    green: str
    blue: str
    amber: str
    row: str
    subtle: str


PALETTES = {
    "dark": Palette(
        bg="#0b1018", card="#111a25", alt="#162231", line="#223142", fg="#edf3fa", dim="#8c9bad",
        green="#51d6a5", blue="#68a9ff", amber="#f4bb65", row="#131e2a", subtle="#637386",
    ),
    "light": Palette(
        bg="#f3f6fa", card="#ffffff", alt="#e5ebf2", line="#d5dee8", fg="#172333", dim="#637386",
        green="#13865f", blue="#2766b2", amber="#98620a", row="#f7f9fc", subtle="#66788c",
    ),
}  # fmt: skip


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "AtlasPC" / "config.json"


def load_config() -> dict:
    try:
        config = json.loads(config_path().read_text(encoding="utf-8"))
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    try:
        config_path().parent.mkdir(parents=True, exist_ok=True)
        config_path().write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError as error:
        log.warning("Préférences non enregistrées : %s", error)


def enable_dpi_awareness() -> None:
    """Rendu net sur les écrans à mise à l'échelle (à appeler avant de créer la fenêtre)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def relaunch_command() -> tuple[str, list[str]]:
    """Exécutable et arguments pour relancer l'application à l'identique."""
    if getattr(sys, "frozen", False):
        return sys.executable, sys.argv[1:]
    executable = sys.executable
    windowed = Path(executable).with_name("pythonw.exe")
    if windowed.is_file():
        executable = str(windowed)
    main_module = sys.modules.get("__main__")
    if getattr(main_module, "__spec__", None) is not None:  # lancé par « python -m atlas »
        return executable, ["-m", "atlas", *sys.argv[1:]]
    return executable, [os.path.abspath(sys.argv[0]), *sys.argv[1:]]


class Atlas(tk.Tk):
    def __init__(self, scanner=scan):
        super().__init__()
        self.scanner = scanner
        self.config_data = load_config()
        self.theme = self.config_data.get("theme") if self.config_data.get("theme") in PALETTES else "dark"
        self.colors = PALETTES[self.theme]
        self.data: dict = {}
        self.page = OVERVIEW
        self.nav: dict[str, tk.Button] = {}
        self.trees: list[ttk.Treeview] = []
        self.wrapped: list[tuple[tk.Label, float, int]] = []
        self.query = tk.StringVar()
        self.query.trace_add("write", self._on_query)
        self._search_job = None
        self._status_job = None
        self._scanning = False
        self._results: queue.Queue = queue.Queue()

        self.title("Atlas PC — Informations système")
        width = min(1160, self.winfo_screenwidth() - 80)
        height = min(770, self.winfo_screenheight() - 120)
        self.geometry(f"{width}x{height}")
        self.minsize(min(880, width), min(600, height))
        self.build()
        self.refresh()

    # ------------------------------------------------------------------ construction

    def build(self) -> None:
        c = self.colors
        self.configure(bg=c.bg)
        self._style()
        header = tk.Frame(self, bg=c.bg, height=72)
        header.pack(fill="x", padx=26, pady=(17, 10))
        header.pack_propagate(False)
        tk.Label(header, text="◆  ATLAS PC", bg=c.bg, fg=c.green, font=(FONT, 18, "bold")).pack(side="left", pady=10)
        tk.Label(header, text=f"v{__version__}", bg=c.bg, fg=c.dim, font=(FONT, 8, "bold")).pack(side="left", padx=12)
        self.refresh_button = self.button(header, "↻ Actualiser", self.refresh, accent=True)
        self.refresh_button.pack(side="right")
        label = "☀ Thème clair" if self.theme == "dark" else "☾ Thème sombre"
        self.button(header, label, self.toggle_theme).pack(side="right", padx=(0, 8))
        self.status = tk.Label(header, bg=c.bg, fg=c.dim, font=(FONT, 9))
        self.status.pack(side="right", padx=12)
        box = tk.Frame(header, bg=c.card, highlightbackground=c.line, highlightthickness=1)
        box.pack(side="right", padx=(0, 4))
        tk.Label(box, text="⌕", bg=c.card, fg=c.dim, font=(FONT, 11)).pack(side="left", padx=(8, 0))
        self.search_entry = tk.Entry(
            box, textvariable=self.query, width=24, relief="flat", highlightthickness=0, bd=0, bg=c.card, fg=c.fg,
            insertbackground=c.fg, font=(FONT, 10),
        )  # fmt: skip
        self.search_entry.pack(side="left", padx=8, pady=7)
        self.bind_all("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.search_entry.bind("<Escape>", lambda _event: self.query.set(""))

        body = tk.Frame(self, bg=c.bg)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
        side = tk.Frame(body, bg=c.bg, width=215)
        side.pack(side="left", fill="y", padx=(0, 17))
        side.pack_propagate(False)
        tk.Label(side, text="MATÉRIEL", bg=c.bg, fg=c.subtle, font=(FONT, 8, "bold")).pack(anchor="w", padx=10, pady=(6, 8))
        self.nav = {}
        for name, icon in PAGES:
            button = tk.Button(
                side, text=f"{icon}   {name}", anchor="w", bg=c.bg, fg=c.dim, activebackground=c.alt,
                activeforeground=c.fg, relief="flat", highlightthickness=0, bd=0, padx=12, pady=7, font=(FONT, 10), cursor="hand2",
                command=lambda page=name: self.open_page(page),
            )  # fmt: skip
            button.pack(fill="x", pady=1)
            self.nav[name] = button
        tk.Frame(side, bg=c.line, height=1).pack(fill="x", pady=10)
        self.button(side, "⇩ Exporter le rapport", self.export).pack(fill="x", pady=(0, 6))
        self.button(side, "⧉ Copier le rapport", self.copy_report).pack(fill="x", pady=(0, 6))
        self.button(side, "⇄ Comparer à un rapport", self.compare).pack(fill="x", pady=(0, 6))
        self.admin_button = self.button(side, "⛨ Relancer en administrateur", self.relaunch_as_admin)

        pane = tk.Frame(body, bg=c.bg)
        pane.pack(side="left", fill="both", expand=True)
        self.title_label = tk.Label(pane, text=self.page, bg=c.bg, fg=c.fg, font=(FONT, 23, "bold"))
        self.title_label.pack(anchor="w")
        self.subtitle = tk.Label(pane, bg=c.bg, fg=c.dim, font=(FONT, 10))
        self.subtitle.pack(anchor="w", pady=(3, 12))
        area = tk.Frame(pane, bg=c.bg)
        area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(area, bg=c.bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview, style="Atlas.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=c.bg)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._on_wheel)
        self._set_status()

    def _style(self) -> None:
        c = self.colors
        style = ttk.Style(self)
        style.theme_use("clam")
        row_height = tk.font.Font(font=(FONT, 10)).metrics("linespace") + 12
        style.configure(
            "Atlas.Treeview", background=c.card, fieldbackground=c.card, foreground=c.fg, bordercolor=c.line,
            lightcolor=c.line, darkcolor=c.line, borderwidth=1, rowheight=row_height, font=(FONT, 10),
        )  # fmt: skip
        style.map("Atlas.Treeview", background=[("selected", c.blue)], foreground=[("selected", c.bg)])
        style.configure(
            "Atlas.Treeview.Heading", background=c.alt, foreground=c.dim, bordercolor=c.line, lightcolor=c.alt,
            darkcolor=c.alt, relief="flat", font=(FONT, 9, "bold"), padding=(8, 6),
        )  # fmt: skip
        style.map("Atlas.Treeview.Heading", background=[("active", c.alt)])
        style.configure(
            "Atlas.Vertical.TScrollbar", background=c.alt, troughcolor=c.bg, bordercolor=c.bg, lightcolor=c.alt,
            darkcolor=c.alt, arrowcolor=c.dim,
        )  # fmt: skip
        style.map("Atlas.Vertical.TScrollbar", background=[("active", c.line)])

    def button(self, parent, text: str, command, accent: bool = False) -> tk.Button:
        c = self.colors
        return tk.Button(
            parent, text=text, command=command, relief="flat", highlightthickness=0, bd=0, bg=c.green if accent else c.alt,
            fg=c.bg if accent else c.fg, activebackground=c.line, activeforeground=c.fg,
            disabledforeground=c.dim, font=(FONT, 9, "bold"), padx=13, pady=8, cursor="hand2",
        )  # fmt: skip

    # ------------------------------------------------------------------ état et événements

    def _set_status(self, flash: str = "") -> None:
        c = self.colors
        if self._status_job:
            self.after_cancel(self._status_job)
            self._status_job = None
        if flash:
            self.status.configure(text=f"✓ {flash}", fg=c.blue)
            self._status_job = self.after(2500, self._set_status)
        elif self._scanning:
            self.status.configure(text="● Analyse en cours…", fg=c.amber)
        elif self.data:
            self.status.configure(text="● Analyse terminée", fg=c.green)
        else:
            self.status.configure(text="● Analyse en attente", fg=c.dim)
        self.refresh_button.configure(state="disabled" if self._scanning else "normal")
        needs_admin = os.name == "nt" and bool(self.data) and "admin" in self.data and not self.data.get("admin")
        if needs_admin and not self.admin_button.winfo_manager():
            self.admin_button.pack(fill="x")
        elif not needs_admin and self.admin_button.winfo_manager():
            self.admin_button.pack_forget()

    def _on_resize(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)
        for label, share, margin in self.wrapped:
            if label.winfo_exists():
                label.configure(wraplength=max(120, int(event.width * share) - margin))

    def _on_wheel(self, event) -> None:
        if not isinstance(event.widget, tk.Misc) or event.widget.winfo_toplevel() is not self:
            return
        if self.canvas.yview() == (0.0, 1.0):
            return
        if event.num in (4, 5):
            steps = -1 if event.num == 4 else 1
        else:
            steps = -1 if event.delta > 0 else 1
            if abs(event.delta) >= 120:
                steps = int(-event.delta / 120)
        self.canvas.yview_scroll(steps, "units")

    def _on_query(self, *_args) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(200, self.render)

    def toggle_theme(self) -> None:
        self.theme = "light" if self.theme == "dark" else "dark"
        self.colors = PALETTES[self.theme]
        self.config_data["theme"] = self.theme
        save_config(self.config_data)
        for widget in self.winfo_children():
            widget.destroy()
        self.build()
        self.render()

    # ------------------------------------------------------------------ collecte

    def refresh(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._set_status()
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(100, self._poll)

    def _worker(self) -> None:
        try:
            result = self.scanner()
        except Exception as error:  # la collecte ne doit jamais faire tomber l'interface
            log.exception("Collecte interrompue")
            result = {
                "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "system": {"computer": socket.gethostname(), "platform": platform.platform(), "architecture": platform.machine()},
                "note": f"Erreur inattendue pendant la collecte : {error}",
            }
        self._results.put(result)

    def _poll(self) -> None:
        """Récupère le résultat dans le thread de l'interface (jamais d'appel Tk depuis le thread de collecte)."""
        try:
            self.data = self._results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll)
            return
        self._scanning = False
        self._set_status()
        self.render()

    # ------------------------------------------------------------------ rendu

    def open_page(self, page: str) -> None:
        self.page = page
        if self.query.get():
            self.query.set("")
        self.render()

    def render(self) -> None:
        self._search_job = None
        c = self.colors
        query = self.query.get().strip()
        for widget in self.inner.winfo_children():
            widget.destroy()
        self.trees = []
        self.wrapped = []
        for name, button in self.nav.items():
            active = name == self.page and not query
            button.configure(bg=c.alt if active else c.bg, fg=c.green if active else c.dim)
        if query:
            self.title_label.configure(text="Recherche")
            self._render_search(query)
        else:
            self.title_label.configure(text=self.page)
            stamp = fmt_date(self.data.get("captured_at", "")[:19]) if self.data else ""
            self.subtitle.configure(text=f"Inventaire du {stamp}" if stamp and stamp != EMPTY else "Analyse en cours…")
            if self.data:
                if self.page == OVERVIEW:
                    self._render_overview()
                else:
                    self._render_sections(build_page(self.data, self.page))
        self.canvas.yview_moveto(0)

    def heading(self, text: str) -> None:
        tk.Label(self.inner, text=text, bg=self.colors.bg, fg=self.colors.fg, font=(FONT, 12, "bold")).pack(anchor="w", pady=(14, 8))

    def note(self, text: str, color: str | None = None) -> None:
        label = tk.Label(
            self.inner, text=text, bg=self.colors.bg, fg=color or self.colors.dim, justify="left", anchor="w", font=(FONT, 9),
        )  # fmt: skip
        label.pack(fill="x", pady=(5, 0))
        self._wrap(label, 1.0, 10)

    def _wrap(self, label: tk.Label, share: float, margin: int) -> None:
        self.wrapped.append((label, share, margin))
        width = self.canvas.winfo_width()
        if width > 1:
            label.configure(wraplength=max(120, int(width * share) - margin))

    def table(self, columns: list[tuple[str, int, bool]], rows: list[tuple], headings: bool = False, parent=None) -> ttk.Treeview:
        """Tableau sélectionnable : Ctrl+C, double-clic ou clic droit pour copier."""
        tree = ttk.Treeview(
            parent or self.inner, columns=[name for name, _w, _s in columns], show="headings" if headings else "",
            height=max(len(rows), 1), selectmode="extended", style="Atlas.Treeview",
        )  # fmt: skip
        for name, width, stretch in columns:
            tree.heading(name, text=name, anchor="w")
            tree.column(name, width=width, minwidth=90, stretch=stretch, anchor="w")
        tree.tag_configure("odd", background=self.colors.row)
        for index, row in enumerate(rows):
            tree.insert("", "end", values=row, tags=("odd",) if index % 2 else ())
        tree.bind("<Control-c>", lambda _event, t=tree: self.copy_rows(t))
        tree.bind("<Control-C>", lambda _event, t=tree: self.copy_rows(t))
        tree.bind("<Double-1>", lambda event, t=tree: self.copy_value(t, event))
        tree.bind("<Button-3>", lambda event, t=tree: self.popup(t, event))
        tree.bind("<<TreeviewSelect>>", lambda _event, t=tree: self._single_selection(t))
        self.trees.append(tree)
        return tree

    def _single_selection(self, active: ttk.Treeview) -> None:
        if not active.selection():
            return
        for tree in self.trees:
            if tree is not active and tree.winfo_exists() and tree.selection():
                tree.selection_remove(*tree.selection())

    def _render_sections(self, sections: list[Section]) -> None:
        for section in sections:
            self.heading(section.title)
            if section.rows:
                rows = [(row.label, row.value) for row in section.rows]
                self.table([("Propriété", 270, False), ("Valeur", 480, True)], rows).pack(fill="x")
            if section.note:
                self.note(section.note, self.colors.amber)
            elif not section.rows:
                self.note("Aucune information détectée.")
        if self.data.get("note"):
            self.note(self.data["note"], self.colors.amber)

    def _render_search(self, query: str) -> None:
        hits = search(self.data, query) if self.data else []
        self.subtitle.configure(text=f"{len(hits)} résultat(s) pour « {query} » — Échap pour revenir")
        if not hits:
            self.note("Aucun résultat. La recherche porte sur toutes les pages, sans tenir compte des accents.")
            return
        rows = [(f"{page} › {section}", row.label, row.value) for page, section, row in hits]
        columns = [("Emplacement", 340, False), ("Propriété", 210, False), ("Valeur", 240, True)]
        self.table(columns, rows, headings=True).pack(fill="x", pady=(4, 0))

    def _render_overview(self) -> None:
        c, d = self.colors, self.data
        host = d.get("system") or {}
        system = d.get("os") or {}
        memory = d.get("memory") or {}
        top = tk.Frame(self.inner, bg=c.bg)
        top.pack(fill="x")
        hero = tk.Frame(top, bg=c.card, highlightbackground=c.line, highlightthickness=1, padx=19, pady=17)
        hero.pack(side="left", fill="both", expand=True, padx=(0, 9))
        tk.Label(hero, text="VOTRE ORDINATEUR", bg=c.card, fg=c.green, font=(FONT, 8, "bold")).pack(anchor="w")
        tk.Label(hero, text=host.get("computer", ""), bg=c.card, fg=c.fg, font=(FONT, 20, "bold")).pack(anchor="w", pady=5)
        version = f" {system['DisplayVersion']}" if system.get("DisplayVersion") else ""
        summary = (
            f"{system.get('Caption') or host.get('platform', '')}{version} · {system.get('OSArchitecture') or host.get('architecture', '')}"
        )
        label = tk.Label(hero, text=summary, bg=c.card, fg=c.dim, justify="left", font=(FONT, 10))
        label.pack(anchor="w")
        self._wrap(label, 1.0, 290)

        card = tk.Frame(top, bg=c.card, highlightbackground=c.line, highlightthickness=1, width=215, padx=15, pady=16)
        card.pack(side="right", fill="y")
        card.pack_propagate(False)
        tk.Label(card, text="MÉMOIRE UTILISÉE", bg=c.card, fg=c.dim, font=(FONT, 8, "bold")).pack(anchor="w")
        percent = memory.get("percent")
        tk.Label(card, text=f"{percent} %" if percent is not None else EMPTY, bg=c.card, fg=c.green, font=(FONT, 24, "bold")).pack(
            anchor="w"
        )
        bar = tk.Frame(card, bg=c.alt, height=6)
        bar.pack(fill="x", pady=(2, 6))
        if percent:
            tk.Frame(bar, bg=c.amber if percent >= 85 else c.green).place(relwidth=min(percent, 100) / 100, relheight=1)
        usage = f"{fmt_binary(memory.get('used'))} sur {fmt_binary(memory.get('total'))}"
        tk.Label(card, text=usage, bg=c.card, fg=c.dim, font=(FONT, 9)).pack(anchor="w")

        self.heading("Vue rapide")
        grid = tk.Frame(self.inner, bg=c.bg)
        grid.pack(fill="x")
        accents = (c.green, c.green, c.green, c.blue, c.amber, c.blue)
        for index, (title, value, detail) in enumerate(overview_tiles(d)):
            tile = tk.Frame(grid, bg=c.card, highlightbackground=c.line, highlightthickness=1, padx=15, pady=13)
            tk.Label(tile, text=title.upper(), bg=c.card, fg=c.dim, font=(FONT, 8, "bold")).pack(anchor="w")
            text = value if value and value != EMPTY else "Non détecté"
            main = tk.Label(tile, text=text, bg=c.card, fg=c.fg, font=(FONT, 12, "bold"), justify="left")
            main.pack(anchor="w", pady=(7, 2))
            self._wrap(main, 1 / 3, 44)
            tk.Label(tile, text=detail, bg=c.card, fg=accents[index % len(accents)], font=(FONT, 9)).pack(anchor="w")
            tile.grid(row=index // 3, column=index % 3, sticky="nsew", padx=(0, 8) if index % 3 < 2 else 0, pady=(0, 8))
        for column in range(3):
            grid.columnconfigure(column, weight=1, uniform="tiles")

        self.heading("Températures")
        readings = [fmt_celsius(zone.get("Celsius")) for zone in (d.get("temperatures") or [])[:4]]
        readings += [
            f"{disk.get('Model')} : {fmt_celsius(disk.get('Temperature'))}"
            for disk in d.get("disks") or []
            if isinstance(disk.get("Temperature"), (int, float)) and 0 < disk["Temperature"] <= 120
        ]
        fallback = "Aucun capteur exposé par Windows. Une session administrateur ou les pilotes du fabricant peuvent être nécessaires."
        message = " · ".join(readings) or fallback
        label = tk.Label(
            self.inner, text=message, bg=c.card, fg=c.amber if readings else c.dim, justify="left", anchor="w", padx=14, pady=13
        )
        label.pack(fill="x")
        self._wrap(label, 1.0, 40)

        errors = d.get("errors") or {}
        if errors:
            names = sorted({SOURCE_NAMES.get(key, key) for key in errors})
            hint = "" if d.get("admin") else " Certaines exigent une session administrateur."
            self.note(f"Sources indisponibles : {', '.join(names)}.{hint} Le détail figure sur chaque page.", c.amber)
        if d.get("note"):
            self.note(d["note"], c.amber)

    # ------------------------------------------------------------------ copie

    def _to_clipboard(self, text: str, message: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status(flash=message)

    def copy_rows(self, tree: ttk.Treeview) -> str:
        lines = ["\t".join(str(value) for value in tree.item(item, "values")) for item in tree.selection()]
        if lines:
            self._to_clipboard("\n".join(lines), f"{len(lines)} ligne(s) copiée(s)")
        return "break"

    def copy_value(self, tree: ttk.Treeview, event=None, item: str = "") -> None:
        item = item or (tree.identify_row(event.y) if event else "")
        if item:
            self._to_clipboard(str(tree.item(item, "values")[-1]), "Valeur copiée")

    def popup(self, tree: ttk.Treeview, event) -> None:
        item = tree.identify_row(event.y)
        if not item:
            return
        if item not in tree.selection():
            tree.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copier la valeur", command=lambda: self.copy_value(tree, item=item))
        menu.add_command(label="Copier la ligne", command=lambda: self.copy_rows(tree))
        menu.tk_popup(event.x_root, event.y_root)

    def copy_report(self) -> None:
        if self.data:
            self._to_clipboard(export.to_text(self.data), "Rapport copié")

    # ------------------------------------------------------------------ export, comparaison, élévation

    def export(self) -> None:
        if not self.data:
            return
        chosen = tk.StringVar()
        path = filedialog.asksaveasfilename(
            parent=self, title="Exporter le rapport", initialfile=f"atlas-pc-{datetime.now():%Y%m%d-%H%M}",
            filetypes=[(label, f"*{suffix}") for suffix, label in export.FORMATS.items()], typevariable=chosen,
        )  # fmt: skip
        if not path:
            return
        try:
            target = export.save(self.data, path, chosen.get())
        except OSError as error:
            messagebox.showerror("Export impossible", str(error), parent=self)
            return
        messagebox.showinfo("Rapport exporté", f"Rapport enregistré :\n{target}", parent=self)

    def compare(self) -> None:
        if not self.data:
            return
        path = filedialog.askopenfilename(parent=self, title="Choisir un rapport JSON d'Atlas PC", filetypes=[("Rapport JSON", "*.json")])
        if not path:
            return
        try:
            previous = export.load(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Rapport illisible", str(error), parent=self)
            return
        changes = diff_reports(previous, self.data)
        stamp = fmt_date(str(previous.get("captured_at", ""))[:19])
        other = (previous.get("system") or {}).get("computer", "")
        if not changes:
            messagebox.showinfo("Comparaison", f"Aucune différence matérielle avec le rapport du {stamp}.", parent=self)
            return
        c = self.colors
        window = tk.Toplevel(self, bg=c.bg)
        window.title("Atlas PC — Comparaison de rapports")
        window.geometry(f"{min(980, self.winfo_screenwidth() - 80)}x{min(560, self.winfo_screenheight() - 160)}")
        text = f"{len(changes)} différence(s) entre le rapport du {stamp} et l'inventaire actuel"
        if other and other != (self.data.get("system") or {}).get("computer"):
            text += f" — attention, ce rapport vient d'un autre poste ({other})"
        tk.Label(window, text=text, bg=c.bg, fg=c.fg, font=(FONT, 11, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 10))
        frame = tk.Frame(window, bg=c.bg)
        frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        columns = [("Emplacement", 250, False), ("Propriété", 190, False), ("Avant", 230, True), ("Maintenant", 230, True)]
        tree = self.table(columns, changes, headings=True, parent=frame)
        tree.configure(height=12)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="Atlas.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

    def relaunch_as_admin(self) -> None:
        if os.name != "nt":
            return
        import ctypes

        executable, arguments = relaunch_command()
        code = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, subprocess.list2cmdline(arguments), os.getcwd(), 1)
        if code > 32:  # la nouvelle instance élevée a démarré
            self.destroy()
        else:
            self._set_status(flash="Élévation annulée")


def run() -> None:
    enable_dpi_awareness()
    Atlas().mainloop()
