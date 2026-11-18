import sqlite3
from datetime import datetime, timezone

import pytest

from giftx import paths
from giftx.compose import DEFAULT_BODY, DEFAULT_SUBJECT
from giftx.storage import DuplicateGroup, Locked, NewerVersion, Storage

NOW = datetime(2026, 11, 15, 1, 30, tzinfo=timezone.utc)


@pytest.fixture
def store():
    paths.data_dir()
    return Storage(paths.db_path())


def group_with(store, *names):
    gid = store.create_group("Family")
    ids = [store.add_person(gid, n, f"{n.lower()}@example.com") for n in names]
    return gid, ids


def ring(ids):
    return {g: ids[(i + 1) % len(ids)] for i, g in enumerate(ids)}


def lock(store, gid):
    con = sqlite3.connect(store.db_path)
    con.execute("UPDATE draws SET locked_at = ? WHERE group_id = ?", (NOW.isoformat(), gid))
    con.commit()
    con.close()


def partners(store, gid):
    return {p.name: p.partner_id for p in store.list_people(gid)}


def test_new_file_gets_schema_version_1(store):
    con = sqlite3.connect(paths.db_path())
    assert con.execute("PRAGMA user_version").fetchone()[0] == 3
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"groups", "people", "draws", "assignments", "sends"} <= tables
    Storage(paths.db_path())  # reopening an existing file is fine


def test_newer_file_is_refused(tmp_path):
    db = tmp_path / "newer.sqlite3"
    con = sqlite3.connect(db)
    con.execute("PRAGMA user_version = 99")
    con.close()
    with pytest.raises(NewerVersion) as err:
        Storage(db)
    assert str(err.value) == "This data was made by a newer version of the app."


def test_groups_are_created_listed_and_deleted(store):
    a = store.create_group("Smiths")
    b = store.create_group("  Parkers  ")
    assert store.list_groups() == [(b, "Parkers"), (a, "Smiths")]
    assert store.get_message(a) == (DEFAULT_SUBJECT, DEFAULT_BODY)
    with pytest.raises(DuplicateGroup):
        store.create_group("smiths")
    store.add_person(a, "Ann", "ann@example.com")
    store.delete_group(a)
    assert store.list_groups() == [(b, "Parkers")]
    assert store.list_people(a) == []


def test_groups_are_separate(store):
    a = store.create_group("A")
    b = store.create_group("B")
    store.add_person(a, "Ann", "ann@example.com")
    store.add_person(b, "Bob", "bob@example.com")
    assert [p.name for p in store.list_people(a)] == ["Ann"]
    assert [p.name for p in store.list_people(b)] == ["Bob"]


def test_people_are_trimmed(store):
    gid = store.create_group("G")
    pid = store.add_person(gid, "  Ann  Lee ", " ann@example.com ")
    (p,) = store.list_people(gid)
    assert (p.id, p.name, p.email, p.partner_id) == (pid, "Ann Lee", "ann@example.com", None)


def test_couples_are_symmetric_and_replace_earlier_partners(store):
    gid, (ann, bob, cy, dee) = group_with(store, "Ann", "Bob", "Cy", "Dee")
    store.set_couple(ann, bob)
    assert partners(store, gid) == {"Ann": bob, "Bob": ann, "Cy": None, "Dee": None}
    store.set_couple(bob, cy)
    assert partners(store, gid) == {"Ann": None, "Bob": cy, "Cy": bob, "Dee": None}
    store.clear_couple(cy)
    assert set(partners(store, gid).values()) == {None}


def test_deleting_one_half_clears_the_other(store):
    gid, (ann, bob) = group_with(store, "Ann", "Bob")
    store.set_couple(ann, bob)
    store.delete_person(ann)
    assert partners(store, gid) == {"Bob": None}


def test_couple_across_groups_is_refused(store):
    a = store.create_group("A")
    b = store.create_group("B")
    x = store.add_person(a, "X", "x@example.com")
    y = store.add_person(b, "Y", "y@example.com")
    with pytest.raises(Exception):
        store.set_couple(x, y)


def test_draw_is_saved_and_status_hides_recipients(store):
    gid, ids = group_with(store, "Ann", "Bob", "Cy")
    draw_id = store.save_draw(gid, ring(ids), NOW)
    got_id, locked_at, givers = store.draw_status(gid)
    assert (got_id, locked_at) == (draw_id, None)
    assert givers == [(ids[0], "Ann"), (ids[1], "Bob"), (ids[2], "Cy")]
    assert store.get_assignments(draw_id) == ring(ids)


def test_draw_again_replaces_the_draw(store):
    gid, ids = group_with(store, "Ann", "Bob", "Cy")
    store.save_draw(gid, ring(ids), NOW)
    second = store.save_draw(gid, ring(ids[::-1]), NOW)
    assert store.draw_status(gid)[0] == second
    assert store.get_assignments(second) == ring(ids[::-1])


def test_draw_for_stale_people_is_refused(store):
    gid, ids = group_with(store, "Ann", "Bob", "Cy")
    with pytest.raises(Exception):
        store.save_draw(gid, ring(ids[:2]), NOW)


@pytest.mark.parametrize("change", ["add", "delete", "rename", "couple", "uncouple"])
def test_people_changes_clear_an_unlocked_draw(store, change):
    gid, ids = group_with(store, "Ann", "Bob", "Cy", "Dee")
    if change == "uncouple":
        store.set_couple(ids[0], ids[1])
    store.save_draw(gid, ring(ids), NOW)
    {
        "add": lambda: store.add_person(gid, "Eve", "eve@example.com"),
        "delete": lambda: store.delete_person(ids[3]),
        "rename": lambda: store.rename_person(ids[0], "Annie"),
        "couple": lambda: store.set_couple(ids[2], ids[3]),
        "uncouple": lambda: store.clear_couple(ids[0]),
    }[change]()
    assert store.draw_status(gid) == (None, None, [])


def test_email_change_keeps_the_draw(store):
    gid, ids = group_with(store, "Ann", "Bob", "Cy")
    draw_id = store.save_draw(gid, ring(ids), NOW)
    store.update_email(ids[0], "new@example.com")
    assert store.draw_status(gid)[0] == draw_id
    assert store.list_people(gid)[0].email == "new@example.com"


def test_locked_draw_allows_only_email_changes(store):
    gid, ids = group_with(store, "Ann", "Bob", "Cy", "Dee")
    draw_id = store.save_draw(gid, ring(ids), NOW)
    lock(store, gid)
    for change in [
        lambda: store.add_person(gid, "Eve", "eve@example.com"),
        lambda: store.delete_person(ids[0]),
        lambda: store.rename_person(ids[0], "Annie"),
        lambda: store.set_couple(ids[0], ids[1]),
        lambda: store.clear_couple(ids[0]),
        lambda: store.save_draw(gid, ring(ids), NOW),
        lambda: store.delete_group(gid),
    ]:
        with pytest.raises(Locked):
            change()
    store.update_email(ids[0], "fixed@example.com")
    assert store.draw_status(gid)[0] == draw_id
    assert len(store.list_people(gid)) == 4


def test_discard_draw_unlocks_and_keeps_people(store):
    gid, ids = group_with(store, "Ann", "Bob", "Cy")
    store.save_draw(gid, ring(ids), NOW)
    lock(store, gid)
    assert store.discard_draw(gid) == 0
    assert store.draw_status(gid) == (None, None, [])
    assert len(store.list_people(gid)) == 3
    store.add_person(gid, "Dee", "dee@example.com")  # no longer locked


def test_storage_is_the_only_module_importing_sqlite3():
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "giftx"
    users = [
        f.name for f in src.rglob("*.py")
        if "import sqlite3" in f.read_text(encoding="utf-8")
    ]
    assert users == ["storage.py"]


# ---------------------------------------------------------------- fixed matches and manual changes

def test_version_1_file_is_upgraded_with_its_data(tmp_path):
    db = tmp_path / "v1.sqlite3"
    s = Storage(db)
    gid = s.create_group("G")
    s.add_person(gid, "Ann", "ann@example.com")
    con = sqlite3.connect(db)
    for table in ("saved_matches", "saved_draws", "pins"):
        con.execute(f"DROP TABLE {table}")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()
    upgraded = Storage(db)
    assert [p.name for p in upgraded.list_people(gid)] == ["Ann"]
    assert upgraded.list_pins(gid) == {}
    assert upgraded.list_snapshots(gid) == []
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 3
    con.close()


def test_pins_replace_conflicts_and_clear_the_draw(store):
    gid, (ann, bob, cy, dee) = group_with(store, "Ann", "Bob", "Cy", "Dee")
    store.set_pin(ann, bob)
    store.set_pin(cy, bob)  # Bob can only be bought for once: replaces Ann's pin
    assert store.list_pins(gid) == {cy: bob}
    store.set_pin(cy, dee)  # one pin per giver
    assert store.list_pins(gid) == {cy: dee}
    store.save_draw(gid, {ann: bob, bob: cy, cy: dee, dee: ann}, NOW)
    store.remove_pin(cy)
    assert store.list_pins(gid) == {}
    assert store.draw_status(gid)[0] is None
    with pytest.raises(Exception):
        store.set_pin(ann, ann)


def test_pins_go_with_deleted_people_and_are_locked_with_the_draw(store):
    gid, (ann, bob, cy, dee) = group_with(store, "Ann", "Bob", "Cy", "Dee")
    store.set_pin(ann, bob)
    store.delete_person(bob)
    assert store.list_pins(gid) == {}
    store.save_draw(gid, {ann: cy, cy: dee, dee: ann}, NOW)
    lock(store, gid)
    with pytest.raises(Locked):
        store.set_pin(ann, cy)


def test_update_assignment_changes_matches_and_drops_practice_records(store):
    gid, (ann, bob, cy) = group_with(store, "Ann", "Bob", "Cy")
    draw_id = store.save_draw(gid, {ann: bob, bob: cy, cy: ann}, NOW)
    from giftx.model import NewRecord
    store.replace_practice_records(draw_id, [NewRecord(ann, "s", "b", None)])
    store.update_assignment(gid, {ann: cy, cy: bob, bob: ann})
    assert store.get_assignments(draw_id) == {ann: cy, cy: bob, bob: ann}
    assert store.draw_status(gid)[0] == draw_id
    assert store.status_rows(draw_id, "practice") == []
    with pytest.raises(Exception):
        store.update_assignment(gid, {ann: ann, bob: cy, cy: bob})
    with pytest.raises(Exception):
        store.update_assignment(gid, {ann: bob, bob: ann})  # Cy left out
    lock(store, gid)
    with pytest.raises(Locked):
        store.update_assignment(gid, {ann: bob, bob: cy, cy: ann})


# ---------------------------------------------------------------- saved draws

def test_save_and_restore_a_draw_after_drawing_again(store):
    gid, (ann, bob, cy, dee) = group_with(store, "Ann", "Bob", "Cy", "Dee")
    good = {ann: bob, bob: cy, cy: dee, dee: ann}
    store.save_draw(gid, good, NOW)
    sid = store.save_snapshot(gid, "  Good one ", NOW)
    store.save_draw(gid, {ann: cy, cy: ann, bob: dee, dee: bob}, NOW)  # "Draw again"
    ((listed_id, name, created_at, usable),) = store.list_snapshots(gid)
    assert (listed_id, name, usable) == (sid, "Good one", True)
    draw_id = store.restore_snapshot(sid, NOW)
    assert store.get_assignments(draw_id) == good
    assert store.draw_status(gid)[0] == draw_id


def test_restore_after_a_people_change_that_cleared_the_draw(store):
    gid, (ann, bob, cy, dee) = group_with(store, "Ann", "Bob", "Cy", "Dee")
    good = {ann: bob, bob: cy, cy: dee, dee: ann}
    store.save_draw(gid, good, NOW)
    sid = store.save_snapshot(gid, "Keep", NOW)
    store.set_couple(cy, dee)  # clears the draw
    assert store.draw_status(gid)[0] is None
    assert store.get_assignments(store.restore_snapshot(sid, NOW)) == good


def test_snapshot_unusable_after_people_change(store):
    gid, (ann, bob, cy, dee) = group_with(store, "Ann", "Bob", "Cy", "Dee")
    store.save_draw(gid, {ann: bob, bob: cy, cy: dee, dee: ann}, NOW)
    added = store.save_snapshot(gid, "Before Eve", NOW)
    removed = store.save_snapshot(gid, "Before Dee left", NOW)
    store.add_person(gid, "Eve", "eve@example.com")
    assert {s[1]: s[3] for s in store.list_snapshots(gid)} == {"Before Eve": False, "Before Dee left": False}
    with pytest.raises(Exception):
        store.restore_snapshot(added, NOW)
    store.delete_person(dee)
    with pytest.raises(Exception):
        store.restore_snapshot(removed, NOW)


def test_snapshot_rules(store):
    gid, (ann, bob, cy) = group_with(store, "Ann", "Bob", "Cy")
    with pytest.raises(Exception):
        store.save_snapshot(gid, "Nothing yet", NOW)  # no draw
    store.save_draw(gid, {ann: bob, bob: cy, cy: ann}, NOW)
    sid = store.save_snapshot(gid, "A", NOW)
    with pytest.raises(Exception):
        store.save_snapshot(gid, "a", NOW)  # same name, ignoring case
    with pytest.raises(Exception):
        store.save_snapshot(gid, "   ", NOW)
    lock(store, gid)
    with pytest.raises(Locked):
        store.restore_snapshot(sid, NOW)
    store.delete_snapshot(sid)
    assert store.list_snapshots(gid) == []


def test_snapshots_survive_a_new_exchange_and_go_with_the_group(store):
    gid, (ann, bob, cy) = group_with(store, "Ann", "Bob", "Cy")
    store.save_draw(gid, {ann: bob, bob: cy, cy: ann}, NOW)
    store.save_snapshot(gid, "Last year", NOW)
    store.discard_draw(gid)
    assert len(store.list_snapshots(gid)) == 1
    store.delete_group(gid)
    assert store.list_snapshots(gid) == []
