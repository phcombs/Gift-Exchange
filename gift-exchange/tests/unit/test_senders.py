from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default

from giftx import compose, paths, pipeline
from giftx.model import Outgoing, Rejected, Sent
from giftx.senders import PracticeSender

NOW = datetime(2026, 11, 15, 1, 30, tzinfo=timezone.utc)


def clock():
    return NOW


def test_practice_sender_writes_the_key_as_a_file():
    result = PracticeSender().send(Outgoing("7/12", "a@example.com", b"raw email"))
    assert result == Sent()
    assert (paths.practice_root() / "7" / "12.eml").read_bytes() == b"raw email"


def test_practice_sender_never_overwrites():
    sender = PracticeSender()
    sender.send(Outgoing("7/12", "a@example.com", b"first"))
    result = sender.send(Outgoing("7/12", "a@example.com", b"second"))
    assert isinstance(result, Rejected)
    assert "a@example.com" not in result.reason
    assert (paths.practice_root() / "7" / "12.eml").read_bytes() == b"first"


def test_practice_sender_reports_disk_errors_as_rejected():
    paths.data_dir()
    paths.practice_root().write_text("a file where the folder should be")
    result = PracticeSender().send(Outgoing("test/x", "a@example.com", b"raw"))
    assert isinstance(result, Rejected)


def test_test_send_writes_one_eml_named_by_utc_time_with_made_up_names():
    result = pipeline.test_send(
        PracticeSender(), "me@example.com", "Your match, {giver}", "Hi {giver}, you buy for {recipient}.",
        None, clock,
    )
    assert result == Sent()
    files = list(paths.practice_test_dir().iterdir())
    assert [f.name for f in files] == ["20261115T013000Z.eml"]
    msg = message_from_bytes(files[0].read_bytes(), policy=default)
    assert msg["To"] == "me@example.com"
    assert msg["Subject"] == "Your match, Alex"
    assert msg.get_content() == "Hi Alex, you buy for Sam.\n"


def test_test_send_adds_a_number_on_a_clash():
    for _ in range(3):
        pipeline.test_send(PracticeSender(), "me@example.com", "s {giver}", "{giver}", None, clock)
    names = sorted(f.name for f in paths.practice_test_dir().iterdir())
    assert names == ["20261115T013000Z-2.eml", "20261115T013000Z-3.eml", "20261115T013000Z.eml"]


def test_test_send_reads_no_draw_and_writes_no_record(monkeypatch):
    from giftx.storage import Storage

    def forbidden(*args, **kwargs):
        raise AssertionError("storage used by a test send")

    for name in ("get_assignments", "draw_status", "list_people", "__init__"):
        monkeypatch.setattr(Storage, name, forbidden)
    assert pipeline.test_send(PracticeSender(), "me@example.com", "s", "{giver}", None, clock) == Sent()


def test_test_send_attaches_a_stored_image():
    paths.images_dir().mkdir(parents=True)
    (paths.images_dir() / "abc.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    pipeline.test_send(PracticeSender(), "me@example.com", "s", "{giver}", "abc.png", clock)
    (eml,) = paths.practice_test_dir().iterdir()
    msg = message_from_bytes(eml.read_bytes(), policy=default)
    ((name, ctype, data, cid),) = compose.inline_images(msg)
    assert (name, ctype) == ("picture.png", "image/png")
