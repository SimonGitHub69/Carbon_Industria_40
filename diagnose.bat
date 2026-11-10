@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m modbus_poller --diagnose
echo.
pause
