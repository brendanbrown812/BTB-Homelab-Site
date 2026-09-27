import ipaddress
import os
import socket

import pytest


# Set this before test modules import the cached application settings. Tests
# must never deliver Discord notifications, even when a developer forgets to
# mock a notification function.
os.environ["DISABLE_OUTBOUND_NOTIFICATIONS"] = "true"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()


def _is_loopback(host: object) -> bool:
    try:
        return ipaddress.ip_address(str(host).strip("[]")).is_loopback
    except ValueError:
        return str(host).lower() == "localhost"


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch):
    """Keep tests from reaching Discord or any other external service."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_connect(sock: socket.socket, address):
        host = address[0] if isinstance(address, tuple) else address
        if not _is_loopback(host):
            raise AssertionError(f"Tests may not open external network connections: {host}")
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address):
        host = address[0] if isinstance(address, tuple) else address
        if not _is_loopback(host):
            raise AssertionError(f"Tests may not open external network connections: {host}")
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
