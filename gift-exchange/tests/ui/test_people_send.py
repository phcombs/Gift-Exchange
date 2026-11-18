"""M3 UI tests: People and Send pages, run through the real sidebar.

AppTest can't switch between function pages, so each test runs a tiny script: the app's sidebar,
then one page function. The data folder is the per-test temp folder set by conftest.
"""

import sqlite3
from datetime import datetime, timezone

import pytest
from streamlit.testing.v1 import AppTest

from giftx import paths
from giftx.storage import Storage
from giftx.ui.common import DRAW_CLEARED

SCRIPT = """
from giftx import app
from giftx.ui import {module}
app.sidebar()
{module}.page()
"""

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)

TWELVE = "\n".join(
    f"{name}, {name.lower()}@example.com"
    for name in ["Ann", "Bob", "Cy", "Dee", "Eve", "Fay", "Gus", "Hal", "Ida", "Jo", "Kit", "Lu"]
)


def load(module, group_id=None):
    at = AppTest.from_string(SCRIPT.format(module=module))
    if group_id is not None:
        at.session_state["group_id"] = group_id
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def rerun(at):
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def store():
    paths.data_dir()
    return Storage(paths.db_path())


def texts(at):
    return [e.value for kind in ("success", "info", "warning", "error") for e in getattr(at, kind)]


def make_group(names=("Ann", "Bob", "Cy", "Dee")):
    s = store()
    gid = s.create_group("Family")
    ids = [s.add_person(gid, n, f"{n.lower()}@example.com") for n in names]
    return s, gid, ids


def test_create_group_selects_it_and_paste_adds_twelve():
    at = load("people")
    at.text_input(key="new_group_name").input("Smiths")
    at.button[0].click()  # Create group
    rerun(at)
    s = store()
    (gid, name), = s.list_groups()
    assert name == "Smiths"
    assert at.session_state["group_id"] == gid
    assert "Group Smiths created. Add people below." in texts(at)

    at.text_area(key="paste_text").input(TWELVE)
    next(b for b in at.button if b.label == "Add these people").click()
    rerun(at)
    assert len(s.list_people(gid)) == 12
    assert "Added 12 people." in texts(at)


def test_bad_pasted_lines_are_listed_and_not_added():
    s, gid, _ = make_group(["Ann"])
    at = load("people", gid)
    at.text_area(key="paste_text").input("Smith, Jr., John, john@example.com\nBob, nope\nann, x@example.com")
    next(b for b in at.button if b.label == "Add these people").click()
    rerun(at)
    assert sorted(p.name for p in s.list_people(gid)) == ["Ann", "Smith, Jr., John"]
    errors = [e.value for e in at.error]
    assert any(e.startswith("Line 2 not added") for e in errors)
    assert any(e.startswith("Line 3 not added") for e in errors)


def test_problems_and_shared_address_notice_show():
    s = store()
    gid = s.create_group("G")
    s.add_person(gid, "Ann", "family@example.com")
    s.add_person(gid, "Bob", "family@example.com")
    s.add_person(gid, "bob", "bad-address")
    at = load("people", gid)
    assert "Ann and Bob share family@example.com. Each can read the other's match." in texts(at)
    assert any("appears 2 times" in e.value for e in at.error)
    send = load("send", gid)
    assert send.button(key="draw").disabled


def test_mark_couple_from_the_page():
    s, gid, (ann, bob, cy, dee) = make_group()
    at = load("people", gid)
    at.selectbox(key="couple_a").select(ann)
    at.selectbox(key="couple_b").select(bob)
    rerun(at)
    at.button(key="couple_set").click()
    rerun(at)
    partners = {p.name: p.partner_id for p in s.list_people(gid)}
    assert partners["Ann"] == bob and partners["Bob"] == ann


def test_draw_shows_givers_with_matches_hidden(monkeypatch):
    s, gid, ids = make_group()

    def spy(self, draw_id):
        pytest.fail("the Send page read the recipients")

    monkeypatch.setattr(Storage, "get_assignments", spy)
    at = load("send", gid)
    assert at.button(key="draw").label == "Draw"
    at.button(key="draw").click()
    rerun(at)
    table = at.dataframe[0].value
    assert list(table["Giver"]) == ["Ann", "Bob", "Cy", "Dee"]
    assert set(table["Buys for"]) == {"match hidden"}
    assert at.button(key="draw").label == "Draw again"
    assert s.draw_status(gid)[0] is not None


def test_impossible_draw_shows_the_reason():
    s, gid, (ann, bob) = make_group(["Ann", "Bob"])
    s.set_couple(ann, bob)
    at = load("send", gid)
    at.button(key="draw").click()
    rerun(at)
    assert "Two people who are a couple cannot draw each other. Add more people." in texts(at)
    assert s.draw_status(gid)[0] is None


def test_people_change_after_draw_clears_it_with_notice():
    s, gid, ids = make_group()
    s.save_draw(gid, {ids[i]: ids[(i + 1) % 4] for i in range(4)}, NOW)
    at = load("people", gid)
    at.text_input(key="add_name").input("Eve")
    at.text_input(key="add_email").input("eve@example.com")
    next(b for b in at.button if b.label == "Add person").click()
    rerun(at)
    assert DRAW_CLEARED in texts(at)
    assert s.draw_status(gid)[0] is None


def test_email_change_after_draw_keeps_it():
    s, gid, ids = make_group()
    draw_id = s.save_draw(gid, {ids[i]: ids[(i + 1) % 4] for i in range(4)}, NOW)
    at = load("people", gid)
    at.selectbox(key="edit_pid").select(ids[0])
    rerun(at)
    at.text_input(key=f"edit_email_{ids[0]}").input("new@example.com")
    at.button(key="edit_save").click()
    rerun(at)
    assert DRAW_CLEARED not in texts(at)
    assert s.draw_status(gid)[0] == draw_id
    assert s.list_people(gid)[0].email == "new@example.com"


def test_delete_group_needs_confirmation():
    s, gid, _ = make_group()
    at = load("people", gid)
    assert at.button(key="delete_group").disabled
    at.checkbox(key="delete_group_sure").check()
    rerun(at)
    at.button(key="delete_group").click()
    rerun(at)
    assert s.list_groups() == []
    assert at.sidebar.selectbox(key="group_id").value is None


def test_newer_database_is_refused_on_the_page():
    paths.data_dir()
    con = sqlite3.connect(paths.db_path())
    con.execute("PRAGMA user_version = 99")
    con.close()
    at = AppTest.from_string(SCRIPT.format(module="people"))
    at.run(timeout=60)
    assert "This data was made by a newer version of the app." in [e.value for e in at.error]


# ---------------------------------------------------------------- fixed matches and manual changes

def test_fix_a_match_then_draw_keeps_it():
    s, gid, (ann, bob, cy, dee) = make_group()
    at = load("send", gid)
    at.selectbox(key="pin_giver").select(ann)
    rerun(at)
    at.selectbox(key="pin_recipient").select(dee)
    rerun(at)
    at.button(key="pin_add").click()
    rerun(at)
    assert s.list_pins(gid) == {ann: dee}
    assert "Fixed: Ann buys for Dee." in texts(at)
    for _ in range(5):
        at.button(key="draw").click()
        rerun(at)
        assert s.get_assignments(s.draw_status(gid)[0])[ann] == dee


def test_remove_a_fixed_match():
    s, gid, (ann, bob, cy, dee) = make_group()
    s.set_pin(ann, dee)
    at = load("send", gid)
    at.button(key=f"pin_remove_{ann}").click()
    rerun(at)
    assert s.list_pins(gid) == {}


def test_change_a_match_after_the_draw_swaps_with_the_other_giver():
    s, gid, (ann, bob, cy, dee) = make_group()
    draw_id = s.save_draw(gid, {ann: bob, bob: cy, cy: dee, dee: ann}, NOW)
    at = load("send", gid)
    at.toggle(key=f"reveal_{gid}").set_value(True)
    rerun(at)
    at.selectbox(key="swap_giver").select(ann)
    rerun(at)
    at.selectbox(key="swap_recipient").select(dee)
    rerun(at)
    at.button(key="swap_go").click()
    rerun(at)
    assert s.get_assignments(draw_id) == {ann: dee, bob: cy, cy: bob, dee: ann}
    assert "Ann now buys for Dee; Cy now buys for Bob." in texts(at)


def test_change_that_would_make_someone_draw_themselves_is_refused():
    s, gid, (ann, bob, cy, dee) = make_group()
    draw_id = s.save_draw(gid, {ann: bob, bob: cy, cy: dee, dee: ann}, NOW)
    at = load("send", gid)
    at.toggle(key=f"reveal_{gid}").set_value(True)
    rerun(at)
    at.selectbox(key="swap_giver").select(ann)  # Ann had Bob; Bob is bought for by Ann
    rerun(at)
    at.selectbox(key="swap_recipient").select(cy)  # Cy is bought for by Bob -> Bob would get Bob
    rerun(at)
    at.button(key="swap_go").click()
    rerun(at)
    assert any("buying for themselves" in e.value for e in at.error)
    assert s.get_assignments(draw_id) == {ann: bob, bob: cy, cy: dee, dee: ann}


def test_no_change_controls_while_hidden_or_locked():
    s, gid, (ann, bob, cy, dee) = make_group()
    s.save_draw(gid, {ann: bob, bob: cy, cy: dee, dee: ann}, NOW)
    at = load("send", gid)
    assert not [b for b in at.button if b.key == "swap_go"]
    con = sqlite3.connect(s.db_path)
    con.execute("UPDATE draws SET locked_at = 'x'")
    con.commit()
    con.close()
    at = load("send", gid)
    at.toggle(key=f"reveal_{gid}").set_value(True)
    rerun(at)
    assert not [b for b in at.button if b.key == "swap_go"]


# ---------------------------------------------------------------- saved draws

def test_save_draw_again_and_restore_from_the_page(monkeypatch):
    s, gid, (ann, bob, cy, dee) = make_group()
    good = {ann: bob, bob: cy, cy: dee, dee: ann}
    s.save_draw(gid, good, NOW)
    reads = []
    real = Storage.get_assignments
    monkeypatch.setattr(Storage, "get_assignments", lambda self, d: reads.append(d) or real(self, d))

    at = load("send", gid)
    at.text_input(key="snap_name").input("Perfect")
    at.button(key="snap_save").click()
    rerun(at)
    assert "Saved the draw as Perfect." in texts(at)
    at.button(key="draw").click()  # draw again
    rerun(at)
    ((sid, name, _, usable),) = s.list_snapshots(gid)
    at.button(key=f"snap_restore_{sid}").click()
    rerun(at)
    assert "Restored the saved draw Perfect. The matches stay hidden." in texts(at)
    assert reads == []  # saving, listing and restoring never read the matches on the page
    assert real(s, s.draw_status(gid)[0]) == good


def test_unusable_saved_draw_cannot_be_restored_from_the_page():
    s, gid, (ann, bob, cy, dee) = make_group()
    s.save_draw(gid, {ann: bob, bob: cy, cy: dee, dee: ann}, NOW)
    sid = s.save_snapshot(gid, "Old", NOW)
    s.add_person(gid, "Eve", "eve@example.com")
    at = load("send", gid)
    assert at.button(key=f"snap_restore_{sid}").disabled
    assert any("people changed since" in m.value for m in at.markdown)
    at.button(key=f"snap_delete_{sid}").click()
    rerun(at)
    assert s.list_snapshots(gid) == []
