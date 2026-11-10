#Requires -Version 5.1
<#
.SYNOPSIS
  Diagnostica perché il servizio Servy / poller non funziona.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Continue"
Set-Location $InstallRoot
Write-Host "=== Fix servizio Carbon Modbus ===" -ForegroundColor Cyan
Write-Host "Root: $InstallRoot"

$py = Join-Path $InstallRoot ".venv\Scripts\python.exe"
$cfg = Join-Path $InstallRoot "file configurazione\service_config.xml"
$lock = Join-Path $InstallRoot "file configurazione\.runtime\modbus_poller.pid"

# 1) Processi orfani
Write-Host "`n[1] Processi python modbus_poller..." -ForegroundColor Yellow
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'modbus_poller' }
if ($procs) {
  $procs | ForEach-Object {
    Write-Host "  STOP PID $($_.ProcessId) :: $($_.CommandLine)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
} else {
  Write-Host "  nessuno"
}

# 2) Lock file
Write-Host "`n[2] Lock file..." -ForegroundColor Yellow
if (Test-Path $lock) {
  Write-Host "  Rimuovo $lock"
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
} else {
  Write-Host "  assente (ok)"
}

# 3) File essenziali
Write-Host "`n[3] File essenziali..." -ForegroundColor Yellow
@(
  $py,
  $cfg,
  (Join-Path $InstallRoot "modbus_poller\__main__.py"),
  (Join-Path $InstallRoot "modbus_poller\instance_lock.py"),
  (Join-Path $InstallRoot "run_service.bat")
) | ForEach-Object {
  if (Test-Path $_) { Write-Host "  OK  $_" -ForegroundColor Green }
  else { Write-Host "  NO  $_" -ForegroundColor Red }
}

# 4) Show config + diagnose
Write-Host "`n[4] --show-config" -ForegroundColor Yellow
if (Test-Path $py) {
  & $py -m modbus_poller --show-config
  Write-Host "`n[5] --diagnose" -ForegroundColor Yellow
  & $py -m modbus_poller --diagnose
} else {
  Write-Host "venv python mancante — esegui scripts\install_client.ps1" -ForegroundColor Red
}

# 5) Servizi
Write-Host "`n[6] Servizi Windows..." -ForegroundColor Yellow
Get-Service *Carbon*, *Modbus*, *Servy* -ErrorAction SilentlyContinue |
  Format-Table Name, Status, DisplayName -AutoSize

Write-Host "`n=== Checklist Servy ===" -ForegroundColor Cyan
Write-Host "Process path:     $py"
Write-Host "Startup directory: $InstallRoot"
Write-Host "Arguments:        -m modbus_poller"
Write-Host "Oppure Process path = run_service.bat e Startup directory = root progetto"
Write-Host ""
Write-Host "Poi: Start del servizio e guarda log stdout/stderr in Servy Manager."
Write-Host "Se fallisce ancora, esegui a mano:"
Write-Host "  $py -m modbus_poller"
Write-Host "e copia l'errore."
