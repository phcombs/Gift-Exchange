import re
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
URL = "http://localhost:8501"

CURL_INSTALL = """#!/bin/sh
echo "curl $*" >> "$LOG"
case "$*" in
  *install.sh*)
    cat <<'EOS'
echo "UV_NO_MODIFY_PATH=$UV_NO_MODIFY_PATH" >> "$LOG"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/uv" <<'EOU'
#!/bin/sh
echo "$0 $*" >> "$LOG"
if [ "$1" = run ]; then sleep 1; fi
exit 0
EOU
chmod +x "$HOME/.local/bin/uv"
EOS
    exit 0 ;;
  *_stcore/health*)
    if grep -q 'uv run' "$LOG" 2>/dev/null; then echo ok; exit 0; fi
    exit 22 ;;
esac
exit 0
"""

CURL_RUNNING = """#!/bin/sh
echo "curl $*" >> "$LOG"
case "$*" in
  *_stcore/health*) echo ok; exit 0 ;;
esac
exit 0
"""

OPEN = """#!/bin/sh
echo "open $*" >> "$LOG"
"""

UV_STUB = """#!/bin/sh
echo "$0 $*" >> "$LOG"
exit 0
"""


def write_stub(folder, name, body):
    path = folder / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def make_sandbox(tmp_path, curl_body, with_uv):
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(REPO / "run", work / "run")
    shutil.copy(REPO / "streamlit_app.py", work / "streamlit_app.py")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    write_stub(stubs, "curl", curl_body)
    write_stub(stubs, "open", OPEN)
    if with_uv:
        write_stub(stubs, "uv", UV_STUB)
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(home), "LOG": str(log)}
    return work, home, log, env


def run_script(work, env):
    start = time.monotonic()
    proc = subprocess.run(
        ["bash", "run"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, time.monotonic() - start


def test_syntax():
    subprocess.run(["bash", "-n", str(REPO / "run")], check=True)
    subprocess.run(["sh", "-n", str(REPO / "scripts/smoke_run.sh")], check=True)


def test_run_is_executable():
    assert (REPO / "run").stat().st_mode & 0o111


def test_uv_version_is_one_exact_version():
    text = (REPO / "run").read_text(encoding="utf-8")
    assert re.search(r"^UV_VERSION=\d+\.\d+\.\d+$", text, re.M)


def test_installs_uv_when_missing(tmp_path):
    work, home, log, env = make_sandbox(tmp_path, CURL_INSTALL, with_uv=False)
    version = re.search(
        r"^UV_VERSION=(\S+)$", (REPO / "run").read_text(encoding="utf-8"), re.M
    ).group(1)
    proc, seconds = run_script(work, env)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert proc.returncode == 0, proc.stderr
    assert seconds < 10
    assert "Installing uv (one time)…" in proc.stdout
    assert any(
        l.startswith("curl") and "-LsSf" in l and f"https://astral.sh/uv/{version}/install.sh" in l
        for l in lines
    )
    assert "UV_NO_MODIFY_PATH=1" in lines
    uv = f"{home}/.local/bin/uv"
    assert f"{uv} sync --frozen" in lines
    assert f"{uv} run --frozen streamlit run streamlit_app.py" in lines
    assert lines.index(f"{uv} sync --frozen") < lines.index(
        f"{uv} run --frozen streamlit run streamlit_app.py"
    )
    assert f"open {URL}" in lines


def test_already_running(tmp_path):
    work, home, log, env = make_sandbox(tmp_path, CURL_RUNNING, with_uv=True)
    proc, _ = run_script(work, env)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert proc.returncode == 0, proc.stderr
    assert f"The app is already running: opening {URL}" in proc.stdout
    assert f"open {URL}" in lines
    assert not any(" sync" in l or " run" in l or l.split()[0].endswith("uv") for l in lines)
