"""Mise à jour depuis GitHub : recherche, téléchargement vérifié, remplacement, et fenêtre Paramètres.

Update from GitHub: check, verified download, replacement, and the Settings window.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

from atlas import __version__, settings, update

NEW_EXE = b"MZ nouvelle version"


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


def release_json(tag: str = "v9.1.0", files: dict[str, bytes] | None = None) -> dict:
    files = files if files is not None else {"AtlasPCMonitor.exe": NEW_EXE}
    sums = "".join(f"{hashlib.sha256(body).hexdigest()}  {name}\n" for name, body in files.items())
    assets = [{"name": name, "url": f"https://api.test/assets/{name}", "size": len(body)} for name, body in files.items()]
    assets.append({"name": "SHA256SUMS.txt", "url": "https://api.test/assets/SHA256SUMS.txt", "size": len(sums)})
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/Bulls64/atlas-pc-monitor/releases/tag/{tag}",
        "body": "- Nouveautés",
        "assets": assets,
    }, sums


def opener_for(info: dict, sums: str, files: dict[str, bytes], seen: list | None = None):
    """Faux urlopen : la release, puis ses fichiers.

    Fake urlopen: the release, then its files.
    """

    def opener(request, timeout):
        if seen is not None:
            seen.append(request)
        url = request.full_url
        if url == update.LATEST_URL:
            return FakeResponse(json.dumps(info).encode())
        name = url.rsplit("/", 1)[-1]
        if name == "SHA256SUMS.txt":
            return FakeResponse(sums.encode())
        return FakeResponse(files[name])

    return opener


def test_versions_compare_numerically():
    assert update.parse_version("v1.10.0") > update.parse_version("1.9.9")
    assert update.parse_version("v2") == (2, 0, 0)
    assert update.parse_version("v1.2.0-beta") == (1, 2, 0)
    assert update.Release("9.0.0", "v9.0.0", "").is_newer
    assert not update.Release(__version__, f"v{__version__}", "").is_newer


def test_check_reads_the_latest_release(monkeypatch):
    info, sums = release_json()
    seen = []
    monkeypatch.setenv(update.TOKEN_VARIABLE, "secret")
    release = update.check(opener_for(info, sums, {}, seen))
    assert release.version == "9.1.0" and release.is_newer and release.notes == "- Nouveautés"
    assert set(release.assets) == {"AtlasPCMonitor.exe", "SHA256SUMS.txt"}
    request = seen[0]
    assert request.get_header("User-agent") == f"AtlasPCMonitor/{__version__}"
    # Jeton facultatif, jamais transmis à l'hôte d'une redirection.
    # Optional token, never passed on to a redirect's host.
    assert request.unredirected_hdrs["Authorization"] == "Bearer secret"


@pytest.mark.parametrize(
    ("code", "message"),
    [(404, "Aucune version publiée"), (403, "limite le nombre de requêtes"), (500, "erreur 500")],
)
def test_check_errors_are_explained(code, message):
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "", {}, None)

    with pytest.raises(update.UpdateError, match=message):
        update.check(opener)


def test_check_offline():
    def opener(request, timeout):
        raise urllib.error.URLError("no network")

    with pytest.raises(update.UpdateError, match="injoignable"):
        update.check(opener)


def test_download_checks_the_fingerprint(tmp_path):
    files = {"AtlasPCMonitor.exe": NEW_EXE}
    info, sums = release_json(files=files)
    release = update.check(opener_for(info, sums, files))
    progress = []
    path = update.download(release, update.EXE, tmp_path, lambda done, total: progress.append((done, total)), opener_for(info, sums, files))
    assert path.read_bytes() == NEW_EXE and progress[-1] == (len(NEW_EXE), len(NEW_EXE))

    tampered = {"AtlasPCMonitor.exe": b"autre chose"}
    with pytest.raises(update.UpdateError, match="empreinte"):
        update.download(release, update.EXE, tmp_path / "b", None, opener_for(info, sums, tampered))
    assert not list((tmp_path / "b").glob("*.download"))


def test_download_refuses_a_release_without_checksums(tmp_path):
    info, _sums = release_json()
    info["assets"] = [a for a in info["assets"] if a["name"] != "SHA256SUMS.txt"]
    release = update.check(opener_for(info, "", {}))
    with pytest.raises(update.UpdateError, match="Empreintes absentes"):
        update.download(release, update.EXE, tmp_path)


def test_asset_matches_the_installation():
    info, sums = release_json(
        files={"AtlasPCMonitor.exe": b"1", "AtlasPCMonitor-windows.zip": b"2", "AtlasPCMonitor-9.1.0-x86_64.AppImage": b"3"}
    )
    release = update.check(opener_for(info, sums, {}))
    assert update.asset_for(release, update.EXE).name == "AtlasPCMonitor.exe"
    assert update.asset_for(release, update.FOLDER).name == "AtlasPCMonitor-windows.zip"
    assert update.asset_for(release, update.APPIMAGE).name == "AtlasPCMonitor-9.1.0-x86_64.AppImage"
    with pytest.raises(update.UpdateError):
        update.asset_for(release, update.SOURCE)


def test_install_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert update.install_mode() == update.SOURCE
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("APPIMAGE", "/opt/AtlasPCMonitor.AppImage")
    assert update.install_mode() == update.APPIMAGE
    monkeypatch.delenv("APPIMAGE")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "AtlasPCMonitor.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "Temp" / "_MEI123"), raising=False)
    assert update.install_mode() == update.EXE
    (tmp_path / "_internal").mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    assert update.install_mode() == update.FOLDER


def test_release_notes_in_the_interface_language():
    body = (
        "### English\n\n#### Added\n\n- Updates\n\n"
        "### Français\n\n#### Ajouts\n\n- Mises à jour\n\n"
        "### Downloads · Téléchargements\n\n- exe"
    )
    assert update.notes_for(body, "fr") == "#### Ajouts\n\n- Mises à jour"
    assert update.notes_for(body, "en") == "#### Added\n\n- Updates"
    assert update.notes_for("- Correctifs", "en") == "- Correctifs"


def test_install_from_source_is_refused(monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    with pytest.raises(update.UpdateError, match="git pull"):
        update.install(update.Release("9.0.0", "v9.0.0", ""))


def test_replace_exe_keeps_the_old_one_aside(tmp_path):
    current = tmp_path / "AtlasPCMonitor.exe"
    current.write_bytes(b"ancienne")
    new = tmp_path / "telechargement" / "AtlasPCMonitor.exe.download"
    new.parent.mkdir()
    new.write_bytes(NEW_EXE)
    assert update.replace_exe(new, current) == [str(current)]
    assert current.read_bytes() == NEW_EXE and Path(str(current) + ".old").read_bytes() == b"ancienne"


def test_replace_appimage_takes_the_new_versioned_name(tmp_path):
    current = tmp_path / "AtlasPCMonitor-1.0.0-x86_64.AppImage"
    current.write_bytes(b"ancienne")
    new = tmp_path / "nouvelle.download"
    new.write_bytes(b"nouvelle")
    command = update.replace_appimage(new, current, "AtlasPCMonitor-9.1.0-x86_64.AppImage")
    target = tmp_path / "AtlasPCMonitor-9.1.0-x86_64.AppImage"
    assert command == [str(target)] and target.read_bytes() == b"nouvelle" and not current.exists()
    if os.name != "nt":  # pas de bit d'exécution sous Windows — no execute bit on Windows
        assert target.stat().st_mode & 0o111


def _fake_release_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AtlasPCMonitor/AtlasPCMonitor.exe", NEW_EXE)
        archive.writestr("AtlasPCMonitor/_internal/nouveau.txt", "2")
        archive.writestr("AtlasPCMonitor/LICENSE", "MIT")


def _fake_app_folder(folder: Path) -> None:
    (folder / "_internal").mkdir(parents=True)
    (folder / "_internal" / "ancien.txt").write_text("1")
    (folder / "AtlasPCMonitor.exe").write_bytes(b"ancienne")
    (folder / "rapport-du-client.json").write_text("{}")


def test_prepare_folder_unpacks_beside_the_application(tmp_path):
    app = tmp_path / "Atlas PC d'atelier"
    _fake_app_folder(app)
    archive = tmp_path / "AtlasPCMonitor-windows.zip"
    _fake_release_zip(archive)
    command = update.prepare_folder(archive, app, pid=4242, relaunch=False)
    assert (app / "_update" / "AtlasPCMonitor" / "_internal" / "nouveau.txt").is_file()
    script = Path(command[-1]).read_text(encoding="utf-8-sig")
    assert "Wait-Process -Id 4242" in script and "'" + str(app).replace("'", "''") + "'" in script
    assert "Start-Process" not in script

    broken = tmp_path / "vide.zip"
    with zipfile.ZipFile(broken, "w") as archive_file:
        archive_file.writestr("AtlasPCMonitor/LICENSE", "MIT")
    with pytest.raises(update.UpdateError, match="incomplète"):
        update.prepare_folder(broken, app, pid=4242)
    assert not (app / "_update").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="script PowerShell : Windows seulement")
def test_folder_swap_script_runs_on_windows(tmp_path):
    """Le vrai script, exécuté par Windows PowerShell : le dossier est échangé, les fichiers de l'utilisateur restent.

    The real script, run by Windows PowerShell: the folder is swapped, the user's files stay.
    """
    app = tmp_path / "Atlas PC d'atelier é"
    _fake_app_folder(app)
    archive = tmp_path / "AtlasPCMonitor-windows.zip"
    _fake_release_zip(archive)
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    command = update.prepare_folder(archive, app, pid=finished.pid, relaunch=False)
    subprocess.run(command, check=True, timeout=120)
    assert (app / "_internal" / "nouveau.txt").is_file() and not (app / "_internal" / "ancien.txt").exists()
    assert (app / "AtlasPCMonitor.exe").read_bytes() == NEW_EXE and (app / "LICENSE").read_text() == "MIT"
    assert (app / "rapport-du-client.json").is_file()
    assert not (app / "_update").exists() and not (app / "_internal.old").exists()
    assert not (app / "AtlasPCMonitor.exe.old").exists()


# ---------------------------------------------------------------------- fenêtre Paramètres / Settings window


class FakeUpdater:
    """Remplace le module update dans la fenêtre : aucune requête réseau.

    Replaces the update module in the window: no network request.
    """

    UpdateError = update.UpdateError
    Release = update.Release

    def __init__(self, release=None, error=None, mode=update.EXE):
        self.release, self.error, self.mode = release, error, mode
        self.launched = None

    def install_mode(self):
        return self.mode

    def check(self):
        if self.error:
            raise update.UpdateError(self.error)
        return self.release

    def install(self, release, progress):
        progress(50, 100)
        return ["AtlasPCMonitor.exe"]

    def launch(self, command):
        self.launched = command


def test_settings_check_and_install(win, qtbot, monkeypatch):
    fake = FakeUpdater(update.Release("9.1.0", "v9.1.0", "https://example.test", "- Nouveautés"))
    win.updater = fake
    quit_calls = []
    monkeypatch.setattr(win, "quit_for_update", lambda: quit_calls.append(True))
    win.open_settings()
    dialog = win.settings_dialog
    assert "Aucune recherche" in dialog.update_status.text() and not dialog.install_button.isVisibleTo(dialog)
    dialog.check_button.click()
    qtbot.waitUntil(lambda: not dialog.busy)
    assert "9.1.0 disponible" in dialog.update_status.text()
    assert dialog.install_button.isVisibleTo(dialog) and dialog.notes.toPlainText().strip() == "Nouveautés"
    assert win.settings_button.text() == "v9.1.0"
    dialog.install_button.click()
    qtbot.waitUntil(lambda: bool(quit_calls))
    assert fake.launched == ["AtlasPCMonitor.exe"]


def test_settings_up_to_date_and_errors(win, qtbot):
    win.updater = FakeUpdater(update.Release(__version__, f"v{__version__}", ""))
    win.open_settings()
    dialog = win.settings_dialog
    dialog.check()
    qtbot.waitUntil(lambda: not dialog.busy)
    assert "à jour" in dialog.update_status.text() and win.settings_button.text() == ""
    win.updater = FakeUpdater(error="GitHub est injoignable")
    dialog.check()
    qtbot.waitUntil(lambda: not dialog.busy)
    assert dialog.update_status.text() == "GitHub est injoignable" and dialog.update_status.property("role") == "note"


def test_settings_from_source_offers_the_release_page(win, qtbot):
    win.updater = FakeUpdater(update.Release("9.1.0", "v9.1.0", ""), mode=update.SOURCE)
    win.open_settings()
    dialog = win.settings_dialog
    dialog.check()
    qtbot.waitUntil(lambda: not dialog.busy)
    assert "git pull" in dialog.update_status.text()
    assert not dialog.install_button.isVisibleTo(dialog) and dialog.page_button.isVisibleTo(dialog)


def test_settings_language_theme_and_startup_option(win, qtbot):
    from atlas import i18n
    from atlas.gui import theme

    win.open_settings()
    dialog = win.settings_dialog
    dialog._set_language("en")
    assert i18n.language() == "en" and dialog.windowTitle() == "Atlas PC Monitor — Settings"
    assert dialog.check_button.text() == "Check for updates"
    dialog._set_theme("light")
    assert theme.P.name == "light" and settings.load_config()["theme"] == "light"
    dialog.auto_check.setChecked(True)
    assert settings.load_config()["check_updates"] is True


def test_startup_check_shows_the_waiting_update(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings.save_config({"check_updates": True})
    from atlas.gui import window

    monkeypatch.setattr(update, "check", lambda: update.Release("9.1.0", "v9.1.0", ""))
    w = window.MainWindow(scanner=lambda: {})
    qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.available_release is not None)
    assert w.settings_button.text() == "v9.1.0" and "9.1.0" in w.settings_button.toolTip()
