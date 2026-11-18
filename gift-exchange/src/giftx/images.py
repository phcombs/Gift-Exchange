"""The shared image library. M4: reading only; upload, checks and picking arrive in M7."""

from giftx import paths


def read_image(name):
    """(bytes, ext) of a stored image. Raises FileNotFoundError if it's gone."""
    path = paths.images_dir() / name
    return path.read_bytes(), path.suffix.lstrip(".").lower()
