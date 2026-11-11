"""Atlas PC — inventaire matériel Windows, interface française."""

import base64, json, os, platform, socket, subprocess, threading
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

BG = "#0b1018"
CARD = "#111a25"
ALT = "#162231"
LINE = "#223142"
FG = "#edf3fa"
DIM = "#8c9bad"
GREEN = "#51d6a5"
BLUE = "#68a9ff"
AMBER = "#f4bb65"
PALETTES = {
    "dark": {
        "BG": "#0b1018",
        "CARD": "#111a25",
        "ALT": "#162231",
        "LINE": "#223142",
        "FG": "#edf3fa",
        "DIM": "#8c9bad",
        "GREEN": "#51d6a5",
        "BLUE": "#68a9ff",
        "AMBER": "#f4bb65",
        "ROW": "#131e2a",
        "SUBTLE": "#637386",
        "NAV": "#607287",
    },
    "light": {
        "BG": "#f3f6fa",
        "CARD": "#ffffff",
        "ALT": "#e5ebf2",
        "LINE": "#d5dee8",
        "FG": "#172333",
        "DIM": "#637386",
        "GREEN": "#13865f",
        "BLUE": "#2766b2",
        "AMBER": "#98620a",
        "ROW": "#f7f9fc",
        "SUBTLE": "#66788c",
        "NAV": "#64758a",
    },
}
PAGES = [
    "Vue d'ensemble",
    "Système",
    "Processeur",
    "Mémoire",
    "Carte mère",
    "Graphiques",
    "Stockage",
    "Réseau",
]
PS = r"""
$ErrorActionPreference='SilentlyContinue'
$a=Get-CimInstance Win32_Processor|Select Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed
$b=Get-CimInstance Win32_OperatingSystem|Select Caption,Version,BuildNumber,OSArchitecture,TotalVisibleMemorySize,FreePhysicalMemory
$c=Get-CimInstance Win32_BaseBoard|Select Manufacturer,Product,Version
$d=Get-CimInstance Win32_PhysicalMemory|Select Manufacturer,PartNumber,Capacity,Speed,DeviceLocator
$e=Get-CimInstance Win32_VideoController|Select Name,AdapterRAM,DriverVersion,VideoModeDescription
$f=Get-CimInstance Win32_DiskDrive|Select Model,MediaType,InterfaceType,Size,Status
$g=Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'|Select DeviceID,VolumeName,FileSystem,Size,FreeSpace
$h=Get-NetAdapter -Physical|Select Name,InterfaceDescription,Status,LinkSpeed,MacAddress
$i=Get-NetIPConfiguration|Where {$_.NetAdapter.Status -eq 'Up'}|%{[pscustomobject]@{Name=$_.InterfaceAlias;IPv4=($_.IPv4Address.IPAddress -join ', ')}}
$j=Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi|%{[pscustomobject]@{Name=$_.InstanceName;Celsius=[math]::Round(($_.CurrentTemperature/10)-273.15,1)}}
[ordered]@{cpu=@($a);os=$b;board=$c;ram=@($d);gpu=@($e);disks=@($f);volumes=@($g);adapters=@($h);network=@($i);temperatures=@($j)}|ConvertTo-Json -Depth 5 -Compress
"""
FIELDS = {
    "Système": (
        "os",
        {
            "Édition": "Caption",
            "Version": "Version",
            "Build": "BuildNumber",
            "Architecture": "OSArchitecture",
        },
    ),
    "Processeur": (
        "cpu",
        {
            "Modèle": "Name",
            "Fabricant": "Manufacturer",
            "Cœurs": "NumberOfCores",
            "Threads": "NumberOfLogicalProcessors",
            "Fréquence max.": "MaxClockSpeed",
        },
    ),
    "Mémoire": (
        "ram",
        {
            "Emplacement": "DeviceLocator",
            "Fabricant": "Manufacturer",
            "Référence": "PartNumber",
            "Capacité": "Capacity",
            "Vitesse": "Speed",
        },
    ),
    "Carte mère": ("board", {"Fabricant": "Manufacturer", "Modèle": "Product", "Révision": "Version"}),
    "Graphiques": (
        "gpu",
        {
            "Modèle": "Name",
            "Mémoire dédiée": "AdapterRAM",
            "Pilote": "DriverVersion",
            "Mode vidéo": "VideoModeDescription",
        },
    ),
    "Stockage": (
        "disks",
        {
            "Modèle": "Model",
            "Type": "MediaType",
            "Interface": "InterfaceType",
            "Capacité": "Size",
            "État": "Status",
        },
    ),
    "Réseau": (
        "adapters",
        {
            "Nom": "Name",
            "Description": "InterfaceDescription",
            "État": "Status",
            "Débit": "LinkSpeed",
            "Adresse MAC": "MacAddress",
        },
    ),
}


def rows(v):
    return v if isinstance(v, list) else ([v] if v else [])


def pretty(n):
    try:
        n = float(n)
    except:
        return "—"
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1000 or unit == "To":
            return f"{n:.1f} {unit}" if unit != "o" else f"{n:.0f} o"
        n /= 1000


def scan():
    d = {
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "system": {
            "computer": socket.gethostname(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
    }
    if os.name != "nt":
        d["note"] = "Informations matérielles détaillées disponibles sous Windows."
        return d
    try:
        cmd = base64.b64encode(PS.encode("utf-16le")).decode()
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", cmd],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if p.returncode == 0:
            d.update(json.loads(p.stdout))
        else:
            d["note"] = "Informations CIM indisponibles."
    except Exception as e:
        d["note"] = str(e)
    try:
        total = int(d["os"].get("TotalVisibleMemorySize", 0)) * 1024
        free = int(d["os"].get("FreePhysicalMemory", 0)) * 1024
        d["memory"] = {
            "total": total,
            "free": free,
            "used": total - free,
            "percent": round((total - free) * 100 / total) if total else 0,
        }
    except:
        d["memory"] = {}
    return d


class Atlas(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Atlas PC — Informations système")
        self.geometry("1160x770")
        self.minsize(880, 600)
        self.theme = "dark"
        self.set_palette()
        self.configure(bg=BG)
        self.data = {}
        self.page = PAGES[0]
        self.nav = {}
        self.build()
        self.refresh()

    def set_palette(self):
        global BG, CARD, ALT, LINE, FG, DIM, GREEN, BLUE, AMBER
        c = PALETTES[self.theme]
        BG, CARD, ALT, LINE, FG, DIM, GREEN, BLUE, AMBER = (
            c[k] for k in ("BG", "CARD", "ALT", "LINE", "FG", "DIM", "GREEN", "BLUE", "AMBER")
        )

    def build(self):
        h = tk.Frame(self, bg=BG, height=72)
        h.pack(fill="x", padx=26, pady=(17, 10))
        h.pack_propagate(False)
        tk.Label(h, text="◆  ATLAS PC", bg=BG, fg=GREEN, font=("Segoe UI", 18, "bold")).pack(
            side="left", pady=10
        )
        tk.Label(h, text="INFORMATIONS SYSTÈME", bg=BG, fg=DIM, font=("Segoe UI", 8, "bold")).pack(
            side="left", padx=12
        )
        self.status = tk.Label(h, text="● Analyse en attente", bg=BG, fg=DIM)
        self.status.pack(side="right", padx=10)
        self.refreshbtn = self.button(h, "↻ Actualiser", self.refresh, True)
        self.refreshbtn.pack(side="right")
        self.themebtn = self.button(
            h, "☀ Thème clair" if self.theme == "dark" else "☾ Thème sombre", self.toggle_theme
        )
        self.themebtn.pack(side="right", padx=(0, 8))
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
        n = tk.Frame(body, bg=BG, width=215)
        n.pack(side="left", fill="y", padx=(0, 17))
        n.pack_propagate(False)
        tk.Label(
            n, text="MATÉRIEL", bg=BG, fg=PALETTES[self.theme]["NAV"], font=("Segoe UI", 8, "bold")
        ).pack(anchor="w", padx=10, pady=10)
        for p, icon in zip(PAGES, ("⌂", "▣", "◉", "▤", "▥", "▰", "▱", "⌁")):
            b = tk.Button(
                n,
                text=f"{icon}   {p}",
                anchor="w",
                bg=BG,
                fg=DIM,
                activebackground=ALT,
                relief="flat",
                bd=0,
                padx=12,
                pady=10,
                font=("Segoe UI", 10),
                command=lambda x=p: self.show(x),
            )
            b.pack(fill="x", pady=1)
            self.nav[p] = b
        tk.Frame(n, bg=LINE, height=1).pack(fill="x", pady=14)
        self.button(n, "⇩ Exporter le rapport", self.export).pack(fill="x")
        tk.Label(
            n,
            text="Températures selon les capteurs exposés par le fabricant.",
            bg=BG,
            fg=PALETTES[self.theme]["SUBTLE"],
            wraplength=190,
            justify="left",
        ).pack(anchor="w", padx=10, pady=18)
        pane = tk.Frame(body, bg=BG)
        pane.pack(side="left", fill="both", expand=True)
        self.titlelabel = tk.Label(pane, text=self.page, bg=BG, fg=FG, font=("Segoe UI", 23, "bold"))
        self.titlelabel.pack(anchor="w")
        self.sub = tk.Label(
            pane, text="Un aperçu clair de votre ordinateur et de ses composants.", bg=BG, fg=DIM
        )
        self.sub.pack(anchor="w", pady=(3, 16))
        area = tk.Frame(pane, bg=BG)
        area.pack(fill="both", expand=True)
        self.cv = tk.Canvas(area, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(area, command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=BG)
        self.win = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self.win, width=e.width))
        self.cv.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units"))

    def button(self, p, t, fn, green=False):
        return tk.Button(
            p,
            text=t,
            command=fn,
            relief="flat",
            bd=0,
            bg=GREEN if green else ALT,
            fg=BG if green else FG,
            font=("Segoe UI", 9, "bold"),
            padx=13,
            pady=9,
            cursor="hand2",
        )

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.set_palette()
        for w in self.winfo_children():
            w.destroy()
        self.nav = {}
        self.build()
        self.status.configure(
            text="● Analyse terminée" if self.data else "● Analyse en attente", fg=GREEN if self.data else DIM
        )
        self.show(self.page)

    def heading(self, t):
        tk.Label(self.inner, text=t, bg=BG, fg=FG, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(16, 9)
        )

    def tile(self, p, label, value, detail, color=GREEN):
        b = tk.Frame(p, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=15, pady=13)
        tk.Label(b, text=label.upper(), bg=CARD, fg=DIM, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(
            b,
            text=value or "Non détecté",
            bg=CARD,
            fg=FG,
            font=("Segoe UI", 12, "bold"),
            wraplength=270,
            justify="left",
        ).pack(anchor="w", pady=(7, 2))
        tk.Label(b, text=detail, bg=CARD, fg=color, font=("Segoe UI", 9)).pack(anchor="w")
        return b

    def show(self, p):
        self.page = p
        self.titlelabel.configure(text=p)
        self.sub.configure(text="Vue synthétique de votre configuration matérielle.")
        for k, b in self.nav.items():
            b.configure(bg=ALT if k == p else BG, fg=GREEN if k == p else DIM)
        for w in self.inner.winfo_children():
            w.destroy()
        if self.data:
            if p == PAGES[0]:
                self.overview()
            else:
                self.detail(p)
        self.cv.yview_moveto(0)

    def overview(self):
        d = self.data
        cpu = (rows(d.get("cpu")) or [{}])[0]
        osd = d.get("os") or {}
        mem = d.get("memory") or {}
        gpus = rows(d.get("gpu"))
        board = d.get("board") or {}
        top = tk.Frame(self.inner, bg=BG)
        top.pack(fill="x")
        hero = tk.Frame(top, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=19, pady=17)
        hero.pack(side="left", fill="both", expand=True, padx=(0, 9))
        tk.Label(hero, text="VOTRE ORDINATEUR", bg=CARD, fg=GREEN, font=("Segoe UI", 8, "bold")).pack(
            anchor="w"
        )
        tk.Label(hero, text=d["system"]["computer"], bg=CARD, fg=FG, font=("Segoe UI", 20, "bold")).pack(
            anchor="w", pady=5
        )
        tk.Label(
            hero,
            text=f"{osd.get('Caption', d['system']['platform'])} · {d['system']['architecture']}",
            bg=CARD,
            fg=DIM,
        ).pack(anchor="w")
        m = tk.Frame(
            top, bg=CARD, highlightbackground=LINE, highlightthickness=1, width=175, padx=15, pady=16
        )
        m.pack(side="right", fill="y")
        m.pack_propagate(False)
        tk.Label(m, text="MÉMOIRE UTILISÉE", bg=CARD, fg=DIM, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(m, text=f"{mem.get('percent', 0)}%", bg=CARD, fg=GREEN, font=("Segoe UI", 26, "bold")).pack(
            anchor="w"
        )
        tk.Label(m, text=f"{pretty(mem.get('used'))} / {pretty(mem.get('total'))}", bg=CARD, fg=DIM).pack(
            anchor="w"
        )
        self.heading("Vue rapide")
        grid = tk.Frame(self.inner, bg=BG)
        grid.pack(fill="x")
        data = [
            (
                "Processeur",
                cpu.get("Name", "Non détecté"),
                f"{cpu.get('NumberOfCores', '—')} cœurs · {cpu.get('NumberOfLogicalProcessors', '—')} threads",
                GREEN,
            ),
            (
                "Carte graphique",
                gpus[0].get("Name", "Non détectée") if gpus else "Non détectée",
                f"{len(gpus)} adaptateur(s)",
                BLUE,
            ),
            (
                "Carte mère",
                " ".join(filter(None, [board.get("Manufacturer"), board.get("Product")])) or "Non détectée",
                "Carte système",
                AMBER,
            ),
            ("Mémoire vive", pretty(mem.get("total")), f"{len(rows(d.get('ram')))} barrette(s)", GREEN),
        ]
        for i, x in enumerate(data):
            self.tile(grid, *x).grid(
                row=i // 2, column=i % 2, sticky="nsew", padx=(0, 8) if i % 2 == 0 else 0, pady=(0, 8)
            )
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.heading("Températures")
        temps = rows(d.get("temperatures"))
        msg = (
            " · ".join(f"{x.get('Celsius')} °C" for x in temps[:4])
            if temps
            else "Aucun capteur exposé. Les pilotes du fabricant peuvent être nécessaires."
        )
        tk.Label(
            self.inner,
            text=msg,
            bg=CARD,
            fg=AMBER if temps else DIM,
            wraplength=730,
            justify="left",
            padx=14,
            pady=13,
        ).pack(fill="x")
        if d.get("note"):
            tk.Label(self.inner, text=d["note"], bg=BG, fg=AMBER, wraplength=730).pack(anchor="w", pady=9)

    def detail(self, p):
        key, fields = FIELDS[p]
        self.heading(
            {
                "os": "Informations Windows",
                "cpu": "Processeurs détectés",
                "ram": "Modules mémoire",
                "board": "Carte mère",
                "gpu": "Adaptateurs graphiques",
                "disks": "Disques physiques",
                "adapters": "Interfaces réseau",
            }[key]
        )
        src = self.data.get(key)
        data = []
        for i, obj in enumerate(rows(src), 1):
            for label, field in fields.items():
                val = obj.get(field)
                if val not in (None, "", 0):
                    data.append(
                        (
                            f"{i} · {label}" if isinstance(src, list) else label,
                            pretty(val) if field in ("Capacity", "Size", "AdapterRAM") else val,
                        )
                    )
        if key == "os":
            data += [
                ("Nom de l’ordinateur", self.data["system"]["computer"]),
                ("Architecture", self.data["system"]["architecture"]),
            ]
        if key == "ram":
            m = self.data.get("memory", {})
            data[:0] = [
                ("Mémoire totale", pretty(m.get("total"))),
                ("Utilisée / disponible", f"{pretty(m.get('used'))} / {pretty(m.get('free'))}"),
            ]
        if key == "disks":
            data += [
                (
                    f"Volume {x.get('DeviceID')}",
                    f"{x.get('VolumeName') or 'Disque local'} · {pretty(x.get('Size'))} · {pretty(x.get('FreeSpace'))} libre · {x.get('FileSystem') or '—'}",
                )
                for x in rows(self.data.get("volumes"))
            ]
        if key == "adapters":
            data += [
                (f"IP · {x.get('Name')}", x.get("IPv4") or "Non attribuée")
                for x in rows(self.data.get("network"))
            ]
        if not data:
            data = [("État", "Aucune information détectée.")]
        table = tk.Frame(self.inner, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        table.pack(fill="x")
        for i, (k, v) in enumerate(data):
            bg = CARD if i % 2 == 0 else PALETTES[self.theme]["ROW"]
            r = tk.Frame(table, bg=bg, padx=14, pady=9)
            r.pack(fill="x")
            tk.Label(r, text=k, width=27, anchor="w", bg=bg, fg=DIM).pack(side="left")
            tk.Label(r, text=str(v), anchor="w", bg=bg, fg=FG, wraplength=540, justify="left").pack(
                side="left", fill="x", expand=True
            )

    def refresh(self):
        self.refreshbtn.configure(state="disabled")
        self.status.configure(text="● Analyse en cours…", fg=AMBER)
        threading.Thread(target=self.load, daemon=True).start()

    def load(self):
        self.data = scan()
        self.after(0, self.loaded)

    def loaded(self):
        self.status.configure(text="● Analyse terminée", fg=GREEN)
        self.refreshbtn.configure(state="normal")
        self.show(self.page)

    def export(self):
        if not self.data:
            return
        p = filedialog.asksaveasfilename(
            title="Exporter le rapport",
            defaultextension=".json",
            initialfile=f"atlas-pc-{datetime.now():%Y%m%d-%H%M}",
            filetypes=[("Rapport JSON", "*.json"), ("Fichier texte", "*.txt")],
        )
        if not p:
            return
        try:
            if p.lower().endswith(".txt"):
                lines = ["ATLAS PC — RAPPORT SYSTÈME", "Généré le " + self.data.get("captured_at", ""), ""]

                def flat(x, prefix=""):
                    if isinstance(x, dict):
                        for k, v in x.items():
                            flat(v, prefix + k + " / ")
                    elif isinstance(x, list):
                        for i, v in enumerate(x, 1):
                            flat(v, prefix + str(i) + ". ")
                    else:
                        lines.append(prefix.rstrip(" /") + ": " + str(x))

                flat(self.data)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(chr(10).join(lines))
            else:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Rapport exporté", "Rapport enregistré : " + p)
        except OSError as e:
            messagebox.showerror("Export impossible", str(e))


if __name__ == "__main__":
    Atlas().mainloop()
