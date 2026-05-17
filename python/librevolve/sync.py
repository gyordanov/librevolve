"""Synchronous wrapper around :class:`DialAxisTurntable`."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import List, Optional, Tuple

from librevolve.client import DialAxisTurntable, TurntableNotConnectedError


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

    def _run(self, coro, timeout: float = 120.0):
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

    def disconnect(self) -> None:
        if self._tt.is_connected:
            self._run(self._tt.disconnect(), timeout=30)

    def send(self, cmd: str) -> Optional[str]:
        return self._run(self._tt.send(cmd))

    def rotate(self, degrees: float) -> Optional[str]:
        return self._run(self._tt.rotate(degrees))

    def tilt(self, degrees: float) -> Optional[str]:
        return self._run(self._tt.tilt(degrees))

    def stop(self) -> None:
        self._run(self._tt.stop())

    def zero(self) -> None:
        self._run(self._tt.zero())

    def get_rotation_angle(self) -> Optional[int]:
        return self._run(self._tt.get_rotation_angle())

    def wait_rotation(self, target_deg: int, poll_interval_s: float = 0.04, timeout_s: float = 120.0) -> bool:
        return self._run(
            self._tt.wait_rotation(target_deg, poll_interval_s=poll_interval_s, timeout_s=timeout_s),
            timeout=timeout_s + 10,
        )
