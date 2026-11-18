# Gift Exchange

A small web app that runs a family gift exchange on your own computer: enter the people, mark couples,
draw who buys for whom (matches stay hidden, even from you), and email everyone their match.

It runs on Windows, macOS and Linux. All you need is **Python 3.8 or newer** ([python.org](https://www.python.org/downloads/)).

## Start it

```text
git clone https://github.com/phcombs/Gift-Exchange.git
cd Gift-Exchange/gift-exchange
```

| System | Command |
|---|---|
| Windows | double-click `run.cmd`, or run `py run.py` |
| macOS / Linux | `./run`, or `python3 run.py` |

The first start takes a minute or two: it installs [uv](https://docs.astral.sh/uv/), which downloads
Python 3.12 and the exact package versions in `uv.lock` into a private `.venv` folder. Nothing is
installed system-wide. Your browser then opens <http://localhost:8501>. Press Ctrl+C in the terminal to
stop the app.

## Use it

1. **People** page: create a group, then add people one at a time or paste a list (one `name, email`
   per line). Mark couples, who never draw each other.
2. **Message** page: edit the subject and message. `{giver}` and `{recipient}` are filled in for each
   person. The preview uses made-up names, and **Send test email** writes a practice email to a file.
3. **Send** page: press **Draw**. The table lists everyone with "match hidden". Then, in Practice mode,
   **Send all unsent** writes everyone's email to a file so you can check them without sending anything.

Sending through Gmail (Real mode) is still being built.

## Your data

Names, addresses and draws stay on your computer, never in this folder or in git:

| System | Folder |
|---|---|
| Windows | `%APPDATA%\Gift Exchange` |
| macOS | `~/Library/Application Support/Gift Exchange` |
| Linux | `~/.local/share/gift-exchange` |

Everything is in one SQLite file, `giftx.sqlite3`; back it up by copying it. Set `GIFTX_DATA_DIR` to use
another folder.

## For developers

Tests: `uv run --frozen pytest -q` from `gift-exchange/`. The design is in
`gift-exchange/docs/designs/design_draft.md`.

---

*That rug tied the room together.*
