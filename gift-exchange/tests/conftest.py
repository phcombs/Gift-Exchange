"""Safety guards applied to every test.

Each guard fails with pytest.fail, whose exception derives from BaseException,
so a broad "except Exception" in product code cannot swallow it.
"""

import socket

import pytest


@pytest.fixture(autouse=True)
def _data_dir_guard(tmp_path, monkeypatch):
    folder = tmp_path / "giftx-data"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(folder))
    return folder


@pytest.fixture(autouse=True)
def _network_guard(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("network access attempted during a test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(autouse=True)
def _google_guard(monkeypatch):
    from giftx import auth, gmail

    def blocked_init(*args, **kwargs):
        pytest.fail("GmailSender was built during a test")

    def blocked_sign_in(*args, **kwargs):
        pytest.fail("auth.sign_in was called during a test")

    monkeypatch.setattr(gmail.GmailSender, "__init__", blocked_init)
    monkeypatch.setattr(auth, "sign_in", blocked_sign_in)
