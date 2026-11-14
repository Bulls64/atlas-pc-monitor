import json
import subprocess

from atlas import collect


def test_as_rows_accepts_every_shape():
    assert collect.as_rows(None) == []
    assert collect.as_rows({}) == []
    assert collect.as_rows({"a": 1}) == [{"a": 1}]
    assert collect.as_rows([{"a": 1}, None, "x"]) == [{"a": 1}]
    assert collect.as_rows({"value": [{"a": 1}], "Count": 1}) == [{"a": 1}]


def test_parse_tolerates_bom_and_noise():
    assert collect.parse_inventory('﻿AVERTISSEMENT\n{"admin": true}') == {"admin": True}


def test_parse_base64_line_survives_any_console_encoding():
    import base64

    line = "ATLAS:" + base64.b64encode('{"nom": "Mémoire Générique"}'.encode()).decode()
    assert collect.parse_inventory(f"bruit\r\n{line}\r\n") == {"nom": "Mémoire Générique"}


def test_scan_normalizes(data):
    assert isinstance(data["cpu"], list) and data["cpu"][0]["NumberOfCores"] == 8
    assert isinstance(data["network"], list) and isinstance(data["battery"], list)
    assert data["secureboot"] == {} and data["tpm"] == {}
    assert data["machine"]["Model"] == "82JU"
    assert data["ram"][1]["Manufacturer"] == "Mémoire Générique"  # accents intacts — accents intact
    assert data["errors"]["tpm"] == "Accès refusé."
    assert "note" not in data


def test_implausible_temperatures_are_dropped(data):
    assert [zone["Name"] for zone in data["temperatures"]] == ["TZ0"]


def test_memory_installed_vs_usable(data):
    memory = data["memory"]
    assert memory["installed"] == 16 * 1024**3
    assert memory["total"] < memory["installed"]
    assert memory["used"] + memory["free"] == memory["total"]
    assert 0 < memory["percent"] < 100


def _windows(monkeypatch):
    monkeypatch.setattr(collect, "is_windows", lambda: True)


def test_scan_reports_timeout(monkeypatch):
    _windows(monkeypatch)

    def runner():
        raise subprocess.TimeoutExpired("powershell", 60)

    result = collect.scan(runner=runner)
    assert "dépassé" in result["note"] and "os" not in result


def test_scan_reports_missing_powershell(monkeypatch):
    _windows(monkeypatch)

    def runner():
        raise FileNotFoundError("powershell.exe")

    assert "Impossible de lancer PowerShell" in collect.scan(runner=runner)["note"]


def test_scan_reports_stderr_when_output_is_not_json(monkeypatch):
    _windows(monkeypatch)
    result = collect.scan(runner=lambda: (1, "", "ligne 1\nAccès refusé au fournisseur CIM"))
    assert "code 1" in result["note"] and "Accès refusé au fournisseur CIM" in result["note"]


def test_scan_outside_windows():
    result = collect.scan(runner=lambda: (_ for _ in ()).throw(AssertionError("ne doit pas être appelé")))
    assert "Windows" in result["note"]
    json.dumps(result)


def test_script_fits_in_a_windows_command_line():
    import base64

    encoded = base64.b64encode(collect.PS_SCRIPT.encode("utf-16le"))
    assert len(encoded) < 30000  # limite CreateProcess : 32 767 caractères — CreateProcess limit: 32,767 characters


def test_timings(data):
    assert data["timings"]["license"] == 2300 and data["powershell_ms"] == 4100
    assert isinstance(data["scan_seconds"], float)
    from atlas import pages

    analysis = next(s for s in pages.page_system(data) if s.title == "Analyse")
    rows = {row.label: row.value for row in analysis.rows}
    assert rows["Source la plus lente"] == "activation Windows (2,3 s)"
    assert all(row.volatile for row in analysis.rows)


def test_timings_tolerate_odd_values(monkeypatch):
    monkeypatch.setattr(collect, "is_windows", lambda: True)
    payload = {"os": {"Caption": "Windows"}, "timings": {"os": "12.5", "cpu": None, "ram": 3}, "total_ms": "40"}
    data = collect.scan(runner=lambda: (0, json.dumps(payload), ""))
    assert data["timings"] == {"os": 12, "ram": 3} and data["powershell_ms"] == 40
    assert collect.base_report("x")["note"] == "x" and "note" not in collect.base_report()
