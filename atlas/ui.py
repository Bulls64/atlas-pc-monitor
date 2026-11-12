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
import tempfile
import threading
import tkinter as tk
import tkinter.font
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, export, fiche, privacy
from .collect import scan
from .findings import FIX, INFO, LEVELS, OK, WATCH, Finding, analyze, summary, summary_text
from .formatting import EMPTY, fmt_binary, fmt_celsius, fmt_date
from .pages import FINDINGS, OVERVIEW, PAGES, SOURCE_LABELS, Section, build_page, diff_reports, overview_tiles, search

log = logging.getLogger("atlas")
FONT = "Segoe UI"

SOURCE_NAMES = SOURCE_LABELS


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
    red: str
    row: str
    subtle: str


PALETTES = {
    "dark": Palette(
        bg="#0b1018", card="#111a25", alt="#162231", line="#223142", fg="#edf3fa", dim="#8c9bad",
        green="#51d6a5", blue="#68a9ff", amber="#f4bb65", red="#ff7b72", row="#131e2a", subtle="#637386",
    ),
    "light": Palette(
        bg="#f3f6fa", card="#ffffff", alt="#e5ebf2", line="#d5dee8", fg="#172333", dim="#637386",
        green="#13865f", blue="#2766b2", amber="#98620a", red="#c0392b", row="#f7f9fc", subtle="#66788c",
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
        self.sharing = bool(self.config_data.get("sharing", False))
        self._shown: tuple[int, bool, dict] | None = None
        self.findings: list[Finding] = []
        self.fiche_info = fiche.FicheInfo(technician=str(self.config_data.get("technician", "")))
        self.fiche_window: tk.Toplevel | None = None
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
        # Facteur d'échelle de l'écran (1 à 100 %, 1,5 à 150 %) : les dimensions en pixels le suivent.
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96)
        width = min(self.px(1160), self.winfo_screenwidth() - 80)
        height = min(self.px(770), self.winfo_screenheight() - 120)
        self.geometry(f"{width}x{height}")
        self.minsize(min(self.px(880), width), min(self.px(600), height))
        self.build()
        self.refresh()

    def px(self, value: float) -> int:
        """Pixels « 100 % » convertis à l'échelle de l'écran."""
        return int(round(value * getattr(self, "scale", 1.0)))

    @property
    def shown(self) -> dict:
        """Inventaire tel qu'il est affiché et partagé : masqué quand le mode partage est actif."""
        if not self.sharing or not self.data:
            return self.data
        key = (id(self.data), self.sharing)
        if self._shown is None or self._shown[:2] != key:
            self._shown = (*key, privacy.anonymize(self.data))
        return self._shown[2]

    # ------------------------------------------------------------------ construction

    def build(self) -> None:
        c = self.colors
        self.configure(bg=c.bg)
        self._style()
        header = tk.Frame(self, bg=c.bg, height=self.px(72))
        header.pack(fill="x", padx=self.px(26), pady=(self.px(17), self.px(10)))
        header.pack_propagate(False)
        tk.Label(header, text="◆  ATLAS PC", bg=c.bg, fg=c.green, font=(FONT, 18, "bold")).pack(side="left", pady=self.px(10))
        tk.Label(header, text=f"v{__version__}", bg=c.bg, fg=c.dim, font=(FONT, 8, "bold")).pack(side="left", padx=self.px(12))
        self.refresh_button = self.button(header, "↻ Actualiser", self.refresh, accent=True)
        self.refresh_button.pack(side="right")
        label = "☀ Thème clair" if self.theme == "dark" else "☾ Thème sombre"
        self.button(header, label, self.toggle_theme).pack(side="right", padx=(self.px(0), self.px(8)))
        self.sharing_button = self.button(header, "", self.toggle_sharing)
        self.sharing_button.pack(side="right", padx=(self.px(0), self.px(8)))

        box = tk.Frame(header, bg=c.card, highlightbackground=c.line, highlightthickness=1)
        box.pack(side="right", padx=(self.px(0), self.px(4)))
        tk.Label(box, text="⌕", bg=c.card, fg=c.dim, font=(FONT, 11)).pack(side="left", padx=(self.px(8), self.px(0)))
        self.search_entry = tk.Entry(
            box, textvariable=self.query, width=24, relief="flat", highlightthickness=0, bd=0, bg=c.card, fg=c.fg,
            insertbackground=c.fg, font=(FONT, 10),
        )  # fmt: skip
        self.search_entry.pack(side="left", padx=self.px(8), pady=self.px(7))
        # placé en dernier : c'est le message d'état, éphémère, qui cède la place si la fenêtre est étroite
        self.status = tk.Label(header, bg=c.bg, fg=c.dim, font=(FONT, 9))
        self.status.pack(side="right", padx=self.px(12))
        self.bind_all("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.search_entry.bind("<Escape>", lambda _event: self.query.set(""))

        body = tk.Frame(self, bg=c.bg)
        body.pack(fill="both", expand=True, padx=self.px(26), pady=(self.px(0), self.px(18)))
        # Barre latérale défilante : sur un petit écran ou à 125-150 %, les boutons du bas restent accessibles.
        self.side_outer = tk.Frame(body, bg=c.bg, width=self.px(215))
        self.side_outer.pack(side="left", fill="y", padx=(0, self.px(17)))
        self.side_outer.pack_propagate(False)
        self.side_canvas = tk.Canvas(self.side_outer, bg=c.bg, highlightthickness=0, bd=0)
        self.side_scrollbar = ttk.Scrollbar(
            self.side_outer, orient="vertical", command=self.side_canvas.yview, style="Atlas.Vertical.TScrollbar"
        )
        self.side_canvas.configure(yscrollcommand=self.side_scrollbar.set)
        self.side_canvas.pack(side="left", fill="both", expand=True)
        side = tk.Frame(self.side_canvas, bg=c.bg)
        self.side_inner = side
        self.side_window = self.side_canvas.create_window((0, 0), window=side, anchor="nw")
        side.bind("<Configure>", lambda _event: self._update_sidebar())
        self.side_canvas.bind("<Configure>", lambda _event: self._update_sidebar())
        tk.Label(side, text="MATÉRIEL", bg=c.bg, fg=c.subtle, font=(FONT, 8, "bold")).pack(
            anchor="w", padx=self.px(10), pady=(self.px(6), self.px(8))
        )
        self.nav = {}
        for name, icon in PAGES:
            button = tk.Button(
                side, text=f"{icon}   {name}", anchor="w", bg=c.bg, fg=c.dim, activebackground=c.alt,
                activeforeground=c.fg, relief="flat", highlightthickness=0, bd=0, padx=self.px(12), pady=self.px(7),
                font=(FONT, 10), cursor="hand2",
                command=lambda page=name: self.open_page(page),
            )  # fmt: skip
            button.pack(fill="x", pady=self.px(1))
            self.nav[name] = button
        tk.Frame(side, bg=c.line, height=1).pack(fill="x", pady=self.px(10))
        self.button(side, "🖨 Fiche d'intervention", self.open_fiche, accent=True).pack(fill="x", pady=(self.px(0), self.px(6)))
        self.button(side, "⇩ Exporter le rapport", self.export).pack(fill="x", pady=(self.px(0), self.px(6)))
        self.button(side, "⧉ Copier le rapport", self.copy_report).pack(fill="x", pady=(self.px(0), self.px(6)))
        self.button(side, "⇄ Comparer à un rapport", self.compare).pack(fill="x", pady=(self.px(0), self.px(6)))

        self.admin_button = self.button(side, "⛨ Relancer en administrateur", self.relaunch_as_admin)

        pane = tk.Frame(body, bg=c.bg)
        pane.pack(side="left", fill="both", expand=True)
        self.title_label = tk.Label(pane, text=self.page, bg=c.bg, fg=c.fg, font=(FONT, 23, "bold"))
        self.title_label.pack(anchor="w")
        self.subtitle = tk.Label(pane, bg=c.bg, fg=c.dim, font=(FONT, 10))
        self.subtitle.pack(anchor="w", pady=(self.px(3), self.px(12)))
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
        row_height = tk.font.Font(font=(FONT, 10)).metrics("linespace") + self.px(12)
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
            disabledforeground=c.dim, font=(FONT, 9, "bold"), padx=self.px(13), pady=self.px(8), cursor="hand2",
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
        if self.sharing:
            self.sharing_button.configure(text="◑ Partage activé", bg=c.amber, fg=c.bg)
        else:
            self.sharing_button.configure(text="◐ Mode partage", bg=c.alt, fg=c.fg)
        needs_admin = os.name == "nt" and bool(self.data) and "admin" in self.data and not self.data.get("admin")
        if needs_admin and not self.admin_button.winfo_manager():
            self.admin_button.pack(fill="x")
        elif not needs_admin and self.admin_button.winfo_manager():
            self.admin_button.pack_forget()

    def _on_resize(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)
        for label, share, margin in self.wrapped:
            if label.winfo_exists():
                label.configure(wraplength=max(self.px(120), int(event.width * share) - self.px(margin)))

    def _update_sidebar(self) -> None:
        """Ajuste la zone défilante et n'affiche l'ascenseur que si le contenu dépasse."""
        canvas = self.side_canvas
        overflow = self.side_inner.winfo_reqheight() > canvas.winfo_height() > 1
        if overflow and not self.side_scrollbar.winfo_manager():
            self.side_scrollbar.pack(side="right", fill="y", before=canvas)
        elif not overflow and self.side_scrollbar.winfo_manager():
            self.side_scrollbar.pack_forget()
            canvas.yview_moveto(0)
        canvas.itemconfigure(self.side_window, width=canvas.winfo_width())
        canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), self.side_inner.winfo_reqheight()))

    def _inside(self, widget, container) -> bool:
        while widget is not None:
            if widget is container:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _on_wheel(self, event) -> None:
        if not isinstance(event.widget, tk.Misc) or event.widget.winfo_toplevel() is not self:
            return
        target = self.side_canvas if self._inside(event.widget, self.side_outer) else self.canvas
        if target.yview() == (0.0, 1.0):
            return
        if event.num in (4, 5):
            steps = -1 if event.num == 4 else 1
        else:
            steps = -1 if event.delta > 0 else 1
            if abs(event.delta) >= 120:
                steps = int(-event.delta / 120)
        target.yview_scroll(steps, "units")

    def _on_query(self, *_args) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(200, self.render)

    def toggle_sharing(self) -> None:
        """Masque ou affiche les identifiants (séries, MAC, IP, nom du poste) partout dans l'application."""
        self.sharing = not self.sharing
        self.config_data["sharing"] = self.sharing
        save_config(self.config_data)
        self._set_status(flash="Identifiants masqués" if self.sharing else "Identifiants affichés")
        if self.data:
            self.render()

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
        self.findings = analyze(self.data)
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
        self._update_findings_nav()
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
                elif self.page == FINDINGS:
                    self._render_findings()
                else:
                    self._render_sections(build_page(self.shown, self.page))
        self.canvas.yview_moveto(0)

    def heading(self, text: str) -> None:
        tk.Label(self.inner, text=text, bg=self.colors.bg, fg=self.colors.fg, font=(FONT, 12, "bold")).pack(
            anchor="w", pady=(self.px(14), self.px(8))
        )

    def note(self, text: str, color: str | None = None) -> None:
        label = tk.Label(
            self.inner, text=text, bg=self.colors.bg, fg=color or self.colors.dim, justify="left", anchor="w", font=(FONT, 9),
        )  # fmt: skip
        label.pack(fill="x", pady=(self.px(5), self.px(0)))
        self._wrap(label, 1.0, 10)

    def _wrap(self, label: tk.Label, share: float, margin: int) -> None:
        self.wrapped.append((label, share, margin))
        width = self.canvas.winfo_width()
        if width > 1:
            label.configure(wraplength=max(self.px(120), int(width * share) - self.px(margin)))

    def table(self, columns: list[tuple[str, int, bool]], rows: list[tuple], headings: bool = False, parent=None) -> ttk.Treeview:
        """Tableau sélectionnable : Ctrl+C, double-clic ou clic droit pour copier."""
        tree = ttk.Treeview(
            parent or self.inner, columns=[name for name, _w, _s in columns], show="headings" if headings else "",
            height=max(len(rows), 1), selectmode="extended", style="Atlas.Treeview",
        )  # fmt: skip
        for name, width, stretch in columns:
            tree.heading(name, text=name, anchor="w")
            tree.column(name, width=self.px(width), minwidth=self.px(90), stretch=stretch, anchor="w")
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
            if section.tip:
                self.note(section.tip)
        if self.data.get("note"):
            self.note(self.data["note"], self.colors.amber)

    def _render_search(self, query: str) -> None:
        hits = search(self.shown, query) if self.data else []
        self.subtitle.configure(text=f"{len(hits)} résultat(s) pour « {query} » — Échap pour revenir")
        if not hits:
            self.note("Aucun résultat. La recherche porte sur toutes les pages, sans tenir compte des accents.")
            return
        rows = [(f"{page} › {section}", row.label, row.value) for page, section, row in hits]
        columns = [("Emplacement", 340, False), ("Propriété", 210, False), ("Valeur", 240, True)]
        self.table(columns, rows, headings=True).pack(fill="x", pady=(self.px(4), self.px(0)))

    def _render_overview(self) -> None:
        c, d = self.colors, self.shown
        host = d.get("system") or {}
        system = d.get("os") or {}
        memory = d.get("memory") or {}
        top = tk.Frame(self.inner, bg=c.bg)
        top.pack(fill="x")
        hero = tk.Frame(top, bg=c.card, highlightbackground=c.line, highlightthickness=1, padx=self.px(19), pady=self.px(17))
        hero.pack(side="left", fill="both", expand=True, padx=(self.px(0), self.px(9)))
        tk.Label(hero, text="VOTRE ORDINATEUR", bg=c.card, fg=c.green, font=(FONT, 8, "bold")).pack(anchor="w")
        tk.Label(hero, text=host.get("computer", ""), bg=c.card, fg=c.fg, font=(FONT, 20, "bold")).pack(anchor="w", pady=self.px(5))
        version = f" {system['DisplayVersion']}" if system.get("DisplayVersion") else ""
        summary = (
            f"{system.get('Caption') or host.get('platform', '')}{version} · {system.get('OSArchitecture') or host.get('architecture', '')}"
        )
        label = tk.Label(hero, text=summary, bg=c.card, fg=c.dim, justify="left", font=(FONT, 10))
        label.pack(anchor="w")
        self._wrap(label, 1.0, 290)

        card = tk.Frame(
            top, bg=c.card, highlightbackground=c.line, highlightthickness=1, width=self.px(215), padx=self.px(15), pady=self.px(16)
        )
        card.pack(side="right", fill="y")
        card.pack_propagate(False)
        tk.Label(card, text="MÉMOIRE UTILISÉE", bg=c.card, fg=c.dim, font=(FONT, 8, "bold")).pack(anchor="w")
        percent = memory.get("percent")
        tk.Label(card, text=f"{percent} %" if percent is not None else EMPTY, bg=c.card, fg=c.green, font=(FONT, 24, "bold")).pack(
            anchor="w"
        )
        bar = tk.Frame(card, bg=c.alt, height=self.px(6))
        bar.pack(fill="x", pady=(self.px(2), self.px(6)))
        if percent:
            tk.Frame(bar, bg=c.amber if percent >= 85 else c.green).place(relwidth=min(percent, 100) / 100, relheight=1)
        usage = f"{fmt_binary(memory.get('used'))} sur {fmt_binary(memory.get('total'))}"
        tk.Label(card, text=usage, bg=c.card, fg=c.dim, font=(FONT, 9)).pack(anchor="w")

        if self.findings:
            self._findings_banner()
        self.heading("Vue rapide")
        grid = tk.Frame(self.inner, bg=c.bg)
        grid.pack(fill="x")
        accents = (c.green, c.green, c.green, c.blue, c.amber, c.blue)
        for index, (title, value, detail) in enumerate(overview_tiles(d)):
            tile = tk.Frame(grid, bg=c.card, highlightbackground=c.line, highlightthickness=1, padx=self.px(15), pady=self.px(13))
            tk.Label(tile, text=title.upper(), bg=c.card, fg=c.dim, font=(FONT, 8, "bold")).pack(anchor="w")
            text = value if value and value != EMPTY else "Non détecté"
            main = tk.Label(tile, text=text, bg=c.card, fg=c.fg, font=(FONT, 12, "bold"), justify="left")
            main.pack(anchor="w", pady=(self.px(7), self.px(2)))
            self._wrap(main, 1 / 3, 44)
            tk.Label(tile, text=detail, bg=c.card, fg=accents[index % len(accents)], font=(FONT, 9)).pack(anchor="w")
            tile.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=(self.px(0), self.px(8)) if index % 3 < 2 else 0,
                pady=(self.px(0), self.px(8)),
            )
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
            self.inner,
            text=message,
            bg=c.card,
            fg=c.amber if readings else c.dim,
            justify="left",
            anchor="w",
            padx=self.px(14),
            pady=self.px(13),
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

    # ------------------------------------------------------------------ constats

    def level_color(self, level: str) -> str:
        c = self.colors
        return {FIX: c.red, WATCH: c.amber, INFO: c.blue, OK: c.green}[level]

    def _update_findings_nav(self) -> None:
        button = self.nav.get(FINDINGS)
        if not button:
            return
        icon = dict(PAGES)[FINDINGS]
        counts = summary(self.findings)
        alerts = counts[FIX] + counts[WATCH]
        button.configure(text=f"{icon}   {FINDINGS}" + (f"  ({alerts})" if alerts else ""))
        if self.page != FINDINGS or self.query.get().strip():
            if counts[FIX]:
                button.configure(fg=self.colors.red)
            elif counts[WATCH]:
                button.configure(fg=self.colors.amber)

    def _findings_banner(self) -> None:
        """Bandeau cliquable de la vue d'ensemble : le résumé des constats."""
        c = self.colors
        counts = summary(self.findings)
        level = FIX if counts[FIX] else WATCH if counts[WATCH] else OK
        color = self.level_color(level)
        banner = tk.Frame(self.inner, bg=c.card, highlightbackground=c.line, highlightthickness=1, cursor="hand2")
        banner.pack(fill="x", pady=(self.px(10), self.px(0)))
        tk.Frame(banner, bg=color, width=self.px(5)).pack(side="left", fill="y")
        body = tk.Frame(banner, bg=c.card, padx=self.px(14), pady=self.px(10), cursor="hand2")
        body.pack(side="left", fill="x", expand=True)
        tk.Label(body, text="CONSTATS", bg=c.card, fg=c.dim, font=(FONT, 8, "bold"), cursor="hand2").pack(anchor="w")
        headline = summary_text(self.findings)
        if level == OK:
            headline = "Rien à corriger ni à surveiller"
        tk.Label(body, text=headline, bg=c.card, fg=color, font=(FONT, 12, "bold"), cursor="hand2").pack(
            anchor="w", pady=(self.px(3), self.px(0))
        )
        urgent = [item.title for item in self.findings if item.level in (FIX, WATCH)][:3]
        if urgent:
            label = tk.Label(body, text=" · ".join(urgent), bg=c.card, fg=c.dim, font=(FONT, 9), justify="left", cursor="hand2")
            label.pack(anchor="w", pady=(self.px(2), self.px(0)))
            self._wrap(label, 1.0, 80)
        link = tk.Label(banner, text="Voir les constats ›", bg=c.card, fg=c.blue, font=(FONT, 9, "bold"), cursor="hand2")
        link.pack(side="right", padx=self.px(14))
        for widget in (banner, body, link, *body.winfo_children()):
            widget.bind("<Button-1>", lambda _event: self.open_page(FINDINGS))

    def _render_findings(self) -> None:
        c = self.colors
        counts = summary(self.findings)
        parts = [
            f"{counts[level]} {LEVELS[level] if level == OK else LEVELS[level].lower()}"
            for level in (FIX, WATCH, INFO, OK)
            if counts[level]
        ]
        self.subtitle.configure(text=" · ".join(parts) or "Aucun constat")
        if not self.findings:
            self.note("Aucun constat : l'inventaire Windows n'a pas pu être lu.", c.amber)
            return
        for level in (FIX, WATCH, INFO, OK):
            items = [item for item in self.findings if item.level == level]
            if not items:
                continue
            header = tk.Label(
                self.inner, text=f"{LEVELS[level]} ({len(items)})", bg=c.bg, fg=self.level_color(level), font=(FONT, 12, "bold")
            )
            header.pack(anchor="w", pady=(self.px(14), self.px(6)))
            for item in items:
                self._finding_card(item)
        tk.Label(
            self.inner,
            text="Seuils et règles : atlas/findings.py. Ce sont des repères d'atelier, pas des normes.",
            bg=c.bg, fg=c.subtle, font=(FONT, 8),
        ).pack(anchor="w", pady=(self.px(14), self.px(0)))  # fmt: skip

    def _finding_card(self, item: Finding) -> None:
        c = self.colors
        color = self.level_color(item.level)
        card = tk.Frame(self.inner, bg=c.card, highlightbackground=c.line, highlightthickness=1)
        card.pack(fill="x", pady=(self.px(0), self.px(6)))
        tk.Frame(card, bg=color, width=self.px(4)).pack(side="left", fill="y")
        body = tk.Frame(card, bg=c.card, padx=self.px(14), pady=self.px(10))
        body.pack(side="left", fill="x", expand=True)
        top = tk.Frame(body, bg=c.card)
        top.pack(fill="x")
        tk.Label(top, text=item.label.upper(), bg=c.card, fg=color, font=(FONT, 8, "bold")).pack(side="left")
        tk.Label(top, text=f"  ·  {item.topic}", bg=c.card, fg=c.dim, font=(FONT, 8)).pack(side="left")
        if item.page:
            link = tk.Label(top, text=f"{item.page} ›", bg=c.card, fg=c.blue, font=(FONT, 9), cursor="hand2")
            link.pack(side="right")
            link.bind("<Button-1>", lambda _event, page=item.page: self.open_page(page))
        title = tk.Label(body, text=item.title, bg=c.card, fg=c.fg, font=(FONT, 11, "bold"), justify="left", anchor="w")
        title.pack(fill="x", pady=(self.px(4), self.px(0)))
        self._wrap(title, 1.0, 60)
        if item.detail:
            detail = tk.Label(body, text=item.detail, bg=c.card, fg=c.fg, font=(FONT, 9), justify="left", anchor="w")
            detail.pack(fill="x", pady=(self.px(3), self.px(0)))
            self._wrap(detail, 1.0, 60)
        if item.advice:
            advice = tk.Label(body, text=f"→ {item.advice}", bg=c.card, fg=c.dim, font=(FONT, 9), justify="left", anchor="w")
            advice.pack(fill="x", pady=(self.px(3), self.px(0)))
            self._wrap(advice, 1.0, 60)
        menu_text = "\n".join(filter(None, [f"[{item.label}] {item.title}", item.detail, item.advice and f"→ {item.advice}"]))
        for widget in (card, body, top, *body.winfo_children()):
            widget.bind("<Button-3>", lambda event, text=menu_text: self._copy_menu(event, text))

    def _copy_menu(self, event, text: str) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copier ce constat", command=lambda: self._to_clipboard(text, "Constat copié"))
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------ fiche d'intervention

    def open_fiche(self) -> None:
        """Formulaire de la fiche : champs saisis, puis ouverture dans le navigateur pour imprimer."""
        if not self.data:
            return
        if self.fiche_window is not None and self.fiche_window.winfo_exists():
            self.fiche_window.lift()
            self.fiche_window.focus_set()
            return
        c = self.colors
        info = self.fiche_info
        if not info.reference:
            info.reference = fiche.default_reference(self.data)
        window = tk.Toplevel(self, bg=c.bg, padx=self.px(20), pady=self.px(16))
        window.title("Atlas PC — Fiche d'intervention")
        window.geometry(f"{min(self.px(640), self.winfo_screenwidth() - 80)}x{min(self.px(720), self.winfo_screenheight() - 120)}")
        window.transient(self)
        self.fiche_window = window
        tk.Label(window, text="Fiche d'intervention", bg=c.bg, fg=c.fg, font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(
            window, text="Tous les champs sont facultatifs : laissés vides, ils s'impriment comme des zones à remplir à la main.",
            bg=c.bg, fg=c.dim, font=(FONT, 9), wraplength=self.px(580), justify="left",
        ).pack(anchor="w", pady=(self.px(2), self.px(10)))  # fmt: skip

        grid = tk.Frame(window, bg=c.bg)
        grid.pack(fill="x")
        entries: dict[str, tk.Entry] = {}
        for row, (key, label) in enumerate(
            (("technician", "Technicien"), ("client", "Client"), ("contact", "Contact"), ("reference", "Référence"))
        ):
            tk.Label(grid, text=label, bg=c.bg, fg=c.dim, font=(FONT, 9, "bold")).grid(row=row, column=0, sticky="w", pady=self.px(3))
            frame = tk.Frame(grid, bg=c.card, highlightthickness=1, highlightbackground=c.line)
            frame.grid(row=row, column=1, sticky="ew", padx=(self.px(12), self.px(0)), pady=self.px(3))
            entry = tk.Entry(frame, relief="flat", bd=0, bg=c.card, fg=c.fg, insertbackground=c.fg, font=(FONT, 10), highlightthickness=0)
            entry.insert(0, getattr(info, key))
            entry.pack(fill="x", padx=self.px(8), pady=self.px(6))
            entry.bind("<FocusIn>", lambda _event, box=frame: box.configure(highlightbackground=c.green))
            entry.bind("<FocusOut>", lambda _event, box=frame: box.configure(highlightbackground=c.line))
            entries[key] = entry
        grid.columnconfigure(1, weight=1)

        texts: dict[str, tk.Text] = {}
        for key, label in (("request", "Demande du client"), ("work", "Travaux réalisés"), ("recommendations", "Recommandations")):
            head = tk.Frame(window, bg=c.bg)
            head.pack(fill="x", pady=(self.px(10), self.px(3)))
            tk.Label(head, text=label, bg=c.bg, fg=c.dim, font=(FONT, 9, "bold")).pack(side="left")
            box = tk.Text(
                window, height=4, wrap="word", relief="flat", bg=c.card, fg=c.fg, insertbackground=c.fg, font=(FONT, 10),
                highlightthickness=1, highlightbackground=c.line, highlightcolor=c.green, padx=self.px(8), pady=self.px(6), undo=True,
            )  # fmt: skip
            box.insert("1.0", getattr(info, key))
            box.pack(fill="both", expand=True)
            texts[key] = box
            if key == "recommendations":
                link = tk.Label(head, text="Reprendre les conseils des constats", bg=c.bg, fg=c.blue, font=(FONT, 9), cursor="hand2")
                link.pack(side="right")
                link.bind("<Button-1>", lambda _event, target=box: self._insert_advice(target))

        def collect() -> fiche.FicheInfo:
            for key, entry in entries.items():
                setattr(info, key, entry.get().strip())
            for key, box in texts.items():
                setattr(info, key, box.get("1.0", "end").strip())
            if info.technician != self.config_data.get("technician", ""):
                self.config_data["technician"] = info.technician
                save_config(self.config_data)
            return info

        bar = tk.Frame(window, bg=c.bg)
        bar.pack(fill="x", pady=(self.px(14), self.px(0)))
        self.button(bar, "🖨 Ouvrir pour imprimer", lambda: self.print_fiche(collect()), accent=True).pack(side="right")
        self.button(bar, "Enregistrer…", lambda: self.save_fiche(collect(), parent=window)).pack(
            side="right", padx=(self.px(0), self.px(8))
        )

        def close() -> None:
            collect()
            window.destroy()

        self.button(bar, "Fermer", close).pack(side="left")
        window.protocol("WM_DELETE_WINDOW", close)
        window.fiche_fields = (entries, texts)  # accès pour les tests
        entries["client"].focus_set()

    def _insert_advice(self, box: tk.Text) -> None:
        """Ajoute les conseils des constats à corriger et à surveiller, sans doublon."""
        current = box.get("1.0", "end")
        lines = [f"- {item.title} : {item.advice}" for item in self.findings if item.level in (FIX, WATCH) and item.advice]
        new = [line for line in lines if line not in current]
        if not new:
            self._set_status(flash="Aucun conseil à ajouter")
            return
        prefix = "" if not current.strip() else "\n"
        box.insert("end-1c", prefix + "\n".join(new))

    def fiche_html(self, info: fiche.FicheInfo) -> str:
        return fiche.to_html(self.shown, info, self.findings)

    def print_fiche(self, info: fiche.FicheInfo) -> Path | None:
        """Écrit la fiche dans le dossier temporaire et l'ouvre dans le navigateur (Ctrl+P pour imprimer ou faire un PDF)."""
        folder = Path(tempfile.gettempdir()) / "AtlasPC"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (info.reference or "fiche"))
        target = folder / f"fiche-{safe}.html"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target.write_text(self.fiche_html(info), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Fiche impossible", str(error), parent=self)
            return None
        if not webbrowser.open(target.as_uri()):
            messagebox.showinfo("Fiche d'intervention", f"Ouvrez ce fichier dans un navigateur pour l'imprimer :\n{target}", parent=self)
        self._set_status(flash="Fiche ouverte dans le navigateur")
        return target

    def save_fiche(self, info: fiche.FicheInfo, parent=None) -> Path | None:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (info.reference or "fiche"))
        path = filedialog.asksaveasfilename(
            parent=parent or self, title="Enregistrer la fiche d'intervention", initialfile=f"fiche-{safe}.html",
            defaultextension=".html", filetypes=[("Page HTML", "*.html")],
        )  # fmt: skip
        if not path:
            return None
        target = Path(path) if Path(path).suffix.lower() in (".html", ".htm") else Path(f"{path}.html")
        try:
            target.write_text(self.fiche_html(info), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Enregistrement impossible", str(error), parent=parent or self)
            return None
        self._set_status(flash="Fiche enregistrée")
        return target

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
            self._to_clipboard(export.to_text(self.shown), "Rapport copié")

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
            target = export.save(self.shown, path, chosen.get())
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
        current = self.data
        if self.sharing or previous.get("anonymized"):  # comparer à masquage égal
            previous, current = privacy.anonymize(previous), privacy.anonymize(current)
        changes = diff_reports(previous, current)
        stamp = fmt_date(str(previous.get("captured_at", ""))[:19])
        other = (previous.get("system") or {}).get("computer", "")
        if not changes:
            messagebox.showinfo("Comparaison", f"Aucune différence matérielle avec le rapport du {stamp}.", parent=self)
            return
        c = self.colors
        window = tk.Toplevel(self, bg=c.bg)
        window.title("Atlas PC — Comparaison de rapports")
        window.geometry(f"{min(self.px(980), self.winfo_screenwidth() - 80)}x{min(self.px(560), self.winfo_screenheight() - 160)}")
        text = f"{len(changes)} différence(s) entre le rapport du {stamp} et l'inventaire actuel"
        if other and other != (self.data.get("system") or {}).get("computer"):
            text += f" — attention, ce rapport vient d'un autre poste ({other})"
        tk.Label(window, text=text, bg=c.bg, fg=c.fg, font=(FONT, 11, "bold"), anchor="w").pack(
            fill="x", padx=self.px(18), pady=(self.px(16), self.px(10))
        )
        frame = tk.Frame(window, bg=c.bg)
        frame.pack(fill="both", expand=True, padx=self.px(18), pady=(self.px(0), self.px(18)))
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
