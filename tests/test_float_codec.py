import struct

from modbus_poller.float_codec import registers_to_float


def test_abcd_float():
    # 25.5 as IEEE754 big-endian words
    raw = struct.pack(">f", 25.5)
    hi, lo = struct.unpack(">HH", raw)
    assert abs(registers_to_float([hi, lo], "abcd") - 25.5) < 1e-6


def test_cdab_float():
    raw = struct.pack(">f", -12.25)
    hi, lo = struct.unpack(">HH", raw)
    assert abs(registers_to_float([lo, hi], "cdab") - (-12.25)) < 1e-6
