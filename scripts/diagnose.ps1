#Requires -Version 5.1
param([string]$InstallRoot = (Split-Path -Parent $PSScriptRoot))
Set-Location $InstallRoot
$py = Join-Path $InstallRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m modbus_poller.diagnose
exit $LASTEXITCODE
