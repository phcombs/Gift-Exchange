"""M5: the send pipeline against fake senders (done items 3 to 6)."""

import inspect
import random
import threading
from email import message_from_bytes
from email.policy import default

import pytest

from giftx import paths, pipeline
from giftx.model import Sent
from giftx.senders import PracticeSender
from giftx.storage import Locked, Storage

NAMES = ["Ann", "Bob", "Cy", "Dee", "Eve"]


@pytest.fixture
def setup(clock):
    paths.data_dir()
    store = Storage(paths.db_path())
    gid = store.create_group("Family")
    ids = [store.add_person(gid, n, f"{n.lower()}@example.com") for n in NAMES]
    draw_id = store.save_draw(gid, {g: ids[(i + 1) % len(ids)] for i, g in enumerate(ids)}, clock())
    return store, gid, ids, draw_id


def statuses(store, draw_id, mode="real"):
    return {r.giver_name: r.status for r in store.status_rows(draw_id, mode)}


def real_run(store, gid, draw_id, sender, clock, **kw):
    pipeline.prepare_real(store, gid, random.Random(1), now=clock)
    return pipeline.run_sends(store, draw_id, "real", sender, clock, **kw)


def test_full_run_sends_each_person_their_own_match(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    sender = fake_sender()
    summary = real_run(store, gid, draw_id, sender, clock)
    assert (summary.sent, summary.failed, summary.unknown, summary.stopped_at) == (5, 0, 0, None)
    assert set(statuses(store, draw_id).values()) == {"sent"}
    bodies = {
        m.to: message_from_bytes(m.raw, policy=default).get_content() for m in sender.delivered
    }
    assert "You are buying a gift for Bob." in bodies["ann@example.com"]
    assert "Hi Ann," in bodies["ann@example.com"]


def test_rejection_stops_and_a_second_run_sends_only_the_rest(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    summary = real_run(store, gid, draw_id, fake_sender(fail_on=3), clock)
    assert (summary.sent, summary.failed, summary.stopped_at) == (2, 1, "Cy")
    assert summary.remaining == 2
    assert statuses(store, draw_id) == {
        "Ann": "sent", "Bob": "sent", "Cy": "failed", "Dee": "pending", "Eve": "pending",
    }
    second = fake_sender()
    pipeline.run_sends(store, draw_id, "real", second, clock)
    # pending first, then the failed one
    assert [m.to for m in second.delivered] == ["dee@example.com", "eve@example.com", "cy@example.com"]
    assert set(statuses(store, draw_id).values()) == {"sent"}


def test_crash_after_delivery_is_recorded_unknown_and_never_resent(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    sender = fake_sender(crash_on=2)
    with pytest.raises(BaseException):
        real_run(store, gid, draw_id, sender, clock)
    assert statuses(store, draw_id)["Bob"] == "unknown"
    again = fake_sender()
    pipeline.run_sends(store, draw_id, "real", again, clock)
    assert "bob@example.com" not in [m.to for m in again.delivered]
    assert len(again.delivered) == 3


def test_unknown_stops_the_run(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    summary = real_run(store, gid, draw_id, fake_sender(unknown_on=1), clock)
    assert (summary.sent, summary.unknown, summary.stopped_at, summary.remaining) == (0, 1, "Ann", 4)
    assert list(statuses(store, draw_id).values()).count("pending") == 4


def test_recover_turns_sending_into_unknown(setup, clock):
    store, gid, ids, draw_id = setup
    pipeline.prepare_real(store, gid, random.Random(1), now=clock)
    record = store.sendable(draw_id, "real")[0]
    assert store.claim(record.id, clock(), "ann@example.com")
    assert store.recover_all_sending() == 1
    assert statuses(store, draw_id)[record.giver_name] == "unknown"
    assert store.recover_all_sending() == 0


def test_two_threads_send_exactly_one_email_per_person(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    sender = fake_sender()
    barrier = threading.Barrier(2)
    errors = []

    def worker():
        try:
            barrier.wait()
            pipeline.prepare_real(store, gid, random.Random(), now=clock)
            pipeline.run_sends(store, draw_id, "real", sender, clock)
        except Exception as err:  # pragma: no cover - reported below
            errors.append(err)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    assert sorted(m.to for m in sender.delivered) == sorted(f"{n.lower()}@example.com" for n in NAMES)
    assert len(store.status_rows(draw_id, "real")) == 5


def test_second_prepare_real_reuses_the_records(setup, clock):
    store, gid, ids, draw_id = setup
    assert pipeline.prepare_real(store, gid, random.Random(1), now=clock) is True
    assert pipeline.prepare_real(store, gid, random.Random(2), now=clock) is False
    assert len(store.status_rows(draw_id, "real")) == 5


def test_practice_run_never_locks_and_never_touches_real_records(setup, clock):
    store, gid, ids, draw_id = setup
    pipeline.prepare_practice(store, gid, random.Random(1))
    summary = pipeline.run_sends(store, draw_id, "practice", PracticeSender(), clock)
    assert summary.sent == 5
    assert store.draw_status(gid)[1] is None
    assert store.status_rows(draw_id, "real") == []
    files = sorted((paths.practice_dir(gid)).iterdir())
    assert len(files) == 5

    pipeline.prepare_practice(store, gid, random.Random(1))  # a second practice run starts fresh
    assert set(statuses(store, draw_id, "practice").values()) == {"pending"}
    assert all(r.started_at is None for r in store.status_rows(draw_id, "practice"))
    assert not paths.practice_dir(gid).exists()


def test_it_went_only_changes_unknown(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    real_run(store, gid, draw_id, fake_sender(unknown_on=1), clock)
    rows = {r.giver_name: r for r in store.status_rows(draw_id, "real")}
    assert store.mark_went(rows["Ann"].id) is True
    assert statuses(store, draw_id)["Ann"] == "sent"
    assert store.mark_went(rows["Ann"].id) is False  # already sent
    assert store.mark_went(rows["Bob"].id) is False  # pending


def test_send_again_after_address_fix_goes_to_the_new_address(setup, fake_sender, clock):
    """CUJ 5."""
    store, gid, ids, draw_id = setup
    real_run(store, gid, draw_id, fake_sender(), clock)
    store.update_email(ids[0], "ann.fixed@example.com")  # allowed on a locked draw
    ann = next(r for r in store.status_rows(draw_id, "real") if r.giver_name == "Ann")
    assert store.reset_to_pending(ann.id)
    sender = fake_sender()
    pipeline.run_sends(store, draw_id, "real", sender, clock, only=ann.id)
    assert [m.to for m in sender.delivered] == ["ann.fixed@example.com"]
    assert next(r for r in store.status_rows(draw_id, "real") if r.giver_name == "Ann").to_address == (
        "ann.fixed@example.com"
    )


def test_real_records_lock_the_draw(setup, clock):
    store, gid, ids, draw_id = setup
    pipeline.prepare_real(store, gid, random.Random(1), now=clock)
    assert store.draw_status(gid)[1] is not None
    for change in [
        lambda: store.add_person(gid, "Fay", "fay@example.com"),
        lambda: store.set_couple(ids[0], ids[1]),
        lambda: store.delete_group(gid),
    ]:
        with pytest.raises(Locked):
            change()
    store.update_email(ids[1], "bob2@example.com")


def test_new_exchange_reports_sent_count_and_keeps_people(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup
    real_run(store, gid, draw_id, fake_sender(fail_on=4), clock)
    pipeline.prepare_practice(store, gid, random.Random(1))
    pipeline.run_sends(store, draw_id, "practice", PracticeSender(), clock)
    store.set_message(gid, "Kept {giver}", "Kept {giver} {recipient}")
    assert store.discard_draw(gid) == 3
    pipeline.clear_practice_files(gid)
    assert store.draw_status(gid) == (None, None, [])
    assert not paths.practice_dir(gid).exists()
    assert len(store.list_people(gid)) == 5
    assert store.get_message(gid)[0] == "Kept {giver}"


def test_progress_callback_that_raises_leaves_the_record_written(setup, fake_sender, clock):
    store, gid, ids, draw_id = setup

    def boom(done, total):
        raise RuntimeError("page went away")

    with pytest.raises(RuntimeError):
        real_run(store, gid, draw_id, fake_sender(), clock, on_progress=boom)
    assert list(statuses(store, draw_id).values()).count("sent") == 1
    assert "sending" not in statuses(store, draw_id).values()


def test_no_streamlit_in_the_pipeline():
    assert "streamlit" not in inspect.getsource(pipeline)


def test_missing_image_stops_before_claiming(setup, fake_sender, clock, monkeypatch):
    store, gid, ids, draw_id = setup
    monkeypatch.setattr(pipeline.images, "pick", lambda rng: "gone.png")
    pipeline.prepare_real(store, gid, random.Random(1), now=clock)
    sender = fake_sender()
    with pytest.raises(pipeline.MissingImage) as err:
        pipeline.run_sends(store, draw_id, "real", sender, clock)
    assert err.value.giver_name == "Ann"
    assert sender.calls == 0
    assert set(statuses(store, draw_id).values()) == {"pending"}


def test_practice_sender_result_is_sent(setup, clock):
    store, gid, ids, draw_id = setup
    pipeline.prepare_practice(store, gid, random.Random(1))
    record = store.sendable(draw_id, "practice")[0]
    assert PracticeSender().send(pipeline.build_outgoing(store, record)) == Sent()
