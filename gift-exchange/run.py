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
        say("Gift Exchange is running at " + URL + ". Press Ctrl+C here to stop it.")
        return proc.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        stop(proc)


if __name__ == "__main__":
    sys.exit(main())
