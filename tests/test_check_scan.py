import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_scan  # noqa: E402


def write(tmp_path, data):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_ok_on_sample(data, tmp_path, capsys):
    assert check_scan.main([write(tmp_path, data)]) == 0
    out = capsys.readouterr().out
    assert "### Résultat : OK" in out and "aucune fuite" in out and "| license | 2300 |" in out


def test_fails_when_collect_failed(tmp_path, capsys):
    assert check_scan.main([write(tmp_path, {"system": {"computer": "x"}, "note": "délai dépassé"})]) == 1
    assert "Collecte en échec : délai dépassé" in capsys.readouterr().out


def test_detects_privacy_leak(data, tmp_path, capsys, monkeypatch):
    from atlas import privacy

    monkeypatch.setattr(privacy, "anonymize", lambda d: dict(d, anonymized=True))  # masquage cassé
    assert check_scan.main([write(tmp_path, data)]) == 1
    assert "identifiant(s) encore visibles" in capsys.readouterr().out
