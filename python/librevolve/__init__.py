"""Revopoint Dual-Axis Turntable (DAT) Bluetooth control."""

from librevolve.client import DialAxisTurntable
from librevolve.protocol import (
    SERVICE_UUID,
    CHARACTERISTIC_UUID,
    DEFAULT_READ_DELAY_S,
    DEFAULT_ROTATION_SPEED,
    DEFAULT_TILT_SPEED,
)
from librevolve.sync import SyncDialAxisTurntable

__all__ = [
    'DialAxisTurntable',
    'SyncDialAxisTurntable',
    'SERVICE_UUID',
    'CHARACTERISTIC_UUID',
    'DEFAULT_READ_DELAY_S',
    'DEFAULT_ROTATION_SPEED',
    'DEFAULT_TILT_SPEED',
]

__version__ = '0.1.0'
