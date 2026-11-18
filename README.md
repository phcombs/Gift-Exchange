# Gift Exchange

A small app that runs a family gift exchange on your own computer: enter the people, mark couples, draw
who buys for whom (the matches stay hidden, even from you), and email everyone their match, with a GIF
if you like.

It runs on **Windows, macOS and Linux**. You don't need to install anything first: the first start sets
up everything it needs (this needs an internet connection and takes a minute or two).

## 1. Get the app

**Easiest (no tools needed):** on the [GitHub page](https://github.com/phcombs/Gift-Exchange), click the
green **Code** button, then **Download ZIP**. Unzip it (Windows: right-click → **Extract All**; Mac:
double-click the zip). Open the folder it makes, then the **gift-exchange** folder inside it.

**With git:**

```text
git clone https://github.com/phcombs/Gift-Exchange.git
cd Gift-Exchange/gift-exchange
```

## 2. Start it

| System | How |
|---|---|
| **Windows** | Double-click **`run.cmd`** in the gift-exchange folder. |
| **macOS** | Double-click **`run`** in the gift-exchange folder. Or in Terminal: `./run` |
| **Linux** | In a terminal, in the gift-exchange folder: `./run` |

A black terminal window opens and shows progress. Your browser then opens the app at
<http://localhost:8501>.

**The first start** downloads what the app needs, once: a small tool called
[uv](https://docs.astral.sh/uv/), Python 3.12 (just for this app) and the app's packages. This takes a
minute or two. Later starts take a few seconds. Nothing is installed system-wide and no admin rights
are needed. If you already have Python 3.8 or newer, it's used to start, and the rest is still set up
privately.

**To stop the app,** close the terminal window (or press **Ctrl+C** in it). To start it again later, do
step 2 again; your groups, people and settings are kept.

If your computer warns you the first time:

- **Windows** ("Windows protected your PC"): click **More info**, then **Run anyway**.
- **macOS** ("can't be opened because it is from an unidentified developer"): right-click `run`, choose
  **Open**, then **Open** again. If it opens as text instead, open Terminal, type `cd ` (with a space),
  drag the gift-exchange folder into the window, press Enter, then type `sh run` and press Enter.

## 3. Run your exchange

The app starts in **Practice** mode (switch in the left sidebar): emails are written to files on your
computer instead of being sent, so you can try everything safely.

1. **People** page: create a group, then add people one at a time, or paste a list with one
   `name, email` per line. Mark couples; they never draw each other.
2. **Message** page: edit the subject and message. `{giver}` becomes the person reading the email and
   `{recipient}` the person they buy for. The preview uses made-up names (Alex and Sam).
3. **Images** page (optional): add a GIF or picture. Each email shows one inside the message.
4. **Send** page: press **Draw**. Everyone is listed with "match hidden". Press **Send all unsent**,
   check the list, and confirm. In Practice mode, open the email files it writes (the page says where)
   to check them.
5. When everything looks right, set up Gmail (next section), switch the sidebar to **Real**, and send.

## 4. Send real email from Gmail

The app sends from your own Gmail account using an **app password**: a separate 16-letter password that
Google makes for one app. It can be revoked at any time and your normal password is never used. You
don't need a developer account or a Google Cloud project.

1. **Turn on 2-Step Verification** for your Google account, if it isn't on yet:
   <https://myaccount.google.com/signinoptions/twosv>. App passwords only exist once this is on.
2. **Create an app password** at <https://myaccount.google.com/apppasswords>. Type a name such as
   "Gift Exchange" and click **Create**. Google shows 16 letters once; copy them.
3. **In the app**, open the **Setup** page. Choose **Gmail**, enter your Gmail address, paste the app
   password (spaces don't matter), and press **Save and test the connection**. It signs in once to
   check, and says "Real mode is ready" when it works.
   - Tick **Remember the app password on this computer** if you don't want to enter it each time you
     start the app. Otherwise it's forgotten when the app stops.
4. **Send yourself a test:** switch the sidebar to **Real**, go to the **Message** page, type your own
   address in **Send test to**, and press **Send test email**. Check your inbox.
5. **Send everyone their match:** on the **Send** page in Real mode, press **Send all unsent** and
   confirm. Each person's status shows in the table.

If the app passwords page says the setting isn't available: 2-Step Verification is off, or the account
is a work/school account (those may not allow app passwords), or it uses Advanced Protection.

**Other providers:** iCloud Mail and Yahoo Mail work the same way with their own app passwords (choose
them on the Setup page). For anything else, choose **Other** and enter the SMTP server, port and
security from your provider's help pages.

**To stop using it:** press **Forget this account** on the Setup page, and delete the app password at
<https://myaccount.google.com/apppasswords>.

Good to know:

- If an email fails, the run stops there. Press **Send all unsent** again to continue. Nobody gets two
  emails unless you press **Send again** for them.
- Your Gmail **Sent** folder holds every email, including the matches. The default message keeps the
  match out of the inbox preview line, but opening a sent email shows it.
- Once real sending starts, the draw is locked: only email addresses can change. **Start a new
  exchange** on the Send page clears the draw for next year and keeps the people and the message.

## More features

- **Pictures:** JPEG, PNG or GIF up to 10 MB each (animated GIFs play in Gmail). With several, everyone
  gets a different one while they last; with one, everyone gets that one. It appears at the end of the
  message, or wherever you type `{picture}`. With no pictures, emails are plain text.
- **Fixed matches:** on the Send page, open **Fixed matches** before drawing to choose who buys for whom
  for anyone you like; everyone else is drawn at random around them.
- **Reveal:** the matches stay hidden, since the organizer is usually in the draw. To see them, turn on
  **Reveal the matches** on the Send page. It's off again in every new tab.
- **Changing a match:** with Reveal on, **Change a match** gives someone a different person (the two
  people involved swap). This works until real emails start going out.
- **Saved draws:** found a draw you like but want to try other things? Open **Saved draws**, name it and
  save it. **Restore** brings it back exactly, as long as the group has the same people.

## Your data

Names, addresses, draws and email settings stay on your computer, outside the app folder, never in git:

| System | Folder |
|---|---|
| Windows | `%APPDATA%\Gift Exchange` (paste into File Explorer's address bar) |
| macOS | `~/Library/Application Support/Gift Exchange` |
| Linux | `~/.local/share/gift-exchange` |

Everything is in one file, `giftx.sqlite3`; back it up by copying it. Practice emails are in the
`practice` folder next to it. Set the `GIFTX_DATA_DIR` environment variable to use another folder.

**Updating:** download the new ZIP (or `git pull`) and start it the same way. Your data is kept, because
it lives outside the app folder.

**Removing it:** delete the app folder and the data folder above. To remove uv as well, delete `uv.exe`
from `%USERPROFILE%\.local\bin` (Windows) or `~/.local/bin/uv` (Mac/Linux), and its downloads with
`uv cache clean` beforehand if you like. Delete the app password in your Google account.

## Troubleshooting

- **The browser didn't open:** go to <http://localhost:8501> yourself.
- **"The app is already running"**: it's open in another window; the browser tab opens again.
- **The terminal window closed right away (Windows):** start `run.cmd` from a terminal to see the
  message, or check your internet connection for the first start.
- **"The server refused the sign-in"**: use the app password, not your normal password, and check that
  2-Step Verification is on.
- **A person shows "may or may not have gone"**: the connection broke mid-send. Look in your Sent
  folder, then press **It went** or **Send again** for that person on the Send page.
- **"The picture for … is missing"**: a picture was deleted outside the app after emails were prepared.
  Run practice again, or **Start a new exchange** before real sending begins.
- The app only listens on your own computer (`localhost`); other devices on your Wi-Fi can't open it.

## For developers

From `gift-exchange/`: run the tests with `uv run --frozen pytest -q`, or start with `python run.py`.
The design is in `gift-exchange/docs/designs/design_draft.md`; `HANDOFF.md` has the current status.

---

*That rug tied the room together.*
