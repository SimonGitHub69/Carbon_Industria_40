"""Decodifica float IEEE754 da 2 registri Modbus (16-bit ciascuno)."""

from __future__ import annotations

import struct


def registers_to_float(registers: list[int], word_order: str = "abcd") -> float:
    if len(registers) < 2:
        raise ValueError("Servono almeno 2 registri per un float")

    hi, lo = registers[0] & 0xFFFF, registers[1] & 0xFFFF
    order = word_order.lower()

    if order == "abcd":
        raw = struct.pack(">HH", hi, lo)
    elif order == "cdab":
        raw = struct.pack(">HH", lo, hi)
    elif order == "badc":
        raw = bytes([hi & 0xFF, (hi >> 8) & 0xFF, lo & 0xFF, (lo >> 8) & 0xFF])
    elif order == "dcba":
        raw = bytes([lo & 0xFF, (lo >> 8) & 0xFF, hi & 0xFF, (hi >> 8) & 0xFF])
    else:
        raise ValueError(f"FLOAT_WORD_ORDER non supportato: {word_order}")

    return struct.unpack(">f", raw)[0]
