from __future__ import annotations

import logging
import time

from .client import ModbusReader
from .config import AppSettings, RegisterPoint
from .database import Database, Reading, utc_now

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
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
        self._db.connect()
        self._last_alarm_state = self._db.load_latest_alarm_states()
        if self._last_alarm_state:
            logger.info(
                "Stati allarme ripresi da DB: %s",
                ", ".join(
                    f"{k}={v[0]}" for k, v in sorted(self._last_alarm_state.items())
                ),
            )
        self._modbus.connect()
        logger.info(
            "Servizio avviato — tabella=%s | analog ogni %.0fs | allarmi ogni %.0fs (solo cambio stato) | mappa=%s",
            self._db.table_name,
            self._settings.poll_interval_sec,
            self._settings.alarm_interval_sec,
            self._settings.modbus_config_path,
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
                now = time.monotonic()
                if now >= next_analog:
                    self.poll_analog(cfg.analog_points)
                    next_analog = time.monotonic() + self._settings.poll_interval_sec
                if now >= next_alarm:
                    self.poll_alarms(cfg.alarm_points)
                    next_alarm = time.monotonic() + self._settings.alarm_interval_sec

                sleep_for = min(next_analog, next_alarm) - time.monotonic()
                time.sleep(max(0.2, sleep_for))
        except KeyboardInterrupt:
            logger.info("Arresto richiesto")
        finally:
            self._modbus.close()
            self._db.close()

    def poll_analog(self, points: tuple[RegisterPoint, ...]) -> None:
        readings = self._read_points(points, point_kind="analog")
        self._db.insert_readings(readings)
        good = sum(1 for r in readings if r.quality == "good")
        logger.info(
            "Ciclo analog: %d/%d ok @ %s → %s",
            good,
            len(readings),
            utc_now().isoformat(timespec="seconds"),
            self._db.table_name,
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
                    "Allarme CAMBIO %s: %s → %s (quality=%s)",
                    key,
                    previous[0] if previous else "(nessuno)",
                    reading.value_bool,
                    reading.quality,
                )

        if changed:
            self._db.insert_readings(changed)
            logger.info(
                "Ciclo alarm: %d cambio/i registrati @ %s → %s",
                len(changed),
                utc_now().isoformat(timespec="seconds"),
                self._db.table_name,
            )
        else:
            logger.debug(
                "Ciclo alarm: nessun cambio di stato (%d punti letti)",
                len(readings),
            )

    def _read_points(
        self, points: tuple[RegisterPoint, ...], point_kind: str
    ) -> list[Reading]:
        cfg = self._settings.modbus
        ts = utc_now()
        readings: list[Reading] = []

        for point in points:
            try:
                value = self._modbus.read_point(point)
                readings.append(
                    Reading(
                        device_name=cfg.device_name,
                        unit_id=cfg.unit_id,
                        cell_dev=point.cell_dev,
                        zone_name=point.zone,
                        point_code=point.code,
                        point_label=point.label,
                        register_addr=point.addr,
                        value_float=float(value) if point.kind == "float" else None,
                        value_bool=bool(value) if point.kind == "bool" else None,
                        point_kind=point_kind,
                        quality="good",
                        polled_at=ts,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Lettura fallita %s [%s] addr=%s: %s",
                    point.code,
                    point.zone,
                    point.addr,
                    exc,
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
                        quality=f"bad:{type(exc).__name__}",
                        polled_at=ts,
                    )
                )
        return readings
