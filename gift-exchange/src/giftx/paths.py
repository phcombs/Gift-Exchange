import os
from pathlib import Path


def _root() -> Path:
    env = os.environ.get("GIFTX_DATA_DIR", "")
    if env:
        return Path(env)
    return Path.home() / "Library/Application Support/Gift Exchange"


def data_dir() -> Path:
    folder = _root()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def db_path() -> Path:
    return _root() / "giftx.sqlite3"


def client_file() -> Path:
    return _root() / "client.json"


def images_dir() -> Path:
    return _root() / "images"


def practice_root() -> Path:
    return _root() / "practice"


def practice_dir(group_id) -> Path:
    return practice_root() / str(group_id)


def practice_test_dir() -> Path:
    return practice_root() / "test"
