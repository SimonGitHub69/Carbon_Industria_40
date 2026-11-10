"""Diagnostica rapida: python -m modbus_poller.diagnose"""

from __future__ import annotations

import sys

from .client import ModbusReader
from .config import load_settings
from .database import Database


def main() -> int:
    print("=== Diagnostica Carbon Modbus ===")
    try:
        s = load_settings()
    except Exception as exc:
        print(f"Config FAIL: {exc}")
        return 1

    print("Config OK")
    print(f"  Modbus: {s.modbus.host}:{s.modbus.port} unit={s.modbus.unit_id}")
    print(f"  Table : {s.modbus.table_name}")
    print(
        f"  Poll  : analog {int(s.poll_interval_sec)}s / alarm {int(s.alarm_interval_sec)}s"
    )

    print("\n1) Test Modbus TCP...")
    reader = ModbusReader(s.modbus, s.modbus_timeout_sec, s.float_word_order)
    try:
        reader.connect()
        batch = reader.read_points_batch(s.modbus.analog_points + s.modbus.alarm_points)
        ok = 0
        for code, value in batch.items():
            if isinstance(value, BaseException):
                print(f"  FAIL {code}: {value}")
            else:
                print(f"  OK   {code}: {value}")
                ok += 1
        print(f"Modbus: {ok}/{len(batch)} punti letti")
    except Exception as exc:
        print(f"Modbus FAIL: {type(exc).__name__}: {exc}")
        print("  -> Gateway acceso? IP corretto? Firewall?")
        print("  -> Test-NetConnection", s.modbus.host, "-Port", s.modbus.port)
        return 2
    finally:
        reader.close()

    print("\n2) Test PostgreSQL...")
    try:
        db = Database(s.database_url, s.modbus.table_name)
        db.connect()
        assert db._conn is not None
        with db._conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            print("  Connect OK")
            cur.execute(f"SELECT COUNT(*) AS n FROM {s.modbus.table_name}")
            n = cur.fetchone()["n"]
            print(f"  Tabella {s.modbus.table_name}: {n} righe")
            cur.execute(
                f"""
                SELECT point_code, value_float, value_bool, quality, polled_at
                FROM {s.modbus.table_name}
                ORDER BY polled_at DESC LIMIT 5
                """
            )
            rows = cur.fetchall()
            if not rows:
                print("  (nessun dato ancora)")
            for row in rows:
                print(" ", dict(row))
        db.close()
        print("PostgreSQL OK")
    except Exception as exc:
        print(f"PostgreSQL FAIL: {type(exc).__name__}: {exc}")
        print("  -> create_postgres_db.ps1 oppure password in service_config.xml")
        return 3

    print("\nTutto OK: il poller dovrebbe leggere e scrivere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
