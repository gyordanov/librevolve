"""Command-line interface for librevolve."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from librevolve.client import (
    DEFAULT_WAIT_TIMEOUT_S,
    DialAxisTurntable,
    MotionTimeoutError,
    TurntableNotFoundError,
)
from librevolve import protocol as proto
from librevolve.discovery import discover_turntables
from librevolve.sequence import SequenceError, SequenceStep, parse_sequence


def _device_address():
    return os.environ.get('LIBREVOLVE_DEVICE')


async def _cmd_scan(_tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    devices = await discover_turntables(timeout=args.timeout, dat_only=not args.all)
    if not devices:
        print('No turntables found.', file=sys.stderr)
        return 1
    for dev in devices:
        print(dev)
    return 0


async def _cmd_connect(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await tt.connect(address=args.address or _device_address())
    print(f'Connected to {tt.device_address}')
    return 0


async def _cmd_disconnect(tt: DialAxisTurntable, _args: argparse.Namespace) -> int:
    await tt.disconnect()
    print('Disconnected')
    return 0


async def _wait_for_motion(tt: DialAxisTurntable, args: argparse.Namespace, step: SequenceStep) -> int:
    if args.no_wait:
        return 0
    try:
        state = await tt.wait_until_idle(timeout=tt.motion_timeout(step, base_timeout=args.wait_timeout))
    except MotionTimeoutError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f'rotation={state.rotation} tilt={state.tilt}')
    return 0


async def _cmd_rotate(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.rotate(args.degrees)
    if resp:
        print(resp)
    return await _wait_for_motion(tt, args, SequenceStep('rotate', args.degrees))


async def _cmd_tilt(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.tilt(args.degrees)
    if resp:
        print(resp)
    return await _wait_for_motion(tt, args, SequenceStep('tilt', args.degrees))


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
    return await _wait_for_motion(tt, args, SequenceStep('zero'))


async def _cmd_spin(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.spin(-1 if args.left else 1)
    if resp:
        print(resp)
    return 0


async def _cmd_sequence(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    try:
        steps = parse_sequence(args.steps)
    except SequenceError as exc:
        print(f'Invalid sequence: {exc}', file=sys.stderr)
        return 2
    await _ensure_connected(tt, args)

    def report(index: int, state) -> None:
        print(f'[{index + 1}/{len(steps)}] {steps[index]}: rotation={state.rotation} tilt={state.tilt}', flush=True)

    try:
        await tt.run_sequence(steps, report, base_timeout=args.wait_timeout)
    except MotionTimeoutError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (asyncio.CancelledError, KeyboardInterrupt):
        print('Interrupted, stopping', file=sys.stderr)
        raise
    return 0


def _leaves_motion_running(args: argparse.Namespace) -> bool:
    # A query must not halt a spin or a --no-wait move started by an earlier call.
    return args.command in ('spin', 'angle') or getattr(args, 'no_wait', False)


async def _cmd_send(tt: DialAxisTurntable, args: argparse.Namespace) -> int:
    await _ensure_connected(tt, args)
    resp = await tt.send(args.command)
    if resp:
        print(resp)
    return 0


async def _ensure_connected(tt: DialAxisTurntable, args: argparse.Namespace) -> None:
    if not tt.is_connected:
        await tt.connect(address=getattr(args, 'address', None) or _device_address())


def _add_wait_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        '--no-wait',
        action='store_true',
        help='Return right after the command is acknowledged; the move continues after exit',
    )
    p.add_argument(
        '--wait-timeout',
        type=float,
        default=DEFAULT_WAIT_TIMEOUT_S,
        help='Minimum seconds to wait for motion to settle; slow speeds get more (default: %(default)s)',
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='revolve', description='Revopoint DAT Bluetooth control')
    parser.add_argument('--address', '-a', help='BLE address (or LIBREVOLVE_DEVICE)')
    parser.add_argument(
        '--speed',
        type=float,
        default=proto.DEFAULT_ROTATION_SPEED,
        help=f'Rotation speed set at connect, seconds per turn, larger is slower '
        f'({proto.ROTATION_SPEED_MIN:g}..{proto.ROTATION_SPEED_MAX:g}, default: %(default)s)',
    )
    parser.add_argument(
        '--tilt-speed',
        type=float,
        default=proto.DEFAULT_TILT_SPEED,
        help=f'Tilt speed set at connect, seconds per 360 degrees '
        f'({proto.TILT_SPEED_MIN:g}..{proto.TILT_SPEED_MAX:g}, default: %(default)s)',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('scan', help='Discover nearby Revopoint DAT devices')
    p.add_argument('--timeout', type=float, default=10.0, help='Scan duration in seconds')
    p.add_argument('--all', action='store_true', help='Show all BLE devices, not only likely DAT')
    p.set_defaults(func=_cmd_scan)

    p = sub.add_parser('connect', help='Connect to turntable')
    p.set_defaults(func=_cmd_connect)

    sub.add_parser('disconnect', help='Disconnect').set_defaults(func=_cmd_disconnect)

    p = sub.add_parser('rotate', help='Rotate by degrees')
    p.add_argument('degrees', type=float)
    _add_wait_args(p)
    p.set_defaults(func=_cmd_rotate)

    p = sub.add_parser('tilt', help='Set absolute tilt (-30..30)')
    p.add_argument('degrees', type=float)
    _add_wait_args(p)
    p.set_defaults(func=_cmd_tilt)

    p = sub.add_parser('angle', help='Query rotation angle')
    p.set_defaults(func=_cmd_angle)

    p = sub.add_parser('spin', help='Rotate continuously until `revolve stop`')
    p.add_argument('--left', action='store_true', help='Spin the other way (TURNCONTINUE=-1)')
    p.set_defaults(func=_cmd_spin)

    p = sub.add_parser(
        'sequence',
        help='Run steps in order, e.g. "r380 t30 r380 t-30 r380"',
        description='Steps: r<deg> rotate by deg, t<deg> tilt to absolute deg (-30..30), '
        'z zero both axes, w<sec> pause. Each step waits for the table to settle. '
        'Ctrl-C stops the table.',
    )
    p.add_argument('steps', help='Whitespace- or comma-separated steps')
    p.add_argument(
        '--wait-timeout',
        type=float,
        default=DEFAULT_WAIT_TIMEOUT_S,
        help='Minimum per-step settle timeout; long moves get more (default: %(default)s)',
    )
    p.set_defaults(func=_cmd_sequence)

    sub.add_parser('stop', help='Stop both axes').set_defaults(func=_cmd_stop)
    p = sub.add_parser('zero', help='Return both axes to zero')
    _add_wait_args(p)
    p.set_defaults(func=_cmd_zero)

    p = sub.add_parser('send', help='Send raw protocol command')
    p.add_argument('command', help='e.g. "+CT,TURNANGLE=45;"')
    p.set_defaults(func=_cmd_send)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        tt = DialAxisTurntable(rotation_speed=args.speed, tilt_speed=args.tilt_speed)
    except ValueError as exc:
        parser.error(str(exc))

    async def run() -> int:
        try:
            if args.command != 'scan' and args.command != 'connect':
                pass
            return await args.func(tt, args)
        finally:
            if tt.is_connected and args.command not in ('connect', 'scan'):
                await tt.disconnect(stop=not _leaves_motion_running(args))

    try:
        return asyncio.run(run())
    except TurntableNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
