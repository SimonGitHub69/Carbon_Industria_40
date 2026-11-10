from __future__ import annotations

import logging
import time

from .client import ModbusReader
from .config import AppSettings, RegisterPoint, load_intervals
from .database import Database, Reading, utc_now

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._poll_interval_sec = settings.poll_interval_sec
        self._alarm_interval_sec = settings.alarm_interval_sec
        self._db = Database(settings.database_url, settings.modbus.table_name)
        self._modbus = ModbusReader(
            settings.modbus,
            timeout=settings.modbus_timeout_sec,
            float_word_order=settings.float_word_order,
        )
        # point_code -> (value_bool, quality) — solo allarmi
        self._last_alarm_state: dict[str, tuple[bool | None, str]] = {}

    def start(self) -> None:
        cfg = self._settings.modbus
        self._wait_db()
        self._last_alarm_state = self._db.load_latest_alarm_states()
        if self._last_alarm_state:
            logger.info(
                "Stati allarme ripresi da DB: %s",
                ", ".join(
                    f"{k}={v[0]}" for k, v in sorted(self._last_alarm_state.items())
                ),
            )
        self._wait_modbus()
        logger.info(
            "Config file: %s",
            self._settings.service_config_path,
        )
        logger.info(
            "Servizio avviato — tabella=%s | analog ogni %.0fs | allarmi ogni %.0fs (solo cambio stato)",
            self._db.table_name,
            self._poll_interval_sec,
            self._alarm_interval_sec,
        )
        logger.info(
            "Punti: %d analog (%s), %d allarmi (%s)",
            len(cfg.analog_points),
            ", ".join(p.code for p in cfg.analog_points),
            len(cfg.alarm_points),
            ", ".join(p.code for p in cfg.alarm_points),
        )

        next_analog = 0.0
        next_alarm = 0.0
        try:
            while True:
                self._reload_intervals_if_changed()
                now = time.monotonic()
                if now >= next_analog:
                    self.poll_analog(cfg.analog_points)
                    next_analog = time.monotonic() + self._poll_interval_sec
                if now >= next_alarm:
                    self.poll_alarms(cfg.alarm_points)
                    next_alarm = time.monotonic() + self._alarm_interval_sec

                # Sleep lungo fino al prossimo ciclo (basso consumo CPU)
                sleep_for = min(next_analog, next_alarm) - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Arresto richiesto")
        finally:
            self._modbus.close()
            self._db.close()

    def _reload_intervals_if_changed(self) -> None:
        """Rilegge poll/alarm da XML senza riavviare il servizio."""
        try:
            poll, alarm = load_intervals(self._settings.service_config_path)
        except Exception as exc:
            logger.warning("Reload intervalli fallito: %s", exc)
            return
        if poll != self._poll_interval_sec or alarm != self._alarm_interval_sec:
            logger.info(
                "Intervalli aggiornati da file: analog %.0fs→%.0fs | alarm %.0fs→%.0fs",
                self._poll_interval_sec,
                poll,
                self._alarm_interval_sec,
                alarm,
            )
            self._poll_interval_sec = poll
            self._alarm_interval_sec = alarm


    def _wait_db(self) -> None:
        delay = 2.0
        while True:
            try:
                self._db.connect()
                logger.info("PostgreSQL connesso (%s)", self._db.table_name)
                return
            except Exception as exc:
                logger.error(
                    "PostgreSQL non disponibile: %s — riprovo tra %.0fs",
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay = min(60.0, delay * 2)

    def _wait_modbus(self) -> None:
        delay = 2.0
        while True:
            try:
                self._modbus.connect()
                return
            except Exception as exc:
                logger.error(
                    "Modbus non raggiungibile (%s:%s): %s — riprovo tra %.0fs",
                    self._settings.modbus.host,
                    self._settings.modbus.port,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay = min(60.0, delay * 2)

    def poll_analog(self, points: tuple[RegisterPoint, ...]) -> None:
        try:
            readings = self._read_points(points, point_kind="analog")
            self._db.insert_readings(readings)
        except Exception as exc:
            logger.error("Ciclo analog fallito: %s", exc)
            return
        good = sum(1 for r in readings if r.quality == "good")
        logger.info(
            "Ciclo analog: %d/%d ok → %s",
            good,
            len(readings),
            self._db.table_name,
        )
        if good == 0 and readings:
            logger.error(
                "Nessun valore analogico valido — controllare gateway Modbus / float_word_order"
            )

    def poll_alarms(self, points: tuple[RegisterPoint, ...]) -> None:
        """Legge i coil; scrive su DB solo se stato (valore o quality) è cambiato."""
        if not points:
            return
        readings = self._read_points(points, point_kind="alarm")
        changed: list[Reading] = []

        for reading in readings:
            key = reading.point_code
            state = (reading.value_bool, reading.quality)
            previous = self._last_alarm_state.get(key)
            if previous is None or previous != state:
                changed.append(reading)
                self._last_alarm_state[key] = state
                logger.info(
                    "Allarme CAMBIO %s: %s → %s",
                    key,
                    previous[0] if previous else "(nessuno)",
                    reading.value_bool,
                )

        if changed:
            self._db.insert_readings(changed)
            logger.info(
                "Ciclo alarm: %d cambio/i → %s",
                len(changed),
                self._db.table_name,
            )

    def _read_points(
        self, points: tuple[RegisterPoint, ...], point_kind: str
    ) -> list[Reading]:
        cfg = self._settings.modbus
        ts = utc_now()
        batch = self._modbus.read_points_batch(points)
        readings: list[Reading] = []

        for point in points:
            value = batch.get(point.code)
            if isinstance(value, BaseException):
                logger.warning(
                    "Lettura fallita %s addr=%s: %s",
                    point.code,
                    point.addr,
                    value,
                )
                readings.append(
                    Reading(
                        device_name=cfg.device_name,
                        unit_id=cfg.unit_id,
                        cell_dev=point.cell_dev,
                        zone_name=point.zone,
                        point_code=point.code,
                        point_label=point.label,
                        register_addr=point.addr,
                        value_float=None,
                        value_bool=None,
                        point_kind=point_kind,
                        quality=f"bad:{type(value).__name__}",
                        polled_at=ts,
                    )
                )
                continue

            if value is None:
                quality = "bad:Missing"
                value_float = None
                value_bool = None
            elif point.kind == "float":
                quality = "good"
                value_float = float(value)
                value_bool = None
            else:
                quality = "good"
                value_float = None
                value_bool = bool(value)

            readings.append(
                Reading(
                    device_name=cfg.device_name,
                    unit_id=cfg.unit_id,
                    cell_dev=point.cell_dev,
                    zone_name=point.zone,
                    point_code=point.code,
                    point_label=point.label,
                    register_addr=point.addr,
                    value_float=value_float,
                    value_bool=value_bool,
                    point_kind=point_kind,
                    quality=quality,
                    polled_at=ts,
                )
            )
        return readings
