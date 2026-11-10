-- Eseguire su carbon_i40 se la tabella allarmi non è ancora presente
-- psql -U carbon -d carbon_i40 -f sql/create_alarms_table.sql

CREATE TABLE IF NOT EXISTS modbus_cella_frigo_alarms (
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
);

CREATE INDEX IF NOT EXISTS idx_modbus_cella_frigo_alarms_changed_at
    ON modbus_cella_frigo_alarms (changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_modbus_cella_frigo_alarms_point
    ON modbus_cella_frigo_alarms (point_code, changed_at DESC);

DROP VIEW IF EXISTS modbus_cella_frigo_alarms_latest CASCADE;
CREATE VIEW modbus_cella_frigo_alarms_latest AS
SELECT DISTINCT ON (point_code)
    device_name, unit_id, cell_dev, zone_name,
    point_code, point_label, register_addr,
    previous_value, value_bool, quality, changed_at
FROM modbus_cella_frigo_alarms
ORDER BY point_code, changed_at DESC;

GRANT ALL ON TABLE modbus_cella_frigo_alarms TO carbon;
GRANT ALL ON SEQUENCE modbus_cella_frigo_alarms_id_seq TO carbon;
GRANT SELECT ON modbus_cella_frigo_alarms_latest TO carbon;
