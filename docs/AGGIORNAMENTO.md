# Aggiornamento — Carbon Modbus Cella Frigo

**Data:** 2026-11-10  
**Versione:** **1.4**  
**Destinazione:** Windows Server (`C:\Gestionale\Progetti\Carbon_Industria_40`)

Zip: `dist\aggiornamento_1.4.zip`

---

## Cosa include la 1.4

| Area | Dettaglio |
|------|-----------|
| Intervallo analog | Default **30** secondi (`poll_interval_sec`) |
| Hot-reload | Cambio intervalli nel XML **senza** riavviare (al ciclo successivo) |
| Config | `python -m modbus_poller --show-config` mostra file e valori usati |
| Diagnostica | `python -m modbus_poller --diagnose` / `diagnose.bat` |
| Lock istanza | Evita doppio poller se il servizio è stoppato ma python resta vivo |
| Retry | DB/Modbus assenti → ritenta con log |
| CPU | Sleep lungo + letture Modbus batch |
| Allarmi | Lettura ogni 60 s; DB **solo al cambio stato** |

---

## File da copiare (obbligatori)

Estrarre lo zip **sopra** `C:\Gestionale\Progetti\Carbon_Industria_40` oppure copiare:

```
modbus_poller\          ← tutto (include instance_lock.py, diagnose.py, …)
file configurazione\
  service_config.xml    ← ATTENZIONE password: vedi sotto
  modbus_server_cella_frigo.xml
requirements.txt
run_service.bat
diagnose.bat
scripts\
docs\AGGIORNAMENTO.md
```

### `service_config.xml` — non perdere la password DB

Se in produzione la password non è più `carbon`:

1. **Non** sovrascrivere tutto il file, **oppure**
2. Dopo la copia, rimetti user/password corretti e lascia:

```xml
<poll_interval_sec>30</poll_interval_sec>
<alarm_interval_sec>60</alarm_interval_sec>
```

---

## Procedura sul server

### 0) Ferma eventuali processi orfani

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'modbus_poller' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Killed" $_.ProcessId }
```

In Servy: **Stop** su `CarbonModbusCellaFrigo`.

### 1) Copia / estrai aggiornamento 1.4

### 2) Verifica config

```powershell
cd C:\Gestionale\Progetti\Carbon_Industria_40
.\.venv\Scripts\python.exe -m modbus_poller --show-config
```

Atteso:
```
poll_interval  = 30 sec
alarm_interval = 60 sec
service_config = C:\Gestionale\Progetti\Carbon_Industria_40\file configurazione\service_config.xml
```

### 3) Diagnostica

```powershell
.\.venv\Scripts\python.exe -m modbus_poller --diagnose
```

Deve dare Modbus 8/8 e PostgreSQL OK.

### 4) (Opzionale) update pip + servizio

```powershell
.\scripts\update_client.ps1
```

Oppure riavvia solo da **Servy Manager**.

### 5) Controlla log Servy

All’avvio deve comparire:
```
analog ogni 30s | allarmi ogni 60s
Config file: C:\Gestionale\...\service_config.xml
Instance lock: ...\file configurazione\.runtime\modbus_poller.pid
```

---

## Se “legge ancora” con servizio stoppato

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'modbus_poller' } |
  Select-Object ProcessId, CommandLine
```

Termina i PID trovati (passo 0). Con la 1.4 una seconda istanza non parte (lock).

---

## Rollback

1. Stop servizio + kill python orfani  
2. Ripristina `modbus_poller\` e XML dalla copia precedente  
3. Start servizio  
