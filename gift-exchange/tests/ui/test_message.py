"""M4 UI tests: the Message page (save rules, preview, practice test send)."""

from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

from giftx import paths
from giftx.compose import DEFAULT_BODY, DEFAULT_SUBJECT
from giftx.storage import Storage

SCRIPT = """
from giftx import app
from giftx.ui import message
app.sidebar()
message.page()
"""


def store():
    paths.data_dir()
    return Storage(paths.db_path())


def load(gid):
    at = AppTest.from_string(SCRIPT)
    at.session_state["group_id"] = gid
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def rerun(at):
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def group():
    s = store()
    gid = s.create_group("Family")
    return s, gid


def all_text(at):
    parts = [e.value for kind in ("success", "info", "warning", "error", "text", "markdown", "caption")
             for e in getattr(at, kind)]
    return "\n".join(str(p) for p in parts)


def test_shows_the_saved_message_and_save_is_off_until_changed():
    s, gid = group()
    at = load(gid)
    assert at.text_input(key=f"msg_subject_{gid}").value == DEFAULT_SUBJECT
    assert at.text_area(key=f"msg_body_{gid}").value == DEFAULT_BODY
    assert at.button(key="msg_save").disabled


def test_subject_with_recipient_is_not_saved():
    s, gid = group()
    at = load(gid)
    at.text_input(key=f"msg_subject_{gid}").input("{giver} buys for {recipient}")
    rerun(at)
    at.button(key="msg_save").click()
    rerun(at)
    assert any("subject can't contain {recipient}" in e.value for e in at.error)
    assert s.get_message(gid)[0] == DEFAULT_SUBJECT


def test_body_without_giver_is_not_saved():
    s, gid = group()
    at = load(gid)
    at.text_area(key=f"msg_body_{gid}").input("You buy for {recipient}")
    rerun(at)
    at.button(key="msg_save").click()
    rerun(at)
    assert any("must contain {giver}" in e.value for e in at.error)
    assert s.get_message(gid)[1] == DEFAULT_BODY


def test_body_without_recipient_saves_with_a_warning():
    s, gid = group()
    at = load(gid)
    at.text_area(key=f"msg_body_{gid}").input("Hello {giver}")
    rerun(at)
    at.button(key="msg_save").click()
    rerun(at)
    assert s.get_message(gid)[1] == "Hello {giver}"
    assert any("doesn't contain {recipient}" in w.value for w in at.warning)
    assert "Message saved." in [m.value for m in at.success]


def test_back_to_default():
    s, gid = group()
    s.set_message(gid, "Custom {giver}", "Custom {giver} {recipient}")
    at = load(gid)
    at.button(key="msg_default").click()
    rerun(at)
    assert at.text_input(key=f"msg_subject_{gid}").value == DEFAULT_SUBJECT
    assert s.get_message(gid)[0] == "Custom {giver}"  # not saved until Save


def test_preview_uses_made_up_names_and_never_the_draw(monkeypatch):
    s, gid = group()
    ids = [s.add_person(gid, n, f"{n.lower()}@example.com") for n in ("Quinn", "Rory", "Tess")]
    s.save_draw(gid, {ids[0]: ids[1], ids[1]: ids[2], ids[2]: ids[0]}, datetime.now(timezone.utc))
    monkeypatch.setattr(Storage, "get_assignments", lambda *a: (_ for _ in ()).throw(AssertionError("read")))
    at = load(gid)
    text = all_text(at)
    assert "Hi Alex," in text and "You are buying a gift for Sam." in text
    for name in ("Quinn", "Rory", "Tess"):
        assert name not in text


def test_practice_test_send_writes_one_file_and_no_record():
    s, gid = group()
    at = load(gid)
    at.text_input(key="test_to").input("me@example.com")
    at.button(key="test_send").click()
    rerun(at)
    assert any("Practice email written" in m.value for m in at.success)
    files = list(paths.practice_test_dir().iterdir())
    assert len(files) == 1 and files[0].suffix == ".eml"
    assert s.draw_status(gid) == (None, None, [])


def test_test_send_needs_a_valid_address():
    s, gid = group()
    at = load(gid)
    at.text_input(key="test_to").input("not an address")
    at.button(key="test_send").click()
    rerun(at)
    assert at.error
    assert not paths.practice_test_dir().exists()


def test_real_mode_test_send_waits_for_email_setup():
    s, gid = group()
    at = load(gid)
    at.sidebar.radio(key="mode").set_value("real")
    rerun(at)
    assert at.button(key="test_send").disabled
    assert "Set up your email account on the Setup page first" in [c.value for c in at.caption]
