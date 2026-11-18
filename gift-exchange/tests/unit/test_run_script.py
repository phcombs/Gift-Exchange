"""Tests for the cross-platform launcher run.py. No network, no real uv, no browser."""

import importlib.util
import py_compile
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
URL = "http://localhost:8501"


def load_run():
    spec = importlib.util.spec_from_file_location("giftx_run_under_test", REPO / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeProc:
    def __init__(self, log, exit_code=None):
        self.log = log
        self.exit_code = exit_code
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else self.exit_code

    def wait(self, timeout=None):
        if not self.stopped and self.exit_code is None:
            self.exit_code = 0  # the app exited on its own
        return 0 if self.stopped else self.exit_code

    def terminate(self):
        self.log.append("terminate")
        self.stopped = True

    def kill(self):
        self.stopped = True


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    run = load_run()
    log = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    monkeypatch.setattr(run.webbrowser, "open", lambda url: log.append("open " + url))
    monkeypatch.delenv("GIFTX_NO_OPEN", raising=False)

    def fake_run(cmd, **kwargs):
        log.append(" ".join(str(c) for c in cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    run.log = log
    return run


def health_after(run, monkeypatch, answers):
    answers = list(answers)
    monkeypatch.setattr(run, "health_ok", lambda timeout=1.0: answers.pop(0) if answers else False)


def popen_recording(run, monkeypatch, exit_code=None):
    procs = []

    def fake_popen(cmd, **kwargs):
        run.log.append(" ".join(str(c) for c in cmd))
        proc = FakeProc(run.log, exit_code)
        procs.append(proc)
        return proc

    monkeypatch.setattr(run.subprocess, "Popen", fake_popen)
    return procs


def test_compiles():
    py_compile.compile(str(REPO / "run.py"), doraise=True)
    py_compile.compile(str(REPO / "scripts/smoke_run.py"), doraise=True)


@pytest.mark.skipif(shutil.which("sh") is None, reason="no POSIX sh on this machine")
def test_shell_wrapper_syntax():
    subprocess.run(["sh", "-n", str(REPO / "run")], check=True)


def test_run_wrapper_is_executable_in_git():
    out = subprocess.run(
        ["git", "ls-files", "-s", "run"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    assert out.startswith("100755 "), out


def test_wrappers_call_run_py():
    assert "run.py" in (REPO / "run").read_text(encoding="utf-8")
    assert "run.py" in (REPO / "run.cmd").read_text(encoding="utf-8")


def test_uv_version_is_one_exact_version():
    text = (REPO / "run.py").read_text(encoding="utf-8")
    assert re.search(r'^UV_VERSION = "\d+\.\d+\.\d+"$', text, re.M)


def test_already_running(launcher, monkeypatch, capsys):
    run = launcher
    health_after(run, monkeypatch, [True])
    monkeypatch.setattr(run, "find_uv", lambda: pytest.fail("uv looked up"))
    assert run.main() == 0
    assert "The app is already running: opening " + URL in capsys.readouterr().out
    assert run.log == ["open " + URL]


def test_starts_app_with_existing_uv(launcher, monkeypatch, capsys):
    run = launcher
    health_after(run, monkeypatch, [False, False, True])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")
    popen_recording(run, monkeypatch)
    assert run.main() == 0
    assert run.log == [
        "UV sync --frozen",
        "UV run --frozen streamlit run streamlit_app.py",
        "open " + URL,
    ]
    assert "running at " + URL in capsys.readouterr().out


def test_no_open_setting_skips_browser(launcher, monkeypatch):
    run = launcher
    monkeypatch.setenv("GIFTX_NO_OPEN", "1")
    health_after(run, monkeypatch, [False, True])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")
    popen_recording(run, monkeypatch)
    assert run.main() == 0
    assert not any(line.startswith("open") for line in run.log)


def test_failed_sync_stops_before_starting(launcher, monkeypatch):
    run = launcher
    health_after(run, monkeypatch, [False])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")
    monkeypatch.setattr(run.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2))
    monkeypatch.setattr(run.subprocess, "Popen", lambda *a, **k: pytest.fail("app started"))
    assert run.main() == 1


def test_app_that_exits_early_reports_and_returns_1(launcher, monkeypatch, capsys):
    run = launcher
    health_after(run, monkeypatch, [False])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")
    popen_recording(run, monkeypatch, exit_code=1)
    assert run.main() == 1
    assert "The app did not start. The messages above say why." in capsys.readouterr().out


def test_app_that_never_answers_is_stopped(launcher, monkeypatch, capsys):
    run = launcher
    health_after(run, monkeypatch, [])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")
    procs = popen_recording(run, monkeypatch)
    assert run.main() == 1
    assert procs[0].stopped and "terminate" in run.log
    assert "The app did not start" in capsys.readouterr().out


def test_ctrl_c_stops_the_app(launcher, monkeypatch):
    run = launcher
    health_after(run, monkeypatch, [False, True])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")

    class Interrupted(FakeProc):
        def wait(self, timeout=None):
            if not self.stopped:
                raise KeyboardInterrupt
            return 0

    proc = Interrupted(run.log)
    monkeypatch.setattr(run.subprocess, "Popen", lambda cmd, **kwargs: proc)
    assert run.main() == 0
    assert proc.stopped


def test_installs_uv_when_missing(launcher, monkeypatch, capsys):
    run = launcher
    health_after(run, monkeypatch, [False, True])
    monkeypatch.setattr(run, "find_uv", lambda: None)
    monkeypatch.setattr(run, "install_with_pip", lambda: "NEWUV")
    monkeypatch.setattr(run, "install_with_script", lambda: pytest.fail("fallback used"))
    popen_recording(run, monkeypatch)
    assert run.main() == 0
    assert "Installing uv (one time)…" in capsys.readouterr().out
    assert run.log[:2] == ["NEWUV sync --frozen", "NEWUV run --frozen streamlit run streamlit_app.py"]


def test_falls_back_to_official_installer(launcher, monkeypatch):
    run = launcher
    monkeypatch.setattr(run, "install_with_pip", lambda: None)
    monkeypatch.setattr(run, "install_with_script", lambda: "SCRIPTUV")
    assert run.install_uv() == "SCRIPTUV"


def test_reports_when_uv_cannot_be_installed(launcher, monkeypatch, capsys):
    run = launcher
    health_after(run, monkeypatch, [False])
    monkeypatch.setattr(run, "find_uv", lambda: None)
    monkeypatch.setattr(run, "install_with_pip", lambda: None)
    monkeypatch.setattr(run, "install_with_script", lambda: None)
    assert run.main() == 1
    assert "Could not install uv" in capsys.readouterr().out


def test_pip_install_pins_the_uv_version(launcher, monkeypatch, tmp_path):
    run = launcher
    monkeypatch.setattr(run, "BOOTSTRAP", tmp_path / "boot")

    def fake_run(cmd, **kwargs):
        run.log.append(cmd)
        if "pip" in cmd:
            uv = run.bootstrap_uv()
            uv.parent.mkdir(parents=True, exist_ok=True)
            uv.write_text("")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    assert run.install_with_pip() == str(run.bootstrap_uv())
    venv_cmd, pip_cmd = run.log
    assert venv_cmd[1:3] == ["-m", "venv"]
    assert pip_cmd[-1] == "uv==" + run.UV_VERSION


def test_find_uv_prefers_path_then_home_then_bootstrap(launcher, monkeypatch, tmp_path):
    run = launcher
    home = tmp_path / "home"
    monkeypatch.setattr(run.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(run, "BOOTSTRAP", tmp_path / "boot")
    monkeypatch.setattr(run.shutil, "which", lambda name: None)
    assert run.find_uv() is None
    run.bootstrap_uv().parent.mkdir(parents=True)
    run.bootstrap_uv().write_text("")
    assert run.find_uv() == str(run.bootstrap_uv())
    run.home_uv().parent.mkdir(parents=True)
    run.home_uv().write_text("")
    assert run.find_uv() == str(run.home_uv())
    monkeypatch.setattr(run.shutil, "which", lambda name: "/on/path/uv")
    assert run.find_uv() == "/on/path/uv"


def test_wrappers_pin_the_same_uv_version_as_run_py():
    version = re.search(r'^UV_VERSION = "(\S+)"$', (REPO / "run.py").read_text(encoding="utf-8"), re.M).group(1)
    assert f"UV_VERSION={version}" in (REPO / "run").read_text(encoding="utf-8")
    assert f'set "UV_VERSION={version}"' in (REPO / "run.cmd").read_text(encoding="utf-8")


def test_wrappers_fall_back_to_uv_without_python():
    for name in ("run", "run.cmd"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert "run --no-project --python 3.12 run.py" in text, name
        assert "UV_NO_MODIFY_PATH" in text, name


# ---------------------------------------------------------------- shortcuts

@pytest.fixture
def shortcuts(launcher, monkeypatch, tmp_path):
    run = launcher
    monkeypatch.delenv("GIFTX_NO_SHORTCUT", raising=False)
    made = []
    monkeypatch.setattr(run, "create_shortcuts", lambda target: made.append(target) or ["desktop"])
    run.made = made
    return run


def test_shortcut_made_once_per_folder(shortcuts, capsys):
    run = shortcuts
    run.ensure_shortcuts()
    run.ensure_shortcuts()
    assert run.made == [run.start_script()]
    assert "Added a Gift Exchange shortcut to your desktop." in capsys.readouterr().out


def test_shortcut_redone_after_the_folder_moved(shortcuts):
    run = shortcuts
    (run.HERE / run.SHORTCUT_MARKER).write_text("/old/place/run\n", encoding="utf-8")
    run.ensure_shortcuts()
    assert run.made == [run.start_script()]


def test_failed_shortcut_is_tried_again_and_never_stops_the_app(shortcuts, monkeypatch):
    run = shortcuts
    monkeypatch.setattr(run, "create_shortcuts", lambda target: [])
    run.ensure_shortcuts()
    assert not (run.HERE / run.SHORTCUT_MARKER).exists()

    def boom(target):
        raise OSError("no desktop")

    monkeypatch.setattr(run, "create_shortcuts", boom)
    run.ensure_shortcuts()  # no exception


def test_shortcuts_can_be_turned_off(shortcuts, monkeypatch):
    monkeypatch.setenv("GIFTX_NO_SHORTCUT", "1")
    shortcuts.ensure_shortcuts()
    assert shortcuts.made == []


def test_app_start_adds_the_shortcut(shortcuts, monkeypatch):
    run = shortcuts
    health_after(run, monkeypatch, [False, True])
    monkeypatch.setattr(run, "find_uv", lambda: "UV")
    popen_recording(run, monkeypatch)
    assert run.main() == 0
    assert run.made == [run.start_script()]


def test_mac_shortcut_is_an_executable_command_file(launcher, monkeypatch, tmp_path):
    run = launcher
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    monkeypatch.setattr(run.Path, "home", classmethod(lambda cls: home))
    assert run._mac_shortcut(tmp_path / "app" / "run") == ["desktop"]
    text = (home / "Desktop" / "Gift Exchange.command").read_text(encoding="utf-8")
    assert text == f'#!/bin/sh\nexec "{tmp_path / "app" / "run"}"\n'


def test_linux_shortcut_is_a_menu_entry(launcher, monkeypatch, tmp_path):
    run = launcher
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert run._linux_shortcut(tmp_path / "app" / "run") == ["applications menu"]
    text = (tmp_path / "xdg" / "applications" / "gift-exchange.desktop").read_text(encoding="utf-8")
    assert "Name=Gift Exchange" in text and "Terminal=true" in text
    assert f'Exec="{tmp_path / "app" / "run"}"' in text


def test_windows_shortcut_passes_paths_by_environment(launcher, monkeypatch, tmp_path):
    run = launcher
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs["env"]))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    target = tmp_path / "it's here" / "run.cmd"
    assert run._windows_shortcuts(target) == ["desktop", "Start menu"]
    ((cmd, env),) = calls
    assert cmd[0] == "powershell" and str(target) not in cmd[-1]
    assert env["GX_TARGET"] == str(target) and env["GX_NAME"] == "Gift Exchange"
