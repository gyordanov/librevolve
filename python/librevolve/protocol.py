"""Revopoint DAT text protocol — command builders and response parsers."""

from __future__ import annotations

import re
from typing import List, Optional

SERVICE_UUID = '0000ffe0-0000-1000-8000-00805f9b34fb'
CHARACTERISTIC_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb'

DEFAULT_READ_DELAY_S = 0.03
DEFAULT_ROTATION_SPEED = 50.0
DEFAULT_TILT_SPEED = 15.0

TILT_MIN = -30.0
TILT_MAX = 30.0

_DATA_RE = re.compile(r'^\+DATA=(?P<value>[-+0-9.]+);?\s*$', re.IGNORECASE)
_DATA_FIELDS_RE = re.compile(r'^\+DATA=(?P<fields>[-+0-9.]+(?:,[-+0-9.]+)*);?\s*$', re.IGNORECASE)


def _format_value(value: float) -> str:
    text = f'{value:g}'
    if text.upper() in ('NAN', 'INF', '-INF'):
        raise ValueError(f'invalid numeric value: {value!r}')
    return text.upper()


def cmd_turn_angle(degrees: float) -> str:
    return f'+CT,TURNANGLE={_format_value(degrees)};'


def cmd_turn_speed(speed: float) -> str:
    return f'+CT,TURNSPEED={_format_value(speed)};'


def cmd_turn_continue(direction: int) -> str:
    if direction not in (-1, 0, 1):
        raise ValueError('direction must be -1, 0, or 1')
    return f'+CT,TURNCONTINUE={direction};'


def cmd_rotation_stop() -> str:
    return '+CT,STOP;'


def cmd_rotation_zero() -> str:
    return '+CT,TOZERO;'


def cmd_tilt_value(degrees: float) -> str:
    clamped = max(TILT_MIN, min(TILT_MAX, degrees))
    return f'+CR,TILTVALUE={_format_value(clamped)};'


def cmd_tilt_speed(speed: float) -> str:
    return f'+CR,TILTSPEED={_format_value(speed)};'


def cmd_tilt_stop() -> str:
    return '+CR,STOP;'


def cmd_tilt_zero() -> str:
    return '+CR,TOZERO;'


def cmd_query_rotation_angle() -> str:
    return '+QT,CHANGEANGLE;'


def cmd_query_rotation_speed() -> str:
    return '+QT,TURNSPEED;'


def cmd_query_tilt_angle() -> str:
    return '+QR,TILTANGLE;'


def cmd_query_tilt_value() -> str:
    return '+QR,TILTVALUE;'


def cmd_query_tilt_speed() -> str:
    return '+QR,TILTSPEED;'


def parse_data_value(response: Optional[str]) -> Optional[float]:
    """Parse ``+DATA=<number>;`` from a device response."""
    if not response:
        return None
    text = response.strip()
    match = _DATA_RE.match(text)
    if not match:
        return None
    try:
        return float(match.group('value'))
    except ValueError:
        return None


def parse_data_int(response: Optional[str]) -> Optional[int]:
    value = parse_data_value(response)
    if value is None:
        return None
    return int(round(value))


def parse_data_fields(response: Optional[str]) -> Optional[List[float]]:
    """Parse ``+DATA=<n>[,<n>...];`` into floats; None if malformed."""
    if not response:
        return None
    match = _DATA_FIELDS_RE.match(response.strip())
    if not match:
        return None
    try:
        return [float(field) for field in match.group('fields').split(',')]
    except ValueError:
        return None


def parse_data_last(response: Optional[str]) -> Optional[float]:
    """Last field of a ``+DATA=`` response.

    Multi-value queries such as ``+QR,TILTANGLE;`` answer ``min,max,current``.
    """
    fields = parse_data_fields(response)
    return fields[-1] if fields else None
