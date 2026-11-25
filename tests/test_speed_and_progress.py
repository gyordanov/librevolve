import pytest

from librevolve import DialAxisTurntable, SequenceStep, StepProgress
from librevolve import client as client_module
from librevolve import protocol as proto
from librevolve.sequence import StepTracker, angle_delta


class Recorder:
    def __init__(self, answer='+OK;'):
        self.answer = answer
        self.sent = []

    async def send(self, cmd):
        self.sent.append(cmd)
        return self.answer


def _turntable(device, **kwargs):
    tt = DialAxisTurntable(**kwargs)
    tt.send = device.send
    return tt


async def test_set_speeds_send_and_remember():
    device = Recorder()
    tt = _turntable(device)
    await tt.set_rotation_speed(131)
    await tt.set_tilt_speed(360)
    assert device.sent == ['+CT,TURNSPEED=131;', '+CR,TILTSPEED=360;']
    assert (tt.rotation_speed, tt.tilt_speed) == (131.0, 360.0)


@pytest.mark.parametrize('speed', [17.3, 10000, True, float('nan')])
async def test_out_of_range_rotation_speed_is_not_sent(speed):
    device = Recorder()
    tt = _turntable(device)
    with pytest.raises(ValueError):
        await tt.set_rotation_speed(speed)
    assert device.sent == []
    assert tt.rotation_speed is None


async def test_device_rejection_keeps_previous_speed():
    tt = _turntable(Recorder('+FAIL,ERR=007;'))
    with pytest.raises(ValueError, match='TILTSPEED=90'):
        await tt.set_tilt_speed(90)
    assert tt.tilt_speed is None


def test_constructor_rejects_tilt_speed_the_device_refuses():
    with pytest.raises(ValueError):
        DialAxisTurntable(tilt_speed=15)


def test_motion_timeout_covers_twice_the_expected_duration_at_slowest_speed():
    tt = DialAxisTurntable(rotation_speed=proto.ROTATION_SPEED_MAX, tilt_speed=proto.TILT_SPEED_MAX)
    rotate = SequenceStep('rotate', 380.0)
    expected = 380 / proto.degrees_per_second(proto.ROTATION_SPEED_MAX)
    assert tt.motion_timeout(rotate) >= 2 * expected
    tilt_expected = 30 / proto.degrees_per_second(proto.TILT_SPEED_MAX)
    assert tt.motion_timeout(SequenceStep('tilt', 30.0)) >= 2 * tilt_expected
    assert tt.motion_timeout(rotate, base_timeout=None) is None


def test_motion_timeout_keeps_base_as_floor():
    tt = DialAxisTurntable(rotation_speed=proto.ROTATION_SPEED_MIN)
    assert tt.motion_timeout(SequenceStep('rotate', 10.0), base_timeout=120.0) == 120.0


@pytest.mark.parametrize('old,new,delta', [(10, 20, 10), (359.9, 0.1, 0.2), (0.1, 359.9, -0.2), (359, -359, 2)])
def test_angle_delta_wraps(old, new, delta):
    assert angle_delta(old, new) == pytest.approx(delta)


def test_rotation_progress_accumulates_across_the_360_wrap():
    tracker = StepTracker(SequenceStep('rotate', 380.0), 57.0, 0.3)
    progress = [tracker.update(r, 0.3) for r in (57.0, 150.0, 250.0, 359.9, 0.4, 40.0, 77.0)]
    assert progress[-1] == StepProgress(pytest.approx(380.0), 380.0)
    assert [p.done for p in progress] == sorted(p.done for p in progress)


def test_negative_rotation_progress_counts_up():
    tracker = StepTracker(SequenceStep('rotate', -380.0), -57.0, 0.0)
    for reading in (-150.0, -300.0, -359.5, -0.5, -77.0):
        progress = tracker.update(reading, 0.0)
    assert progress == StepProgress(pytest.approx(380.0), 380.0)


def test_tilt_and_zero_progress():
    tilt = StepTracker(SequenceStep('tilt', 30.0), 0.0, -10.0)
    assert tilt.update(0.0, 5.0) == StepProgress(15.0, 40.0)
    zero = StepTracker(SequenceStep('zero'), 20.0, 10.0)
    assert zero.update(5.0, 0.0) == StepProgress(25.0, 30.0)


class FakeBleak:
    """Stands in for BleakClient: records writes, answers every read with one reading."""

    written = []

    def __init__(self, address, timeout=None):
        self.is_connected = False

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def write_gatt_char(self, _uuid, data, response=False):
        FakeBleak.written.append(data.decode())

    async def read_gatt_char(self, _uuid):
        return b'+DATA=1.0;'


@pytest.fixture
def fake_bleak(monkeypatch):
    FakeBleak.written = []
    monkeypatch.setattr(client_module, 'BleakClient', FakeBleak)
    return FakeBleak


async def test_connect_sends_only_chosen_speeds(fake_bleak):
    await DialAxisTurntable(read_delay_s=0).connect('AA')
    assert fake_bleak.written == []
    await DialAxisTurntable(read_delay_s=0, rotation_speed=131).connect('AA')
    assert fake_bleak.written == ['+CT,TURNSPEED=131;']


@pytest.mark.parametrize(
    'argv,expected',
    [
        (['angle'], ['+QT,CHANGEANGLE;']),
        (['--speed', '360', 'spin'], ['+CT,TURNSPEED=360;', '+CT,TURNCONTINUE=1;']),
        (['stop'], [proto.cmd_rotation_stop(), proto.cmd_tilt_stop()] * 2),
    ],
)
def test_cli_sends_speed_only_when_given(fake_bleak, monkeypatch, argv, expected):
    from librevolve import cli

    monkeypatch.setattr(client_module.proto, 'DEFAULT_READ_DELAY_S', 0)
    assert cli.main(['--address', 'AA', *argv]) == 0
    assert fake_bleak.written == expected


@pytest.mark.parametrize('speed', [131, 1800, 9999])
def test_settle_time_covers_three_reading_steps(speed):
    tt = DialAxisTurntable(rotation_speed=speed, tilt_speed=speed)
    rate = proto.degrees_per_second(speed)
    for step in (SequenceStep('rotate', 10.0), SequenceStep('tilt', 5.0), SequenceStep('zero')):
        assert tt.settle_time(step) == pytest.approx(0.3 / rate)


def test_settle_time_unknown_without_speed():
    assert DialAxisTurntable().settle_time(SequenceStep('rotate', 10.0)) is None
    assert DialAxisTurntable().motion_timeout(SequenceStep('rotate', 10.0)) is None


class Script:
    def __init__(self, rotation):
        self.rotation = list(rotation)

    async def send(self, cmd):
        if cmd == proto.cmd_query_rotation_angle():
            return self.rotation.pop(0) if len(self.rotation) > 1 else self.rotation[0]
        return '+DATA=0.3;'


def _slow_readings():
    # A slow axis: the 0.1-degree reading changes only every 20 fast polls.
    return [f'+DATA={tenth / 10:.1f};' for tenth in range(4) for _ in range(20)]


async def test_slow_axis_without_settle_time_ends_early():
    tt = DialAxisTurntable()
    tt.send = Script(_slow_readings()).send
    state = await tt.wait_until_idle(poll_interval=0, settle_polls=3, start_grace=0)
    assert state.rotation < 0.3


async def test_settle_time_waits_out_a_slow_axis():
    tt = DialAxisTurntable()
    tt.send = Script(_slow_readings()).send
    state = await tt.wait_until_idle(poll_interval=0, settle_polls=3, start_grace=0, settle_time=0.05)
    assert state.rotation == 0.3


async def test_settle_time_extends_the_start_grace():
    tt = DialAxisTurntable()
    tt.send = Script(['+DATA=0.0;'] * 50 + ['+DATA=0.1;', '+DATA=0.2;']).send
    state = await tt.wait_until_idle(poll_interval=0, settle_polls=3, start_grace=0, settle_time=0.05)
    assert state.rotation == 0.2
