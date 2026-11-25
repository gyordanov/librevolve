"""Revopoint Dual-Axis Turntable (DAT) Bluetooth control."""

from librevolve.client import (
    DialAxisTurntable,
    MotionState,
    MotionTimeoutError,
    TurntableNotConnectedError,
    TurntableNotFoundError,
)
from librevolve.discovery import (
    TurntableDevice,
    discover_turntables,
    discover_turntables_sync,
    find_first_turntable,
    find_first_turntable_sync,
)
from librevolve.protocol import (
    SERVICE_UUID,
    CHARACTERISTIC_UUID,
    DEFAULT_READ_DELAY_S,
    DEFAULT_ROTATION_SPEED,
    DEFAULT_TILT_SPEED,
    ROTATION_SPEED_MAX,
    ROTATION_SPEED_MIN,
    TILT_SPEED_MAX,
    TILT_SPEED_MIN,
    degrees_per_second,
)
from librevolve.sequence import SequenceError, SequenceStep, StepProgress, parse_sequence
from librevolve.sync import SyncDialAxisTurntable

__all__ = [
    'DialAxisTurntable',
    'MotionState',
    'MotionTimeoutError',
    'SequenceError',
    'SequenceStep',
    'StepProgress',
    'SyncDialAxisTurntable',
    'TurntableDevice',
    'TurntableNotConnectedError',
    'TurntableNotFoundError',
    'discover_turntables',
    'discover_turntables_sync',
    'find_first_turntable',
    'find_first_turntable_sync',
    'parse_sequence',
    'SERVICE_UUID',
    'CHARACTERISTIC_UUID',
    'DEFAULT_READ_DELAY_S',
    'DEFAULT_ROTATION_SPEED',
    'DEFAULT_TILT_SPEED',
    'ROTATION_SPEED_MAX',
    'ROTATION_SPEED_MIN',
    'TILT_SPEED_MAX',
    'TILT_SPEED_MIN',
    'degrees_per_second',
]

__version__ = '0.1.0'
