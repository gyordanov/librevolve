"""Async BLE client for the Revopoint Dual-Axis Turntable."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional, Tuple

from bleak import BleakClient, BleakScanner

from librevolve import protocol as proto

logger = logging.getLogger(__name__)

NAME_HINTS = ('REVOPOINT', 'DAT', 'DUAL', 'TURNTABLE')


class TurntableNotFoundError(Exception):
    """No matching turntable found during scan."""


class TurntableNotConnectedError(Exception):
    """Operation requires an active BLE connection."""


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

    async def scan(self, timeout: float = 10.0) -> List[Tuple[str, str]]:
        """Return ``(address, name)`` pairs advertising the DAT service."""
        scanner = BleakScanner(service_uuids=[proto.SERVICE_UUID])
        devices = await scanner.discover(timeout=timeout)
        results: List[Tuple[str, str]] = []
        seen = set()
        for dev in devices:
            if dev.address in seen:
                continue
            seen.add(dev.address)
            name = dev.name or '(unknown)'
            results.append((dev.address, name))
        if not results:
            for dev in await BleakScanner.discover(timeout=timeout):
                name = (dev.name or '').upper()
                if any(hint in name for hint in NAME_HINTS):
                    if dev.address not in seen:
                        seen.add(dev.address)
                        results.append((dev.address, dev.name or '(unknown)'))
        return results

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
            found = await self.scan(timeout=min(timeout, 15.0))
            if not found:
                raise TurntableNotFoundError(
                    'No Revopoint DAT found. Power on the turntable, disconnect other BLE clients, '
                    'or set LIBREVOLVE_DEVICE.'
                )
            addr = found[0][0]
            logger.info('Auto-selected device %s (%s)', found[0][0], found[0][1])

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
            await self._client.write_gatt_char(self._char_uuid, cmd.encode('utf-8'), response=True)
            await asyncio.sleep(self.read_delay_s)
            data = await self._client.read_gatt_char(self._char_uuid)
            response = data.decode('utf-8', errors='replace').strip()
            logger.debug('RX %s', response)
            return response or None

    async def rotate(self, degrees: float) -> Optional[str]:
        return await self.send(proto.cmd_turn_angle(degrees))

    async def set_rotation_speed(self, speed: float) -> Optional[str]:
        self.rotation_speed = speed
        return await self.send(proto.cmd_turn_speed(speed))

    async def rotation_stop(self) -> Optional[str]:
        return await self.send(proto.cmd_rotation_stop())

    async def rotation_zero(self) -> Optional[str]:
        return await self.send(proto.cmd_rotation_zero())

    async def tilt(self, degrees: float) -> Optional[str]:
        return await self.send(proto.cmd_tilt_value(degrees))

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

    async def zero(self) -> None:
        await self.rotation_zero()
        await asyncio.sleep(0.05)
        await self.tilt_zero()

    async def get_rotation_angle(self) -> Optional[int]:
        resp = await self.send(proto.cmd_query_rotation_angle())
        return proto.parse_data_int(resp)

    async def get_rotation_speed(self) -> Optional[float]:
        resp = await self.send(proto.cmd_query_rotation_speed())
        return proto.parse_data_value(resp)

    async def get_tilt_angle(self) -> Optional[float]:
        resp = await self.send(proto.cmd_query_tilt_angle())
        value = proto.parse_data_value(resp)
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
