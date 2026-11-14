import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GIB = 1024**3

# Ce que renverrait le script PowerShell sur un portable type (valeurs fictives).
PAYLOAD = {
    "admin": False,
    "machine": {
        "Manufacturer": "LENOVO",
        "Model": "82JU",
        "SystemFamily": "Legion 5 15ACH6H",
        "SystemType": "x64-based PC",
        "TotalPhysicalMemory": 16 * GIB - 90_000_000,
        "HypervisorPresent": True,
        "PartOfDomain": False,
        "Domain": "WORKGROUP",
    },
    "bios": {"Manufacturer": "LENOVO", "Version": "GKCN59WW", "ReleaseDate": "2023-08-14", "SerialNumber": "PF3ABCDE"},
    "secureboot": [],
    "os": {
        "Caption": "Microsoft Windows 11 Famille",
        "Version": "10.0.26100",
        "BuildNumber": "26100",
        "DisplayVersion": "24H2",
        "OSArchitecture": "64 bits",
        "TotalVisibleMemorySize": (16 * GIB - 90_000_000) // 1024,
        "FreePhysicalMemory": 6 * GIB // 1024,
        "InstallDate": "2025-01-12T09:30:00",
        "LastBootUpTime": "2026-11-09T08:00:00",
    },
    # objet seul là où l'on attend une liste : cas réel avec ConvertTo-Json
    "cpu": {
        "Name": "AMD Ryzen 7 5800H with Radeon Graphics",
        "Manufacturer": "AuthenticAMD",
        "NumberOfCores": 8,
        "NumberOfLogicalProcessors": 16,
        "MaxClockSpeed": 3201,
        "CurrentClockSpeed": 3201,
        "SocketDesignation": "FP6",
        "L2CacheSize": 4096,
        "L3CacheSize": 16384,
        "VirtualizationFirmwareEnabled": True,
        "LoadPercentage": 7,
    },
    "board": {"Manufacturer": "LENOVO", "Product": "LNVNB161216", "Version": "SDK0T76463 WIN", "SerialNumber": "PF3ABCDE"},
    "ram": [
        {
            "Manufacturer": "Samsung",
            "PartNumber": "M471A1K43DB1-CWE ",
            "SerialNumber": "1234ABCD",
            "Capacity": 8 * GIB,
            "Speed": 3200,
            "ConfiguredClockSpeed": 3200,
            "DeviceLocator": "DIMM 0",
            "BankLabel": "P0 CHANNEL A",
            "SMBIOSMemoryType": 26,
            "FormFactor": 12,
        },
        {
            "Manufacturer": "Mémoire Générique",
            "PartNumber": "X",
            "SerialNumber": "5678EFGH",
            "Capacity": 8 * GIB,
            "Speed": 3200,
            "ConfiguredClockSpeed": 2933,
            "DeviceLocator": "DIMM 1",
            "BankLabel": "P0 CHANNEL B",
            "SMBIOSMemoryType": 26,
            "FormFactor": 12,
        },
    ],
    "memoryarray": {"MemoryDevices": 2, "MaxCapacity": 64 * 1024 * 1024},
    "gpu": [
        {
            "Name": "NVIDIA GeForce RTX 3060 Laptop GPU",
            "VRAM": 6 * GIB,
            "VRAMSource": "registre",
            "DriverVersion": "32.0.15.6094",
            "DriverDate": "2026-08-01",
            "VideoModeDescription": "1920 x 1080 x 4294967296 couleurs",
            "RefreshRate": 165,
        },
        {"Name": "Carte capée", "VRAM": 4293918720, "VRAMSource": "AdapterRAM", "DriverVersion": "1.0"},
    ],
    "disks": [
        {
            "Model": "SAMSUNG MZVLB512HBJQ",
            "MediaType": "SSD",
            "BusType": "NVMe",
            "Size": 512110190592,
            "Health": "Healthy",
            "Status": "OK",
            "SerialNumber": "S4EWNX0R",
            "Firmware": "EXF7201Q",
            "Temperature": 41,
            "PowerOnHours": 5120,
            "Wear": 3,
            "ReadErrors": 0,
        },
        {
            "Model": "ST1000LM035",
            "MediaType": "3",
            "BusType": "11",
            "Size": 1000204886016,
            "Health": "Warning",
            "Status": "OK",
            "SerialNumber": "WL1ABCDE",
            "Firmware": "LCM2",
            "Temperature": None,
            "PowerOnHours": None,
            "Wear": None,
            "ReadErrors": None,
        },
    ],
    "volumes": [{"DeviceID": "C:", "VolumeName": "Système", "FileSystem": "NTFS", "Size": 511000000000, "FreeSpace": 120000000000}],
    "bitlocker": [],
    "adapters": [
        {
            "Name": "Wi-Fi",
            "InterfaceDescription": "Intel(R) Wi-Fi 6 AX200",
            "Status": "Up",
            "LinkSpeed": "866.7 Mbps",
            "MacAddress": "AA-BB-CC-DD-EE-FF",
        }
    ],
    "network": {"Name": "Wi-Fi", "IPv4": "192.168.1.42", "IPv6": "fe80::1", "Gateway": "192.168.1.1", "DNS": "192.168.1.1, 1.1.1.1"},
    "temperatures": [{"Name": "TZ0", "Celsius": 47.5}, {"Name": "TZ1", "Celsius": -273.1}, {"Name": "TZ2", "Celsius": 300}],
    "battery": {"Name": "L20C4PC0", "Charge": 83, "Status": 2, "FullCapacity": 68000, "DesignCapacity": 80000},
    "monitors": [{"Name": "LEN156FHD", "Manufacturer": "BOE", "SerialNumber": "0", "Year": 2020, "WidthCm": 34, "HeightCm": 19}],
    "audio": [{"Name": "Realtek(R) Audio", "Manufacturer": "Realtek", "Status": "OK"}],
    "tpm": [],
    "license": {"Name": "Windows(R), Core edition", "Description": "Windows(R) Operating System, OEM_DM channel", "LicenseStatus": 1},
    "errors": {"secureboot": "Accès refusé.", "tpm": "Accès refusé.", "bitlocker": "Accès refusé."},
    "timings": {"machine": 120, "os": 210, "disks": 900, "license": 2300, "cpu": 80},
    "total_ms": 4100,
}


@pytest.fixture(autouse=True)
def not_windows(monkeypatch):
    """Par défaut, aucun test ne lance PowerShell, même sous Windows : le vrai inventaire
    est vérifié à part (tools/check_scan.py, job « windows-scan » de la CI)."""
    from atlas import collect

    monkeypatch.setattr(collect, "is_windows", lambda: False)


@pytest.fixture(autouse=True)
def french(monkeypatch):
    """Les tests attendent l'interface en français, quelle que soit la langue du système qui les lance."""
    from atlas import i18n

    for name in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")  # lu en premier par i18n.system_language()
    i18n.set_language("fr")
    yield
    i18n.set_language("fr")


@pytest.fixture
def english():
    from atlas import i18n

    i18n.set_language("en")
    yield
    i18n.set_language("fr")


@pytest.fixture
def payload():
    return json.loads(json.dumps(PAYLOAD))


@pytest.fixture
def data(payload, monkeypatch):
    """Inventaire complet tel que scan() le produirait sous Windows."""
    from atlas import collect

    monkeypatch.setattr(collect, "is_windows", lambda: True)
    stdout = "﻿" + json.dumps(payload, ensure_ascii=False)
    result = collect.scan(runner=lambda: (0, stdout, ""))
    result["captured_at"] = "2026-11-11T10:30:00+01:00"
    return result


@pytest.fixture
def win(qtbot, monkeypatch, tmp_path):
    """Fenêtre principale sous un « Windows » simulé, inventaire d'exemple chargé."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from atlas import collect
    from atlas.gui import theme, window

    monkeypatch.setattr(collect, "is_windows", lambda: True)
    theme.load_fonts()
    theme.set_theme("dark")

    def fake_scan():
        return collect.scan(runner=lambda: (0, json.dumps(PAYLOAD), ""))

    w = window.MainWindow(scanner=fake_scan)
    qtbot.addWidget(w)
    w.resize(1320, 900)
    w.show()
    qtbot.waitUntil(lambda: bool(w.data) and not w._scanning, timeout=5000)
    return w
