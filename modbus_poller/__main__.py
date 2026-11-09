from __future__ import annotations

import logging
import sys

from .config import load_settings
from .poller import Poller


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger(__name__)
    try:
        settings = load_settings()
    except Exception as exc:
        log.error("Config non valida: %s", exc)
        return 1

    log.info(
        "Device=%s tabella=%s host=%s:%s unit=%s",
        settings.modbus.device_name,
        settings.modbus.table_name,
        settings.modbus.host,
        settings.modbus.port,
        settings.modbus.unit_id,
    )
    log.info(
        "Intervalli: analog=%ss allarmi=%ss | config=%s",
        int(settings.poll_interval_sec),
        int(settings.alarm_interval_sec),
        settings.service_config_path,
    )
    Poller(settings).start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
