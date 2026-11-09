# Aggiornamento — Carbon Modbus Cella Frigo

**Data:** 2026-11-09  
**Versione:** 1.1  
**Destinazione:** Windows Server (Servy + PostgreSQL)

---

## Cosa cambia in questa versione

| Area | Dettaglio |
|------|-----------|
| Mappa Modbus | File ufficiale `modbus_server_cella_frigo.xml` (`SA` @ addr **13**) |
| Config servizio | Intervalli in `service_config.xml` (secondi) |
| Temperature | Registrazione periodica ogni `poll_interval_sec` (default **300** = 5 min) |
| Allarmi | Lettura ogni `alarm_interval_sec` (default **30**); **scrittura DB solo al cambio di stato** |
| Database | Tabella `modbus_cella_frigo` (nome da dispositivo) |
| Float | Ordine word **CDAB** |

### Allarmi — comportamento

- Punti: `dor`, `HI`, `S_ALM_ALTA_TEMP`
- Non vengono più salvati a ogni lettura
- Su PostgreSQL solo se cambia `ON/OFF` (o la quality)
- Al riavvio del servizio riprende l’ultimo stato dal DB

---

## File da copiare sul server

Sostituire nella cartella installazione (es. `C:\Carbon_Industria_40`):

```
modbus_poller\          ← tutto il package (obbligatorio)
file configurazione\
  modbus_server_cella_frigo.xml
  service_config.xml    ← solo se non hai custom locali; altrimenti unisci a mano
requirements.txt
run_service.bat
scripts\                ← opzionale ma consigliato
docs\
  AGGIORNAMENTO.md
  INSTALL_WINDOWS_SERVER.md
README.md
```

**Non sovrascrivere** se sul cliente hai già password/intervalli personalizzati:

- `file configurazione\service_config.xml` → confronta e aggiorna solo le sezioni nuove

**Non copiare:** `.venv`, `__pycache__`, `.git`

---

## Procedura di aggiornamento sul server

Aprire PowerShell **come Administrator**:

```powershell
cd C:\Carbon_Industria_40

# 1. Ferma il servizio Servy (CarbonModbusCellaFrigo) da Servy Manager o:
#    Stop-Service CarbonModbusCellaFrigo   # se registrato come servizio Windows

# 2. Copia i file aggiornati (da USB/rete) sopra quelli esistenti

# 3. Aggiorna dipendenze Python
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. Verifica config
.\.venv\Scripts\python.exe -c "from modbus_poller.config import load_settings; s=load_settings(); print(s.modbus.table_name, int(s.poll_interval_sec), int(s.alarm_interval_sec))"

# 5. Test breve (Ctrl+C dopo i primi log)
.\.venv\Scripts\python.exe -m modbus_poller

# 6. Riavvia il servizio Servy
```

Oppure usa lo script:

```powershell
.\scripts\update_client.ps1
```

---

## Verifica post-aggiornamento

```sql
-- Ultimi valori
SELECT * FROM modbus_cella_frigo_latest;

-- Solo cambi allarme (dovrebbero essere pochi)
SELECT point_code, value_bool, quality, polled_at
FROM modbus_cella_frigo
WHERE point_kind = 'alarm'
ORDER BY polled_at DESC
LIMIT 20;

-- Temperature (ogni ~5 min)
SELECT point_code, value_float, polled_at
FROM modbus_cella_frigo
WHERE point_kind = 'analog'
ORDER BY polled_at DESC
LIMIT 20;
```

In log servizio cerca:

- `solo cambio stato`
- `Allarme CAMBIO …` solo quando lo stato cambia
- `Ciclo analog: … ok`

---

## Config di riferimento (`service_config.xml`)

```xml
<poll_interval_sec>300</poll_interval_sec>
<alarm_interval_sec>30</alarm_interval_sec>
<float_word_order>cdab</float_word_order>
<modbus_host>192.168.75.220</modbus_host>
```

---

## Rollback

1. Ferma servizio  
2. Ripristina la cartella `modbus_poller` e gli XML dalla copia precedente  
3. Riavvia servizio  
