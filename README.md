# Carbon Industria 4.0 — Servizio Modbus → PostgreSQL

Servizio Python (adatto a **Servy** su Windows) che:

1. Legge la mappa da `file configurazione/modbus_server_cella_frigo.xml`
2. Legge intervalli e DB da `file configurazione/service_config.xml`
3. Scrive su PostgreSQL:
   - temperature → `modbus_cella_frigo`
   - allarmi (solo cambio stato) → `modbus_cella_frigo_alarms`

## Intervalli (secondi)

In `service_config.xml`:

| Tag | Default | Significato |
|-----|---------|-------------|
| `poll_interval_sec` | `300` | Temperature / analogici (5 minuti) — sempre registrati |
| `alarm_interval_sec` | `60` | Frequenza **lettura** allarmi; su DB solo al **cambio di stato** |

## Mappa Modbus (file ufficiale)

Host: `192.168.75.220:502` · Unit **1** · Float **CDAB**

| Code | Addr | Tipo | Zona |
|------|------|------|------|
| `Sd` | 2 | float | Anticella |
| `dor` | 4 | coil | Anticella |
| `S_SONDA_2` | 5 | float | Cella −20 |
| `S_SONDA_3` | 7 | float | Cella −20 |
| `S_SONDA_VIRTUALE` | 9 | float | Cella −20 |
| `S_ALM_ALTA_TEMP` | 11 | coil | Cella −20 |
| `HI` | 12 | coil | Anticella |
| `SA` | 13 | float | Anticella |

## Installazione sul cliente (Windows Server 2025)

Guida completa: [`docs/INSTALL_WINDOWS_SERVER.md`](docs/INSTALL_WINDOWS_SERVER.md)  
Aggiornamenti: [`docs/AGGIORNAMENTO.md`](docs/AGGIORNAMENTO.md) · script `scripts\update_client.ps1`

```powershell
# Copia progetto in C:\Carbon_Industria_40 poi:
cd C:\Carbon_Industria_40
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_client.ps1
.\scripts\check_prerequisites.ps1
```

## Avvio manuale

```powershell
docker compose up -d   # oppure PostgreSQL nativo
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m modbus_poller
```

Oppure: `run_service.bat`

## Dashboard temperature (SA / S_SONDA_VIRTUALE)

```powershell
pip install -r requirements.txt
python -m dashboard
```

Apri http://localhost:8080 — server **Waitress** (produzione).  
Grafico di default; spunta **Mostra tabella valori** per la tabella; export Excel/CSV.  
Oppure: `run_dashboard.bat`  
Opzionale Servy: stessi path del poller, Process Parameters `-m dashboard`.

## Configurazione Servy (servizio Windows)

1. Installa [Servy](https://github.com/aelassas/servy) / Servy Manager
2. **New service**
3. Compila:
   - **Name:** `CarbonModbusCellaFrigo`
   - **Process path:**  
     `D:\Progetti\Carbon_Industria_40\.venv\Scripts\python.exe`
   - **Startup directory:**  
     `D:\Progetti\Carbon_Industria_40`
   - **Process arguments:**  
     `-m modbus_poller`
   - **Environment variables** (opzionale):  
     `SERVICE_CONFIG=D:\Progetti\Carbon_Industria_40\file configurazione\service_config.xml`
4. Startup type: Automatic  
5. Install / Start

In alternativa punta **Process path** a `run_service.bat` (meno preferibile: dipende da `cmd`).

### Secondo servizio — Dashboard (Waitress)

| Campo | Valore |
|-------|--------|
| Name | `CarbonDashboardCellaFrigo` |
| Process path | `...\Carbon_Industria_40\.venv\Scripts\python.exe` |
| Startup directory | `...\Carbon_Industria_40` |
| Process Parameters | `-m dashboard` |
| Env (opz.) | `SERVICE_CONFIG=...\file configurazione\service_config.xml` |

Startup: Automatic → Install → Start. Vedi anche `docs\SERVY_DASHBOARD.txt`.

Prima di avviare il servizio, chiudi `run_dashboard.bat` e altri processi `-m dashboard`.

Log: in Servy abilita cattura stdout/stderr, oppure controlla Event Viewer.

## Database

Tabelle create automaticamente:
- `modbus_cella_frigo` + vista `modbus_cella_frigo_latest` (temperature)
- `modbus_cella_frigo_alarms` + vista `modbus_cella_frigo_alarms_latest` (eventi)

```sql
SELECT * FROM modbus_cella_frigo_latest;
SELECT * FROM modbus_cella_frigo ORDER BY polled_at DESC LIMIT 50;

SELECT * FROM modbus_cella_frigo_alarms_latest;
SELECT point_code, previous_value, value_bool, changed_at
  FROM modbus_cella_frigo_alarms
 ORDER BY changed_at DESC LIMIT 50;
```


Credenziali in `service_config.xml` → sezione `<database>`.

## File di configurazione

```
file configurazione/
  modbus_server_cella_frigo.xml   ← mappa punti (export gateway)
  service_config.xml              ← intervalli, DB, host, ordine float
```
