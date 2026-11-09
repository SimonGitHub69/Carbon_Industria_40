#Requires -Version 5.1
<#
.SYNOPSIS
  Prepara l'ambiente Python del poller Modbus su Windows Server.
.NOTES
  Eseguire da PowerShell (consigliato come Administrator) nella root del progetto.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$SkipPip,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
Set-Location $InstallRoot

Write-Host "=== Carbon Industria 4.0 — install client ===" -ForegroundColor Cyan
Write-Host "Root: $InstallRoot"

# --- Python ---
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python non trovato nel PATH. Installare Python 3.12+ e riprovare."
}
$pyVer = & python --version 2>&1
Write-Host "Python: $pyVer"

# --- File obbligatori ---
$required = @(
    "requirements.txt",
    "modbus_poller\__main__.py",
    "file configurazione\service_config.xml",
    "file configurazione\modbus_server_cella_frigo.xml"
)
foreach ($rel in $required) {
    $p = Join-Path $InstallRoot $rel
    if (-not (Test-Path $p)) {
        Write-Error "File mancante: $p"
    }
    Write-Host "OK  $rel"
}

# --- venv ---
$venvPython = Join-Path $InstallRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creazione virtualenv .venv ..."
    & python -m venv (Join-Path $InstallRoot ".venv")
}
if (-not (Test-Path $venvPython)) {
    Write-Error "Impossibile creare .venv"
}
Write-Host "venv: $venvPython"

# --- dipendenze ---
if (-not $SkipPip) {
    Write-Host "Installazione requirements.txt ..."
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $InstallRoot "requirements.txt")
}

# --- import / config check ---
Write-Host "Verifica config ..."
$env:SERVICE_CONFIG = Join-Path $InstallRoot "file configurazione\service_config.xml"
& $venvPython -c @"
from modbus_poller.config import load_settings
s = load_settings()
print('device =', s.modbus.device_name)
print('table  =', s.modbus.table_name)
print('host   =', s.modbus.host, s.modbus.port)
print('poll   =', int(s.poll_interval_sec), 's')
print('alarm  =', int(s.alarm_interval_sec), 's')
print('analog =', [p.code for p in s.modbus.analog_points])
print('alarms =', [p.code for p in s.modbus.alarm_points])
"@

# --- rete Modbus (informativo) ---
Write-Host "Test porta Modbus 502 ..."
try {
    $tnc = Test-NetConnection -ComputerName 192.168.75.220 -Port 502 -WarningAction SilentlyContinue
    if ($tnc.TcpTestSucceeded) {
        Write-Host "OK  TCP 192.168.75.220:502 raggiungibile" -ForegroundColor Green
    } else {
        Write-Host "WARN TCP 192.168.75.220:502 NON raggiungibile (verificare rete/firewall)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "WARN Test-NetConnection non riuscito: $_" -ForegroundColor Yellow
}

if ($SmokeTest) {
    Write-Host "Smoke test: un ciclo (Ctrl+C per uscire se resta in loop) — avvio 8s ..."
    $job = Start-Job -ScriptBlock {
        param($root, $py)
        Set-Location $root
        $env:SERVICE_CONFIG = Join-Path $root "file configurazione\service_config.xml"
        & $py -m modbus_poller
    } -ArgumentList $InstallRoot, $venvPython
    Start-Sleep -Seconds 8
    Stop-Job $job -ErrorAction SilentlyContinue
    Receive-Job $job
    Remove-Job $job -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Installazione ambiente completata ===" -ForegroundColor Green
Write-Host "Prossimi passi:"
Write-Host "  1. Configurare PostgreSQL e password in service_config.xml"
Write-Host "  2. Test:  .\.venv\Scripts\python.exe -m modbus_poller"
Write-Host "  3. Creare servizio Servy (vedi docs\INSTALL_WINDOWS_SERVER.md)"
Write-Host ""
Write-Host "Servy — Process path:"
Write-Host "  $venvPython"
Write-Host "Servy — Startup directory:"
Write-Host "  $InstallRoot"
Write-Host "Servy — Arguments:"
Write-Host "  -m modbus_poller"
