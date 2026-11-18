#!/usr/bin/env python3
"""Start Gift Exchange.

    macOS / Linux:  ./run        (or: python3 run.py)
    Windows:        run.cmd      (double-click, or: py run.py)

Only Python 3.8 or newer is needed to start. This script uses the standard library only.
It finds uv (installing it the first time), and uv downloads Python 3.12 and the exact
packages in uv.lock into .venv, then starts the app and opens it in the browser.
Ctrl+C in this terminal stops the app.
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

UV_VERSION = "0.13.8"
URL = "http://localhost:8501"
HEALTH_URL = URL + "/_stcore/health"
HERE = Path(__file__).resolve().parent
BOOTSTRAP = HERE / ".uv-bootstrap"
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""
START_TRIES = 60  # half-second polls: 30 seconds for start-up (downloads already happened)


def say(message):
    print(message, flush=True)


def health_ok(timeout=1.0):
    """True when Streamlit's health check on localhost answers "ok"."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(HEALTH_URL, timeout=timeout) as response:
            return response.read().strip() == b"ok"
    except Exception:
        return False


def open_browser():
    if os.environ.get("GIFTX_NO_OPEN") != "1":
        webbrowser.open(URL)


def home_uv():
    return Path.home() / ".local" / "bin" / ("uv" + EXE)


def bootstrap_uv():
    return BOOTSTRAP / ("Scripts" if WINDOWS else "bin") / ("uv" + EXE)


def find_uv():
    on_path = shutil.which("uv")
    if on_path:
        return on_path
    for candidate in (home_uv(), bootstrap_uv()):
        if candidate.is_file():
            return str(candidate)
    return None


def install_with_pip():
    """Install uv from PyPI into a private virtual environment next to this script."""
    python = BOOTSTRAP / ("Scripts" if WINDOWS else "bin") / ("python" + EXE)
    try:
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(BOOTSTRAP)], check=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
             "uv==" + UV_VERSION],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    uv = bootstrap_uv()
    return str(uv) if uv.is_file() else None


def install_with_script():
    """Fallback: uv's official installer, into ~/.local/bin, without editing shell profiles."""
    env = dict(os.environ, UV_NO_MODIFY_PATH="1")
    base = "https://astral.sh/uv/" + UV_VERSION
    try:
        if WINDOWS:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "ByPass", "-Command",
                 "irm " + base + "/install.ps1 | iex"],
                env=env,
            )
        elif shutil.which("curl"):
            subprocess.run("curl -LsSf " + base + "/install.sh | sh", shell=True, env=env)
        else:
            return None
    except OSError:
        return None
    uv = home_uv()
    return str(uv) if uv.is_file() else None


def install_uv():
    say("Installing uv (one time)…")
    return install_with_pip() or install_with_script()


def wait_until_up(proc):
    for _ in range(START_TRIES):
        if health_ok():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.5)
    return False


def stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ------------------------------------------------------------------ shortcuts

SHORTCUT_NAME = "Gift Exchange"
SHORTCUT_MARKER = ".shortcut"  # in the app folder: the start script the shortcuts point to


def start_script():
    return HERE / ("run.cmd" if WINDOWS else "run")


def _windows_shortcuts(target):
    """Desktop and Start menu shortcuts (.lnk) through PowerShell; paths go in by environment."""
    script = (
        "$w = New-Object -ComObject WScript.Shell; "
        "foreach ($d in @([Environment]::GetFolderPath('Desktop'), "
        "[Environment]::GetFolderPath('Programs'))) { "
        "  if (-not $d) { continue }; "
        "  $s = $w.CreateShortcut((Join-Path $d ($env:GX_NAME + '.lnk'))); "
        "  $s.TargetPath = $env:GX_TARGET; $s.WorkingDirectory = $env:GX_DIR; "
        "  $s.Description = 'Start Gift Exchange'; "
        "  $s.IconLocation = \"$env:SystemRoot\\System32\\shell32.dll,43\"; $s.Save() }"
    )
    env = dict(os.environ, GX_NAME=SHORTCUT_NAME, GX_TARGET=str(target), GX_DIR=str(target.parent))
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "ByPass", "-Command", script],
        env=env, capture_output=True,
    )
    return ["desktop", "Start menu"] if result.returncode == 0 else []


def _mac_shortcut(target):
    """A .command file on the Desktop: double-clicking it opens Terminal and starts the app."""
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        return []
    path = desktop / (SHORTCUT_NAME + ".command")
    path.write_text('#!/bin/sh\nexec "' + str(target).replace('"', '\\"') + '"\n', encoding="utf-8")
    path.chmod(0o755)
    return ["desktop"]


def _linux_shortcut(target):
    """An entry in the applications menu (freedesktop .desktop file)."""
    folder = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "gift-exchange.desktop"
    path.write_text(
        "[Desktop Entry]\nType=Application\nName=" + SHORTCUT_NAME + "\n"
        "Comment=Run a family gift exchange\n"
        'Exec="' + str(target) + '"\nPath=' + str(target.parent) + "\nTerminal=true\n"
        "Icon=applications-office\nCategories=Office;\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return ["applications menu"]


def create_shortcuts(target):
    if WINDOWS:
        return _windows_shortcuts(target)
    if sys.platform == "darwin":
        return _mac_shortcut(target)
    return _linux_shortcut(target)


def ensure_shortcuts():
    """Once per app folder: add a "Gift Exchange" shortcut. Also again if the folder was moved.

    A shortcut the user deleted is not brought back. GIFTX_NO_SHORTCUT=1 turns this off.
    Never stops the app: any problem here is skipped silently.
    """
    if os.environ.get("GIFTX_NO_SHORTCUT") == "1":
        return
    marker = HERE / SHORTCUT_MARKER
    target = start_script()
    try:
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == str(target):
            return
        places = create_shortcuts(target)
        if not places:
            return  # try again next start
        marker.write_text(str(target) + "\n", encoding="utf-8")
    except Exception:
        return
    if places:
        say("Added a " + SHORTCUT_NAME + " shortcut to your " + " and ".join(places)
            + ". Use it to start the app next time.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    os.chdir(str(HERE))

    if health_ok():
        say("The app is already running: opening " + URL)
        open_browser()
        return 0

    uv = find_uv() or install_uv()
    if not uv:
        say("Could not install uv. Check your internet connection and try again.")
        return 1

    if subprocess.run([uv, "sync", "--frozen"]).returncode != 0:
        return 1

    proc = subprocess.Popen([uv, "run", "--frozen", "streamlit", "run", "streamlit_app.py"])
    try:
        if not wait_until_up(proc):
            say("The app did not start. The messages above say why.")
            return 1
        open_browser()
        ensure_shortcuts()
        say("Gift Exchange is running at " + URL + ". Close this window (or press Ctrl+C) to stop it.")
        return proc.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        stop(proc)


if __name__ == "__main__":
    sys.exit(main())
