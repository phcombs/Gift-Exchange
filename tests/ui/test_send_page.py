"""M5 UI tests: practice sending from the Send page, real mode waiting for sign-in, recovery, new exchange."""

import random
from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

from giftx import paths, pipeline
from giftx.storage import Storage

SCRIPT = """
from giftx import app
from giftx.ui import send
app.sidebar()
send.page()
"""
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
NAMES = ["Ann", "Bob", "Cy", "Dee"]


def store():
    paths.data_dir()
    return Storage(paths.db_path())


def drawn_group():
    s = store()
    gid = s.create_group("Family")
    ids = [s.add_person(gid, n, f"{n.lower()}@example.com") for n in NAMES]
    draw_id = s.save_draw(gid, {g: ids[(i + 1) % 4] for i, g in enumerate(ids)}, NOW)
    return s, gid, ids, draw_id


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


def test_practice_send_all_with_confirm_step():
    s, gid, ids, draw_id = drawn_group()
    at = load(gid)
    at.button(key="send_all").click()
    rerun(at)
    heading = [m.value for m in at.markdown if "Practice send" in m.value]
    assert heading == ["**Practice send for Family: 4 emails**"]
    confirm = at.dataframe[-1].value
    assert list(confirm.columns) == ["Giver", "Address"]
    assert list(confirm["Address"]) == [f"{n.lower()}@example.com" for n in NAMES]

    at.button(key="confirm_go").click()
    rerun(at)
    assert any(m.value.startswith("Wrote 4 practice emails") for m in at.success)
    assert len(list(paths.practice_dir(gid).iterdir())) == 4
    status = at.dataframe[-1].value
    assert set(status["Status"]) == {"written to a practice file"}
    assert s.draw_status(gid)[1] is None  # practice never locks


def test_cancel_closes_the_confirm_step():
    s, gid, ids, draw_id = drawn_group()
    at = load(gid)
    at.button(key="send_all").click()
    rerun(at)
    at.button(key="confirm_cancel").click()
    rerun(at)
    assert not any("Practice send" in m.value for m in at.markdown)
    assert not paths.practice_dir(gid).exists()


def test_real_mode_send_buttons_wait_for_email_setup():
    s, gid, ids, draw_id = drawn_group()
    at = load(gid)
    at.sidebar.radio(key="mode").set_value("real")
    rerun(at)
    assert at.button(key="send_all").disabled
    assert "Set up your email account on the Setup page first" in [c.value for c in at.caption]


def test_recovery_runs_once_per_process_and_database(clock):
    s, gid, ids, draw_id = drawn_group()
    pipeline.prepare_real(s, gid, random.Random(1), now=clock)
    first, second = s.sendable(draw_id, "real")[:2]
    s.claim(first.id, NOW, "ann@example.com")
    load(gid)
    assert {r.id: r.status for r in s.status_rows(draw_id, "real")}[first.id] == "unknown"

    s.claim(second.id, NOW, "bob@example.com")  # as if a send were in flight in this process
    load(gid)  # a new session in the same process does not run recovery again
    assert {r.id: r.status for r in s.status_rows(draw_id, "real")}[second.id] == "sending"


def test_real_status_table_and_it_went(fake_sender, clock):
    s, gid, ids, draw_id = drawn_group()
    pipeline.prepare_real(s, gid, random.Random(1), now=clock)
    pipeline.run_sends(s, draw_id, "real", fake_sender(unknown_on=1), clock)
    at = load(gid)
    at.sidebar.radio(key="mode").set_value("real")
    rerun(at)
    status = at.dataframe[-1].value
    texts = dict(zip(status["Giver"], status["Status"]))
    assert texts["Ann"] == "This may or may not have gone to ann@example.com. Check your Sent folder."
    assert texts["Bob"] == "waiting"
    at.selectbox(key="action_record").select(next(r.id for r in s.status_rows(draw_id, "real")
                                                  if r.giver_name == "Ann"))
    rerun(at)
    at.button(key="action_went").click()
    rerun(at)
    assert {r.giver_name: r.status for r in s.status_rows(draw_id, "real")}["Ann"] == "sent"


def test_start_a_new_exchange_states_count_and_keeps_people(fake_sender, clock):
    s, gid, ids, draw_id = drawn_group()
    pipeline.prepare_real(s, gid, random.Random(1), now=clock)
    pipeline.run_sends(s, draw_id, "real", fake_sender(fail_on=3), clock)
    at = load(gid)
    assert any("2 emails have already gone out" in m.value for m in at.markdown)
    assert at.button(key="new_exchange").disabled
    at.checkbox(key="new_exchange_sure").check()
    rerun(at)
    at.button(key="new_exchange").click()
    rerun(at)
    assert s.draw_status(gid) == (None, None, [])
    assert len(s.list_people(gid)) == 4
    assert at.button(key="draw").label == "Draw"
