#Requires -Version 5.1
<#
.SYNOPSIS
  Verifica rapida prerequisiti sul server cliente.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ModbusHost = "192.168.75.220",
    [int]$ModbusPort = 502,
    [string]$PgHost = "localhost",
    [int]$PgPort = 5432
)

$ErrorActionPreference = "Continue"
Write-Host "=== Check prerequisiti ===" -ForegroundColor Cyan

function Show-Result($ok, $msg) {
    if ($ok) { Write-Host "[OK]  $msg" -ForegroundColor Green }
    else { Write-Host "[NO]  $msg" -ForegroundColor Red }
}

$py = Get-Command python -ErrorAction SilentlyContinue
Show-Result ($null -ne $py) "Python nel PATH"
if ($py) { & python --version }

$venv = Join-Path $InstallRoot ".venv\Scripts\python.exe"
Show-Result (Test-Path $venv) "venv: $venv"

$cfg = Join-Path $InstallRoot "file configurazione\service_config.xml"
$map = Join-Path $InstallRoot "file configurazione\modbus_server_cella_frigo.xml"
Show-Result (Test-Path $cfg) "service_config.xml"
Show-Result (Test-Path $map) "modbus_server_cella_frigo.xml"

$tncM = Test-NetConnection -ComputerName $ModbusHost -Port $ModbusPort -WarningAction SilentlyContinue
Show-Result $tncM.TcpTestSucceeded "Modbus $ModbusHost`:$ModbusPort"

$tncP = Test-NetConnection -ComputerName $PgHost -Port $PgPort -WarningAction SilentlyContinue
Show-Result $tncP.TcpTestSucceeded "PostgreSQL $PgHost`:$PgPort"

if (Test-Path $venv) {
    Push-Location $InstallRoot
    $env:SERVICE_CONFIG = $cfg
    & $venv -c "from modbus_poller.config import load_settings; s=load_settings(); print('config OK ->', s.modbus.table_name)" 2>$null
    $ok = $LASTEXITCODE -eq 0
    Show-Result $ok "Caricamento config Python"
    Pop-Location
}

Write-Host "Fine check."
