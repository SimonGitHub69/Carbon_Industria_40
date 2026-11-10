@echo off
REM Entry point consigliato per Servy
cd /d "%~dp0"
set "SERVICE_CONFIG=%~dp0file configurazione\service_config.xml"

REM Rimuove lock stale se presente
if exist "%~dp0file configurazione\.runtime\modbus_poller.pid" (
  del /f /q "%~dp0file configurazione\.runtime\modbus_poller.pid" >nul 2>&1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo ERRORE: manca .venv\Scripts\python.exe
  exit /b 1
)

"%~dp0.venv\Scripts\python.exe" -m modbus_poller
set ERR=%ERRORLEVEL%
exit /b %ERR%
