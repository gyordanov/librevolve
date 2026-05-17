import os

import pytest


def pytest_configure(config):
    config.addinivalue_line('markers', 'hardware: requires physical Revopoint DAT')


def pytest_collection_modifyitems(config, items):
    if os.environ.get('LIBREVOLVE_DEVICE'):
        return
    skip = pytest.mark.skip(reason='Set LIBREVOLVE_DEVICE to run hardware tests')
    for item in items:
        if 'hardware' in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def device_address():
    addr = os.environ.get('LIBREVOLVE_DEVICE')
    if not addr:
        pytest.skip('LIBREVOLVE_DEVICE not set')
    return addr
