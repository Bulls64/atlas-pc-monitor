"""Collecte de l'inventaire : un seul appel PowerShell/CIM, normalisé en dictionnaire."""

from __future__ import annotations

import base64
import json
import logging
import os
import platform
import socket
import subprocess
from datetime import datetime

from . import __version__
from .formatting import to_number

log = logging.getLogger("atlas")

TIMEOUT_SECONDS = 60
MARKER = "ATLAS:"

# Sections renvoyant un seul objet ; toutes les autres sont des listes.
SINGLE_SECTIONS = ("machine", "bios", "secureboot", "os", "board", "memoryarray", "tpm")
LIST_SECTIONS = (
    "cpu",
    "ram",
    "gpu",
    "disks",
    "volumes",
    "bitlocker",
    "adapters",
    "network",
    "temperatures",
    "battery",
    "monitors",
    "audio",
    "license",
)
# Sources que Windows ne livre en général qu'à un processus élevé.
ADMIN_SECTIONS = ("secureboot", "tpm", "bitlocker", "temperatures")

PS_SCRIPT = r"""
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$err=[ordered]@{}
function Q([string]$n,[scriptblock]$b){try{,@(& $b)}catch{$script:err[$n]="$($_.Exception.Message)".Trim();,@()}}
function S($a){if($a){(-join($a|Where-Object{$_ -ne 0}|ForEach-Object{[char]$_})).Trim()}}
function I($d,[string]$f='s'){if($d){([datetime]$d).ToString($f)}}

$admin=$false
try{$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}catch{}

$machine=Q 'machine' {Get-CimInstance Win32_ComputerSystem|Select-Object Manufacturer,Model,SystemFamily,SystemType,TotalPhysicalMemory,HypervisorPresent,PartOfDomain,Domain}
$bios=Q 'bios' {Get-CimInstance Win32_BIOS|ForEach-Object{[pscustomobject]@{Manufacturer=$_.Manufacturer;Version=$_.SMBIOSBIOSVersion;ReleaseDate=(I $_.ReleaseDate 'yyyy-MM-dd');SerialNumber=$_.SerialNumber}}}
$secureboot=Q 'secureboot' {[pscustomobject]@{Enabled=[bool](Confirm-SecureBootUEFI)}}
$os=Q 'os' {Get-CimInstance Win32_OperatingSystem|ForEach-Object{$r=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction SilentlyContinue;[pscustomobject]@{Caption=$_.Caption;Version=$_.Version;BuildNumber=$_.BuildNumber;DisplayVersion=$r.DisplayVersion;OSArchitecture=$_.OSArchitecture;TotalVisibleMemorySize=$_.TotalVisibleMemorySize;FreePhysicalMemory=$_.FreePhysicalMemory;InstallDate=(I $_.InstallDate);LastBootUpTime=(I $_.LastBootUpTime)}}}
$cpu=Q 'cpu' {Get-CimInstance Win32_Processor|Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed,SocketDesignation,L2CacheSize,L3CacheSize,VirtualizationFirmwareEnabled,LoadPercentage}
$board=Q 'board' {Get-CimInstance Win32_BaseBoard|Select-Object Manufacturer,Product,Version,SerialNumber}
$ram=Q 'ram' {Get-CimInstance Win32_PhysicalMemory|Select-Object Manufacturer,PartNumber,SerialNumber,Capacity,Speed,ConfiguredClockSpeed,DeviceLocator,BankLabel,SMBIOSMemoryType,FormFactor}
$memoryarray=Q 'memoryarray' {Get-CimInstance Win32_PhysicalMemoryArray|Select-Object -First 1 MemoryDevices,MaxCapacity}

$vram=@{}
try{Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction SilentlyContinue|ForEach-Object{$m=$_.'HardwareInformation.qwMemorySize';if($m -is [byte[]]){if($m.Length -ge 8){$m=[BitConverter]::ToUInt64($m,0)}else{$m=$null}};if($m -and $_.DriverDesc){$vram[[string]$_.DriverDesc]=[uint64]$m}}}catch{}
$gpu=Q 'gpu' {Get-CimInstance Win32_VideoController|ForEach-Object{$k=[string]$_.Name;$v=$_.AdapterRAM;$s='AdapterRAM';if($vram.ContainsKey($k)){$v=$vram[$k];$s='registre'};[pscustomobject]@{Name=$_.Name;VRAM=$v;VRAMSource=$s;DriverVersion=$_.DriverVersion;DriverDate=(I $_.DriverDate 'yyyy-MM-dd');VideoModeDescription=$_.VideoModeDescription;RefreshRate=$_.CurrentRefreshRate}}}

$disks=Q 'disks' {Get-PhysicalDisk|ForEach-Object{$r=$null;try{$r=$_|Get-StorageReliabilityCounter -ErrorAction Stop}catch{};[pscustomobject]@{Model=$_.FriendlyName;MediaType="$($_.MediaType)";BusType="$($_.BusType)";Size=$_.Size;Health="$($_.HealthStatus)";Status="$($_.OperationalStatus)";SerialNumber="$($_.SerialNumber)".Trim();Firmware=$_.FirmwareVersion;Temperature=$r.Temperature;PowerOnHours=$r.PowerOnHours;Wear=$r.Wear;ReadErrors=$r.ReadErrorsTotal}}}
if(-not $disks.Count){$disks=Q 'disks_fallback' {Get-CimInstance Win32_DiskDrive|ForEach-Object{[pscustomobject]@{Model=$_.Model;MediaType='';BusType=$_.InterfaceType;Size=$_.Size;Status=$_.Status;SerialNumber="$($_.SerialNumber)".Trim()}}}}
$volumes=Q 'volumes' {Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'|Select-Object DeviceID,VolumeName,FileSystem,Size,FreeSpace}
$bitlocker=Q 'bitlocker' {Get-BitLockerVolume|ForEach-Object{[pscustomobject]@{MountPoint=$_.MountPoint;Protection="$($_.ProtectionStatus)";Status="$($_.VolumeStatus)";Percent=$_.EncryptionPercentage}}}

$adapters=Q 'adapters' {Get-NetAdapter -Physical|ForEach-Object{[pscustomobject]@{Name=$_.Name;InterfaceDescription=$_.InterfaceDescription;Status="$($_.Status)";LinkSpeed="$($_.LinkSpeed)";MacAddress=$_.MacAddress}}}
$network=Q 'network' {Get-NetIPConfiguration|Where-Object{$_.NetAdapter.Status -eq 'Up'}|ForEach-Object{[pscustomobject]@{Name=$_.InterfaceAlias;IPv4=($_.IPv4Address.IPAddress -join ', ');IPv6=($_.IPv6Address.IPAddress -join ', ');Gateway=($_.IPv4DefaultGateway.NextHop -join ', ');DNS=($_.DNSServer.ServerAddresses -join ', ')}}}
$temperatures=Q 'temperatures' {Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi|ForEach-Object{[pscustomobject]@{Name=$_.InstanceName;Celsius=[math]::Round(($_.CurrentTemperature/10)-273.15,1)}}}
$battery=Q 'battery' {Get-CimInstance Win32_Battery|ForEach-Object{$full=$null;$design=$null;try{$full=(Get-CimInstance -Namespace root/wmi BatteryFullChargedCapacity -ErrorAction Stop|Select-Object -First 1).FullChargedCapacity;$design=(Get-CimInstance -Namespace root/wmi BatteryStaticData -ErrorAction Stop|Select-Object -First 1).DesignedCapacity}catch{};[pscustomobject]@{Name=$_.Name;Charge=$_.EstimatedChargeRemaining;Status=$_.BatteryStatus;FullCapacity=$full;DesignCapacity=$design}}}
$monitors=Q 'monitors' {$p=@{};try{Get-CimInstance -Namespace root/wmi WmiMonitorBasicDisplayParams -ErrorAction Stop|ForEach-Object{$p[$_.InstanceName]=$_}}catch{};Get-CimInstance -Namespace root/wmi WmiMonitorID|ForEach-Object{$d=$p[$_.InstanceName];[pscustomobject]@{Name=(S $_.UserFriendlyName);Manufacturer=(S $_.ManufacturerName);SerialNumber=(S $_.SerialNumberID);Year=$_.YearOfManufacture;WidthCm=$d.MaxHorizontalImageSize;HeightCm=$d.MaxVerticalImageSize}}}
$audio=Q 'audio' {Get-CimInstance Win32_SoundDevice|Select-Object Name,Manufacturer,Status}
$tpm=Q 'tpm' {Get-CimInstance -Namespace root/cimv2/security/microsofttpm -ClassName Win32_Tpm|Select-Object IsEnabled_InitialValue,IsActivated_InitialValue,SpecVersion,ManufacturerVersion}
$license=Q 'license' {Get-CimInstance SoftwareLicensingProduct -Filter "ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL"|Select-Object Name,Description,LicenseStatus}

$json=[ordered]@{admin=$admin;machine=$machine;bios=$bios;secureboot=$secureboot;os=$os;cpu=$cpu;board=$board;ram=$ram;memoryarray=$memoryarray;gpu=$gpu;disks=$disks;volumes=$volumes;bitlocker=$bitlocker;adapters=$adapters;network=$network;temperatures=$temperatures;battery=$battery;monitors=$monitors;audio=$audio;tpm=$tpm;license=$license;errors=$err}|ConvertTo-Json -Depth 6 -Compress
# Sortie en base64 : le JSON traverse intact n'importe quelle page de code console.
'ATLAS:'+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
"""


def is_windows() -> bool:
    return os.name == "nt"


def powershell_path() -> str:
    """Chemin absolu de Windows PowerShell, sans dépendre du PATH."""
    root = os.environ.get("SystemRoot", r"C:\Windows")
    # « Sysnative » donne le PowerShell 64 bits à un Python 32 bits.
    for folder in ("Sysnative", "System32"):
        candidate = os.path.join(root, folder, "WindowsPowerShell", "v1.0", "powershell.exe")
        if os.path.isfile(candidate):
            return candidate
    return "powershell.exe"


def run_powershell(script: str = PS_SCRIPT, timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """Exécute le script et renvoie (code retour, sortie standard, sortie d'erreur)."""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        [powershell_path(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stdout = result.stdout.decode("utf-8-sig", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    return result.returncode, stdout, stderr


def as_rows(value) -> list[dict]:
    """Normalise une valeur CIM (objet seul, tableau, ou enveloppe {value, Count}) en liste."""
    if isinstance(value, dict) and "value" in value and "Count" in value:
        value = value["value"]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and value:
        return [value]
    return []


def parse_inventory(stdout: str) -> dict:
    """Extrait l'inventaire de la sortie PowerShell (ligne « ATLAS:<base64> », ou JSON brut)."""
    text = stdout
    for line in stdout.splitlines():
        if line.strip().startswith(MARKER):
            text = base64.b64decode(line.strip()[len(MARKER) :]).decode("utf-8")
            break
    start = text.find("{")
    if start < 0:
        raise ValueError("aucun inventaire dans la sortie de PowerShell")
    payload = json.loads(text[start:])
    if not isinstance(payload, dict):
        raise ValueError("la sortie de PowerShell n'est pas un objet JSON")
    return payload


def normalize(payload: dict) -> dict:
    """Met les sections dans une forme stable : un dict pour les objets seuls, une liste sinon."""
    data: dict = {"admin": bool(payload.get("admin"))}
    for key in SINGLE_SECTIONS:
        rows = as_rows(payload.get(key))
        data[key] = rows[0] if rows else {}
    for key in LIST_SECTIONS:
        data[key] = as_rows(payload.get(key))
    errors = payload.get("errors")
    data["errors"] = {str(k): str(v) for k, v in errors.items()} if isinstance(errors, dict) else {}
    # Une zone ACPI absente ou à 0 K renvoie des valeurs absurdes : on ne garde que le plausible.
    data["temperatures"] = [
        t for t in data["temperatures"] if (to_number(t.get("Celsius")) or 0) > 0 and to_number(t.get("Celsius")) <= 120
    ]
    return data


def compute_memory(data: dict) -> dict:
    """Mémoire installée (somme des barrettes) et mémoire utilisable vue par Windows."""
    system = data.get("os") or {}
    usable = (to_number(system.get("TotalVisibleMemorySize")) or 0) * 1024
    free = (to_number(system.get("FreePhysicalMemory")) or 0) * 1024
    installed = sum(to_number(stick.get("Capacity")) or 0 for stick in data.get("ram") or [])
    if not usable:
        usable = to_number((data.get("machine") or {}).get("TotalPhysicalMemory")) or 0
    if not usable:
        return {}
    used = max(usable - free, 0)
    return {
        "installed": int(installed or usable),
        "total": int(usable),
        "free": int(free),
        "used": int(used),
        "percent": round(used * 100 / usable),
    }


def scan(runner=run_powershell) -> dict:
    """Inventaire complet. Ne lève jamais : un échec est décrit dans data['note']."""
    data: dict = {
        "atlas_version": __version__,
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "system": {
            "computer": socket.gethostname(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
    }
    if not is_windows():
        data["note"] = "Informations matérielles détaillées disponibles sous Windows."
        return data
    try:
        code, stdout, stderr = runner()
    except subprocess.TimeoutExpired:
        data["note"] = f"La collecte a dépassé {TIMEOUT_SECONDS} s et a été interrompue. Réessayez avec « Actualiser »."
        log.warning("PowerShell : délai dépassé")
        return data
    except OSError as error:
        data["note"] = f"Impossible de lancer PowerShell : {error}"
        log.warning("PowerShell : %s", error)
        return data
    log.debug("PowerShell code=%s stdout=%d car. stderr=%r", code, len(stdout), stderr[:2000])
    try:
        payload = parse_inventory(stdout)
        log.debug("Inventaire brut : %s", json.dumps(payload, ensure_ascii=False))
        data.update(normalize(payload))
    except (ValueError, TypeError) as error:
        detail = (stderr.strip().splitlines() or [str(error)])[-1]
        data["note"] = f"La collecte PowerShell a échoué (code {code}) : {detail}"
        log.warning("Sortie PowerShell illisible : %s", error)
        return data
    data["memory"] = compute_memory(data)
    return data
