import pytest

from librevolve import protocol as proto


@pytest.mark.parametrize(
    'builder,expected',
    [
        (lambda: proto.cmd_turn_angle(45), '+CT,TURNANGLE=45;'),
        (lambda: proto.cmd_turn_angle(-90.5), '+CT,TURNANGLE=-90.5;'),
        (lambda: proto.cmd_turn_speed(50), '+CT,TURNSPEED=50;'),
        (lambda: proto.cmd_turn_continue(1), '+CT,TURNCONTINUE=1;'),
        (lambda: proto.cmd_rotation_stop(), '+CT,STOP;'),
        (lambda: proto.cmd_rotation_zero(), '+CT,TOZERO;'),
        (lambda: proto.cmd_tilt_value(10), '+CR,TILTVALUE=10;'),
        (lambda: proto.cmd_tilt_value(-30), '+CR,TILTVALUE=-30;'),
        (lambda: proto.cmd_tilt_value(50), '+CR,TILTVALUE=30;'),
        (lambda: proto.cmd_tilt_speed(15), '+CR,TILTSPEED=15;'),
        (lambda: proto.cmd_tilt_stop(), '+CR,STOP;'),
        (lambda: proto.cmd_query_rotation_angle(), '+QT,CHANGEANGLE;'),
    ],
)
def test_command_format(builder, expected):
    assert builder() == expected


def test_parse_data_int():
    assert proto.parse_data_int('+DATA=120;') == 120
    assert proto.parse_data_int('+data=45;') == 45
    assert proto.parse_data_int('') is None
    assert proto.parse_data_int('ok') is None


def test_parse_data_float():
    assert proto.parse_data_value('+DATA=15.5;') == 15.5


def test_turn_continue_invalid():
    with pytest.raises(ValueError):
        proto.cmd_turn_continue(2)
