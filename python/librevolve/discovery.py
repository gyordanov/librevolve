"""BLE discovery for Revopoint Dual-Axis Turntables."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Sequence

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from librevolve import protocol as proto

# Substrings matched against advertised name (case-insensitive).
NAME_HINTS: Sequence[str] = (
    'REVO_DUAL',
    'REVOPOINT',
    'DUAL_AXIS',
    'DUAL-AXIS',
    'DAT',
    'TURNTABLE',
)

SERVICE_UUID_SHORT = 'ffe0'


@dataclass(frozen=True, slots=True)
class TurntableDevice:
    """A BLE device that may be a Revopoint DAT."""

    address: str
    name: str
    rssi: Optional[int] = None
    has_dat_service: bool = False
    name_match: bool = False

    @property
    def likely_dat(self) -> bool:
        return self.has_dat_service or self.name_match

    def __str__(self) -> str:
        flags = []
        if self.has_dat_service:
            flags.append('service')
        if self.name_match:
            flags.append('name')
        hint = f" [{','.join(flags)}]" if flags else ''
        rssi = f' {self.rssi} dBm' if self.rssi is not None else ''
        return f'{self.address}\t{self.name}{rssi}{hint}'


def _normalize_uuid(uuid: str) -> str:
    return uuid.replace('-', '').lower()


def _advertises_dat_service(adv: Optional[AdvertisementData]) -> bool:
    if adv is None or not adv.service_uuids:
        return False
    target = _normalize_uuid(proto.SERVICE_UUID)
    short = SERVICE_UUID_SHORT
    for uuid in adv.service_uuids:
        norm = _normalize_uuid(uuid)
        if norm == target or norm.endswith(short):
            return True
    return False


def _name_matches(name: Optional[str]) -> bool:
    if not name:
        return False
    upper = name.upper()
    return any(hint in upper for hint in NAME_HINTS)


def _device_from_ble(
    device: BLEDevice,
    adv: Optional[AdvertisementData],
) -> TurntableDevice:
    has_service = _advertises_dat_service(adv)
    name = device.name or (adv.local_name if adv else None) or '(unknown)'
    name_match = _name_matches(name) or _name_matches(adv.local_name if adv else None)
    rssi: Optional[int] = None
    if adv is not None:
        rssi = getattr(adv, 'rssi', None)
    return TurntableDevice(
        address=device.address,
        name=name,
        rssi=rssi,
        has_dat_service=has_service,
        name_match=name_match,
    )


async def discover_turntables(
    timeout: float = 10.0,
    *,
    dat_only: bool = True,
) -> List[TurntableDevice]:
    """Scan for nearby turntables.

    Parameters
    ----------
    timeout:
        Scan duration in seconds.
    dat_only:
        If True (default), return only devices advertising the DAT GATT
        service (``ffe0``) or with a matching advertised name. If False,
        return every device seen during the scan with ``likely_dat`` set
        appropriately.

    Returns
    -------
    list[TurntableDevice]
        Devices sorted by signal strength (strongest first) when RSSI is
        available, otherwise by name.
    """
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    results: List[TurntableDevice] = []
    seen: set[str] = set()

    for device, adv in discovered.values():
        if device.address in seen:
            continue
        seen.add(device.address)
        entry = _device_from_ble(device, adv)
        if dat_only and not entry.likely_dat:
            continue
        results.append(entry)

    def sort_key(d: TurntableDevice) -> tuple:
        # Strongest RSSI first (higher is better); missing RSSI sorts last.
        rssi_key = -(d.rssi if d.rssi is not None else -9999)
        return (rssi_key, d.name)

    results.sort(key=sort_key)
    return results


async def find_first_turntable(timeout: float = 10.0) -> Optional[TurntableDevice]:
    """Return the strongest likely DAT seen during a scan, or None."""
    found = await discover_turntables(timeout=timeout, dat_only=True)
    return found[0] if found else None


def discover_turntables_sync(timeout: float = 10.0, *, dat_only: bool = True) -> List[TurntableDevice]:
    """Synchronous wrapper around :func:`discover_turntables`."""
    return asyncio.run(discover_turntables(timeout=timeout, dat_only=dat_only))


def find_first_turntable_sync(timeout: float = 10.0) -> Optional[TurntableDevice]:
    """Synchronous wrapper around :func:`find_first_turntable`."""
    return asyncio.run(find_first_turntable(timeout=timeout))
