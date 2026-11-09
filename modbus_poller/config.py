from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVICE_CONFIG = PROJECT_ROOT / "file configurazione" / "service_config.xml"


@dataclass(frozen=True)
class RegisterPoint:
    kind: str  # "float" | "bool"
    addr: int
    cell_dev: int
    zone: str
    code: str
    label: str
    flags: str
    source: str  # "holding" | "coil"


@dataclass(frozen=True)
class ModbusConfig:
    host: str
    port: int
    unit_id: int
    device_name: str
    table_name: str
    points: tuple[RegisterPoint, ...]

    @property
    def analog_points(self) -> tuple[RegisterPoint, ...]:
        return tuple(p for p in self.points if p.kind == "float")

    @property
    def alarm_points(self) -> tuple[RegisterPoint, ...]:
        return tuple(p for p in self.points if p.kind == "bool")


@dataclass(frozen=True)
class AppSettings:
    poll_interval_sec: float
    alarm_interval_sec: float
    modbus_timeout_sec: float
    float_word_order: str
    database_url: str
    modbus_config_path: Path
    service_config_path: Path
    modbus: ModbusConfig


def _project_path(raw: str) -> Path:
    path = Path(raw.strip())
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def sanitize_table_name(device_name: str) -> str:
    """Nome tabella PostgreSQL dal nome dispositivo (es. Modbus Cella frigo)."""
    slug = device_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_") or "modbus_device"
    if slug[0].isdigit():
        slug = f"dev_{slug}"
    return slug[:63]


def _parse_point(el: ET.Element, kind: str, source: str) -> RegisterPoint:
    cell = el.attrib.get("dev") or el.attrib.get("line") or "0"
    code = el.attrib["code"]
    zone = el.attrib.get("zone")
    if not zone:
        zone = (
            "ANTICELLA_+4"
            if cell == "10"
            else "CELLA_-20"
            if cell == "11"
            else f"dev_{cell}"
        )
    return RegisterPoint(
        kind=kind,
        addr=int(el.attrib["addr"]),
        cell_dev=int(cell),
        zone=zone,
        code=code,
        label=el.attrib.get("label", code),
        flags=el.attrib.get("flags", "ro"),
        source=source,
    )


def load_modbus_xml(path: Path, host_override: str | None = None) -> ModbusConfig:
    tree = ET.parse(path)
    root = tree.getroot()

    host = (host_override or "").strip() or root.attrib.get("ip") or root.attrib.get("host")
    if not host:
        raise ValueError(
            f"Manca IP Modbus: impostare <modbus_host> in service_config.xml "
            f"oppure attributo ip in {path}"
        )

    port = int(root.attrib.get("port", "502"))
    device = root.find("device")
    if device is None:
        raise ValueError(f"Nessun elemento <device> in {path}")

    unit_id = int(device.attrib["addr"])
    device_name = device.attrib.get("name", f"unit_{unit_id}")
    points: list[RegisterPoint] = []

    for reg in device.findall("reg"):
        points.append(_parse_point(reg, kind="float", source="holding"))
    for coil in device.findall("coil"):
        points.append(_parse_point(coil, kind="bool", source="coil"))

    if not points:
        raise ValueError(f"Nessun punto reg/coil in {path}")

    return ModbusConfig(
        host=host,
        port=port,
        unit_id=unit_id,
        device_name=device_name,
        table_name=sanitize_table_name(device_name),
        points=tuple(points),
    )


def _text(el: ET.Element | None, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _database_url_from_xml(db: ET.Element | None) -> str:
    if db is None:
        return "postgresql://carbon:carbon@localhost:5432/carbon_i40"
    url = _text(db.find("url"))
    if url:
        return url
    host = _text(db.find("host"), "localhost")
    port = _text(db.find("port"), "5432")
    name = _text(db.find("name"), "carbon_i40")
    user = _text(db.find("user"), "carbon")
    password = _text(db.find("password"), "carbon")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def load_settings(service_config_path: Path | None = None) -> AppSettings:
    """Carica service_config.xml (+ mappa Modbus). Override path via env SERVICE_CONFIG."""
    cfg_path = service_config_path or Path(
        os.getenv("SERVICE_CONFIG", str(DEFAULT_SERVICE_CONFIG))
    )
    if not cfg_path.is_absolute():
        cfg_path = _project_path(str(cfg_path))
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config servizio non trovata: {cfg_path}")

    root = ET.parse(cfg_path).getroot()
    map_path = _project_path(
        _text(root.find("modbus_map"), "file configurazione/modbus_server_cella_frigo.xml")
    )
    host_override = _text(root.find("modbus_host")) or None
    modbus = load_modbus_xml(map_path, host_override=host_override)

    poll = float(_text(root.find("poll_interval_sec"), "300"))
    alarm = float(_text(root.find("alarm_interval_sec"), "30"))
    if poll <= 0 or alarm <= 0:
        raise ValueError("poll_interval_sec e alarm_interval_sec devono essere > 0")

    return AppSettings(
        poll_interval_sec=poll,
        alarm_interval_sec=alarm,
        modbus_timeout_sec=float(_text(root.find("modbus_timeout_sec"), "3")),
        float_word_order=_text(root.find("float_word_order"), "cdab").lower(),
        database_url=_database_url_from_xml(root.find("database")),
        modbus_config_path=map_path,
        service_config_path=cfg_path,
        modbus=modbus,
    )
