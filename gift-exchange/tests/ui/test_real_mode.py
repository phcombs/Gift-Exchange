"""M6 UI tests: Setup page email account, then real sending through a fake SMTP server."""

import smtplib
from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default

from streamlit.testing.v1 import AppTest

from giftx import account, paths
from giftx.storage import Storage

PAGE = """
from giftx import app
from giftx.ui import {module}
app.sidebar()
{module}.page()
"""
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
NAMES = ["Ann", "Bob", "Cy", "Dee"]


def load(module, gid=None, real=False):
    at = AppTest.from_string(PAGE.format(module=module))
    if gid is not None:
        at.session_state["group_id"] = gid
    if real:
        at.session_state["mode"] = "real"
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def rerun(at):
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def set_up_account(smtp_server, remember=False):
    at = load("setup")
    at.text_input(key="acct_address").input("me@example.com")
    at.text_input(key="acct_password").input("abcd efgh ijkl mnop")
    if remember:
        at.checkbox(key="acct_remember").check()
    at.button(key="acct_save").click()
    return rerun(at)


def drawn_group():
    paths.data_dir()
    s = Storage(paths.db_path())
    gid = s.create_group("Family")
    ids = [s.add_person(gid, n, f"{n.lower()}@example.com") for n in NAMES]
    draw_id = s.save_draw(gid, {g: ids[(i + 1) % 4] for i, g in enumerate(ids)}, NOW)
    return s, gid, ids, draw_id


def test_setup_saves_after_a_successful_sign_in(smtp_server):
    at = set_up_account(smtp_server)
    assert smtp_server.calls == [("smtp.gmail.com", 465, "ssl")]
    assert smtp_server.logins == [("me@example.com", "abcdefghijklmnop")]
    assert any("Real mode is ready" in m.value for m in at.success)
    saved = account.load()
    assert saved.address == "me@example.com" and saved.password is None  # not remembered


def test_remembered_password_is_saved(smtp_server):
    set_up_account(smtp_server, remember=True)
    assert account.load().password == "abcdefghijklmnop"


def test_refused_sign_in_saves_nothing(smtp_server):
    smtp_server.login_error = smtplib.SMTPAuthenticationError(535, b"bad")
    at = set_up_account(smtp_server)
    assert any("refused the sign-in" in e.value for e in at.error)
    assert account.load() is None


def test_forget_account(smtp_server):
    set_up_account(smtp_server, remember=True)
    at = load("setup")
    at.button(key="acct_forget").click()
    rerun(at)
    assert account.load() is None


def test_real_send_all_goes_through_smtp_and_locks_the_draw(smtp_server):
    set_up_account(smtp_server)
    s, gid, ids, draw_id = drawn_group()
    at = load("send", gid, real=True)
    assert not at.button(key="send_all").disabled
    at.button(key="send_all").click()
    rerun(at)
    assert any("Real send for Family: 4 emails" in m.value for m in at.markdown)
    at.button(key="confirm_go").click()
    rerun(at)
    assert "Sent 4 emails." in [m.value for m in at.success]
    assert sorted(to[0] for _, to, _ in smtp_server.sent) == [f"{n.lower()}@example.com" for n in NAMES]
    ann = next(raw for _, to, raw in smtp_server.sent if to == ["ann@example.com"])
    assert "You are buying a gift for Bob." in message_from_bytes(ann, policy=default).get_content()
    assert s.draw_status(gid)[1] is not None  # locked
    assert {r.status for r in s.status_rows(draw_id, "real")} == {"sent"}


def test_real_send_stops_at_a_refused_address_and_resumes(smtp_server):
    set_up_account(smtp_server)
    s, gid, ids, draw_id = drawn_group()
    smtp_server.send_error = smtplib.SMTPRecipientsRefused({"x": (550, b"no")})
    at = load("send", gid, real=True)
    at.button(key="send_all").click()
    rerun(at)
    at.button(key="confirm_go").click()
    rerun(at)
    assert any(w.value.startswith("Stopped at Ann: failed") for w in at.warning)
    smtp_server.send_error = None
    at.button(key="send_all").click()
    rerun(at)
    at.button(key="confirm_go").click()
    rerun(at)
    assert {r.status for r in s.status_rows(draw_id, "real")} == {"sent"}
    assert len(smtp_server.sent) == 4


def test_real_test_send_from_the_message_page(smtp_server):
    set_up_account(smtp_server)
    paths.data_dir()
    gid = Storage(paths.db_path()).create_group("Family")
    at = load("message", gid, real=True)
    at.text_input(key="test_to").input("me@example.com")
    at.button(key="test_send").click()
    rerun(at)
    assert "Test email sent to me@example.com." in [m.value for m in at.success]
    ((_, to, raw),) = smtp_server.sent
    assert to == ["me@example.com"]
    assert "Hi Alex," in message_from_bytes(raw, policy=default).get_content()
