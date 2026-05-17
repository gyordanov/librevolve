"""Command-line interface for librevolve."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from librevolve.client import DialAxisTurntable, TurntableNotFoundError


def _device_address():
    return os.environ.get('LIBREVOLVE_DEVICE')


async def _cmd_scan(tt: DialAxisTurntable, _args: argparse.Namespace) -> int:
    devices = await tt.scan()
    if not devices:
        print('No devices found.', file=sys.stderr)
        return 1
    for addr, name in devices:
        print(f'{addr}\t{name}')
    return 0


async def _cmd_connect(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await tt.connect(address=args.address or _device_address())
    print(f'Connected to {tt.device_address}')
    return 0


async def _cmd_disconnect(tt: DialAxisTurntable, _args: argparse.Namespace) -> int:
    await tt.disconnect()
    print('Disconnected')
    return 0


async def _cmd_rotate(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.rotate(args.degrees)
    if resp:
        print(resp)
    return 0


async def _cmd_tilt(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.tilt(args.degrees)
    if resp:
        print(resp)
    return 0


async def _cmd_angle(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    angle = await tt.get_rotation_angle()
    if angle is None:
        print('No angle response', file=sys.stderr)
        return 1
    print(angle)
    return 0


async def _cmd_stop(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    await tt.stop()
    return 0


async def _cmd_zero(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    await tt.zero()
    return 0


async def _cmd_send(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.send(args.command)
    if resp:
        print(resp)
    return 0


async def _ensure_connected(tt: DialAxisTurntable, args: argparse.Namespace) -> None:
    if not tt.is_connected:
        await tt.connect(address=getattr(args, 'address', None) or _device_address())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='revolve', description='Revopoint DAT Bluetooth control')
    parser.add_argument('--address', '-a', help='BLE address (or LIBREVOLVE_DEVICE)')
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('scan', help='Scan for turntables').set_defaults(func=_cmd_scan)

    p = sub.add_parser('connect', help='Connect to turntable')
    p.set_defaults(func=_cmd_connect)

    sub.add_parser('disconnect', help='Disconnect').set_defaults(func=_cmd_disconnect)

    p = sub.add_parser('rotate', help='Rotate by degrees')
    p.add_argument('degrees', type=float)
    p.set_defaults(func=_cmd_rotate)

    p = sub.add_parser('tilt', help='Set absolute tilt (-30..30)')
    p.add_argument('degrees', type=float)
    p.set_defaults(func=_cmd_tilt)

    p = sub.add_parser('angle', help='Query rotation angle')
    p.set_defaults(func=_cmd_angle)

    sub.add_parser('stop', help='Stop both axes').set_defaults(func=_cmd_stop)
    sub.add_parser('zero', help='Return both axes to zero').set_defaults(func=_cmd_zero)

    p = sub.add_parser('send', help='Send raw protocol command')
    p.add_argument('command', help='e.g. "+CT,TURNANGLE=45;"')
    p.set_defaults(func=_cmd_send)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    tt = DialAxisTurntable()

    async def run() -> int:
        try:
            if args.command != 'scan' and args.command != 'connect':
                pass
            return await args.func(tt, args)
        finally:
            if tt.is_connected and args.command not in ('connect', 'scan'):
                await tt.disconnect()

    try:
        return asyncio.run(run())
    except TurntableNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
