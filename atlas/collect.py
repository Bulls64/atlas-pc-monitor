"""Collecte de l'inventaire : un seul appel PowerShell/CIM, normalisé en dictionnaire.

Inventory collection: a single PowerShell/CIM call, normalized into a dictionary.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import platform
import socket
import subprocess
import time
from datetime import datetime

from . import __version__
from .formatting import to_number
from .i18n import _

log = logging.getLogger("atlas")

TIMEOUT_SECONDS = 60
MARKER = "ATLAS:"

# Sections renvoyant un seul objet ; toutes les autres sont des listes.
# Sections that return a single object; all the others are lists.
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
    "pnp",
)
# Sources que Windows ne livre en général qu'à un processus élevé.
# Sources that Windows usually only provides to an elevated process.
ADMIN_SECTIONS = ("secureboot", "tpm", "bitlocker", "temperatures")

PS_SCRIPT = r"""
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$err=[ordered]@{}
$time=[ordered]@{}
$total=[Diagnostics.Stopwatch]::StartNew()
function Q([string]$n,[scriptblock]$b){$w=[Diagnostics.Stopwatch]::StartNew();try{$r=,@(& $b)}catch{$script:err[$n]="$($_.Exception.Message)".Trim();$r=,@()};$script:time[$n]=$w.ElapsedMilliseconds;$r}
function S($a){if($a){(-join($a|Where-Object{$_ -ne 0}|ForEach-Object{[char]$_})).Trim()}}
function I($d,[string]$f='s'){if($d){([datetime]$d).ToString($f)}}

$admin=$false
try{$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}catch{}

$machine=Q 'machine' {Get-CimInstance Win32_ComputerSystem|Select-Object Manufacturer,Model,SystemFamily,SystemType,TotalPhysicalMemory,HypervisorPresent,PartOfDomain,Domain}
$bios=Q 'bios' {Get-CimInstance Win32_BIOS|ForEach-Object{[pscustomobject]@{Manufacturer=$_.Manufacturer;Version=$_.SMBIOSBIOSVersion;ReleaseDate=(I $_.ReleaseDate 'yyyy-MM-dd');SerialNumber=$_.SerialNumber}}}
$secureboot=Q 'secureboot' {[pscustomobject]@{Enabled=[bool](Confirm-SecureBootUEFI)}}
$os=Q 'os' {Get-CimInstance Win32_OperatingSystem|ForEach-Object{$r=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction SilentlyContinue;[pscustomobject]@{Caption=$_.Caption;SystemDrive=$_.SystemDrive;FirmwareType=$env:firmware_type;Version=$_.Version;BuildNumber=$_.BuildNumber;DisplayVersion=$r.DisplayVersion;OSArchitecture=$_.OSArchitecture;TotalVisibleMemorySize=$_.TotalVisibleMemorySize;FreePhysicalMemory=$_.FreePhysicalMemory;InstallDate=(I $_.InstallDate);LastBootUpTime=(I $_.LastBootUpTime)}}}
$cpu=Q 'cpu' {Get-CimInstance Win32_Processor|Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed,SocketDesignation,L2CacheSize,L3CacheSize,VirtualizationFirmwareEnabled,LoadPercentage}
$board=Q 'board' {Get-CimInstance Win32_BaseBoard|Select-Object Manufacturer,Product,Version,SerialNumber}
$ram=Q 'ram' {Get-CimInstance Win32_PhysicalMemory|Select-Object Manufacturer,PartNumber,SerialNumber,Capacity,Speed,ConfiguredClockSpeed,DeviceLocator,BankLabel,SMBIOSMemoryType,FormFactor}
$memoryarray=Q 'memoryarray' {Get-CimInstance Win32_PhysicalMemoryArray|Select-Object -First 1 MemoryDevices,MaxCapacity}

$vram=@{}
$null=Q 'vram' {Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction SilentlyContinue|ForEach-Object{$m=$_.'HardwareInformation.qwMemorySize';if($m -is [byte[]]){if($m.Length -ge 8){$m=[BitConverter]::ToUInt64($m,0)}else{$m=$null}};if($m -and $_.DriverDesc){$vram[[string]$_.DriverDesc]=[uint64]$m}}}
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
$pnp=Q 'pnp' {Get-CimInstance Win32_PnPEntity -Filter 'ConfigManagerErrorCode<>0'|Select-Object Name,PNPClass,ConfigManagerErrorCode}
$license=Q 'license' {Get-CimInstance SoftwareLicensingProduct -Filter "ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL"|Select-Object Name,Description,LicenseStatus}

$json=[ordered]@{admin=$admin;machine=$machine;bios=$bios;secureboot=$secureboot;os=$os;cpu=$cpu;board=$board;ram=$ram;memoryarray=$memoryarray;gpu=$gpu;disks=$disks;volumes=$volumes;bitlocker=$bitlocker;adapters=$adapters;network=$network;temperatures=$temperatures;battery=$battery;monitors=$monitors;audio=$audio;tpm=$tpm;license=$license;pnp=$pnp;errors=$err;timings=$time;total_ms=$total.ElapsedMilliseconds}|ConvertTo-Json -Depth 6 -Compress
# Sortie en base64 : le JSON traverse intact n'importe quelle page de code console.
# Base64 output: the JSON passes intact through any console code page.
'ATLAS:'+[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
"""


def is_windows() -> bool:
    return os.name == "nt"


VIRTUAL_MACHINES = ("virtual machine", "vmware", "virtualbox", "qemu", "kvm", "parallels", "xen", "bochs")


def is_virtual(data: dict) -> bool:
    """Inventaire d'une machine virtuelle (Hyper-V, VMware…) : sa « mémoire » n'est pas faite de vraies barrettes.

    Inventory of a virtual machine (Hyper-V, VMware…): its "memory" is not made of real modules.
    """
    machine = data.get("machine") or {}
    text = f"{machine.get('Manufacturer') or ''} {machine.get('Model') or ''}".lower()
    return any(word in text for word in VIRTUAL_MACHINES)


def powershell_path() -> str:
    """Chemin absolu de Windows PowerShell, sans dépendre du PATH.

    Absolute path of Windows PowerShell, without relying on PATH.
    """
    root = os.environ.get("SystemRoot", r"C:\Windows")
    # « Sysnative » donne le PowerShell 64 bits à un Python 32 bits.
    # "Sysnative" gives a 32-bit Python the 64-bit PowerShell.
    for folder in ("Sysnative", "System32"):
        candidate = os.path.join(root, folder, "WindowsPowerShell", "v1.0", "powershell.exe")
        if os.path.isfile(candidate):
            return candidate
    return "powershell.exe"


def run_powershell(script: str = PS_SCRIPT, timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """Exécute le script et renvoie (code retour, sortie standard, sortie d'erreur).

    Runs the script and returns (exit code, standard output, standard error).
    """
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
    """Normalise une valeur CIM (objet seul, tableau, ou enveloppe {value, Count}) en liste.

    Normalizes a CIM value (single object, array, or {value, Count} wrapper) into a list.
    """
    if isinstance(value, dict) and "value" in value and "Count" in value:
        value = value["value"]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and value:
        return [value]
    return []


def parse_inventory(stdout: str) -> dict:
    """Extrait l'inventaire de la sortie PowerShell (ligne « ATLAS:<base64> », ou JSON brut).

    Extracts the inventory from the PowerShell output ("ATLAS:<base64>" line, or raw JSON).
    """
    text = stdout
    for line in stdout.splitlines():
        if line.strip().startswith(MARKER):
            text = base64.b64decode(line.strip()[len(MARKER) :]).decode("utf-8")
            break
    start = text.find("{")
    if start < 0:
        raise ValueError(_("aucun inventaire dans la sortie de PowerShell"))
    payload = json.loads(text[start:])
    if not isinstance(payload, dict):
        raise ValueError(_("la sortie de PowerShell n'est pas un objet JSON"))
    return payload


def normalize(payload: dict) -> dict:
    """Met les sections dans une forme stable : un dict pour les objets seuls, une liste sinon.

    Puts the sections into a stable shape: a dict for single objects, a list otherwise.
    """
    data: dict = {"admin": bool(payload.get("admin"))}
    for key in SINGLE_SECTIONS:
        rows = as_rows(payload.get(key))
        data[key] = rows[0] if rows else {}
    for key in LIST_SECTIONS:
        data[key] = as_rows(payload.get(key))
    errors = payload.get("errors")
    data["errors"] = {str(k): str(v) for k, v in errors.items()} if isinstance(errors, dict) else {}
    # Une zone ACPI absente ou à 0 K renvoie des valeurs absurdes : on ne garde que le plausible.
    # A missing ACPI zone, or one at 0 K, returns absurd values: only plausible ones are kept.
    data["temperatures"] = [t for t in data["temperatures"] if 0 < (to_number(t.get("Celsius")) or 0) <= 120]
    return data


def compute_memory(data: dict) -> dict:
    """Mémoire installée (somme des barrettes) et mémoire utilisable vue par Windows.

    Installed memory (sum of the modules) and usable memory as seen by Windows.
    """
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


def base_report(note: str = "") -> dict:
    """Ce que l'on sait sans PowerShell : version, horodatage, nom du poste, plateforme.

    What is known without PowerShell: version, timestamp, computer name, platform.
    """
    data: dict = {
        "atlas_version": __version__,
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "system": {
            "computer": socket.gethostname(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
    }
    if note:
        data["note"] = note
    return data


def scan(runner=run_powershell) -> dict:
    """Inventaire complet. Ne lève jamais : un échec est décrit dans data['note'].

    Full inventory. Never raises: a failure is described in data['note'].
    """
    data = base_report()
    if not is_windows():
        data["note"] = _("Informations matérielles détaillées disponibles sous Windows.")
        return data
    started = time.perf_counter()
    try:
        code, stdout, stderr = runner()
    except subprocess.TimeoutExpired:
        data["note"] = _("La collecte a dépassé {0} s et a été interrompue. Réessayez avec « Actualiser ».", TIMEOUT_SECONDS)
        log.warning("PowerShell : délai dépassé")
        return data
    except OSError as error:
        data["note"] = _("Impossible de lancer PowerShell : {0}", error)
        log.warning("PowerShell : %s", error)
        return data
    log.debug("PowerShell code=%s stdout=%d car. stderr=%r", code, len(stdout), stderr[:2000])
    try:
        payload = parse_inventory(stdout)
        log.debug("Inventaire brut : %s", json.dumps(payload, ensure_ascii=False))
        data.update(normalize(payload))
    except (ValueError, TypeError) as error:
        detail = (stderr.strip().splitlines() or [str(error)])[-1]
        data["note"] = _("La collecte PowerShell a échoué (code {0}) : {1}", code, detail)
        log.warning("Sortie PowerShell illisible : %s", error)
        return data
    data["memory"] = compute_memory(data)
    data["scan_seconds"] = round(time.perf_counter() - started, 2)
    timings = payload.get("timings")
    if isinstance(timings, dict):
        data["timings"] = {str(k): int(n) for k, v in timings.items() if (n := to_number(v)) is not None}
        data["powershell_ms"] = int(to_number(payload.get("total_ms")) or 0)
        slowest = sorted(data["timings"].items(), key=lambda item: -item[1])[:5]
        log.debug("Durée : %.2f s ; PowerShell %s ms ; plus lentes : %s", data["scan_seconds"], data["powershell_ms"], slowest)
    return data
