"""Manual smoke test: copy the tracked files to a temp folder, start run.py there, wait for health.

    python scripts/smoke_run.py

Works on macOS, Linux and Windows. Not called from check.sh or any test. Needs network: uv
downloads the locked packages into a fresh cache, as on a cloner's first run. Prints pass or fail.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEALTH_URL = "http://localhost:8501/_stcore/health"
TIMEOUT = 300
WINDOWS = os.name == "nt"


def healthy():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(HEALTH_URL, timeout=1) as response:
            return response.read().strip() == b"ok"
    except Exception:
        return False


def copy_tracked(dst):
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout.split("\0")
    for name in filter(None, names):
        src = REPO / name
        if src.is_file():
            (dst / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / name)


def stop_tree(proc):
    if proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        # the child was started in its own session, so its process group id is its pid
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def main():
    if healthy():
        print("fail: something already answers on localhost:8501")
        return 1

    work = Path(tempfile.mkdtemp(prefix="giftx-smoke-"))
    result = "fail"
    try:
        app = work / "app"
        app.mkdir()
        copy_tracked(app)
        env = dict(
            os.environ,
            UV_CACHE_DIR=str(work / "uv-cache"),
            GIFTX_DATA_DIR=str(work / "data"),
            GIFTX_NO_OPEN="1",
        )
        if WINDOWS:
            group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            group = {"start_new_session": True}
        log_path = work / "run.log"
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                [sys.executable, "run.py"], cwd=app, env=env, stdout=log,
                stderr=subprocess.STDOUT, **group
            )
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                if healthy():
                    result = "pass"
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
            stop_tree(proc)
        if result == "fail":
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            print("\n".join(lines[-20:]))
    finally:
        time.sleep(1)
        shutil.rmtree(work, ignore_errors=True)
    print(result)
    return 0 if result == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
