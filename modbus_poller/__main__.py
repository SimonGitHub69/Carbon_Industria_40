from __future__ import annotations

import logging
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--diagnose" in args or "diagnose" in args:
        from .diagnose import main as diagnose_main

        return diagnose_main()

    if "--show-config" in args:
        from .config import load_settings

        s = load_settings()
        print("service_config =", s.service_config_path)
        print("exists         =", s.service_config_path.exists())
        print("poll_interval  =", int(s.poll_interval_sec), "sec")
        print("alarm_interval =", int(s.alarm_interval_sec), "sec")
        print("modbus_map     =", s.modbus_config_path)
        print("modbus_host    =", s.modbus.host, s.modbus.port)
        print("table          =", s.modbus.table_name)
        try:
            text = s.service_config_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "poll_interval" in line or "alarm_interval" in line:
                    print("xml:", line.strip())
        except Exception as exc:
            print("xml read error:", exc)
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger(__name__)

    from .config import load_settings
    from .poller import Poller

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
        "Intervalli: analog=%ss allarmi=%ss",
        int(settings.poll_interval_sec),
        int(settings.alarm_interval_sec),
    )
    log.info("Config file usato: %s", settings.service_config_path.resolve())

    from .instance_lock import acquire_lock, release_lock

    try:
        acquire_lock(settings.service_config_path.parent / ".runtime")
    except RuntimeError as exc:
        log.error("%s", exc)
        return 4

    try:
        Poller(settings).start()
    finally:
        release_lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
