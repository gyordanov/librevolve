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
revolve stop
revolve disconnect
```

Use `LIBREVOLVE_DEVICE=AA:BB:CC:DD:EE:FF` to skip scanning.

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
| `+CT,TURNSPEED=X;` | Set rotation speed (35.64–131 in DATRAPP UI) |
| `+CT,TURNCONTINUE=X;` | Continuous rotation (1=right, -1=left) |
| `+CT,TOZERO;` | Return rotation to boot zero |
| `+CT,STOP;` | Stop rotation |

### Tilt (CR)

| Command | Description |
|---------|-------------|
| `+CR,TILTVALUE=X;` | Absolute tilt -30…+30° |
| `+CR,TILTSPEED=X;` | Set tilt speed (9–35 in DATRAPP UI) |
| `+CR,TOZERO;` | Return tilt to zero |
| `+CR,STOP;` | Stop tilt |

### Queries

| Command | Response |
|---------|----------|
| `+QT,CHANGEANGLE;` | `+DATA=<degrees>;` rotation tracker |
| `+QT,TURNSPEED;` | Current rotation speed |
| `+QR,TILTANGLE;` | Current tilt |
| `+QR,TILTVALUE;` | Current tilt (alias) |
| `+QR,TILTSPEED;` | Current tilt speed |

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
