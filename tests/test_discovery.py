from librevolve.discovery import (
    TurntableDevice,
    _advertises_dat_service,
    _name_matches,
)
from librevolve import protocol as proto


class FakeAdv:
    def __init__(self, service_uuids=None, local_name=None, rssi=None):
        self.service_uuids = service_uuids or []
        self.local_name = local_name
        self.rssi = rssi


def test_name_matches():
    assert _name_matches('REVO_DUAL_AXIS_TABLE')
    assert _name_matches('Revopoint Turntable')
    assert not _name_matches('iPhone')
    assert not _name_matches(None)


def test_advertises_dat_service():
    adv = FakeAdv(service_uuids=[proto.SERVICE_UUID])
    assert _advertises_dat_service(adv)
    adv_short = FakeAdv(service_uuids=['0000ffe0-0000-1000-8000-00805f9b34fb'])
    assert _advertises_dat_service(adv_short)
    assert not _advertises_dat_service(FakeAdv(service_uuids=['00001800-0000-1000-8000-00805f9b34fb']))


def test_turntable_device_likely_dat():
    d = TurntableDevice('aa:bb', 'foo', has_dat_service=True)
    assert d.likely_dat
    d2 = TurntableDevice('aa:bb', 'REVO_DUAL', name_match=True)
    assert d2.likely_dat
    d3 = TurntableDevice('aa:bb', 'random', name_match=False, has_dat_service=False)
    assert not d3.likely_dat


def test_turntable_device_str():
    d = TurntableDevice('DE:B6:85:86:6C:5A', 'REVO_DUAL', rssi=-55, name_match=True)
    text = str(d)
    assert 'DE:B6:85:86:6C:5A' in text
    assert 'REVO_DUAL' in text
