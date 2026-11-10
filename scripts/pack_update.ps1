#Requires -Version 5.1
<#
.SYNOPSIS
  Crea lo zip di aggiornamento da copiare sul server cliente.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Version = "1.7"
)

$ErrorActionPreference = "Stop"
Set-Location $InstallRoot

$dist = Join-Path $InstallRoot "dist"
$stage = Join-Path $dist "aggiornamento_$Version"
$zip = Join-Path $dist "aggiornamento_$Version.zip"

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null

$items = @(
    "modbus_poller",
    "dashboard",
    "file configurazione",
    "scripts",
    "docs",
    "sql",
    "requirements.txt",
    "run_service.bat",
    "run_dashboard.bat",
    "verifica_dashboard.bat",
    "AGGIORNA_DASHBOARD.txt",
    "diagnose.bat",

    "README.md",
    "docker-compose.yml",
    ".env.example",
    ".gitignore"
)

foreach ($item in $items) {
    $src = Join-Path $InstallRoot $item
    if (-not (Test-Path $src)) {
        Write-Warning "Mancante (skip): $item"
        continue
    }
    $dst = Join-Path $stage $item
    if (Test-Path $src -PathType Container) {
        Copy-Item $src $dst -Recurse -Force
    } else {
        $parent = Split-Path $dst -Parent
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item $src $dst -Force
    }
}

# Rimuovi cache Python dallo stage
Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

Copy-Item (Join-Path $InstallRoot "docs\AGGIORNAMENTO.md") (Join-Path $stage "LEGGIMI_AGGIORNAMENTO.md") -Force

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force

Write-Host "OK zip creato:" -ForegroundColor Green
Write-Host "  $zip"
Write-Host ""
Write-Host "Sul server: estrai in C:\Carbon_Industria_40 (sovrascrivi), poi:"
Write-Host "  .\scripts\update_client.ps1"
Write-Host "Vedi LEGGIMI_AGGIORNAMENTO.md / docs\AGGIORNAMENTO.md"
