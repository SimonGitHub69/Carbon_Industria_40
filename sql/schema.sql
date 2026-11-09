-- Schema di riferimento. A runtime la tabella viene creata dal poller
-- con nome derivato dal device (es. "Modbus Cella frigo" → modbus_cella_frigo).

CREATE TABLE IF NOT EXISTS modbus_cella_frigo (
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
);

CREATE INDEX IF NOT EXISTS idx_modbus_cella_frigo_polled_at
    ON modbus_cella_frigo (polled_at DESC);

CREATE INDEX IF NOT EXISTS idx_modbus_cella_frigo_point
    ON modbus_cella_frigo (point_code, polled_at DESC);

CREATE OR REPLACE VIEW modbus_cella_frigo_latest AS
SELECT DISTINCT ON (point_code)
    device_name, unit_id, cell_dev, zone_name,
    point_code, point_label, register_addr,
    value_float, value_bool, point_kind, quality, polled_at
FROM modbus_cella_frigo
ORDER BY point_code, polled_at DESC;
