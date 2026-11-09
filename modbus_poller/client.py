from __future__ import annotations

import logging

from pymodbus.client import ModbusTcpClient

from .config import ModbusConfig, RegisterPoint
from .float_codec import registers_to_float

logger = logging.getLogger(__name__)


class ModbusReader:
    def __init__(
        self,
        config: ModbusConfig,
        timeout: float,
        float_word_order: str,
    ) -> None:
        self._config = config
        self._float_word_order = float_word_order
        self._client = ModbusTcpClient(
            host=config.host,
            port=config.port,
            timeout=timeout,
        )

    def connect(self) -> None:
        if not self._client.connect():
            raise ConnectionError(
                f"Connessione Modbus fallita verso {self._config.host}:{self._config.port}"
            )
        logger.info(
            "Connesso a Modbus %s:%s unit=%s (%s)",
            self._config.host,
            self._config.port,
            self._config.unit_id,
            self._config.device_name,
        )

    def close(self) -> None:
        self._client.close()

    def read_point(self, point: RegisterPoint) -> float | bool:
        unit = self._config.unit_id
        kwargs = self._unit_kwargs(unit)

        if point.source == "holding":
            result = self._client.read_holding_registers(
                address=point.addr,
                count=2,
                **kwargs,
            )
            if result.isError():
                raise RuntimeError(f"Errore holding @{point.addr}: {result}")
            return registers_to_float(list(result.registers), self._float_word_order)

        if point.source == "coil":
            result = self._client.read_coils(
                address=point.addr,
                count=1,
                **kwargs,
            )
            if result.isError():
                raise RuntimeError(f"Errore coil @{point.addr}: {result}")
            return bool(result.bits[0])

        raise ValueError(f"Source sconosciuto: {point.source}")

    @staticmethod
    def _unit_kwargs(unit: int) -> dict:
        """Compatibilità pymodbus 3.x (slave) / 3.7+ (device_id)."""
        import inspect

        params = inspect.signature(
            ModbusTcpClient.read_holding_registers
        ).parameters
        if "device_id" in params:
            return {"device_id": unit}
        if "slave" in params:
            return {"slave": unit}
        return {}
