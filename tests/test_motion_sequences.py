import re

import pytest

from librevolve import DialAxisTurntable, MotionState, SequenceError, SequenceStep, parse_sequence
from librevolve import protocol as proto
from librevolve.sequence import step_timeout


class FakeBleClient:
    def __init__(self):
        self.is_connected = True
        self.disconnected = False

    async def disconnect(self):
        self.is_connected = False
        self.disconnected = True


class SimulatedTable:
    """Moves each axis toward its target by *step* degrees per angle query."""

    def __init__(self, step=10.0):
        self.step = step
        self.rotation = self.rotation_target = 0.0
        self.tilt = self.tilt_target = 0.0
        self.sent = []

    def _advance(self, current, target):
        if abs(target - current) <= self.step:
            return target
        return current + self.step * (1 if target > current else -1)

    async def send(self, cmd):
        self.sent.append(cmd)
        if cmd == proto.cmd_query_rotation_angle():
            self.rotation = self._advance(self.rotation, self.rotation_target)
            return f'+DATA={self.rotation:.1f};'
        if cmd == proto.cmd_query_tilt_value():
            self.tilt = self._advance(self.tilt, self.tilt_target)
            return f'+DATA={self.tilt:.1f};'
        if match := re.match(r'\+CT,TURNANGLE=(.+);', cmd):
            self.rotation_target += float(match.group(1))
        elif match := re.match(r'\+CR,TILTVALUE=(.+);', cmd):
            self.tilt_target = float(match.group(1))
        elif cmd == proto.cmd_rotation_zero():
            self.rotation_target = 0.0
        elif cmd == proto.cmd_tilt_zero():
            self.tilt_target = 0.0
        return '+OK;'

    def motion_commands(self):
        return [c for c in self.sent if not c.startswith('+Q')]


def _turntable(device, client=None):
    tt = DialAxisTurntable()
    tt.send = device.send
    tt._client = client
    return tt


async def test_disconnect_without_stop_sends_nothing():
    device, client = SimulatedTable(), FakeBleClient()
    await _turntable(device, client).disconnect(stop=False)
    assert device.sent == []
    assert client.disconnected


async def test_disconnect_default_still_stops():
    device, client = SimulatedTable(), FakeBleClient()
    await _turntable(device, client).disconnect()
    assert device.sent == [proto.cmd_rotation_stop(), proto.cmd_tilt_stop()]
    assert client.disconnected


@pytest.mark.parametrize('direction,expected', [(1, '+CT,TURNCONTINUE=1;'), (-1, '+CT,TURNCONTINUE=-1;')])
async def test_spin_command(direction, expected):
    device = SimulatedTable()
    await _turntable(device).spin(direction)
    assert device.sent == [expected]


async def test_spin_rejects_zero_direction():
    with pytest.raises(ValueError):
        await _turntable(SimulatedTable()).spin(0)


def test_parse_sequence_valid():
    assert parse_sequence('r380 t30, R-20.5  t-30 z w1.5') == [
        SequenceStep('rotate', 380.0),
        SequenceStep('tilt', 30.0),
        SequenceStep('rotate', -20.5),
        SequenceStep('tilt', -30.0),
        SequenceStep('zero'),
        SequenceStep('wait', 1.5),
    ]
    assert [str(s) for s in parse_sequence('r380 t-30 z w2')] == ['r380', 't-30', 'z', 'w2']


@pytest.mark.parametrize(
    'text,fragment',
    [
        ('', 'empty'),
        ('r380 x5', "step 2 'x5'"),
        ('t31', 'outside'),
        ('t', 'missing number'),
        ('z5', 'no value'),
        ('w-1', '>= 0'),
        ('r1e3', "'r1e3'"),
        ('r--5', "'r--5'"),
    ],
)
def test_parse_sequence_rejects(text, fragment):
    with pytest.raises(SequenceError, match=re.escape(fragment)):
        parse_sequence(text)


def test_step_timeout_scales_with_travel():
    assert step_timeout(SequenceStep('rotate', 10.0), base_timeout=120.0) == 120.0
    assert step_timeout(SequenceStep('rotate', -900.0), base_timeout=120.0) == pytest.approx(900 / 3 + 15)
    assert step_timeout(
        SequenceStep('tilt', 5.0), base_timeout=1.0, current_tilt=-5.0
    ) == pytest.approx(10 / 3 + 15)
    assert step_timeout(SequenceStep('tilt', 5.0), base_timeout=1.0) == pytest.approx(60 / 3 + 15)
    assert step_timeout(
        SequenceStep('zero'), base_timeout=1.0, current_rotation=-600.0, current_tilt=0.0
    ) == pytest.approx(600 / 3 + 15)


async def test_run_sequence_waits_between_steps_and_reports_progress():
    device = SimulatedTable(step=10.0)
    tt = _turntable(device)
    progress = []
    final = await tt.run_sequence(
        [('rotate', 40), ('tilt', 5), ('wait', 0), ('rotate', -40), ('zero',)],
        lambda index, state: progress.append((index, state)),
        poll_interval=0.001,
    )
    assert device.motion_commands() == [
        '+CT,TURNANGLE=40;',
        '+CR,TILTVALUE=5;',
        '+CT,TURNANGLE=-40;',
        '+CT,TOZERO;',
        '+CR,TOZERO;',
    ]
    tilt_sent = device.sent.index('+CR,TILTVALUE=5;')
    assert device.sent[:tilt_sent].count(proto.cmd_query_rotation_angle()) >= 5
    assert [index for index, _ in progress] == [0, 1, 2, 3, 4]
    assert progress[0][1] == MotionState(rotation=40.0, tilt=0.0)
    assert progress[1][1] == MotionState(rotation=40.0, tilt=5.0)
    assert progress[3][1] == MotionState(rotation=0.0, tilt=5.0)
    assert final == MotionState(rotation=0.0, tilt=0.0)


async def test_run_sequence_validates_before_moving():
    device = SimulatedTable()
    with pytest.raises(SequenceError):
        await _turntable(device).run_sequence([('rotate', 10), ('tilt', 45)])
    assert device.sent == []


@pytest.mark.parametrize(
    'argv,keeps_moving',
    [
        (['rotate', '30', '--no-wait'], True),
        (['rotate', '30'], False),
        (['spin', '--left'], True),
        (['sequence', 'r20 t5'], False),
        (['angle'], True),
        (['stop'], False),
    ],
)
def test_cli_disconnect_skips_stop_only_for_fire_and_return(argv, keeps_moving):
    from librevolve import cli

    assert cli._leaves_motion_running(cli._build_parser().parse_args(argv)) is keeps_moving
