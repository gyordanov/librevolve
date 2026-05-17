import pytest

from librevolve import DialAxisTurntable


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_connect_query_disconnect(device_address):
    tt = DialAxisTurntable()
    await tt.connect(address=device_address)
    assert tt.is_connected
    angle = await tt.get_rotation_angle()
    assert angle is not None
    await tt.stop()
    await tt.disconnect()
    assert not tt.is_connected
