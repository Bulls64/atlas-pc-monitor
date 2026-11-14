"""Ce qu'une version publiée doit contenir : section du CHANGELOG, licences et mentions tierces.

What a published version must contain: CHANGELOG section, licenses and third-party notices.
"""

from pathlib import Path

from atlas import __version__

ROOT = Path(__file__).resolve().parent.parent
LICENSES = ["LGPL-3.0.txt", "GPL-3.0.txt", "Python-PSF.txt"]


def test_changelog_describes_the_current_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}] - " in changelog
    assert f"[{__version__}]: https://github.com/" in changelog


def test_license_texts_are_shipped_with_every_build():
    for name in LICENSES:
        assert (ROOT / "licenses" / name).stat().st_size > 5000
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert all(f"licenses/{name}" in notices for name in LICENSES)
    spec = (ROOT / "atlas_pc.spec").read_text(encoding="utf-8")
    assert all(f'"{name}"' in spec for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "licenses", "CHANGELOG.md"))
    script = (ROOT / "tools" / "build_appimage.sh").read_text(encoding="utf-8")
    assert "cp -a LICENSE THIRD-PARTY-NOTICES.md licenses" in script
