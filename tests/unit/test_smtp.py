"""M6: account settings and the SMTP sender, against a fake SMTP server (no network)."""

import os
import smtplib
import sys
from email import message_from_bytes
from email.policy import default

import pytest

from giftx import account, compose, paths, senders
from giftx.account import EmailSettings
from giftx.model import Outgoing, Rejected, Sent, Unknown
from giftx.senders import SmtpSender, login_problem


def outgoing(to="ann@example.com"):
    raw = compose.build_email(to, "Your match, Ann", "Hi Ann,\n\nYou buy for Bob.\n")
    return Outgoing("1/1", to, raw)


def sender():
    return SmtpSender("smtp.gmail.com", 465, "ssl", "me@example.com", "abcdefghijklmnop")


# ---------------------------------------------------------------- sender

def test_sends_with_from_date_message_id_and_crlf(smtp_server):
    assert sender().send(outgoing()) == Sent()
    assert smtp_server.calls == [("smtp.gmail.com", 465, "ssl")]
    assert smtp_server.logins == [("me@example.com", "abcdefghijklmnop")]
    ((from_addr, to_addrs, raw),) = smtp_server.sent
    assert (from_addr, to_addrs) == ("me@example.com", ["ann@example.com"])
    assert b"\n" not in raw.replace(b"\r\n", b"")
    msg = message_from_bytes(raw, policy=default)
    assert msg["From"] == "me@example.com"
    assert msg["Date"] and msg["Message-ID"]
    assert msg["Subject"] == "Your match, Ann"
    assert "You buy for Bob." in msg.get_content()
    assert smtp_server.closed


def test_connect_failure_is_rejected(monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(senders, "open_connection", refuse)
    assert isinstance(sender().send(outgoing()), Rejected)


@pytest.mark.parametrize(
    "error,kind",
    [
        (smtplib.SMTPAuthenticationError(535, b"bad"), Rejected),
        (smtplib.SMTPServerDisconnected("gone"), Rejected),
    ],
)
def test_login_failures_are_rejected(smtp_server, error, kind):
    smtp_server.login_error = error
    assert isinstance(sender().send(outgoing()), kind)
    assert smtp_server.sent == [] and smtp_server.closed


@pytest.mark.parametrize(
    "error,kind",
    [
        (smtplib.SMTPRecipientsRefused({"ann@example.com": (550, b"no such user")}), Rejected),
        (smtplib.SMTPSenderRefused(553, b"no", "me@example.com"), Rejected),
        (smtplib.SMTPDataError(552, b"too big"), Rejected),
        (smtplib.SMTPServerDisconnected("dropped"), Unknown),
        (TimeoutError(), Unknown),
        (ConnectionResetError(), Unknown),
    ],
)
def test_send_failures(smtp_server, error, kind):
    smtp_server.send_error = error
    result = sender().send(outgoing())
    assert isinstance(result, kind)
    assert "ann@example.com" not in result.reason
    assert smtp_server.closed


def test_login_problem(smtp_server):
    assert login_problem("smtp.gmail.com", 465, "ssl", "me@example.com", "pw") is None
    smtp_server.login_error = smtplib.SMTPAuthenticationError(535, b"bad")
    assert "refused the sign-in" in login_problem("smtp.gmail.com", 465, "ssl", "me@example.com", "pw")


def test_real_smtp_is_blocked_in_tests():
    with pytest.raises(BaseException):
        senders.open_connection("smtp.gmail.com", 465, "ssl")


# ---------------------------------------------------------------- account settings

def gmail(address="me@example.com", password=None):
    p = account.PRESETS["gmail"]
    return EmailSettings("gmail", p.host, p.port, p.security, address, password)


def test_no_settings_until_saved():
    assert account.load() is None


def test_save_without_remembering_keeps_no_password():
    account.save(gmail(password="abcd efgh ijkl mnop"), remember_password=False)
    loaded = account.load()
    assert loaded.address == "me@example.com" and loaded.password is None
    assert "abcd" not in paths.email_settings_file().read_text()


def test_save_remembering_strips_spaces():
    account.save(gmail(password="abcd efgh ijkl mnop"), remember_password=True)
    assert account.load().password == "abcdefghijklmnop"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file modes")
def test_settings_file_is_private():
    account.save(gmail(password="x"), remember_password=True)
    assert os.stat(paths.email_settings_file()).st_mode & 0o077 == 0


def test_forget_removes_everything():
    account.save(gmail(password="x"), remember_password=True)
    account.forget()
    assert account.load() is None
    account.forget()  # twice is fine


def test_settings_problems():
    assert account.settings_problem(gmail()) is None
    assert "email address" in account.settings_problem(gmail(address="nope"))
    other = EmailSettings("other", "", 587, "starttls", "me@example.com")
    assert "SMTP server" in account.settings_problem(other)


def test_settings_live_in_the_data_folder():
    assert paths.email_settings_file().parent == paths.data_dir()
