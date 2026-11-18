from pathlib import Path

import pytest

from giftx import paths

SRC = Path(__file__).resolve().parents[2] / "src"


def test_data_dir_uses_env_and_creates(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "data"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(target))
    assert paths.data_dir() == target
    assert target.is_dir()


def fake_home(monkeypatch, tmp_path, platform):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(paths, "_platform", lambda: platform)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


@pytest.mark.parametrize("unset", [True, False], ids=["unset", "empty"])
@pytest.mark.parametrize(
    "platform,relative",
    [
        ("darwin", "Library/Application Support/Gift Exchange"),
        ("win32", "AppData/Roaming/Gift Exchange"),
        ("linux", ".local/share/gift-exchange"),
    ],
)
def test_data_dir_default_when_unset_or_empty(monkeypatch, tmp_path, unset, platform, relative):
    home = fake_home(monkeypatch, tmp_path, platform)
    if unset:
        monkeypatch.delenv("GIFTX_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("GIFTX_DATA_DIR", "")
    expected = home / relative
    assert paths.data_dir() == expected
    assert expected.is_dir()


def test_windows_uses_appdata(monkeypatch, tmp_path):
    fake_home(monkeypatch, tmp_path, "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert paths.default_root() == tmp_path / "roaming" / "Gift Exchange"


def test_linux_uses_absolute_xdg_data_home_only(monkeypatch, tmp_path):
    home = fake_home(monkeypatch, tmp_path, "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert paths.default_root() == tmp_path / "xdg" / "gift-exchange"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/dir")
    assert paths.default_root() == home / ".local/share/gift-exchange"


def test_derived_paths_and_no_creation(monkeypatch, tmp_path):
    base = tmp_path / "d"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(base))
    checks = [
        (paths.db_path, (), base / "giftx.sqlite3"),
        (paths.client_file, (), base / "client.json"),
        (paths.images_dir, (), base / "images"),
        (paths.practice_root, (), base / "practice"),
        (paths.practice_dir, (7,), base / "practice" / "7"),
        (paths.practice_test_dir, (), base / "practice" / "test"),
    ]
    for func, args, expected in checks:
        assert func(*args) == expected
        assert not base.exists(), func.__name__
    paths.data_dir()
    assert base.is_dir()


def test_no_path_literals_outside_paths_module():
    offenders = []
    for f in SRC.rglob("*"):
        if not f.is_file() or (f.name == "paths.py" and f.parent.name == "giftx"):
            continue
        if f.suffix == ".pyc" or "__pycache__" in f.parts:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if "Application Support" in text or "GIFTX_DATA_DIR" in text:
            offenders.append(str(f))
    assert offenders == []
