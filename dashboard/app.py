"""Dashboard temperature SA / S_SONDA_VIRTUALE — Flask + Chart.js."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from psycopg.rows import dict_row
import psycopg

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modbus_poller.config import load_settings  # noqa: E402

app = Flask(__name__)

DASHBOARD_VERSION = "1.7.8"

POINTS = ("SA", "S_SONDA_VIRTUALE")
LABELS = {
    "SA": "Anticella SA (°C)",
    "S_SONDA_VIRTUALE": "Cella virtual (°C)",
}
LOCAL_TZ = ZoneInfo("Europe/Rome")
# Limite soft: oltre questa soglia si aggrega per intervallo (range completo).
MAX_RAW_POINTS = 12_000
# Limite assoluto di sicurezza.
HARD_MAX_POINTS = 100_000

_SAFE_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _db_url() -> str:
    return load_settings().database_url


def _table() -> str:
    name = load_settings().modbus.table_name
    if not _SAFE_TABLE.match(name):
        raise ValueError(f"Nome tabella non valido: {name!r}")
    return name


def _parse_dt(raw: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Accetta ISO, datetime-local HTML, o solo data YYYY-MM-DD (fuso Europe/Rome)."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        base = datetime.fromisoformat(s).replace(tzinfo=LOCAL_TZ)
        if end_of_day:
            return base.replace(hour=23, minute=59, second=59, microsecond=999999)
        return base
    if "T" not in s and " " in s:
        s = s.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"Data/ora non valida: {raw!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt


def _bucket_seconds(span: timedelta, approx_points: int = 4000) -> int:
    total = max(span.total_seconds(), 1.0)
    step = int(total / approx_points)
    for candidate in (
        30,
        60,
        120,
        300,
        600,
        900,
        1800,
        3600,
        7200,
        14400,
        21600,
        43200,
        86400,
    ):
        if step <= candidate:
            return candidate
    return 86400


def _resolve_range() -> tuple[datetime, datetime, float | None]:
    """Restituisce (from_utc, to_utc, hours|None) dai query params."""
    dt_from = _parse_dt(request.args.get("from"), end_of_day=False)
    dt_to = _parse_dt(request.args.get("to"), end_of_day=True)

    hours: float | None = None
    if dt_from is None and dt_to is None:
        hours = float(request.args.get("hours", "6"))
        hours = max(0.25, min(hours, 24 * 365))
        dt_to = datetime.now(timezone.utc)
        dt_from = dt_to - timedelta(hours=hours)
    elif dt_from is None:
        assert dt_to is not None
        dt_from = dt_to - timedelta(days=7)
    elif dt_to is None:
        dt_to = datetime.now(timezone.utc)

    assert dt_from is not None and dt_to is not None
    if dt_to < dt_from:
        raise ValueError("La data 'a' deve essere >= 'da'")

    return dt_from.astimezone(timezone.utc), dt_to.astimezone(timezone.utc), hours


def _fetch_export_rows(
    table: str, dt_from: datetime, dt_to: datetime, *, limit: int = HARD_MAX_POINTS
) -> tuple[list[dict], bool]:
    """Righe pivot SA / S_SONDA_VIRTUALE per export (valori grezzi)."""
    with psycopg.connect(_db_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  polled_at,
                  MAX(value_float) FILTER (WHERE point_code = 'SA') AS sa,
                  MAX(value_float) FILTER (WHERE point_code = 'S_SONDA_VIRTUALE') AS sonda
                FROM {table}
                WHERE point_code = ANY(%s)
                  AND value_float IS NOT NULL
                  AND polled_at >= %s
                  AND polled_at <= %s
                GROUP BY polled_at
                ORDER BY polled_at ASC
                LIMIT %s
                """,
                (list(POINTS), dt_from, dt_to, limit + 1),
            )
            rows = cur.fetchall()
    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]
    return rows, truncated


@app.route("/")
def index():
    resp = app.make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/bounds")
def api_bounds():
    """Primo/ultimo campione disponibile per SA e S_SONDA_VIRTUALE."""
    table = _table()
    try:
        with psycopg.connect(_db_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                      MIN(polled_at) AS first_at,
                      MAX(polled_at) AS last_at,
                      COUNT(*)::bigint AS n
                    FROM {table}
                    WHERE point_code = ANY(%s)
                      AND value_float IS NOT NULL
                    """,
                    (list(POINTS),),
                )
                row = cur.fetchone() or {}
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    first_at = row.get("first_at")
    last_at = row.get("last_at")
    return jsonify(
        {
            "ok": True,
            "table": table,
            "count": int(row.get("n") or 0),
            "first_at": first_at.isoformat() if first_at else None,
            "last_at": last_at.isoformat() if last_at else None,
            "tz": "Europe/Rome",
        }
    )


@app.route("/api/series")
def api_series():
    """Serie temporali SA e S_SONDA_VIRTUALE.

    Parametri:
      - from / to : intervallo completo (ISO o YYYY-MM-DD[THH:MM])
      - hours     : scorciatoia relative alle ultime N ore (se from/to assenti)
      - raw=1     : forza punti grezzi (fino a HARD_MAX_POINTS)
    """
    table = _table()
    force_raw = request.args.get("raw", "0") in ("1", "true", "yes")

    try:
        dt_from, dt_to, hours = _resolve_range()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    span = dt_to - dt_from

    series: dict[str, list[dict]] = {p: [] for p in POINTS}
    latest: dict[str, float | None] = {p: None for p in POINTS}
    stats: dict[str, dict] = {
        p: {"count": 0, "min": None, "max": None, "avg": None} for p in POINTS
    }
    mode = "raw"
    bucket_sec = None
    truncated = False

    try:
        with psycopg.connect(_db_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT point_code, COUNT(*)::bigint AS n
                    FROM {table}
                    WHERE point_code = ANY(%s)
                      AND value_float IS NOT NULL
                      AND polled_at >= %s
                      AND polled_at <= %s
                    GROUP BY point_code
                    """,
                    (list(POINTS), dt_from, dt_to),
                )
                counts = {r["point_code"]: int(r["n"]) for r in cur.fetchall()}
                total = sum(counts.values())

                use_bucket = (not force_raw and total > MAX_RAW_POINTS) or (
                    force_raw and total > HARD_MAX_POINTS
                )
                if force_raw and total > HARD_MAX_POINTS:
                    truncated = True

                if use_bucket and not (force_raw and total <= HARD_MAX_POINTS):
                    mode = "bucket"
                    bucket_sec = _bucket_seconds(span)
                    cur.execute(
                        f"""
                        SELECT
                          point_code,
                          to_timestamp(
                            floor(extract(epoch FROM polled_at) / %s) * %s
                          ) AS bucket_at,
                          AVG(value_float) AS value_float,
                          MIN(value_float) AS v_min,
                          MAX(value_float) AS v_max,
                          COUNT(*)::bigint AS n
                        FROM {table}
                        WHERE point_code = ANY(%s)
                          AND value_float IS NOT NULL
                          AND polled_at >= %s
                          AND polled_at <= %s
                        GROUP BY point_code, 2
                        ORDER BY 2 ASC
                        """,
                        (bucket_sec, bucket_sec, list(POINTS), dt_from, dt_to),
                    )
                    for row in cur.fetchall():
                        code = row["point_code"]
                        if code not in series:
                            continue
                        ts = row["bucket_at"]
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        val = round(float(row["value_float"]), 2)
                        series[code].append({"t": ts.isoformat(), "v": val})
                        latest[code] = val
                        st = stats[code]
                        st["count"] += int(row["n"])
                        vmin = float(row["v_min"])
                        vmax = float(row["v_max"])
                        st["min"] = vmin if st["min"] is None else min(st["min"], vmin)
                        st["max"] = vmax if st["max"] is None else max(st["max"], vmax)
                else:
                    limit = HARD_MAX_POINTS if force_raw else MAX_RAW_POINTS
                    cur.execute(
                        f"""
                        SELECT point_code, value_float, polled_at
                        FROM {table}
                        WHERE point_code = ANY(%s)
                          AND value_float IS NOT NULL
                          AND polled_at >= %s
                          AND polled_at <= %s
                        ORDER BY polled_at ASC
                        LIMIT %s
                        """,
                        (list(POINTS), dt_from, dt_to, limit + 1),
                    )
                    rows = cur.fetchall()
                    if len(rows) > limit:
                        truncated = True
                        rows = rows[:limit]
                    sums: dict[str, float] = {p: 0.0 for p in POINTS}
                    for row in rows:
                        code = row["point_code"]
                        if code not in series:
                            continue
                        ts = row["polled_at"]
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        val = round(float(row["value_float"]), 2)
                        series[code].append({"t": ts.isoformat(), "v": val})
                        latest[code] = val
                        st = stats[code]
                        st["count"] += 1
                        st["min"] = val if st["min"] is None else min(st["min"], val)
                        st["max"] = val if st["max"] is None else max(st["max"], val)
                        sums[code] += float(row["value_float"])

                    for code in POINTS:
                        if stats[code]["count"]:
                            stats[code]["avg"] = round(
                                sums[code] / stats[code]["count"], 2
                            )

                # Completa avg anche in modalità bucket
                if mode == "bucket":
                    for code in POINTS:
                        pts = series[code]
                        if pts:
                            stats[code]["avg"] = round(
                                sum(p["v"] for p in pts) / len(pts), 2
                            )
                            if stats[code]["min"] is not None:
                                stats[code]["min"] = round(stats[code]["min"], 2)
                            if stats[code]["max"] is not None:
                                stats[code]["max"] = round(stats[code]["max"], 2)
                else:
                    for code in POINTS:
                        if stats[code]["min"] is not None:
                            stats[code]["min"] = round(stats[code]["min"], 2)
                        if stats[code]["max"] is not None:
                            stats[code]["max"] = round(stats[code]["max"], 2)

    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "hours": hours,
            "from": dt_from.isoformat(),
            "to": dt_to.isoformat(),
            "mode": mode,
            "bucket_sec": bucket_sec,
            "truncated": truncated,
            "labels": LABELS,
            "latest": latest,
            "stats": stats,
            "series": series,
            "table": table,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.route("/api/export.xlsx")
def api_export_xlsx():
    """Esporta SA / S_SONDA_VIRTUALE in Excel per il periodo selezionato."""
    table = _table()
    try:
        dt_from, dt_to, hours = _resolve_range()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    try:
        rows, truncated = _fetch_export_rows(table, dt_from, dt_to)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    wb = Workbook()
    ws = wb.active
    ws.title = "Temperature"

    header_font = Font(bold=True)
    headers = [
        "#",
        "Data/ora (Europe/Rome)",
        "SA (°C)",
        "S_SONDA_VIRTUALE (°C)",
        "Delta SA-Sonda (°C)",
    ]
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font

    for i, row in enumerate(rows, start=1):
        ts = row["polled_at"]
        if ts is not None and getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local_ts = ts.astimezone(LOCAL_TZ) if ts is not None else None
        sa = float(row["sa"]) if row["sa"] is not None else None
        sonda = float(row["sonda"]) if row["sonda"] is not None else None
        delta = (sa - sonda) if sa is not None and sonda is not None else None

        ws.cell(row=i + 1, column=1, value=i)
        cell_dt = ws.cell(
            row=i + 1,
            column=2,
            value=local_ts.replace(tzinfo=None) if local_ts else None,
        )
        cell_dt.number_format = "DD/MM/YYYY HH:MM:SS"
        cell_dt.alignment = Alignment(horizontal="left")
        if sa is not None:
            c = ws.cell(row=i + 1, column=3, value=round(sa, 2))
            c.number_format = "0.00"
        if sonda is not None:
            c = ws.cell(row=i + 1, column=4, value=round(sonda, 2))
            c.number_format = "0.00"
        if delta is not None:
            c = ws.cell(row=i + 1, column=5, value=round(delta, 2))
            c.number_format = "0.00"

    for col, width in enumerate((6, 24, 12, 22, 18), start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    meta = wb.create_sheet("Info", 0)
    meta["A1"] = "Export temperature cella frigo"
    meta["A1"].font = Font(bold=True)
    meta["A3"] = "Tabella"
    meta["B3"] = table
    meta["A4"] = "Da (UTC)"
    meta["B4"] = dt_from.isoformat()
    meta["A5"] = "A (UTC)"
    meta["B5"] = dt_to.isoformat()
    meta["A6"] = "Da (Europe/Rome)"
    meta["B6"] = dt_from.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M:%S")
    meta["A7"] = "A (Europe/Rome)"
    meta["B7"] = dt_to.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M:%S")
    meta["A8"] = "Ore (scorciatoia)"
    meta["B8"] = hours if hours is not None else ""
    meta["A9"] = "Righe"
    meta["B9"] = len(rows)
    meta["A10"] = "Troncato"
    meta["B10"] = "SI" if truncated else "NO"
    meta["A11"] = "Generato"
    meta["B11"] = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y %H:%M:%S")
    meta.column_dimensions["A"].width = 22
    meta.column_dimensions["B"].width = 36

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    stamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"temperature_cella_{stamp}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/version")
def api_version():
    tpl = Path(__file__).resolve().parent / "templates" / "index.html"
    text = tpl.read_text(encoding="utf-8", errors="ignore") if tpl.exists() else ""
    return jsonify(
        {
            "ok": True,
            "version": DASHBOARD_VERSION,
            "template": str(tpl),
            "has_table": "Tabella valori" in text,
            "cwd": str(Path.cwd()),
        }
    )


@app.route("/api/health")
def health():
    try:
        with psycopg.connect(_db_url()) as conn:
            conn.execute("SELECT 1")
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def main() -> None:
    """Avvio produzione con Waitress (WSGI), adatto a Windows Server / Servy."""
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    threads = int(os.getenv("DASHBOARD_THREADS", "4"))

    from waitress import serve

    print(f"Dashboard {DASHBOARD_VERSION} (Waitress) su http://{host}:{port}")
    print("CTRL+C per fermare.")
    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
