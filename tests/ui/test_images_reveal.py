"""M7 UI tests: the Images page and Reveal."""

import random
import struct
import zlib
from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

from giftx import images, paths, pipeline
from giftx.storage import Storage

PAGE = """
from giftx import app
from giftx.ui import {module}
app.sidebar()
{module}.page()
"""
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def png(shade=0):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes([0, shade, shade, shade]))) + chunk(b"IEND", b""))


def load(module, gid=None):
    at = AppTest.from_string(PAGE.format(module=module))
    if gid is not None:
        at.session_state["group_id"] = gid
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def rerun(at):
    at.run(timeout=60)
    assert not at.exception, at.exception
    return at


def drawn():
    paths.data_dir()
    s = Storage(paths.db_path())
    gid = s.create_group("Family")
    ids = [s.add_person(gid, n, f"{n.lower()}@example.com") for n in ("Ann", "Bob", "Cy", "Dee")]
    draw_id = s.save_draw(gid, {g: ids[(i + 1) % 4] for i, g in enumerate(ids)}, NOW)
    return s, gid, ids, draw_id


def test_empty_library_says_emails_have_no_picture():
    at = load("images")
    assert any("No pictures yet" in m.value for m in at.markdown)


def test_gallery_and_delete():
    a, b = images.save_image(png(1)), images.save_image(png(2))
    at = load("images")
    assert any(m.value.startswith("2 pictures") for m in at.markdown)
    at.button(key=f"img_del_{a}").click()
    rerun(at)
    assert images.list_images() == [b]


def test_picture_in_use_cannot_be_deleted_and_says_by_whom():
    s, gid, ids, draw_id = drawn()
    name = images.save_image(png())
    pipeline.prepare_practice(s, gid, random.Random(1))
    at = load("images")
    assert at.button(key=f"img_del_{name}").disabled
    assert "Used by emails for Family" in [c.value for c in at.caption]


def test_reveal_is_off_and_reads_no_match_until_turned_on(monkeypatch):
    s, gid, ids, draw_id = drawn()
    calls = []
    real = Storage.get_assignments

    def spy(self, did):
        calls.append(did)
        return real(self, did)

    monkeypatch.setattr(Storage, "get_assignments", spy)
    at = load("send", gid)
    toggle = at.toggle(key=f"reveal_{gid}")
    assert toggle.value is False
    assert set(at.dataframe[0].value["Buys for"]) == {"match hidden"}
    assert calls == []

    toggle.set_value(True)
    rerun(at)
    assert calls == [draw_id]
    table = at.dataframe[0].value
    assert dict(zip(table["Giver"], table["Buys for"])) == {"Ann": "Bob", "Bob": "Cy", "Cy": "Dee", "Dee": "Ann"}

    assert load("send", gid).toggle(key=f"reveal_{gid}").value is False  # new tab: off again
