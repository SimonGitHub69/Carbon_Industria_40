#Requires -Version 5.1
<#
.SYNOPSIS
  Aggiorna dipendenze e verifica config dopo aver copiato i file nuovi.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ServiceName = "CarbonModbusCellaFrigo"
)

$ErrorActionPreference = "Stop"
Set-Location $InstallRoot

Write-Host "=== Aggiornamento Carbon Modbus 1.4 ===" -ForegroundColor Cyan
Write-Host "Root: $InstallRoot"
Write-Host "Vedi docs\AGGIORNAMENTO.md (poll 30s, hot-reload, lock istanza)"

# Termina eventuali poller orfani
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'modbus_poller' } |
  ForEach-Object {
    Write-Host "Stop processo orfano PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }


$venvPython = Join-Path $InstallRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "venv non trovato. Esegui prima scripts\install_client.ps1"
}

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "Arresto servizio $ServiceName ..."
    Stop-Service -Name $ServiceName -Force
    Start-Sleep -Seconds 2
}

Write-Host "pip install -r requirements.txt ..."
& $venvPython -m pip install -r (Join-Path $InstallRoot "requirements.txt")

$env:SERVICE_CONFIG = Join-Path $InstallRoot "file configurazione\service_config.xml"
Write-Host "Verifica config ..."
& $venvPython -c @"
from modbus_poller.config import load_settings
s = load_settings()
print('OK', s.modbus.device_name, '->', s.modbus.table_name)
print('poll', int(s.poll_interval_sec), 's | alarm read', int(s.alarm_interval_sec), 's (DB solo cambio stato)')
print('alarms', [p.code for p in s.modbus.alarm_points])
"@

if ($svc) {
    Write-Host "Avvio servizio $ServiceName ..."
    Start-Service -Name $ServiceName
    Get-Service -Name $ServiceName | Format-Table Name, Status -AutoSize
} else {
    Write-Host "Servizio '$ServiceName' non trovato: riavvia manualmente da Servy." -ForegroundColor Yellow
}

Write-Host "=== Aggiornamento completato ===" -ForegroundColor Green
