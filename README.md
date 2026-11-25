# librevolve

Python and C library for controlling the **Revopoint Dual-Axis Turntable (DAT)** over Bluetooth Low Energy.

Designed for integration with scan workflows (e.g. [ferret-scan](https://github.com/benklop/ferret-scan)); the Python API is the primary interface.

## Requirements

- Revopoint Dual-Axis Turntable (DAT)
- Bluetooth 4.0+ (BLE)
- **Linux:** BlueZ 5.41+, user in the `bluetooth` group
- **Python:** 3.9+ with `bleak`

Only one client should connect at a time (disconnect the Revopoint phone app or Web UI before using librevolve).

## Install (Python)

```bash
pip install -e ".[dev]"
```

## Use with ferret-scan

[ferret-scan](https://github.com/benklop/ferret-scan) vendors this repo as a git submodule and exposes it as the optional `revolve` extra:

```bash
git submodule update --init packages/librevolve
uv sync --extra revolve
```

## Discovery

Find turntables without connecting:

```python
from librevolve import discover_turntables, discover_turntables_sync

# Async
devices = await discover_turntables(timeout=10.0)
for dev in devices:
    print(dev.address, dev.name, dev.rssi, dev.likely_dat)

# Sync
devices = discover_turntables_sync()
```

CLI:

```bash
revolve scan              # likely DAT devices only
revolve scan --all        # every advertiser (with likely_dat flags)
revolve scan --timeout 15
```

Each result is a `TurntableDevice` with `address`, `name`, optional `rssi`, and flags `has_dat_service` / `name_match`. Use `likely_dat` to filter programmatically.

## Quick start

```python
import asyncio
from librevolve import DialAxisTurntable, discover_turntables

async def main():
    tt = DialAxisTurntable()
    await tt.connect()          # scan for service 0xFFE0
    await tt.rotate(45)
    print(await tt.get_rotation_angle())
    await tt.disconnect()

asyncio.run(main())
```

Synchronous API (e.g. for GUI threads):

```python
from librevolve import SyncDialAxisTurntable

tt = SyncDialAxisTurntable()
tt.connect()
tt.rotate(45)
tt.disconnect()
```

## CLI

```bash
revolve scan
revolve connect
revolve rotate 45
revolve tilt -10
revolve angle
revolve spin            # rotate continuously; --left for the other way
revolve stop
revolve sequence "r380 t30 r380 t-30 r380"
revolve disconnect
```

Use `LIBREVOLVE_DEVICE=AA:BB:CC:DD:EE:FF` to skip scanning.

`rotate`, `tilt` and `zero` stay connected until the table stops moving, then
print `rotation=… tilt=…`, send STOP and disconnect. They poll both angles every
0.25 s and treat the table as idle after 4 unchanged polls (±0.05°). Motion can
start a moment after `+OK;`, so a still table only counts as idle once it has
moved or 1.5 s have passed. A move's timeout grows with its travel and the
configured speed (below); `--wait-timeout SECONDS` (default 120) is the floor.
On timeout the command exits 1.

Speed: `revolve --speed 131 --tilt-speed 131 rotate 380` sets the speeds at
connect (every connect sets them; defaults 50 and 40). Both are **seconds per
360°**, so a larger value is slower: rotation 17.4..9999 (20.7..0.036 °/s),
tilt 40..999999. Measured on a DAT, °/s = 360 / value within ~2 %:

| TURNSPEED | °/s  | TILTSPEED | °/s  |
|-----------|------|-----------|------|
| 17.5      | 20   | 40        | 10   |
| 50        | 7.3  | 90        | 4.2  |
| 131       | 2.76 | 131       | 2.9  |
| 360       | 1.0  | 360       | 1.06 |
| 3600      | 0.1  |           |      |

A new speed applies at once, even to a move or spin already running. Values
outside the range answer `+FAIL,ERR=004;` (rotation) or `+FAIL,ERR=007;`
(tilt), and `set_rotation_speed` / `set_tilt_speed` raise `ValueError`.
`+QT,TURNSPEED;` / `+QR,TILTSPEED;` answer the same constant fields whatever
the setting, so they cannot confirm it.
Idle detection needs the 0.1° reading to change within 4 polls (1 s), so above
about 1800 s per turn (0.2 °/s) a slow move can be taken as finished early.

`--no-wait` sends the move and disconnects without STOP, so the table finishes
the move after the CLI exits (fire-and-return). `spin` does the same with
`+CT,TURNCONTINUE=±1;`: the table keeps turning until `revolve stop`. `angle`
also disconnects without STOP, so it can watch a spin or a `--no-wait` move.

`sequence` runs steps in order, each one waiting for the table to settle:

| Step     | Meaning                                  |
|----------|------------------------------------------|
| `r<deg>` | rotate by `deg` (relative, may be > 360) |
| `t<deg>` | tilt to `deg` (absolute, -30..30)        |
| `z`      | return both axes to zero                 |
| `w<sec>` | pause                                    |

Steps are separated by spaces or commas; a malformed step or out-of-range tilt
is rejected before anything moves (exit 2). Each step prints
`[i/n] step: rotation=… tilt=…`. Ctrl-C stops the table and exits 130. A step's
timeout is `max(--wait-timeout, 2 × travel / (360 / speed) + 15 s)`: twice the
time the move takes at the configured speed, so `r380` at the default 50
(about 53 s) gets 121 s and at 131 (about 138 s) gets 292 s. A slow speed never
times out early; a table still moving past that point is treated as stuck.

The reported rotation wraps at ±360: after `rotate 380` from 57 it reads 77.
Tilt is read from `+QR,TILTVALUE;`.

From Python: `await tt.wait_until_idle()` (or `rotate(..., wait=True)`; the
same on `SyncDialAxisTurntable`) returns a `MotionState(rotation, tilt)` and
raises `MotionTimeoutError` on timeout. Also:

```python
await tt.spin(1)                     # until tt.stop()
await tt.disconnect(stop=False)      # leave a move or spin running
await tt.run_sequence(
    [("rotate", 380), ("tilt", 30), ("rotate", 380), ("tilt", -30), ("rotate", 380)],
    on_progress=lambda i, state: print(i, state.rotation, state.tilt),
)
await tt.run_sequence(parse_sequence("r20 t5 r-20 t0"))
```

`run_sequence` validates every step first and raises `SequenceError`
(a `ValueError`) on bad input; `on_progress(step_index, MotionState)` runs after
each step settles. `on_poll(step_index, MotionState, StepProgress)` runs on
every reading while a step moves; `StepProgress(done, total)` is degrees, with
rotation accumulated across the ±360 wrap. `base_timeout=None` drops the
timeout and waits for stillness alone; `wait_until_idle(timeout=None,
on_poll=...)` does the same for a single move. `SyncDialAxisTurntable` has the
same `spin`, `run_sequence`, `set_rotation_speed`, `set_tilt_speed` and
`disconnect(stop=...)`; its callbacks run on the library's loop thread.

## Protocol

Nordic UART-style GATT bridge:

| Item | UUID |
|------|------|
| Service | `0000ffe0-0000-1000-8000-00805f9b34fb` |
| Characteristic | `0000ffe1-0000-1000-8000-00805f9b34fb` |

Commands are UTF-8 text: `+AXIS,COMMAND=VALUE;` (ALL CAPS, no spaces).

Write command → wait ~30 ms → read characteristic → response often `+DATA=…;`

### Rotation (CT)

| Command | Description |
|---------|-------------|
| `+CT,TURNANGLE=X;` | Rotate incrementally by X degrees |
| `+CT,TURNSPEED=X;` | Seconds per turn, 17.4–9999 (35.64–131 in DATRAPP UI) |
| `+CT,TURNCONTINUE=X;` | Continuous rotation (1=right, -1=left) |
| `+CT,TOZERO;` | Return rotation to boot zero |
| `+CT,STOP;` | Stop rotation |

### Tilt (CR)

| Command | Description |
|---------|-------------|
| `+CR,TILTVALUE=X;` | Absolute tilt -30…+30° |
| `+CR,TILTSPEED=X;` | Seconds per 360°, 40–999999 (DATRAPP UI shows 9–35) |
| `+CR,TOZERO;` | Return tilt to zero |
| `+CR,STOP;` | Stop tilt |

### Queries

| Command | Response |
|---------|----------|
| `+QT,CHANGEANGLE;` | `+DATA=<degrees>;` rotation tracker |
| `+QT,TURNSPEED;` | `+DATA=17.5,90.0,2.0;` whatever the setting |
| `+QR,TILTANGLE;` | `+DATA=-30,30,X;` limits; X does not follow motion |
| `+QR,TILTVALUE;` | Current tilt (live) |
| `+QR,TILTSPEED;` | `+DATA=6.8,90.0,1.0;` whatever the setting |

## C library (optional)

```bash
cmake -B build-cmake -DCMAKE_BUILD_TYPE=Release
cmake --build build-cmake -j
./build-cmake/revolve scan
./build-cmake/revolve rotate 45 AA:BB:CC:DD:EE:FF
```

Uses [SimpleBLE](https://github.com/OpenBluetoothToolbox/SimpleBLE) via CMake FetchContent. Python does not require the C build.

## Hardware validation checklist

With the turntable powered on and no other BLE client connected:

1. `revolve scan` — device appears with service `ffe0`
2. `revolve connect` — connects without error
3. `revolve rotate 90` — platform rotates
4. `revolve angle` — reports changing angle
5. `revolve tilt 10` then `revolve tilt -10` — tilt moves (absolute)
6. `revolve stop` — motion stops
7. `revolve disconnect` — clean disconnect

Automated (requires hardware):

```bash
export LIBREVOLVE_DEVICE=XX:XX:XX:XX:XX:XX
pytest -m hardware
```

## Credits

Protocol and behavior derived from community reverse-engineering and open controllers:

- [Volkula/DATRAPP](https://github.com/Volkula/DATRAPP) — Web Bluetooth reference UI
- [eXplOiD1/Revopoint-Dual-Axis-Turntable-webbased-Controller](https://github.com/eXplOiD1/Revopoint-Dual-Axis-Turntable-webbased-Controller/)
- [opensourcemanufacturing/Revopoint-Dual-Turntable](https://github.com/opensourcemanufacturing/Revopoint-Dual-Turntable)

## License

MIT — see [LICENSE](LICENSE). Applications under GPL (e.g. ferret-scan) may link/use this library per MIT terms.
