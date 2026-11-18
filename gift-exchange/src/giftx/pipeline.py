"""Sending orchestration: compose records, then claim -> send -> record, one email at a time.

Safety rules (see the design's "Sending" section):
- No Streamlit calls between claim and record; the progress callback runs after record.
- Anything that goes wrong after a claim is recorded as "unknown" by the finally block.
- The run stops at the first result that isn't Sent.
- Only pending and failed records are ever sent.
"""

import shutil
from datetime import datetime, timezone

from giftx import compose, images, paths
from giftx.model import NewRecord, Outgoing, Sent, Summary, Unknown


class MissingImage(Exception):
    """The frozen picture for a record is gone. Carries the giver name for the page, not the message."""

    def __init__(self, giver_name):
        super().__init__("a picture file is missing")
        self.giver_name = giver_name


class NoDraw(Exception):
    pass


def _utc_now():
    return datetime.now(timezone.utc)


def _compose_rows(storage, group_id, draw_id, rng):
    subject, body = storage.get_message(group_id)
    names = {p.id: p.name for p in storage.list_people(group_id)}
    rows = []
    for giver, recipient in storage.get_assignments(draw_id).items():
        rows.append(
            NewRecord(
                giver_id=giver,
                subject=compose.fill(subject, names[giver], names[recipient]),
                body=compose.fill(body, names[giver], names[recipient]),
                image_name=images.pick(rng),
            )
        )
    return rows


def _draw_id(storage, group_id):
    draw_id, locked_at, _ = storage.draw_status(group_id)
    if draw_id is None:
        raise NoDraw("there is no draw for this group")
    return draw_id, locked_at


def prepare_real(storage, group_id, rng, now=_utc_now):
    """Compose and store the real records, locking the draw. False if they already existed."""
    draw_id, locked_at = _draw_id(storage, group_id)
    if locked_at is not None:
        return False
    return storage.create_real_records(draw_id, _compose_rows(storage, group_id, draw_id, rng), now())


def prepare_practice(storage, group_id, rng):
    """A fresh practice run: delete the old practice records and files, compose new ones. Never locks."""
    draw_id, _ = _draw_id(storage, group_id)
    clear_practice_files(group_id)
    storage.replace_practice_records(draw_id, _compose_rows(storage, group_id, draw_id, rng))


def build_outgoing(storage, record):
    """The giver's current address, the frozen text and the image bytes. Raises MissingImage."""
    people = {p.id: p for p in storage.list_people(record.group_id)}
    to = people[record.giver_id].email
    image = None
    if record.image_name:
        try:
            image = images.read_image(record.image_name)
        except OSError:
            raise MissingImage(record.giver_name) from None
    raw = compose.build_email(to, record.subject, record.body, image)
    return Outgoing(key=f"{record.group_id}/{record.id}", to=to, raw=raw)


def run_sends(storage, draw_id, mode, sender, now, on_progress=None, only=None):
    """Send every pending, then failed, record of this draw and mode, stopping at the first non-Sent.

    Raises MissingImage before anything is claimed for that record.
    """
    records = storage.sendable(draw_id, mode, only)
    total = len(records)
    counts = {"sent": 0, "failed": 0, "unknown": 0}
    stopped_at = None
    done = 0
    for record in records:
        outgoing = build_outgoing(storage, record)
        if not storage.claim(record.id, now(), outgoing.to):
            continue  # another tab or click claimed it first
        result = Unknown("interrupted")
        try:
            result = sender.send(outgoing)
        finally:
            storage.record(record.id, result, now())
        done += 1
        if isinstance(result, Sent):
            counts["sent"] += 1
        elif isinstance(result, Unknown):
            counts["unknown"] += 1
        else:
            counts["failed"] += 1
        if on_progress:
            on_progress(done, total)
        if not isinstance(result, Sent):
            stopped_at = record.giver_name
            break
    remaining = 0
    if stopped_at:
        remaining = sum(1 for r in storage.sendable(draw_id, mode, only) if r.status == "pending")
    return Summary(counts["sent"], counts["failed"], counts["unknown"], stopped_at, remaining)


def _test_key(now):
    """"test/<UTC time>", with -2, -3, ... added when a practice file of that name exists."""
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key, n = f"test/{stamp}", 1
    while (paths.practice_root() / f"{key}.eml").exists():
        n += 1
        key = f"test/{stamp}-{n}"
    return key


def test_send(sender, to, subject, body, image_name, now):
    """Send the message filled with the made-up pair to one typed address.

    Reads no draw and creates or changes no send record. now: a Clock.
    """
    subject, body = compose.preview(subject, body)
    image = images.read_image(image_name) if image_name else None
    raw = compose.build_email(to, subject, body, image)
    return sender.send(Outgoing(key=_test_key(now()), to=to, raw=raw))


test_send.__test__ = False  # not a pytest test, despite the name


def clear_practice_files(group_id):
    shutil.rmtree(paths.practice_dir(group_id), ignore_errors=True)
