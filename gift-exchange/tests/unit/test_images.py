"""M7: the image library, picking, freezing on records, and the in-use rule (done item 7)."""

import random
import struct
import zlib
from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default

import pytest

from giftx import images, paths, pipeline
from giftx.model import Problem
from giftx.senders import PracticeSender
from giftx.storage import Storage

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
       b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def png(shade=0):
    """A real 1x1 PNG; shade makes different files."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = zlib.compress(bytes([0, shade, shade, shade]))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


@pytest.mark.parametrize("data,ext", [(png(), "png"), (GIF, "gif"), (b"\xff\xd8\xff\xe0rest", "jpg")])
def test_checked_by_content(data, ext):
    assert images.check_image(data) == ext


def test_renamed_text_file_and_big_file_are_refused():
    assert isinstance(images.check_image(b"hello, I am a text file"), Problem)
    big = b"\x89PNG\r\n\x1a\n" + b"\0" * images.MAX_BYTES
    problem = images.check_image(big)
    assert isinstance(problem, Problem) and "2 MB" in problem.message


def test_save_names_by_content_and_keeps_one_copy():
    first = images.save_image(png(1))
    assert first == images.save_image(png(1))
    second = images.save_image(GIF)
    assert first.endswith(".png") and second.endswith(".gif")
    assert images.list_images() == sorted([first, second])
    with pytest.raises(ValueError):
        images.save_image(b"not a picture")


def test_pick_is_none_without_images_and_random_with_them():
    rng = random.Random(3)
    assert images.pick(rng) is None
    names = {images.save_image(png(i)) for i in range(3)}
    assert {images.pick(rng) for _ in range(50)} == names


def test_delete_refused_while_in_use():
    name = images.save_image(png())
    assert images.delete_image(name, {name}).code == "in_use"
    assert name in images.list_images()
    assert images.delete_image(name, set()) is None
    assert images.list_images() == []


@pytest.fixture
def drawn():
    paths.data_dir()
    s = Storage(paths.db_path())
    gid = s.create_group("Family")
    ids = [s.add_person(gid, n, f"{n.lower()}@example.com") for n in ("Ann", "Bob", "Cy", "Dee")]
    draw_id = s.save_draw(gid, {g: ids[(i + 1) % 4] for i, g in enumerate(ids)}, NOW)
    return s, gid, draw_id


def test_no_images_means_no_picture_on_records(drawn):
    s, gid, draw_id = drawn
    pipeline.prepare_practice(s, gid, random.Random(1))
    assert {r.image_name for r in s.status_rows(draw_id, "practice")} == {None}


def test_each_record_gets_one_frozen_picture_and_each_email_one_attachment(drawn):
    s, gid, draw_id = drawn
    names = {images.save_image(png(1)), images.save_image(GIF)}
    pipeline.prepare_practice(s, gid, random.Random(1))
    frozen = {r.giver_name: r.image_name for r in s.status_rows(draw_id, "practice")}
    assert set(frozen.values()) <= names and None not in frozen.values()
    images.save_image(png(2))  # adding a picture later does not change prepared records
    assert {r.giver_name: r.image_name for r in s.status_rows(draw_id, "practice")} == frozen
    pipeline.run_sends(s, draw_id, "practice", PracticeSender(), lambda: NOW)
    for eml in paths.practice_dir(gid).iterdir():
        msg = message_from_bytes(eml.read_bytes(), policy=default)
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1 and attachments[0].get_filename().startswith("picture.")


def test_in_use_until_new_exchange(drawn):
    s, gid, draw_id = drawn
    name = images.save_image(png())
    pipeline.prepare_real(s, gid, random.Random(1), now=lambda: NOW)
    assert s.images_in_use() == {name}
    assert s.image_users() == {name: ["Family"]}
    assert images.delete_image(name, s.images_in_use()).code == "in_use"
    s.discard_draw(gid)
    assert s.images_in_use() == set()
    assert images.delete_image(name, s.images_in_use()) is None


def test_missing_frozen_picture_stops_before_claiming(drawn, fake_sender):
    s, gid, draw_id = drawn
    name = images.save_image(png())
    pipeline.prepare_real(s, gid, random.Random(1), now=lambda: NOW)
    (paths.images_dir() / name).unlink()  # removed outside the app
    sender = fake_sender()
    with pytest.raises(pipeline.MissingImage):
        pipeline.run_sends(s, draw_id, "real", sender, lambda: NOW)
    assert sender.calls == 0
    assert {r.status for r in s.status_rows(draw_id, "real")} == {"pending"}
