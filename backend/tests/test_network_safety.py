import socket

import pytest


def test_external_network_is_blocked_for_the_test_suite():
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="Tests may not open external network connections"):
            connection.connect(("1.1.1.1", 443))
