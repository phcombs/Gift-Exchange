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
    con.execute("PRAGMA user_version = 2")
    con.close()
    at = AppTest.from_string(SCRIPT.format(module="people"))
    at.run(timeout=60)
    assert "This data was made by a newer version of the app." in [e.value for e in at.error]
