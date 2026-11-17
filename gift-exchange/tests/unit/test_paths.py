from pathlib import Path

import pytest

from giftx import paths

SRC = Path(__file__).resolve().parents[2] / "src"


def test_data_dir_uses_env_and_creates(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "data"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(target))
    assert paths.data_dir() == target
    assert target.is_dir()


@pytest.mark.parametrize("unset", [True, False], ids=["unset", "empty"])
def test_data_dir_default_when_unset_or_empty(monkeypatch, tmp_path, unset):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    if unset:
        monkeypatch.delenv("GIFTX_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("GIFTX_DATA_DIR", "")
    expected = home / "Library/Application Support/Gift Exchange"
    assert paths.data_dir() == expected
    assert expected.is_dir()


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
