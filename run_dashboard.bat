@echo off
cd /d "%~dp0"
set "SERVICE_CONFIG=%~dp0file configurazione\service_config.xml"
if not exist ".venv\Scripts\python.exe" (
  echo ERRORE: .venv non trovato. Esegui prima scripts\update_client.ps1
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import flask, waitress" 2>nul
if errorlevel 1 (
  echo Installo dipendenze dashboard...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
echo.
echo Dashboard produzione Waitress: http://localhost:8080
echo Lascia questa finestra aperta. CTRL+C per fermare.
echo.
".venv\Scripts\python.exe" -m dashboard
if errorlevel 1 (
  echo.
  echo Avvio fallito. Controlla PostgreSQL e service_config.xml
)
pause
