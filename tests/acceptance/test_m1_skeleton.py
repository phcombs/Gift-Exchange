"""M1 acceptance tests: the skeleton (config, paths, guards, repo hygiene, page, launcher).

No network, no server. Real-terminal criteria are checked by hand (see the verifier report).
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = str(REPO / "streamlit_app.py")
PRACTICE = "Practice mode: nothing is emailed"
REAL = "Real mode: emails are sent from your Gmail"


# ---------------------------------------------------------------- config

def _config_show():
    out = subprocess.run(
        [sys.executable, "-m", "streamlit", "config", "show"],
        cwd=REPO, capture_output=True, text=True, timeout=600, check=True,
    ).stdout
    values, section = {}, None
    for line in out.splitlines():
        s = line.strip()
        m = re.match(r"\[(\w+)\]$", s)
        if m:
            section = m.group(1)
        elif s and not s.startswith("#") and "=" in s and section:
            k, v = s.split("=", 1)
            values[(section, k.strip())] = v.strip()
    return values


@pytest.fixture(scope="module")
def config():
    return _config_show()


@pytest.mark.parametrize("key,expected", [
    (("server", "address"), '"localhost"'),
    (("server", "port"), "8501"),
    (("server", "headless"), "true"),
    (("server", "showEmailPrompt"), "false"),
    (("browser", "gatherUsageStats"), "false"),
    (("client", "toolbarMode"), '"minimal"'),
    (("client", "showErrorDetails"), '"none"'),
    (("logger", "level"), '"warning"'),
])
def test_streamlit_config_show_reports_committed_value(config, key, expected):
    assert config.get(key) == expected


def test_terminal_shows_no_email_prompt_config_is_off(config):
    # The prompt itself is checked by hand; here the setting that suppresses it.
    assert config[("server", "showEmailPrompt")] == "false"
    assert config[("server", "headless")] == "true"


# ---------------------------------------------------------------- paths

def _fresh_paths(monkeypatch):
    sys.modules.pop("giftx.paths", None)
    from giftx import paths
    return paths


def test_data_dir_returns_giftx_data_dir_when_set(monkeypatch, tmp_path):
    target = tmp_path / "custom data"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(target))
    from giftx import paths
    assert paths.data_dir() == target
    assert target.is_dir()


PLATFORM_FOLDERS = [
    ("darwin", "Library/Application Support/Gift Exchange"),
    ("win32", "AppData/Roaming/Gift Exchange"),
    ("linux", ".local/share/gift-exchange"),
]


def _os_home(monkeypatch, tmp_path, platform):
    from giftx import paths
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths, "_platform", lambda: platform)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return paths


@pytest.mark.parametrize("platform,relative", PLATFORM_FOLDERS)
def test_data_dir_defaults_to_the_os_user_data_folder(monkeypatch, tmp_path, platform, relative):
    monkeypatch.delenv("GIFTX_DATA_DIR", raising=False)
    paths = _os_home(monkeypatch, tmp_path, platform)
    assert paths.data_dir() == tmp_path / relative
    assert paths.data_dir().is_dir()


@pytest.mark.parametrize("platform,relative", PLATFORM_FOLDERS)
def test_empty_giftx_data_dir_counts_as_unset(monkeypatch, tmp_path, platform, relative):
    monkeypatch.setenv("GIFTX_DATA_DIR", "")
    paths = _os_home(monkeypatch, tmp_path, platform)
    assert paths.data_dir() == tmp_path / relative


def test_derived_paths_and_no_folder_created_by_them(monkeypatch, tmp_path):
    target = tmp_path / "d"
    monkeypatch.setenv("GIFTX_DATA_DIR", str(target))
    from giftx import paths
    assert paths.db_path() == target / "giftx.sqlite3"
    assert paths.client_file() == target / "client.json"
    assert paths.images_dir() == target / "images"
    assert paths.practice_root() == target / "practice"
    assert paths.practice_dir(7) == target / "practice" / "7"
    assert paths.practice_test_dir() == target / "practice" / "test"
    assert not target.exists()


def test_data_dir_is_idempotent_when_folder_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("GIFTX_DATA_DIR", str(tmp_path))
    from giftx import paths
    assert paths.data_dir() == tmp_path
    assert paths.data_dir() == tmp_path


def test_no_other_src_file_names_the_folder_or_variable():
    offenders = []
    for f in (REPO / "src").rglob("*"):
        if f.is_file() and f.suffix in (".py", ".toml", ".txt", ".md", ""):
            if f.name == "paths.py":
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "Application Support" in text or "GIFTX_DATA_DIR" in text:
                offenders.append(str(f))
    assert offenders == []


# ---------------------------------------------------------------- guards (done item 9)

GUARD_TESTS = textwrap.dedent('''
    import smtplib
    import socket

    def test_socket_connect():
        s = socket.socket()
        s.connect(("127.0.0.1", 9))

    def test_socket_connect_ex():
        s = socket.socket()
        s.connect_ex(("127.0.0.1", 9))

    def test_create_connection():
        socket.create_connection(("127.0.0.1", 9))

    def test_smtp():
        smtplib.SMTP("smtp.example.com", 587)

    def test_smtp_ssl():
        smtplib.SMTP_SSL("smtp.example.com", 465)

    def test_swallowed_by_broad_except_still_fails():
        try:
            socket.create_connection(("127.0.0.1", 9))
        except Exception:
            pass
''')


def test_suite_fails_tests_that_open_sockets_or_smtp_connections(tmp_path):
    shutil.copy(REPO / "tests" / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_probe.py").write_text(GUARD_TESTS, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=300,
        # explicit path: do not depend on the venv's .pth file (macOS can flag it hidden under ~/Documents)
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "6 failed" in out, out
    assert "passed" not in out, out


def test_guard_data_dir_points_inside_test_tmp(tmp_path):
    # conftest runs for acceptance tests too
    assert Path(os.environ["GIFTX_DATA_DIR"]).resolve().is_relative_to(tmp_path.resolve().parent)


def test_no_google_client_libraries_in_src():
    # real email goes over SMTP with an app password since 2026-11-17; no Google sign-in code remains
    for f in (REPO / "src").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "import google" not in text and "from google" not in text, f


# ---------------------------------------------------------------- repo hygiene (done item 10)

def _hygiene():
    spec = importlib.util.spec_from_file_location("hyg_under_test", REPO / "tests/unit/test_repo_hygiene.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tracked_copy(tmp_path):
    dst = tmp_path / "copy"
    dst.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    names = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split("\0")
    for n in filter(None, names):
        if (REPO / n).is_file():
            (dst / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / n, dst / n)
    subprocess.run(["git", "add", "-f", "."], cwd=dst, check=True)
    return dst


def test_repo_hygiene_passes_on_the_repo():
    assert _hygiene().scan(REPO) == []


def test_repo_hygiene_fails_after_non_example_address_added(tmp_path):
    dst = _tracked_copy(tmp_path)
    assert _hygiene().scan(dst) == []
    address = "pat" + "@" + "made-up" + "." + "invalid-tld"
    with open(dst / "pyproject.toml", "a", encoding="utf-8") as f:
        f.write(f"\n# {address}\n")
    subprocess.run(["git", "add", "-f", "."], cwd=dst, check=True)
    assert _hygiene().scan(dst) != []


def test_repo_hygiene_fails_after_client_secret_json_added(tmp_path):
    dst = _tracked_copy(tmp_path)
    (dst / "client_secret_x.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "client_secret_x.json"], cwd=dst, check=True)
    assert _hygiene().scan(dst) != []


def test_repo_hygiene_allows_example_domains_only(tmp_path):
    dst = _tracked_copy(tmp_path)
    with open(dst / "pyproject.toml", "a", encoding="utf-8") as f:
        f.write("\n# a@example.com b@example.org\n")
    subprocess.run(["git", "add", "-f", "."], cwd=dst, check=True)
    assert _hygiene().scan(dst) == []


def test_repo_tracks_no_secret_like_files_and_no_email_in_pyproject():
    names = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.splitlines()
    for n in names:
        b = Path(n).name
        assert not (b.startswith("client_secret") or b.endswith(".token.json") or b == "client.json"
                    or b.endswith(".eml") or ".sqlite" in b), n
    assert "@" not in (REPO / "pyproject.toml").read_text()


# ---------------------------------------------------------------- page (banner + sidebar)

def _load():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP)
    at.run(timeout=60)
    assert not at.exception
    return at


def test_page_shows_only_the_practice_banner_on_first_load():
    at = _load()
    assert [i.value for i in at.info] == [PRACTICE]
    assert len(at.warning) == 0 and len(at.error) == 0
    # the banner comes first (since M6 the Setup page also holds the email account form)
    assert at.main.children[0].value == PRACTICE


def test_sidebar_mode_switch_defaults_to_practice_with_two_options():
    at = _load()
    r = at.sidebar.radio(key="mode")
    assert r.value == "practice"
    assert list(r.options) == ["Practice", "Real"]


def test_sidebar_group_selector_is_empty_with_value_none():
    at = _load()
    g = at.sidebar.selectbox(key="group_id")
    assert list(g.options) == []
    assert g.value is None


def test_real_mode_shows_the_warning_banner_instead():
    at = _load()
    at.sidebar.radio(key="mode").set_value("real").run(timeout=60)
    assert [w.value for w in at.warning] == [REAL]
    assert len(at.info) == 0


def test_navigation_has_five_pages_so_the_menu_shows():
    from streamlit.testing.v1 import AppTest
    script = (
        "import streamlit as st\n"
        "from giftx.ui import common\n"
        "pg = common.pages()\n"
        "st.session_state['titles'] = [p.title for p in pg]\n"
        "st.navigation(pg, position='hidden')\n"
    )
    at = AppTest.from_string(script)
    at.run(timeout=60)
    assert not at.exception
    assert at.session_state["titles"] == ["Setup", "People", "Message", "Images", "Send"]


def test_new_session_defaults_back_to_practice():
    at = _load()
    at.sidebar.radio(key="mode").set_value("real").run(timeout=60)
    at2 = _load()
    assert at2.sidebar.radio(key="mode").value == "practice"


# ---------------------------------------------------------------- run script (offline parts)

def _launcher():
    spec = importlib.util.spec_from_file_location("run_accept", REPO / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_launchers_exist_for_every_os_and_shell_wrapper_is_executable():
    out = subprocess.run(["git", "ls-files", "-s", "run", "run.py", "run.cmd", "scripts/smoke_run.py"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    modes = {line.split("\t")[1]: line.split()[0] for line in out.splitlines()}
    assert set(modes) == {"run", "run.py", "run.cmd", "scripts/smoke_run.py"}
    assert modes["run"] == "100755"


def test_launcher_uses_only_the_standard_library():
    import ast
    tree = ast.parse((REPO / "run.py").read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


def test_run_pins_the_uv_version_that_is_installed_here():
    m = re.search(r'^UV_VERSION = "(\S+)"$', (REPO / "run.py").read_text(encoding="utf-8"), re.M)
    assert m
    out = subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout
    assert out.split()[1] == m.group(1)


def test_run_while_app_already_running_prints_message_opens_page_and_calls_no_uv(monkeypatch, capsys, tmp_path):
    run = _launcher()
    calls = []
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GIFTX_NO_OPEN", raising=False)
    monkeypatch.setattr(run, "health_ok", lambda timeout=1.0: True)
    monkeypatch.setattr(run.webbrowser, "open", lambda url: calls.append("open " + url))
    monkeypatch.setattr(run.subprocess, "run", lambda *a, **k: calls.append("subprocess"))
    monkeypatch.setattr(run.subprocess, "Popen", lambda *a, **k: calls.append("subprocess"))
    assert run.main() == 0
    assert "The app is already running" in capsys.readouterr().out
    assert calls == ["open http://localhost:8501"]
