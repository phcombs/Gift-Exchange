import fnmatch
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ALLOWED_DOMAINS = {"example.com", "example.org"}
FORBIDDEN_NAMES = [
    "client_secret*.json",
    "*.token.json",
    "client.json",
    "*.sqlite*",
    "*.eml",
]


def tracked_files(folder):
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=folder,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def scan(folder):
    """Return a list of problems found in the tracked files of the repo at folder."""
    folder = Path(folder)
    problems = []
    for name in tracked_files(folder):
        base = Path(name).name
        for pattern in FORBIDDEN_NAMES:
            if fnmatch.fnmatch(base, pattern):
                problems.append(f"{name}: forbidden file name ({pattern})")
        path = folder / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in EMAIL.finditer(text):
            domain = match.group(0).split("@", 1)[1].lower()
            if domain not in ALLOWED_DOMAINS:
                problems.append(f"{name}: email address at {domain}")
        if base.lower().endswith(".json"):
            for word in ("client_secret", "refresh_token"):
                if word in text:
                    problems.append(f"{name}: contains {word}")
    return problems


def make_repo(folder):
    folder.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
    (folder / "notes.txt").write_text("hello from a made-up note\n", encoding="utf-8")
    (folder / "config.txt").write_text("Contact: someone@example.org\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "."], cwd=folder, check=True)


def git_add(folder, name):
    subprocess.run(["git", "add", "-f", name], cwd=folder, check=True)


def test_this_repo_is_clean():
    assert scan(REPO) == []


def test_clean_temp_repo_passes(tmp_path):
    repo = tmp_path / "r"
    make_repo(repo)
    assert scan(repo) == []


def test_non_example_address_fails(tmp_path):
    repo = tmp_path / "r"
    make_repo(repo)
    address = "pat" + "@" + "mail" + "." + "test" + "site.net"
    (repo / "notes.txt").write_text(f"write to {address}\n", encoding="utf-8")
    git_add(repo, "notes.txt")
    problems = scan(repo)
    assert any("notes.txt" in p for p in problems)


def test_client_secret_file_name_fails(tmp_path):
    repo = tmp_path / "r"
    make_repo(repo)
    (repo / "client_secret_x.json").write_text("{}\n", encoding="utf-8")
    git_add(repo, "client_secret_x.json")
    problems = scan(repo)
    assert any("client_secret_x.json" in p for p in problems)


def test_other_forbidden_names_fail(tmp_path):
    repo = tmp_path / "r"
    make_repo(repo)
    for name in ["a.token.json", "client.json", "db.sqlite3", "m.eml"]:
        (repo / name).write_text("x\n", encoding="utf-8")
        git_add(repo, name)
    problems = scan(repo)
    for name in ["a.token.json", "client.json", "db.sqlite3", "m.eml"]:
        assert any(p.startswith(name + ":") for p in problems), name


def test_json_with_secret_words_fails(tmp_path):
    repo = tmp_path / "r"
    make_repo(repo)
    (repo / "data.json").write_text('{"refresh' + '_token": "x"}\n', encoding="utf-8")
    git_add(repo, "data.json")
    assert any(p.startswith("data.json:") for p in scan(repo))


def test_not_addresses():
    assert EMAIL.search("egm@egm") is None
    assert EMAIL.search("pkg@1.2") is None
