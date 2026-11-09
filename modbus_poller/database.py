from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


@dataclass
class Reading:
    device_name: str
    unit_id: int
    cell_dev: int
    zone_name: str
    point_code: str
    point_label: str
    register_addr: int
    value_float: float | None
    value_bool: bool | None
    point_kind: str  # analog | alarm
    quality: str
    polled_at: datetime


class Database:
    def __init__(self, database_url: str, table_name: str) -> None:
        self._url = database_url
        self._table = table_name
        self._conn: psycopg.Connection | None = None

    @property
    def table_name(self) -> str:
        return self._table

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
        idx_ts = sql.Identifier(f"idx_{self._table}_polled_at")
        idx_pt = sql.Identifier(f"idx_{self._table}_point")
        view = sql.Identifier(f"{self._table}_latest")

        stmts = [
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
                    value_bool    BOOLEAN,
                    point_kind    TEXT        NOT NULL DEFAULT 'analog',
                    quality       TEXT        NOT NULL DEFAULT 'good',
                    polled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(tbl=tbl),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (polled_at DESC)"
            ).format(idx=idx_ts, tbl=tbl),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (point_code, polled_at DESC)"
            ).format(idx=idx_pt, tbl=tbl),
            sql.SQL(
                """
                CREATE OR REPLACE VIEW {view} AS
                SELECT DISTINCT ON (point_code)
                    device_name, unit_id, cell_dev, zone_name,
                    point_code, point_label, register_addr,
                    value_float, value_bool, point_kind, quality, polled_at
                FROM {tbl}
                ORDER BY point_code, polled_at DESC
                """
            ).format(view=view, tbl=tbl),
        ]
        with self._conn.cursor() as cur:
            for stmt in stmts:
                cur.execute(stmt)
        self._conn.commit()

    def load_latest_alarm_states(self) -> dict[str, tuple[bool | None, str]]:
        """Ultimo value_bool/quality per ogni allarme (punto di ripartenza dopo restart)."""
        assert self._conn is not None
        query = sql.SQL(
            """
            SELECT DISTINCT ON (point_code)
                point_code, value_bool, quality
            FROM {tbl}
            WHERE point_kind = 'alarm'
            ORDER BY point_code, polled_at DESC
            """
        ).format(tbl=sql.Identifier(self._table))
        with self._conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        return {
            row["point_code"]: (row["value_bool"], row["quality"])
            for row in rows
        }

    def insert_readings(self, readings: list[Reading]) -> None:
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
                r.value_bool,
                r.point_kind,
                r.quality,
                r.polled_at,
            )
            for r in readings
        ]
        query = sql.SQL(
            """
            INSERT INTO {tbl} (
                device_name, unit_id, cell_dev, zone_name, point_code, point_label,
                register_addr, value_float, value_bool, point_kind, quality, polled_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        ).format(tbl=sql.Identifier(self._table))
        with self._conn.cursor() as cur:
            cur.executemany(query, rows)
        self._conn.commit()



def utc_now() -> datetime:
    return datetime.now(timezone.utc)
