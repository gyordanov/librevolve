"""Async BLE client for the Revopoint Dual-Axis Turntable."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from bleak import BleakClient

from librevolve import protocol as proto
from librevolve.discovery import TurntableDevice, discover_turntables, find_first_turntable

logger = logging.getLogger(__name__)


class TurntableNotFoundError(Exception):
    """No matching turntable found during scan."""


class TurntableNotConnectedError(Exception):
    """Operation requires an active BLE connection."""


class MotionTimeoutError(TimeoutError):
    """Motion did not settle in time; ``state`` holds the last reading."""

    def __init__(self, message: str, state: 'MotionState') -> None:
        super().__init__(message)
        self.state = state


@dataclass(frozen=True)
class MotionState:
    """Axis angles in degrees; None where the device gave no parseable answer."""

    rotation: Optional[float]
    tilt: Optional[float]


DEFAULT_WAIT_TIMEOUT_S = 120.0
DEFAULT_POLL_INTERVAL_S = 0.25
DEFAULT_SETTLE_POLLS = 4
DEFAULT_START_GRACE_S = 1.5
DEFAULT_EPSILON_DEG = 0.05


def _axis_changed(old: Optional[float], new: Optional[float], epsilon: float) -> bool:
    if old is None or new is None:
        return False
    return abs(new - old) > epsilon


class DialAxisTurntable:
    """Async controller for the Revopoint Dual-Axis Turntable."""

    def __init__(
        self,
        read_delay_s: float = proto.DEFAULT_READ_DELAY_S,
        rotation_speed: float = proto.DEFAULT_ROTATION_SPEED,
        tilt_speed: float = proto.DEFAULT_TILT_SPEED,
    ) -> None:
        self.read_delay_s = read_delay_s
        self.rotation_speed = rotation_speed
        self.tilt_speed = tilt_speed
        self._client: Optional[BleakClient] = None
        self._char_uuid = proto.CHARACTERISTIC_UUID
        self._lock = asyncio.Lock()
        self._device_address: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def device_address(self) -> Optional[str]:
        return self._device_address

    async def scan(self, timeout: float = 10.0, *, dat_only: bool = True) -> List[TurntableDevice]:
        """Discover nearby turntables. Prefer :func:`librevolve.discover_turntables`."""
        return await discover_turntables(timeout=timeout, dat_only=dat_only)

    async def scan_pairs(self, timeout: float = 10.0, *, dat_only: bool = True) -> List[Tuple[str, str]]:
        """Return ``(address, name)`` pairs (legacy helper)."""
        return [(d.address, d.name) for d in await self.scan(timeout=timeout, dat_only=dat_only)]

    async def connect(
        self,
        address: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        """Connect to the turntable. Scan if *address* is omitted."""
        if self.is_connected:
            await self.disconnect()

        addr = address or os.environ.get('LIBREVOLVE_DEVICE')
        if not addr:
            device = await find_first_turntable(timeout=min(timeout, 15.0))
            if device is None:
                raise TurntableNotFoundError(
                    'No Revopoint DAT found. Power on the turntable, disconnect other BLE clients, '
                    'or set LIBREVOLVE_DEVICE.'
                )
            addr = device.address
            logger.info('Auto-selected device %s (%s)', device.address, device.name)

        self._client = BleakClient(addr, timeout=timeout)
        await self._client.connect()
        if not self._client.is_connected:
            raise TurntableNotConnectedError(f'Failed to connect to {addr}')
        self._device_address = addr
        await self.set_rotation_speed(self.rotation_speed)
        await self.set_tilt_speed(self.tilt_speed)

    async def disconnect(self) -> None:
        """Stop motors and disconnect."""
        if self._client is None:
            return
        if self._client.is_connected:
            try:
                await self.stop()
            except Exception:
                logger.debug('Stop before disconnect failed', exc_info=True)
            await self._client.disconnect()
        self._client = None
        self._device_address = None

    async def send(self, cmd: str) -> Optional[str]:
        """Send a command and read the GATT response."""
        if not self.is_connected or self._client is None:
            raise TurntableNotConnectedError('Not connected')

        async with self._lock:
            logger.debug('TX %s', cmd)
            # DAT GATT char supports write-without-response only (not write-with-response).
            await self._client.write_gatt_char(self._char_uuid, cmd.encode('utf-8'), response=False)
            await asyncio.sleep(self.read_delay_s)
            data = await self._client.read_gatt_char(self._char_uuid)
            response = data.decode('utf-8', errors='replace').strip()
            logger.debug('RX %s', response)
            return response or None

    async def rotate(self, degrees: float, *, wait: bool = False) -> Optional[str]:
        """Rotate by *degrees*; with *wait*, block until :meth:`wait_until_idle`."""
        resp = await self.send(proto.cmd_turn_angle(degrees))
        if wait:
            await self.wait_until_idle()
        return resp

    async def set_rotation_speed(self, speed: float) -> Optional[str]:
        self.rotation_speed = speed
        return await self.send(proto.cmd_turn_speed(speed))

    async def rotation_stop(self) -> Optional[str]:
        return await self.send(proto.cmd_rotation_stop())

    async def rotation_zero(self) -> Optional[str]:
        return await self.send(proto.cmd_rotation_zero())

    async def tilt(self, degrees: float, *, wait: bool = False) -> Optional[str]:
        """Tilt to absolute *degrees*; with *wait*, block until :meth:`wait_until_idle`."""
        resp = await self.send(proto.cmd_tilt_value(degrees))
        if wait:
            await self.wait_until_idle()
        return resp

    async def set_tilt_speed(self, speed: float) -> Optional[str]:
        self.tilt_speed = speed
        return await self.send(proto.cmd_tilt_speed(speed))

    async def tilt_stop(self) -> Optional[str]:
        return await self.send(proto.cmd_tilt_stop())

    async def tilt_zero(self) -> Optional[str]:
        return await self.send(proto.cmd_tilt_zero())

    async def stop(self) -> None:
        await self.rotation_stop()
        await asyncio.sleep(0.05)
        await self.tilt_stop()

    async def zero(self, *, wait: bool = False) -> None:
        await self.rotation_zero()
        await asyncio.sleep(0.05)
        await self.tilt_zero()
        if wait:
            await self.wait_until_idle()

    async def get_rotation_angle(self) -> Optional[int]:
        resp = await self.send(proto.cmd_query_rotation_angle())
        return proto.parse_data_int(resp)

    async def get_rotation_speed(self) -> Optional[float]:
        resp = await self.send(proto.cmd_query_rotation_speed())
        return proto.parse_data_value(resp)

    async def get_tilt_angle(self) -> Optional[float]:
        resp = await self.send(proto.cmd_query_tilt_angle())
        value = proto.parse_data_last(resp)
        if value is not None:
            return value
        resp = await self.send(proto.cmd_query_tilt_value())
        return proto.parse_data_value(resp)

    async def wait_rotation(
        self,
        target_deg: int,
        poll_interval_s: float = 0.04,
        timeout_s: float = 120.0,
    ) -> bool:
        """Poll rotation angle until ``target_deg`` is reached."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            angle = await self.get_rotation_angle()
            if angle is not None and angle >= target_deg:
                return True
            await asyncio.sleep(poll_interval_s)
        return False

    async def get_motion_state(self) -> MotionState:
        """Read both axes; rotation keeps the device's 0.1-degree resolution."""
        rotation = proto.parse_data_last(await self.send(proto.cmd_query_rotation_angle()))
        tilt = proto.parse_data_last(await self.send(proto.cmd_query_tilt_angle()))
        return MotionState(rotation=rotation, tilt=tilt)

    async def wait_until_idle(
        self,
        timeout: float = DEFAULT_WAIT_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
        settle_polls: int = DEFAULT_SETTLE_POLLS,
        start_grace: float = DEFAULT_START_GRACE_S,
        epsilon: float = DEFAULT_EPSILON_DEG,
    ) -> MotionState:
        """Poll both axes until neither moves more than *epsilon* for *settle_polls* polls.

        The device may start moving late, so stillness only counts once motion
        was seen or *start_grace* seconds passed. Raises :class:`MotionTimeoutError`.
        """
        loop = asyncio.get_running_loop()
        start = loop.time()
        previous: Optional[MotionState] = None
        stable = 0
        moved = False
        while True:
            state = await self.get_motion_state()
            if previous is not None:
                if _axis_changed(previous.rotation, state.rotation, epsilon) or _axis_changed(
                    previous.tilt, state.tilt, epsilon
                ):
                    moved = True
                    stable = 0
                elif state.rotation is not None or state.tilt is not None:
                    stable += 1
            previous = state
            elapsed = loop.time() - start
            if stable >= settle_polls and (moved or elapsed >= start_grace):
                return state
            if elapsed >= timeout:
                raise MotionTimeoutError(
                    f'Motion did not settle within {timeout}s (last {state})', state
                )
            await asyncio.sleep(poll_interval)
