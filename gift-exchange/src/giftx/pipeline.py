"""Sending orchestration. M4: the test send only; the send loop arrives in M5."""

from datetime import timezone

from giftx import compose, images, paths
from giftx.model import Outgoing


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
