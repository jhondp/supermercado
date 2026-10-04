"""Global test guards: the suite must never reach the network."""

import socket

import pytest


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("network access is forbidden in tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("curl_cffi.requests.Session.request", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
