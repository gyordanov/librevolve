"""Async BLE client for the Revopoint Dual-Axis Turntable."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

from bleak import BleakClient

from librevolve import protocol as proto
from librevolve.discovery import TurntableDevice, discover_turntables, find_first_turntable
from librevolve.sequence import (
    SequenceStep,
    StepLike,
    StepProgress,
    StepTracker,
    make_steps,
    step_timeout,
)

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
# A step's timeout assumes the axis moves at this fraction of its configured rate.
TIMEOUT_SPEED_FRACTION = 0.5


def _checked_speed(name: str, speed: float, low: float, high: float) -> float:
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not low <= speed <= high:
        raise ValueError(f'{name} must be {low:g}..{high:g} seconds per turn, got {speed!r}')
    return float(speed)


def _raise_if_rejected(resp: Optional[str], name: str, speed: float) -> None:
    if resp and resp.upper().startswith('+FAIL'):
        raise ValueError(f'device rejected {name}={speed:g}: {resp}')


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
        self.rotation_speed = _checked_speed(
            'rotation_speed', rotation_speed, proto.ROTATION_SPEED_MIN, proto.ROTATION_SPEED_MAX
        )
        self.tilt_speed = _checked_speed('tilt_speed', tilt_speed, proto.TILT_SPEED_MIN, proto.TILT_SPEED_MAX)
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

    async def disconnect(self, stop: bool = True) -> None:
        """Disconnect, first stopping both motors unless *stop* is False.

        With ``stop=False`` a move or spin already started keeps running on the device.
        """
        if self._client is None:
            return
        if self._client.is_connected:
            try:
                if stop:
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
            await self.wait_until_idle(timeout=self.motion_timeout(SequenceStep('rotate', float(degrees))))
        return resp

    async def spin(self, direction: int = 1) -> Optional[str]:
        """Rotate continuously (``+CT,TURNCONTINUE=±1;``) until :meth:`stop`."""
        if direction not in (-1, 1):
            raise ValueError('direction must be 1 or -1')
        return await self.send(proto.cmd_turn_continue(direction))

    async def set_rotation_speed(self, speed: float) -> Optional[str]:
        """Set seconds per turn (larger is slower); applies at once, even mid-move.

        Raises ValueError outside the device range or when the device answers +FAIL.
        """
        speed = _checked_speed('rotation speed', speed, proto.ROTATION_SPEED_MIN, proto.ROTATION_SPEED_MAX)
        resp = await self.send(proto.cmd_turn_speed(speed))
        _raise_if_rejected(resp, 'TURNSPEED', speed)
        self.rotation_speed = speed
        return resp

    async def rotation_stop(self) -> Optional[str]:
        return await self.send(proto.cmd_rotation_stop())

    async def rotation_zero(self) -> Optional[str]:
        return await self.send(proto.cmd_rotation_zero())

    async def tilt(self, degrees: float, *, wait: bool = False) -> Optional[str]:
        """Tilt to absolute *degrees*; with *wait*, block until :meth:`wait_until_idle`."""
        resp = await self.send(proto.cmd_tilt_value(degrees))
        if wait:
            await self.wait_until_idle(timeout=self.motion_timeout(SequenceStep('tilt', float(degrees))))
        return resp

    async def set_tilt_speed(self, speed: float) -> Optional[str]:
        """Like :meth:`set_rotation_speed` for the tilt axis."""
        speed = _checked_speed('tilt speed', speed, proto.TILT_SPEED_MIN, proto.TILT_SPEED_MAX)
        resp = await self.send(proto.cmd_tilt_speed(speed))
        _raise_if_rejected(resp, 'TILTSPEED', speed)
        self.tilt_speed = speed
        return resp

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
            await self.wait_until_idle(timeout=self.motion_timeout(SequenceStep('zero')))

    async def get_rotation_angle(self) -> Optional[int]:
        resp = await self.send(proto.cmd_query_rotation_angle())
        return proto.parse_data_int(resp)

    def motion_timeout(
        self,
        step: SequenceStep,
        state: Optional[MotionState] = None,
        base_timeout: Optional[float] = DEFAULT_WAIT_TIMEOUT_S,
    ) -> Optional[float]:
        """Settle timeout for *step* at the configured speeds; None when *base_timeout* is None.

        Only speeds set through this client count; a raw ``send`` of TURNSPEED is not seen.
        """
        return step_timeout(
            step,
            base_timeout=base_timeout,
            current_tilt=state.tilt if state else None,
            current_rotation=state.rotation if state else None,
            min_speed_deg_s=proto.degrees_per_second(self.rotation_speed) * TIMEOUT_SPEED_FRACTION,
            tilt_min_speed_deg_s=proto.degrees_per_second(self.tilt_speed) * TIMEOUT_SPEED_FRACTION,
        )

    async def get_rotation_speed(self) -> Optional[float]:
        resp = await self.send(proto.cmd_query_rotation_speed())
        return proto.parse_data_value(resp)

    async def get_tilt_angle(self) -> Optional[float]:
        """Live tilt from ``+QR,TILTVALUE;``; TILTANGLE's last field does not follow motion."""
        resp = await self.send(proto.cmd_query_tilt_value())
        return proto.parse_data_last(resp)

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
        """Read both axes; rotation keeps the device's 0.1-degree resolution and wraps at ±360."""
        rotation = proto.parse_data_last(await self.send(proto.cmd_query_rotation_angle()))
        tilt = await self.get_tilt_angle()
        return MotionState(rotation=rotation, tilt=tilt)

    async def wait_until_idle(
        self,
        timeout: Optional[float] = DEFAULT_WAIT_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
        settle_polls: int = DEFAULT_SETTLE_POLLS,
        start_grace: float = DEFAULT_START_GRACE_S,
        epsilon: float = DEFAULT_EPSILON_DEG,
        on_poll: Optional[Callable[[MotionState], None]] = None,
    ) -> MotionState:
        """Poll both axes until neither moves more than *epsilon* for *settle_polls* polls.

        The device may start moving late, so stillness only counts once motion was
        seen or *start_grace* seconds passed. *on_poll* gets every reading; *timeout*
        None waits for stillness alone. Raises :class:`MotionTimeoutError`.
        """
        loop = asyncio.get_running_loop()
        start = loop.time()
        previous: Optional[MotionState] = None
        stable = 0
        moved = False
        while True:
            state = await self.get_motion_state()
            if on_poll is not None:
                on_poll(state)
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
            if timeout is not None and elapsed >= timeout:
                raise MotionTimeoutError(
                    f'Motion did not settle within {timeout}s (last {state})', state
                )
            await asyncio.sleep(poll_interval)

    async def run_sequence(
        self,
        steps: Iterable[StepLike],
        on_progress: Optional[Callable[[int, MotionState], None]] = None,
        *,
        base_timeout: Optional[float] = DEFAULT_WAIT_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
        on_poll: Optional[Callable[[int, MotionState, StepProgress], None]] = None,
    ) -> MotionState:
        """Run steps in order, each settling before the next; returns the final state.

        *on_progress* gets ``(step_index, state)`` after each step, *on_poll*
        ``(step_index, state, StepProgress)`` on every reading while it moves. Each
        wait's timeout follows travel and the configured speed (:meth:`motion_timeout`);
        *base_timeout* None waits for stillness alone.
        """
        plan: List[SequenceStep] = make_steps(steps)
        state = await self.get_motion_state()
        for index, step in enumerate(plan):
            timeout = self.motion_timeout(step, state, base_timeout)
            tracker = StepTracker(step, state.rotation, state.tilt)

            def report(reading: MotionState, index: int = index, tracker: StepTracker = tracker) -> None:
                if on_poll is not None:
                    on_poll(index, reading, tracker.update(reading.rotation, reading.tilt))

            if step.action == 'wait':
                await asyncio.sleep(step.value)
                state = await self.get_motion_state()
            else:
                if step.action == 'rotate':
                    await self.rotate(step.value)
                elif step.action == 'tilt':
                    await self.tilt(step.value)
                else:
                    await self.zero()
                state = await self.wait_until_idle(
                    timeout=timeout, poll_interval=poll_interval, on_poll=report
                )
            if on_progress is not None:
                on_progress(index, state)
        return state
