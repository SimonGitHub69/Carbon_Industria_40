@echo off
cd /d "%~dp0"
echo === Verifica dashboard ===
echo Cartella: %CD%
echo.

if not exist "dashboard\templates\index.html" (
  echo ERRORE: manca dashboard\templates\index.html
  echo Stai nella cartella sbagliata oppure lo zip non e' stato estratto qui.
  pause
  exit /b 1
)

findstr /C:"Tabella valori" "dashboard\templates\index.html" >nul
if errorlevel 1 (
  echo ERRORE: index.html VECCHIO - senza tabella.
  echo Estrai aggiornamento_1.7.8.zip in QUESTA cartella sovrascrivendo.
) else (
  echo OK: index.html contiene "Tabella valori"
)

findstr /C:"dashboard 1.7.8" "dashboard\templates\index.html" >nul
if errorlevel 1 (
  echo AVVISO: non trovo badge "dashboard 1.7.8"
) else (
  echo OK: versione template 1.7.8
)

echo.
echo File:
dir "dashboard\templates\index.html"
echo.
echo Se la dashboard e' avviata, apri anche:
echo   http://localhost:8080/api/version
echo Deve rispondere has_table: true e version: 1.7.8
echo.
pause
