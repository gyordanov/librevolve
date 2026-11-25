"""Synchronous wrapper around :class:`DialAxisTurntable`."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Callable, Iterable, List, Optional, Tuple

from librevolve.client import (
    DEFAULT_EPSILON_DEG,
    DEFAULT_POLL_INTERVAL_S,
    DEFAULT_SETTLE_POLLS,
    DEFAULT_START_GRACE_S,
    DEFAULT_WAIT_TIMEOUT_S,
    DialAxisTurntable,
    MotionState,
    TurntableNotConnectedError,
)
from librevolve.sequence import StepLike

# Slack over the motion timeout so MotionTimeoutError, not the loop-bridge timeout, reports it.
_WAIT_SLACK_S = 15.0


class SyncDialAxisTurntable:
    """Thread-safe synchronous API backed by a dedicated asyncio loop."""

    def __init__(self, **kwargs) -> None:
        self._tt = DialAxisTurntable(**kwargs)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name='librevolve-async', daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro, timeout: Optional[float] = 120.0):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f'Operation timed out after {timeout}s') from exc

    def close(self) -> None:
        if self._tt.is_connected:
            try:
                self.disconnect()
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
        self._loop.close()

    def __enter__(self) -> 'SyncDialAxisTurntable':
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        return self._tt.is_connected

    @property
    def device_address(self) -> Optional[str]:
        return self._tt.device_address

    def scan(self, timeout: float = 10.0) -> List[Tuple[str, str]]:
        return self._run(self._tt.scan(timeout=timeout), timeout=timeout + 5)

    def connect(self, address: Optional[str] = None, timeout: float = 30.0) -> None:
        self._run(self._tt.connect(address=address, timeout=timeout), timeout=timeout + 15)

    def disconnect(self, stop: bool = True) -> None:
        if self._tt.is_connected:
            self._run(self._tt.disconnect(stop=stop), timeout=30)

    def send(self, cmd: str) -> Optional[str]:
        return self._run(self._tt.send(cmd))

    def rotate(self, degrees: float, *, wait: bool = False) -> Optional[str]:
        return self._run(self._tt.rotate(degrees, wait=wait), timeout=DEFAULT_WAIT_TIMEOUT_S + _WAIT_SLACK_S)

    def tilt(self, degrees: float, *, wait: bool = False) -> Optional[str]:
        return self._run(self._tt.tilt(degrees, wait=wait), timeout=DEFAULT_WAIT_TIMEOUT_S + _WAIT_SLACK_S)

    def spin(self, direction: int = 1) -> Optional[str]:
        return self._run(self._tt.spin(direction))

    def run_sequence(
        self,
        steps: Iterable[StepLike],
        on_progress: Optional[Callable[[int, MotionState], None]] = None,
        *,
        base_timeout: float = DEFAULT_WAIT_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
    ) -> MotionState:
        """Blocking :meth:`DialAxisTurntable.run_sequence`; *on_progress* runs on the loop thread."""
        # No bridge timeout: every step's wait is already bounded by its own scaled timeout.
        return self._run(
            self._tt.run_sequence(
                list(steps), on_progress, base_timeout=base_timeout, poll_interval=poll_interval
            ),
            timeout=None,
        )

    def stop(self) -> None:
        self._run(self._tt.stop())

    def zero(self, *, wait: bool = False) -> None:
        self._run(self._tt.zero(wait=wait), timeout=DEFAULT_WAIT_TIMEOUT_S + _WAIT_SLACK_S)

    def get_motion_state(self) -> MotionState:
        return self._run(self._tt.get_motion_state())

    def wait_until_idle(
        self,
        timeout: float = DEFAULT_WAIT_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
        settle_polls: int = DEFAULT_SETTLE_POLLS,
        start_grace: float = DEFAULT_START_GRACE_S,
        epsilon: float = DEFAULT_EPSILON_DEG,
    ) -> MotionState:
        return self._run(
            self._tt.wait_until_idle(
                timeout=timeout,
                poll_interval=poll_interval,
                settle_polls=settle_polls,
                start_grace=start_grace,
                epsilon=epsilon,
            ),
            timeout=timeout + _WAIT_SLACK_S,
        )

    def get_rotation_angle(self) -> Optional[int]:
        return self._run(self._tt.get_rotation_angle())

    def wait_rotation(self, target_deg: int, poll_interval_s: float = 0.04, timeout_s: float = 120.0) -> bool:
        return self._run(
            self._tt.wait_rotation(target_deg, poll_interval_s=poll_interval_s, timeout_s=timeout_s),
            timeout=timeout_s + 10,
        )
