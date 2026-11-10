from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


@dataclass
class AnalogReading:
    device_name: str
    unit_id: int
    cell_dev: int
    zone_name: str
    point_code: str
    point_label: str
    register_addr: int
    value_float: float | None
    quality: str
    polled_at: datetime


@dataclass
class AlarmEvent:
    device_name: str
    unit_id: int
    cell_dev: int
    zone_name: str
    point_code: str
    point_label: str
    register_addr: int
    previous_value: bool | None
    value_bool: bool | None
    quality: str
    changed_at: datetime


# Retrocompatibilità nomi usati dal poller precedente
Reading = AnalogReading


class Database:
    def __init__(self, database_url: str, table_name: str) -> None:
        self._url = database_url
        self._table = table_name  # analog: modbus_cella_frigo
        self._alarms_table = f"{table_name}_alarms"
        self._conn: psycopg.Connection | None = None

    @property
    def table_name(self) -> str:
        return self._table

    @property
    def alarms_table_name(self) -> str:
        return self._alarms_table

    def connect(self) -> None:
        self._conn = psycopg.connect(self._url, row_factory=dict_row)
        self._conn.autocommit = False
        self.ensure_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def ensure_schema(self) -> None:
        assert self._conn is not None
        tbl = sql.Identifier(self._table)
        alarms = sql.Identifier(self._alarms_table)
        idx_ts = sql.Identifier(f"idx_{self._table}_polled_at")
        idx_pt = sql.Identifier(f"idx_{self._table}_point")
        view = sql.Identifier(f"{self._table}_latest")
        idx_a_ts = sql.Identifier(f"idx_{self._alarms_table}_changed_at")
        idx_a_pt = sql.Identifier(f"idx_{self._alarms_table}_point")
        view_a = sql.Identifier(f"{self._alarms_table}_latest")

        # 1) Tabelle prima (non dipendono dalle view)
        table_stmts = [
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {tbl} (
                    id            BIGSERIAL PRIMARY KEY,
                    device_name   TEXT        NOT NULL,
                    unit_id       INTEGER     NOT NULL,
                    cell_dev      INTEGER     NOT NULL,
                    zone_name     TEXT        NOT NULL DEFAULT '',
                    point_code    TEXT        NOT NULL,
                    point_label   TEXT        NOT NULL DEFAULT '',
                    register_addr INTEGER     NOT NULL,
                    value_float   DOUBLE PRECISION,
                    quality       TEXT        NOT NULL DEFAULT 'good',
                    polled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(tbl=tbl),
            sql.SQL(
                "ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS value_bool BOOLEAN"
            ).format(tbl=tbl),
            sql.SQL(
                "ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS point_kind TEXT DEFAULT 'analog'"
            ).format(tbl=tbl),
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {alarms} (
                    id             BIGSERIAL PRIMARY KEY,
                    device_name    TEXT        NOT NULL,
                    unit_id        INTEGER     NOT NULL,
                    cell_dev       INTEGER     NOT NULL,
                    zone_name      TEXT        NOT NULL DEFAULT '',
                    point_code     TEXT        NOT NULL,
                    point_label    TEXT        NOT NULL DEFAULT '',
                    register_addr  INTEGER     NOT NULL,
                    previous_value BOOLEAN,
                    value_bool     BOOLEAN,
                    quality        TEXT        NOT NULL DEFAULT 'good',
                    changed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(alarms=alarms),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (polled_at DESC)"
            ).format(idx=idx_ts, tbl=tbl),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (point_code, polled_at DESC)"
            ).format(idx=idx_pt, tbl=tbl),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {alarms} (changed_at DESC)"
            ).format(idx=idx_a_ts, alarms=alarms),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {alarms} (point_code, changed_at DESC)"
            ).format(idx=idx_a_pt, alarms=alarms),
        ]
        with self._conn.cursor() as cur:
            for stmt in table_stmts:
                cur.execute(stmt)
        self._conn.commit()

        # 2) View: DROP + CREATE (REPLACE fallisce se cambiano le colonne)
        view_stmts = [
            sql.SQL("DROP VIEW IF EXISTS {view} CASCADE").format(view=view),
            sql.SQL(
                """
                CREATE VIEW {view} AS
                SELECT DISTINCT ON (point_code)
                    device_name, unit_id, cell_dev, zone_name,
                    point_code, point_label, register_addr,
                    value_float, quality, polled_at
                FROM {tbl}
                WHERE COALESCE(point_kind, 'analog') <> 'alarm'
                ORDER BY point_code, polled_at DESC
                """
            ).format(view=view, tbl=tbl),
            sql.SQL("DROP VIEW IF EXISTS {view} CASCADE").format(view=view_a),
            sql.SQL(
                """
                CREATE VIEW {view} AS
                SELECT DISTINCT ON (point_code)
                    device_name, unit_id, cell_dev, zone_name,
                    point_code, point_label, register_addr,
                    previous_value, value_bool, quality, changed_at
                FROM {alarms}
                ORDER BY point_code, changed_at DESC
                """
            ).format(view=view_a, alarms=alarms),
        ]
        with self._conn.cursor() as cur:
            for stmt in view_stmts:
                cur.execute(stmt)
        self._conn.commit()


    def load_latest_alarm_states(self) -> dict[str, tuple[bool | None, str]]:
        """Ultimo stato allarme: prima dalla tabella eventi, poi fallback legacy."""
        assert self._conn is not None
        query_new = sql.SQL(
            """
            SELECT DISTINCT ON (point_code)
                point_code, value_bool, quality
            FROM {alarms}
            ORDER BY point_code, changed_at DESC
            """
        ).format(alarms=sql.Identifier(self._alarms_table))
        with self._conn.cursor() as cur:
            cur.execute(query_new)
            rows = cur.fetchall()
        if rows:
            return {
                row["point_code"]: (row["value_bool"], row["quality"])
                for row in rows
            }

        # Fallback: vecchi allarmi ancora nella tabella unica
        query_legacy = sql.SQL(
            """
            SELECT DISTINCT ON (point_code)
                point_code, value_bool, quality
            FROM {tbl}
            WHERE point_kind = 'alarm'
            ORDER BY point_code, polled_at DESC
            """
        ).format(tbl=sql.Identifier(self._table))
        try:
            with self._conn.cursor() as cur:
                cur.execute(query_legacy)
                rows = cur.fetchall()
            return {
                row["point_code"]: (row["value_bool"], row["quality"])
                for row in rows
            }
        except Exception:
            self._conn.rollback()
            return {}

    def insert_analog_readings(self, readings: list[AnalogReading]) -> None:
        if not readings:
            return
        assert self._conn is not None
        rows = [
            (
                r.device_name,
                r.unit_id,
                r.cell_dev,
                r.zone_name,
                r.point_code,
                r.point_label,
                r.register_addr,
                r.value_float,
                r.quality,
                r.polled_at,
            )
            for r in readings
        ]
        query = sql.SQL(
            """
            INSERT INTO {tbl} (
                device_name, unit_id, cell_dev, zone_name, point_code, point_label,
                register_addr, value_float, quality, polled_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        ).format(tbl=sql.Identifier(self._table))
        with self._conn.cursor() as cur:
            cur.executemany(query, rows)
        self._conn.commit()

    def insert_alarm_events(self, events: list[AlarmEvent]) -> None:
        if not events:
            return
        assert self._conn is not None
        rows = [
            (
                e.device_name,
                e.unit_id,
                e.cell_dev,
                e.zone_name,
                e.point_code,
                e.point_label,
                e.register_addr,
                e.previous_value,
                e.value_bool,
                e.quality,
                e.changed_at,
            )
            for e in events
        ]
        query = sql.SQL(
            """
            INSERT INTO {alarms} (
                device_name, unit_id, cell_dev, zone_name, point_code, point_label,
                register_addr, previous_value, value_bool, quality, changed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        ).format(alarms=sql.Identifier(self._alarms_table))
        with self._conn.cursor() as cur:
            cur.executemany(query, rows)
        self._conn.commit()

    # Alias legacy
    def insert_readings(self, readings: list[AnalogReading]) -> None:
        self.insert_analog_readings(readings)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
