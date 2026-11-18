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
   person. The preview uses made-up names, and **Send test email** sends the preview to one address.
3. **Send** page: press **Draw**. The table lists everyone with "match hidden". Then press
   **Send all unsent**, check the list, and confirm.

The app starts in **Practice** mode (sidebar): emails are written to files you can open, and nothing is
sent. Switch to **Real** mode when you're ready.

## Sending real email

Real mode sends from your own email account using an **app password**, a separate password your
provider creates for one app. You can revoke it at any time. Nothing else is needed: no developer
account, no Google Cloud project.

For Gmail:

1. Turn on [2-Step Verification](https://myaccount.google.com/signinoptions/twosv) for your Google account.
2. Create an app password at <https://myaccount.google.com/apppasswords> (any name, e.g. "Gift Exchange").
   Google shows 16 letters once.
3. In the app, open **Setup**, pick **Gmail**, enter your address and the app password, and press
   **Save and test the connection**. Tick "Remember" if you don't want to type it each time.
4. On the **Message** page, in Real mode, send a test email to yourself first.

iCloud Mail and Yahoo Mail work the same way with their own app passwords. For other providers choose
**Other** and enter the SMTP server, port and security from your provider's help pages.

Good to know:

- If an email fails, the run stops there; press **Send all unsent** again to continue. Nobody gets two
  emails unless you press **Send again** for them.
- Your Gmail **Sent** folder holds every email, including the matches. The default message keeps the
  match out of the preview line, but opening a sent email shows it.
- Once real sending starts, the draw is locked: only email addresses can change. **Start a new
  exchange** on the Send page clears the draw for next year and keeps the people and the message.

## Your data

Names, addresses, draws and email settings stay on your computer, never in this folder or in git:

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
