# Aggiornamento — Carbon Modbus Cella Frigo

**Versione:** **1.7** — 2026-11-10  
Zip: `dist\aggiornamento_1.7.zip`

## Novità 1.7 — dashboard temperature

Dashboard web Flask + Chart.js con grafico **SA** (Anticella) e **S_SONDA_VIRTUALE** (Cella).

```powershell
# dopo estrazione + update_client
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python -m dashboard.app
# oppure: run_dashboard.bat
# Apri http://localhost:8080
```

## Novità 1.6 — tabella allarmi separata

| Tabella | Contenuto |
|---------|-----------|
| `modbus_cella_frigo` | Temperature (ogni `poll_interval_sec`) |
| `modbus_cella_frigo_alarms` | Eventi allarme **solo al cambio stato** (`previous_value` → `value_bool`) |

Viste: `modbus_cella_frigo_latest`, `modbus_cella_frigo_alarms_latest`

La tabella allarmi viene creata al primo avvio del poller. Gli stati precedenti in `modbus_cella_frigo` (point_kind=alarm) restano come storico; i nuovi eventi vanno solo in `*_alarms`.

## Sul server

```powershell
cd C:\Gestionale\Progetti\Carbon_Industria_40

# 1) Stop Servy + eventuali python orfani
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'modbus_poller' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2) Estrai aggiornamento_1.7.zip (sovrascrivi modbus_poller\, dashboard\, docs\, sql\, scripts\)

# 3) Verifica
.\.venv\Scripts\python.exe -m modbus_poller --show-config
.\.venv\Scripts\python.exe -m modbus_poller --diagnose
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4) Start Servy (Process Parameters: -m modbus_poller)
# 5) Opzionale dashboard: python -m dashboard.app  →  http://localhost:8080
```

## Query utili

```sql
SELECT * FROM modbus_cella_frigo_latest;
SELECT * FROM modbus_cella_frigo_alarms_latest;
```
