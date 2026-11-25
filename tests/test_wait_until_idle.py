import pytest

from librevolve import DialAxisTurntable, MotionState, MotionTimeoutError
from librevolve import protocol as proto


class ScriptedDevice:
    """Answers angle queries from per-axis scripts; the last value repeats forever."""

    def __init__(self, rotation, tilt):
        self.rotation = list(rotation)
        self.tilt = list(tilt)
        self.sent = []

    @staticmethod
    def _next(script):
        return script.pop(0) if len(script) > 1 else script[0]

    async def send(self, cmd):
        self.sent.append(cmd)
        if cmd == proto.cmd_query_rotation_angle():
            return self._next(self.rotation)
        if cmd == proto.cmd_query_tilt_angle():
            return self._next(self.tilt)
        return '+OK;'


def _turntable(device):
    tt = DialAxisTurntable()
    tt.send = device.send
    return tt


FAST = dict(poll_interval=0.001, settle_polls=3, timeout=5.0)
TILT_IDLE = '+DATA=-30.0,30.0,0.3;'


async def test_returns_once_rotation_settles():
    device = ScriptedDevice(
        ['+DATA=-334.0;', '+DATA=-327.6;', '+DATA=-321.1;', '+DATA=-304.4;'],
        [TILT_IDLE],
    )
    state = await _turntable(device).wait_until_idle(start_grace=10.0, **FAST)
    assert state == MotionState(rotation=-304.4, tilt=0.3)


async def test_grace_ignores_stillness_before_motion_starts():
    still_then_moving = ['+DATA=0.0;'] * 6 + ['+DATA=5.0;', '+DATA=10.0;']
    device = ScriptedDevice(still_then_moving, [TILT_IDLE])
    state = await _turntable(device).wait_until_idle(start_grace=10.0, **FAST)
    assert state.rotation == 10.0


async def test_no_motion_returns_after_grace():
    device = ScriptedDevice(['+DATA=12.0;'], [TILT_IDLE])
    state = await _turntable(device).wait_until_idle(start_grace=0.0, **FAST)
    assert state == MotionState(rotation=12.0, tilt=0.3)


async def test_tilt_motion_keeps_waiting():
    device = ScriptedDevice(
        ['+DATA=0.0;'],
        ['+DATA=-30.0,30.0,0.0;', '+DATA=-30.0,30.0,2.0;', '+DATA=-30.0,30.0,4.0;'],
    )
    state = await _turntable(device).wait_until_idle(start_grace=10.0, **FAST)
    assert state.tilt == 4.0


async def test_timeout_raises_with_last_state():
    endless = [f'+DATA={i}.0;' for i in range(100000)]
    device = ScriptedDevice(endless, [TILT_IDLE])
    with pytest.raises(MotionTimeoutError) as excinfo:
        await _turntable(device).wait_until_idle(timeout=0.05, poll_interval=0.001, settle_polls=3)
    assert excinfo.value.state.rotation is not None
    assert isinstance(excinfo.value, TimeoutError)


async def test_rotate_wait_polls_after_command():
    device = ScriptedDevice(['+DATA=0.0;', '+DATA=10.0;', '+DATA=20.0;'], [TILT_IDLE])
    tt = _turntable(device)
    resp = await tt.rotate(20, wait=True)
    assert resp == '+OK;'
    assert device.sent[0] == '+CT,TURNANGLE=20;'
    assert proto.cmd_query_rotation_angle() in device.sent[1:]


async def test_rotate_default_does_not_poll():
    device = ScriptedDevice(['+DATA=0.0;'], [TILT_IDLE])
    await _turntable(device).rotate(20)
    assert device.sent == ['+CT,TURNANGLE=20;']
