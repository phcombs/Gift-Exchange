"""The shared image library: one folder of pictures; each email gets one picked at random.

Types are checked by the file's first bytes, not its name. Files are named by content hash, so
uploading the same picture twice keeps one copy.
"""

import hashlib

from giftx import paths
from giftx.model import Problem

MAX_BYTES = 2 * 1024 * 1024  # 2 MB: about 2.7 MB once base64-encoded in the email

_SIGNATURES = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
]
EXTENSIONS = {"jpg", "png", "gif"}


def check_image(data):
    """The extension for this picture, or a Problem saying why it can't be used."""
    if len(data) > MAX_BYTES:
        size = len(data) / (1024 * 1024)
        return Problem("too_big", f"The picture is {size:.1f} MB; the limit is 2 MB. Make it smaller first.")
    for magic, ext in _SIGNATURES:
        if data.startswith(magic):
            return ext
    return Problem("not_an_image", "That file isn't a JPEG, PNG or GIF picture.")


def save_image(data):
    """Store a checked picture; returns its name. An identical file keeps its existing name."""
    ext = check_image(data)
    if isinstance(ext, Problem):
        raise ValueError(ext.message)
    name = f"{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
    folder = paths.images_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return name


def list_images():
    folder = paths.images_dir()
    if not folder.is_dir():
        return []
    return sorted(
        f.name for f in folder.iterdir() if f.is_file() and f.suffix.lstrip(".") in EXTENSIONS
    )


def read_image(name):
    """(bytes, ext) of a stored image. Raises FileNotFoundError if it's gone."""
    path = paths.images_dir() / name
    return path.read_bytes(), path.suffix.lstrip(".").lower()


def delete_image(name, in_use):
    """Delete a picture unless a send record names it. Returns a Problem if refused."""
    if name in in_use:
        return Problem("in_use", "This picture is used by emails that were prepared. It can be deleted "
                                 "after \"Start a new exchange\" or a new practice run.")
    try:
        (paths.images_dir() / name).unlink()
    except FileNotFoundError:
        pass
    return None


def pick(rng):
    """A random picture name for one email, or None when the library is empty."""
    names = list_images()
    return rng.choice(names) if names else None


def deal(rng, count):
    """Picture names for count emails, dealt like cards: all different while the library lasts, then
    reshuffled for the next round. [None] * count when the library is empty."""
    names = list_images()
    if not names:
        return [None] * count
    dealt = []
    while len(dealt) < count:
        deck = list(names)
        rng.shuffle(deck)
        dealt.extend(deck)
    return dealt[:count]
