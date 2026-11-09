# Installazione cliente — Windows Server 2025

Guida per installare il servizio **Carbon Modbus → PostgreSQL** sul server del cliente.

## Architettura

```
[Gateway Modbus 192.168.75.220:502]
        ↑ TCP
[Windows Server 2025]
  ├─ Servizio Servy → python -m modbus_poller
  └─ PostgreSQL (locale o remoto)
```

## Checklist pre-installazione

| Voce | Note |
|------|------|
| Rete | Il server deve raggiungere `192.168.75.220` porta **502** (TCP) |
| Account | Accesso Administrator o installazione con elevazione |
| Cartella destinazione | Es. `C:\Carbon_Industria_40` |
| Password DB | Cambiare `carbon` in produzione |

## 1. Copia del software

Copiare l’intera cartella progetto (senza `.venv` e senza `__pycache__`) su:

```
C:\Carbon_Industria_40\
```

Struttura minima richiesta:

```
C:\Carbon_Industria_40\
  file configurazione\
    modbus_server_cella_frigo.xml
    service_config.xml
  modbus_poller\
  sql\
  requirements.txt
  run_service.bat
  scripts\install_client.ps1
```

## 2. Python 3.12+

1. Scaricare [Python 3.12 Windows 64-bit](https://www.python.org/downloads/windows/)
2. Installare con:
   - **Add python.exe to PATH**
   - **Install for all users** (consigliato su Server)
3. Verificare in PowerShell **come Administrator**:

```powershell
python --version
```

## 3. PostgreSQL 16

### Opzione A — Installazione nativa (consigliata in produzione)

1. Scaricare [PostgreSQL 16 Windows](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads)
2. Durante il setup:
   - Porta: `5432`
   - Password superuser `postgres`: annotarla
3. Aprire **pgAdmin** o `psql` e creare DB/utente:

```sql
CREATE USER carbon WITH PASSWORD 'CAMBIARE_PASSWORD';
CREATE DATABASE carbon_i40 OWNER carbon;
GRANT ALL PRIVILEGES ON DATABASE carbon_i40 TO carbon;
```

4. In `service_config.xml` aggiornare `<database>` con host/user/password reali.

### Opzione B — Docker (se Docker Engine è già sul server)

```powershell
cd C:\Carbon_Industria_40
docker compose up -d
```

## 4. Script di installazione automatica

Aprire PowerShell **come Administrator**:

```powershell
cd C:\Carbon_Industria_40
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_client.ps1
```

Lo script:

- crea il virtualenv `.venv`
- installa le dipendenze da `requirements.txt`
- verifica la presenza dei file XML di config
- esegue un test di avvio breve (opzionale)

## 5. Configurazione XML

### `file configurazione\service_config.xml`

```xml
<poll_interval_sec>300</poll_interval_sec>   <!-- temperature: 5 min -->
<alarm_interval_sec>30</alarm_interval_sec>  <!-- allarmi -->
<modbus_host>192.168.75.220</modbus_host>
```

Sezione database: host, porta, nome DB, user, password.

### `file configurazione\modbus_server_cella_frigo.xml`

Mappa punti ufficiale. Non modificare gli `addr`/`code` se non cambia il gateway.

## 6. Test manuale (prima del servizio)

```powershell
cd C:\Carbon_Industria_40
.\.venv\Scripts\Activate.ps1
python -m modbus_poller
```

Log attesi:

- connessione Modbus ok
- `Ciclo analog: … ok`
- `Ciclo alarm: … ok`

Arrestare con `Ctrl+C`.

Verifica DB:

```sql
SELECT * FROM modbus_cella_frigo_latest;
```

## 7. Firewall Windows

Sul **server** (uscita verso gateway):

```powershell
# Di solito l'outbound è già consentito; se bloccato:
New-NetFirewallRule -DisplayName "Modbus TCP out" -Direction Outbound `
  -Protocol TCP -RemoteAddress 192.168.75.220 -RemotePort 502 -Action Allow
```

Sul **gateway** / rete: assicurarsi che la porta 502 accetti connessioni dal server.

Test:

```powershell
Test-NetConnection 192.168.75.220 -Port 502
```

Deve risultare `TcpTestSucceeded : True`.

## 8. Servizio Windows con Servy

1. Installare [Servy](https://github.com/aelassas/servy/releases)
2. Creare un nuovo servizio:

| Campo Servy | Valore |
|-------------|--------|
| Name | `CarbonModbusCellaFrigo` |
| Display name | `Carbon Modbus Cella Frigo` |
| Process path | `C:\Carbon_Industria_40\.venv\Scripts\python.exe` |
| Startup directory | `C:\Carbon_Industria_40` |
| Arguments | `-m modbus_poller` |
| Startup type | Automatic |
| Env (opzionale) | `SERVICE_CONFIG=C:\Carbon_Industria_40\file configurazione\service_config.xml` |

3. Abilitare cattura **stdout/stderr** nei log Servy
4. Install → Start
5. Verificare in `services.msc` che il servizio sia **Running**

## 9. Account servizio

Consigliato: eseguire Servy con account che abbia:

- lettura sulla cartella `C:\Carbon_Industria_40`
- accesso rete al gateway Modbus
- accesso a PostgreSQL (localhost o remoto)

## 10. Manutenzione

| Operazione | Come |
|------------|------|
| Cambiare intervalli | Modificare `service_config.xml` → riavviare servizio |
| Aggiornare mappa punti | Sostituire `modbus_server_cella_frigo.xml` → riavviare |
| Aggiornare codice | Copiare file → `pip install -r requirements.txt` nel venv → riavviare |
| Log | Log Servy / Event Viewer |

## 11. Troubleshooting

| Sintomo | Verifica |
|---------|----------|
| Servizio si ferma subito | Log Servy: config XML, Python path, working directory |
| Nessun dato in DB | Credenziali PostgreSQL, tabella `modbus_cella_frigo` |
| Errori Modbus | `Test-NetConnection`, Unit ID 1, gateway Attivo |
| Float assurdi | `float_word_order` deve restare `cdab` |

## Riepilogo percorsi tipici cliente

```
App:     C:\Carbon_Industria_40
Python:  C:\Carbon_Industria_40\.venv\Scripts\python.exe
Config:  C:\Carbon_Industria_40\file configurazione\service_config.xml
Mappa:   C:\Carbon_Industria_40\file configurazione\modbus_server_cella_frigo.xml
DB:      localhost:5432 / carbon_i40
Tabella: modbus_cella_frigo
```
