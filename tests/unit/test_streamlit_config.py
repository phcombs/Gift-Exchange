import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EXPECTED = {
    "server": {
        "address": '"localhost"',
        "port": "8501",
        "headless": "true",
        "showEmailPrompt": "false",
    },
    "browser": {"gatherUsageStats": "false"},
    "client": {"toolbarMode": '"minimal"', "showErrorDetails": '"none"'},
    "logger": {"level": '"warning"'},
}


def parse(output):
    sections = {}
    current = None
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections[current] = {}
        elif "=" in line and current is not None:
            key, value = line.split("=", 1)
            sections[current][key.strip()] = value.strip()
    return sections


def test_streamlit_config_values():
    out = subprocess.run(
        [sys.executable, "-m", "streamlit", "config", "show"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    sections = parse(out)
    for section, values in EXPECTED.items():
        for key, value in values.items():
            assert sections[section][key] == value, (section, key)
