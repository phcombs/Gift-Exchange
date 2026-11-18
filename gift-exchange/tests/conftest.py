"""Safety guards applied to every test.

Each guard fails with pytest.fail, whose exception derives from BaseException,
so a broad "except Exception" in product code cannot swallow it.
"""

import socket
import threading

import pytest

_local = threading.local()


@pytest.fixture(autouse=True)
def _data_dir_guard(tmp_path, monkeypatch):
    folder = tmp_path / "giftx-data"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(folder))
    return folder


@pytest.fixture(autouse=True)
def _network_guard(monkeypatch):
    real_connect = socket.socket.connect
    real_socketpair = socket.socketpair

    def blocked(*args, **kwargs):
        pytest.fail("network access attempted during a test")

    def connect(self, *args, **kwargs):
        # On Windows, socket.socketpair() (used by asyncio's event loop) is built
        # from a loopback listen + connect inside this process. Allow only that.
        if getattr(_local, "in_socketpair", False):
            return real_connect(self, *args, **kwargs)
        blocked()

    def socketpair(*args, **kwargs):
        _local.in_socketpair = True
        try:
            return real_socketpair(*args, **kwargs)
        finally:
            _local.in_socketpair = False

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socketpair", socketpair)


@pytest.fixture(autouse=True)
def _google_guard(monkeypatch):
    from giftx import auth, gmail

    def blocked_init(*args, **kwargs):
        pytest.fail("GmailSender was built during a test")

    def blocked_sign_in(*args, **kwargs):
        pytest.fail("auth.sign_in was called during a test")

    monkeypatch.setattr(gmail.GmailSender, "__init__", blocked_init)
    monkeypatch.setattr(auth, "sign_in", blocked_sign_in)
