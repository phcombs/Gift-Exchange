import os
import sys
from pathlib import Path

FOLDER_NAME = "Gift Exchange"
LINUX_FOLDER_NAME = "gift-exchange"


def _platform() -> str:
    return sys.platform


def default_root() -> Path:
    """The per-user data folder this OS expects.

    macOS:   ~/Library/Application Support/Gift Exchange
    Windows: %APPDATA%\\Gift Exchange  (normally C:\\Users\\<you>\\AppData\\Roaming)
    Linux and others: $XDG_DATA_HOME/gift-exchange, else ~/.local/share/gift-exchange
    """
    platform = _platform()
    home = Path.home()
    if platform == "darwin":
        return home / "Library" / "Application Support" / FOLDER_NAME
    if platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / FOLDER_NAME
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".local" / "share"
    return base / LINUX_FOLDER_NAME


def _root() -> Path:
    env = os.environ.get("GIFTX_DATA_DIR", "")
    if env:
        return Path(env)
    return default_root()


def data_dir() -> Path:
    folder = _root()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def db_path() -> Path:
    return _root() / "giftx.sqlite3"


def client_file() -> Path:
    return _root() / "client.json"


def email_settings_file() -> Path:
    return _root() / "email.json"


def images_dir() -> Path:
    return _root() / "images"


def practice_root() -> Path:
    return _root() / "practice"


def practice_dir(group_id) -> Path:
    return practice_root() / str(group_id)


def practice_test_dir() -> Path:
    return practice_root() / "test"
