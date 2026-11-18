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
    monkeypatch.setenv("GIFTX_NO_SHORTCUT", "1")  # never put shortcuts on the real desktop
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
def _smtp_guard(monkeypatch):
    """No test may open a real SMTP connection; tests that send replace senders.open_connection."""
    import smtplib

    def blocked(*args, **kwargs):
        pytest.fail("a real SMTP connection was opened during a test")

    monkeypatch.setattr(smtplib.SMTP, "__init__", blocked)
    monkeypatch.setattr(smtplib.SMTP_SSL, "__init__", blocked)


# ---------------------------------------------------------------- M5: fake sender and fixed clock

class SenderCrash(BaseException):
    """Raised by FakeSender(crash_on=N) after the email counts as delivered (like a killed process)."""


class FakeSender:
    """Counts calls (1-based). fail_on -> Rejected, unknown_on -> Unknown, crash_on -> delivered, then raises."""

    def __init__(self, fail_on=None, crash_on=None, unknown_on=None):
        from giftx.model import Rejected, Sent, Unknown

        self._results = (Sent, Rejected, Unknown)
        self.fail_on, self.crash_on, self.unknown_on = fail_on, crash_on, unknown_on
        self.calls = 0
        self.delivered = []  # Outgoing messages that "reached" the recipient
        self._lock = threading.Lock()

    def send(self, msg):
        Sent, Rejected, Unknown = self._results
        with self._lock:
            self.calls += 1
            n = self.calls
        if n == self.fail_on:
            return Rejected("refused by the fake sender")
        with self._lock:
            self.delivered.append(msg)
        if n == self.crash_on:
            raise SenderCrash()
        if n == self.unknown_on:
            return Unknown("the fake sender lost the reply")
        return Sent()


@pytest.fixture
def fake_sender():
    return FakeSender


@pytest.fixture
def clock():
    from datetime import datetime, timezone

    fixed = datetime(2026, 11, 15, 1, 30, tzinfo=timezone.utc)
    return lambda: fixed


# ---------------------------------------------------------------- M6: fake SMTP server

class FakeSMTP:
    """Stands in for an SMTP connection. Set login_error / send_error to an exception to fail."""

    def __init__(self):
        self.login_error = self.send_error = None
        self.logins, self.sent, self.calls = [], [], []
        self.closed = False

    def login(self, user, password):
        self.logins.append((user, password))
        if self.login_error:
            raise self.login_error

    def sendmail(self, from_addr, to_addrs, raw):
        if self.send_error:
            raise self.send_error
        self.sent.append((from_addr, to_addrs, raw))
        return {}

    def quit(self):
        self.closed = True

    def close(self):
        self.closed = True


@pytest.fixture
def smtp_server(monkeypatch):
    """Replace senders.open_connection with a fake server; returns it."""
    from giftx import senders

    fake = FakeSMTP()

    def connect(host, port, security, timeout=None):
        fake.calls.append((host, port, security))
        return fake

    monkeypatch.setattr(senders, "open_connection", connect)
    return fake
