# Carbon Industria 4.0 — Servizio Modbus → PostgreSQL

Servizio Python (adatto a **Servy** su Windows) che:

1. Legge la mappa da `file configurazione/modbus_server_cella_frigo.xml`
2. Legge intervalli e DB da `file configurazione/service_config.xml`
3. Scrive su PostgreSQL in una tabella dal **nome dispositivo** (`Modbus Cella frigo` → `modbus_cella_frigo`)

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

Log: in Servy abilita cattura stdout/stderr, oppure controlla Event Viewer.

## Database

Tabella creata automaticamente: `modbus_cella_frigo`  
Vista ultimi valori: `modbus_cella_frigo_latest`

```sql
SELECT * FROM modbus_cella_frigo_latest;
SELECT * FROM modbus_cella_frigo
 WHERE point_kind = 'analog'
 ORDER BY polled_at DESC LIMIT 50;
SELECT * FROM modbus_cella_frigo
 WHERE point_kind = 'alarm'
 ORDER BY polled_at DESC LIMIT 50;
```

Credenziali in `service_config.xml` → sezione `<database>`.

## File di configurazione

```
file configurazione/
  modbus_server_cella_frigo.xml   ← mappa punti (export gateway)
  service_config.xml              ← intervalli, DB, host, ordine float
```
