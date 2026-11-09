@echo off
REM Entry point per Servy / Task Scheduler
cd /d "%~dp0"
set "SERVICE_CONFIG=%~dp0file configurazione\service_config.xml"
"%~dp0.venv\Scripts\python.exe" -m modbus_poller
if errorlevel 1 exit /b 1
