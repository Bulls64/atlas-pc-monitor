"""Mise à jour depuis les releases GitHub du projet, à la demande de l'utilisateur.

Module sans interface. Il interroge la dernière release publiée, télécharge le fichier qui correspond à
la façon dont l'application est installée, vérifie son empreinte SHA-256 (SHA256SUMS.txt de la même
release), puis remplace l'application :

- fichier unique Windows (AtlasPCMonitor.exe) : l'exe en cours est renommé en .old, le nouveau prend
  sa place ; le .old est supprimé au lancement suivant ;
- dossier Windows (AtlasPCMonitor-windows.zip) : un petit script PowerShell attend la fermeture de
  l'application, échange le dossier _internal et l'exe, puis relance ;
- AppImage Linux : le nouveau fichier remplace l'ancien ;
- lancement depuis les sources : rien n'est remplacé, la page de la release est proposée.

Rien n'est envoyé à GitHub à part la requête elle-même (aucune donnée de l'inventaire).

Update from the project's GitHub releases, at the user's request.

Module with no interface. It queries the latest published release, downloads the file that matches the
way the application is installed, checks its SHA-256 fingerprint (SHA256SUMS.txt of the same release),
then replaces the application:

- Windows single file (AtlasPCMonitor.exe): the running exe is renamed to .old and the new one takes its
  place; the .old file is removed at the next launch;
- Windows folder (AtlasPCMonitor-windows.zip): a small PowerShell script waits for the application to
  close, swaps the _internal folder and the exe, then restarts it;
- Linux AppImage: the new file replaces the old one;
- run from source: nothing is replaced, the release page is offered instead.

Nothing is sent to GitHub apart from the request itself (no inventory data).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .i18n import N_, _

log = logging.getLogger("atlas")

REPOSITORY = "Bulls64/atlas-pc-monitor"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
TIMEOUT_SECONDS = 15
EXE_NAME = "AtlasPCMonitor.exe"
ZIP_NAME = "AtlasPCMonitor-windows.zip"
SUMS_NAME = "SHA256SUMS.txt"
CA_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/ca-bundle.pem", "/etc/ssl/cert.pem")
APPIMAGE_PATTERN = re.compile(r"^AtlasPCMonitor-[\w.]+-x86_64\.AppImage$")
# Jeton facultatif, pour un dépôt privé (jamais enregistré par l'application).
# Optional token, for a private repository (never saved by the application).
TOKEN_VARIABLE = "ATLAS_GITHUB_TOKEN"

# Façons dont l'application peut être installée.
# Ways the application can be installed.
EXE, FOLDER, APPIMAGE, SOURCE = "exe", "folder", "appimage", "source"

Progress = Callable[[int, int], None]
FROM_SOURCE = N_(
    "Lancée depuis les sources, l'application ne se remplace pas elle-même : récupérez la nouvelle version (git pull) ou téléchargez-la."
)


class UpdateError(Exception):
    """Échec compréhensible par l'utilisateur ; le message est déjà traduit.

    Failure the user can understand; the message is already translated.
    """


@dataclass
class Asset:
    name: str
    url: str  # adresse de l'API (téléchargement avec Accept: application/octet-stream) — API address
    size: int = 0


@dataclass
class Release:
    version: str
    tag: str
    page: str
    notes: str = ""
    assets: dict[str, Asset] = field(default_factory=dict)

    @property
    def is_newer(self) -> bool:
        return parse_version(self.version) > parse_version(__version__)


def parse_version(text: str) -> tuple[int, ...]:
    """« v1.2.3 » → (1, 2, 3) ; ce qui suit un tiret (préversion) est ignoré.

    "v1.2.3" → (1, 2, 3); anything after a dash (pre-release) is ignored.
    """
    numbers = re.findall(r"\d+", text.strip().lstrip("vV").split("-")[0])
    return tuple(int(n) for n in numbers[:3]) + (0,) * (3 - len(numbers[:3]))


def _context() -> ssl.SSLContext:
    """Contexte TLS vérifié ; sous Linux, ajoute le magasin de certificats de la distribution.

    Verified TLS context; on Linux, adds the distribution's certificate store.
    """
    context = ssl.create_default_context()
    if sys.platform.startswith("linux"):
        for bundle in CA_BUNDLES:
            if os.path.isfile(bundle):
                with contextlib.suppress(ssl.SSLError, OSError):
                    context.load_verify_locations(bundle)
                break
    return context


def _request(url: str, accept: str) -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": f"AtlasPCMonitor/{__version__}", "X-GitHub-Api-Version": "2022-11-28"}
    request = urllib.request.Request(url, headers=headers)
    token = os.environ.get(TOKEN_VARIABLE, "").strip()
    if token:
        # Pas transmis lors d'une redirection vers le stockage des fichiers.
        # Not passed on when redirected to the file storage.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return request


def _open(url: str, accept: str, opener=None):
    try:
        if opener is not None:
            return opener(_request(url, accept), timeout=TIMEOUT_SECONDS)
        return urllib.request.urlopen(_request(url, accept), timeout=TIMEOUT_SECONDS, context=_context())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError(_("Aucune version publiée trouvée sur GitHub (dépôt privé ou sans release).")) from error
        if error.code in (403, 429):
            raise UpdateError(_("GitHub limite le nombre de requêtes : réessayez dans quelques minutes.")) from error
        raise UpdateError(_("GitHub a répondu par une erreur {0}.", error.code)) from error
    except (urllib.error.URLError, OSError) as error:
        raise UpdateError(_("GitHub est injoignable : vérifiez la connexion à Internet.")) from error


def check(opener=None) -> Release:
    """Dernière release publiée. UpdateError en cas d'échec.

    Latest published release. UpdateError on failure.
    """
    with _open(LATEST_URL, "application/vnd.github+json", opener) as response:
        try:
            data = json.loads(response.read().decode("utf-8"))
            tag = str(data["tag_name"])
        except (ValueError, KeyError, TypeError) as error:
            raise UpdateError(_("Réponse de GitHub illisible.")) from error
    assets = {}
    for item in data.get("assets") or []:
        if isinstance(item, dict) and item.get("name") and item.get("url"):
            assets[item["name"]] = Asset(item["name"], item["url"], int(item.get("size") or 0))
    version = ".".join(str(n) for n in parse_version(tag))
    return Release(version, tag, str(data.get("html_url") or RELEASES_PAGE), str(data.get("body") or ""), assets)


def notes_for(body: str, language: str) -> str:
    """Notes de version dans la langue voulue : la section « ### English » ou « ### Français » si elles existent.

    Release notes in the requested language: the "### English" or "### Français" section when they exist.
    """
    wanted = "english" if language == "en" else "français"
    sections: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("### "):
            current = line[4:].strip().lower()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    if wanted not in sections:
        return body.strip()
    return "\n".join(sections[wanted]).strip()


# ---------------------------------------------------------------------- installation actuelle / current installation


def install_mode() -> str:
    """Comment l'application tourne : exe (fichier unique), folder (dossier), appimage ou source.

    How the application runs: exe (single file), folder, appimage or source.
    """
    if os.environ.get("APPIMAGE") and sys.platform.startswith("linux"):
        return APPIMAGE
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        internal = Path(sys.executable).parent / "_internal"
        bundle = Path(getattr(sys, "_MEIPASS", ""))
        return FOLDER if internal.is_dir() and bundle == internal else EXE
    return SOURCE


def can_install(mode: str | None = None) -> bool:
    return (mode or install_mode()) != SOURCE


def asset_for(release: Release, mode: str) -> Asset:
    """Fichier de la release qui correspond à l'installation.

    Release file that matches the installation.
    """
    if mode == EXE:
        names = [EXE_NAME]
    elif mode == FOLDER:
        names = [ZIP_NAME]
    elif mode == APPIMAGE:
        names = [name for name in release.assets if APPIMAGE_PATTERN.match(name)]
    else:
        names = []
    for name in names:
        if name in release.assets:
            return release.assets[name]
    raise UpdateError(_("Cette release ne contient pas de fichier pour cette installation."))


def cleanup() -> None:
    """Supprime l'ancien exe laissé par une mise à jour (fichier unique Windows).

    Removes the old exe left by an update (Windows single file).
    """
    if getattr(sys, "frozen", False):
        with contextlib.suppress(OSError):
            Path(sys.executable + ".old").unlink()


# ---------------------------------------------------------------------- téléchargement / download


def _download(asset: Asset, target: Path, progress: Progress | None = None, opener=None) -> Path:
    digest = hashlib.sha256()
    done = 0
    with _open(asset.url, "application/octet-stream", opener) as response, open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or asset.size or 0) if hasattr(response, "headers") else asset.size
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    target.with_suffix(target.suffix + ".sha256").write_text(digest.hexdigest(), encoding="ascii")
    return target


def expected_hashes(text: str) -> dict[str, str]:
    """SHA256SUMS.txt (« empreinte  nom ») → {nom: empreinte}.

    SHA256SUMS.txt ("hash  name") → {name: hash}.
    """
    hashes = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            hashes[parts[1].lstrip("*")] = parts[0].lower()
    return hashes


def download(release: Release, mode: str, folder: Path, progress: Progress | None = None, opener=None) -> Path:
    """Télécharge le fichier de l'installation et vérifie son empreinte. UpdateError sinon.

    Downloads the installation's file and checks its fingerprint. UpdateError otherwise.
    """
    asset = asset_for(release, mode)
    sums = release.assets.get(SUMS_NAME)
    if sums is None:
        raise UpdateError(_("Empreintes absentes de la release : mise à jour refusée."))
    folder.mkdir(parents=True, exist_ok=True)
    sums_path = _download(sums, folder / SUMS_NAME, None, opener)
    expected = expected_hashes(sums_path.read_text(encoding="utf-8", errors="replace")).get(asset.name)
    if not expected:
        raise UpdateError(_("Empreintes absentes de la release : mise à jour refusée."))
    path = _download(asset, folder / (asset.name + ".download"), progress, opener)
    actual = path.with_suffix(path.suffix + ".sha256").read_text(encoding="ascii")
    if actual != expected:
        with contextlib.suppress(OSError):
            path.unlink()
        raise UpdateError(_("Le fichier téléchargé ne correspond pas à son empreinte : mise à jour annulée."))
    return path


# ---------------------------------------------------------------------- remplacement / replacement


def _writable(folder: Path) -> None:
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".atlas-write-test-"):
            pass
    except OSError as error:
        raise UpdateError(
            _(
                "Pas le droit d'écrire dans le dossier de l'application ({0}) : "
                "relancez en administrateur, ou téléchargez la nouvelle version à la main.",
                folder,
            )
        ) from error


def replace_exe(new_file: Path, current: Path) -> list[str]:
    """Fichier unique : l'exe en cours devient .old, le nouveau prend sa place. Renvoie la commande de relance.

    Single file: the running exe becomes .old, the new one takes its place. Returns the restart command.
    """
    old = Path(str(current) + ".old")
    with contextlib.suppress(OSError):
        old.unlink()
    os.replace(current, old)
    try:
        shutil.move(str(new_file), str(current))
    except OSError:
        os.replace(old, current)
        raise
    return [str(current)]


def replace_appimage(new_file: Path, current: Path, new_name: str) -> list[str]:
    """AppImage : le nouveau fichier remplace l'ancien (sous son nom versionné si l'ancien l'était).

    AppImage: the new file replaces the old one (under its versioned name if the old one had one).
    """
    os.chmod(new_file, 0o755)
    target = current.with_name(new_name) if APPIMAGE_PATTERN.match(current.name) else current
    os.replace(new_file, target)
    if target != current:
        with contextlib.suppress(OSError):
            current.unlink()
    return [str(target)]


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def folder_script(pid: int, new_root: Path, app_folder: Path, relaunch: bool = True) -> str:
    """Script PowerShell qui échange le dossier de l'application une fois celle-ci fermée.

    PowerShell script that swaps the application folder once the application is closed.
    """
    files = ", ".join(_ps_quote(name) for name in (EXE_NAME, "LICENSE", "THIRD-PARTY-NOTICES.md"))
    exe, exe_old = _ps_quote(EXE_NAME), _ps_quote(EXE_NAME + ".old")
    return f"""$ErrorActionPreference = 'Stop'
$dest = {_ps_quote(app_folder)}
$new = {_ps_quote(new_root)}
$internal = Join-Path $dest '_internal'
$old = Join-Path $dest '_internal.old'
$exe = Join-Path $dest {exe}
$exeOld = Join-Path $dest {exe_old}
try {{ Wait-Process -Id {int(pid)} -Timeout 120 }} catch {{ }}
Start-Sleep -Milliseconds 500
$failed = $false
$moved = $false
try {{
    if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Recurse -Force }}
    Move-Item -LiteralPath $internal -Destination $old
    $moved = $true
    Copy-Item -LiteralPath $exe -Destination $exeOld -Force
    Move-Item -LiteralPath (Join-Path $new '_internal') -Destination $internal
    foreach ($name in @({files})) {{
        $source = Join-Path $new $name
        if (Test-Path -LiteralPath $source) {{ Copy-Item -LiteralPath $source -Destination (Join-Path $dest $name) -Force }}
    }}
}} catch {{
    $failed = $true
    # Retour à l'ancienne version, seulement si elle a déjà été mise de côté.
    # Back to the old version, only if it was already set aside.
    if ($moved) {{
        if (Test-Path -LiteralPath $internal) {{ Remove-Item -LiteralPath $internal -Recurse -Force }}
        Move-Item -LiteralPath $old -Destination $internal
        if (Test-Path -LiteralPath $exeOld) {{ Copy-Item -LiteralPath $exeOld -Destination $exe -Force }}
    }}
}}
Remove-Item -LiteralPath (Split-Path -Parent $new) -Recurse -Force -ErrorAction SilentlyContinue
if (-not $failed) {{ Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue }}
Remove-Item -LiteralPath $exeOld -Force -ErrorAction SilentlyContinue
{"Start-Process -FilePath $exe" if relaunch else ""}
"""


def prepare_folder(zip_path: Path, app_folder: Path, pid: int, relaunch: bool = True) -> list[str]:
    """Dossier : décompresse la nouvelle version à côté, écrit le script d'échange, renvoie sa commande.

    Folder: unpacks the new version alongside, writes the swap script, returns its command.
    """
    staging = app_folder / "_update"
    shutil.rmtree(staging, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(staging)
    roots = [p for p in staging.iterdir() if p.is_dir()]
    new_root = roots[0] if len(roots) == 1 and not (staging / "_internal").is_dir() else staging
    if not (new_root / "_internal").is_dir() or not (new_root / EXE_NAME).is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError(_("Archive de mise à jour incomplète : mise à jour annulée."))
    if new_root == staging:
        # Le script supprime le parent du dossier décompressé : on décale d'un niveau.
        # The script removes the unpacked folder's parent: shift by one level.
        moved = staging / "AtlasPCMonitor"
        moved.mkdir()
        for item in list(staging.iterdir()):
            if item != moved:
                shutil.move(str(item), str(moved / item.name))
        new_root = moved
    script = Path(tempfile.gettempdir()) / "atlas-pc-monitor-update.ps1"
    # BOM UTF-8 : Windows PowerShell 5 lit alors correctement les chemins accentués.
    # UTF-8 BOM: Windows PowerShell 5 then reads accented paths correctly.
    script.write_text(folder_script(pid, new_root, app_folder, relaunch), encoding="utf-8-sig")
    from .collect import powershell_path

    return [powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)]


def install(release: Release, progress: Progress | None = None, opener=None) -> list[str]:
    """Télécharge, vérifie et installe la release. Renvoie la commande à lancer juste avant de quitter.

    Downloads, checks and installs the release. Returns the command to start right before quitting.
    """
    mode = install_mode()
    if mode == SOURCE:
        raise UpdateError(_(FROM_SOURCE))
    current = Path(os.environ["APPIMAGE"]) if mode == APPIMAGE else Path(sys.executable)
    app_folder = current.parent
    _writable(app_folder)
    workdir = Path(tempfile.mkdtemp(prefix="atlas-update-", dir=app_folder if mode == APPIMAGE else None))
    try:
        path = download(release, mode, workdir, progress, opener)
        if mode == EXE:
            return replace_exe(path, current)
        if mode == APPIMAGE:
            return replace_appimage(path, current, asset_for(release, mode).name)
        return prepare_folder(path, app_folder, os.getpid())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def launch(command: list[str]) -> None:
    """Lance la commande détachée de l'application (elle doit survivre à sa fermeture).

    Starts the command detached from the application (it must outlive it).
    """
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(command, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(command, start_new_session=True, close_fds=True)
