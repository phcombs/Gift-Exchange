"""Regenerate the README screenshots in docs/screenshots/.

    uv run --group docs playwright install chromium     (once: downloads the browser)
    uv run --group docs python scripts/screenshots.py

Starts its own copy of the app on port 8502 with a temporary data folder full of made-up people
(example.com addresses) and a generated GIF, clicks through it in a headless browser, and saves one
PNG per step. Your real data and a running copy of the app on port 8501 are not touched. Nothing is
emailed: the app stays in practice mode, and the Setup page is only filled in, never saved.
"""

import base64
import html
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "screenshots"
PORT = 8502
URL = f"http://localhost:{PORT}"
VIEWPORT = {"width": 1280, "height": 2400}  # tall: pages never scroll, shots are cropped instead

PEOPLE = [
    ("Alex Smith", "Jamie Smith"),
    ("Morgan Lee", "Riley Lee"),
    ("Sam Carter", "Taylor Carter"),
    ("Jordan Park", None),
    ("Casey Nguyen", None),
]


# ------------------------------------------------------------------ demo data

def gift_gif(path):
    """A small animated GIF of a wrapped present (drawn with Pillow, which Streamlit already needs)."""
    from PIL import Image, ImageDraw

    frames = []
    for i in range(8):
        img = Image.new("RGB", (240, 200), (250, 246, 238))
        d = ImageDraw.Draw(img)
        lift = [0, 3, 6, 8, 6, 3, 0, 0][i]
        d.rectangle([60, 90, 180, 180], fill=(200, 40, 50))  # box
        d.rectangle([52, 70 - lift, 188, 95 - lift], fill=(220, 60, 70))  # lid
        d.rectangle([112, 70 - lift, 128, 180], fill=(245, 200, 60))  # ribbon
        d.ellipse([92, 48 - lift, 120, 72 - lift], outline=(245, 200, 60), width=6)  # bow
        d.ellipse([120, 48 - lift, 148, 72 - lift], outline=(245, 200, 60), width=6)
        for k in range(6):  # sparkles
            x, y = (30 + k * 37) % 230, (20 + k * 53 + i * 9) % 60
            d.text((x, y), "*", fill=(240, 170, 40))
        frames.append(img)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=120, loop=0)


def seed(data_dir):
    os.environ["GIFTX_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(REPO / "src"))
    from giftx import images, paths
    from giftx.draw import make_draw
    from giftx.storage import Storage

    paths.data_dir()
    store = Storage(paths.db_path())
    gid = store.create_group("Smith family")
    for a, b in PEOPLE:
        pa = store.add_person(gid, a, a.split()[0].lower() + "@example.com")
        if b:
            pb = store.add_person(gid, b, b.split()[0].lower() + "@example.com")
            store.set_couple(pa, pb)
    gif = Path(data_dir) / "gift.gif"
    gift_gif(gif)
    images.save_image(gif.read_bytes())
    gif.unlink()
    people = store.list_people(gid)
    partner_of = {p.id: p.partner_id for p in people if p.partner_id}
    store.save_draw(gid, make_draw([p.id for p in people], partner_of, random.Random(7)),
                    datetime.now(timezone.utc))
    return gid


# ------------------------------------------------------------------ app and browser

def healthy():
    try:
        with urllib.request.urlopen(URL + "/_stcore/health", timeout=1) as r:
            return r.read().strip() == b"ok"
    except Exception:
        return False


def start_app(data_dir):
    env = dict(os.environ, GIFTX_DATA_DIR=str(data_dir), GIFTX_NO_SHORTCUT="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
         "--server.port", str(PORT), "--server.headless", "true"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(120):
        if healthy():
            return proc
        time.sleep(0.5)
    proc.kill()
    raise SystemExit("The app did not start on port 8502.")


def settle(page, text=None):
    """Wait for a rerun to finish (and for some text, if given)."""
    if text:
        page.get_by_text(text, exact=False).first.wait_for(timeout=20_000)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=20_000
    )
    page.wait_for_timeout(700)


MAIN_COLUMN = (410, 1170)  # x range of the page's content column, for shots that start mid-page


def shot(page, name, bottom, top=None, pad=28, top_pad=12, main_only=False):
    """Crop from the top of the page (or just above `top`) to just below `bottom` (locators), so each
    picture ends at a clean edge and shows only what its README step talks about. Shots that start
    mid-page (main_only) leave out the sidebar, which would only be an empty strip there."""
    path = OUT / f"{name}.png"
    page.mouse.move(VIEWPORT["width"] - 5, 5)  # away from tables and the sidebar's collapse button
    page.wait_for_timeout(300)
    y0 = max(0, top.bounding_box()["y"] - top_pad) if top is not None else 0
    box = bottom.bounding_box()
    y1 = box["y"] + box["height"] + pad
    x0, x1 = MAIN_COLUMN if main_only else (0, VIEWPORT["width"])
    page.screenshot(path=str(path), clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
    print("saved", path.relative_to(REPO))


def open_page(page, path, text):
    page.goto(f"{URL}/{path}")
    settle(page, text)


def render_email(page, data_dir):
    """Show one practice email the way a mail app would: headers, then the HTML part with the picture."""
    eml = sorted((Path(data_dir) / "practice").rglob("*.eml"))[0]
    msg = message_from_bytes(eml.read_bytes(), policy=default)
    body = msg.get_body(("html",)).get_content()
    for part in msg.walk():
        if part.get_content_maintype() == "image":
            uri = f"data:{part.get_content_type()};base64,{base64.b64encode(part.get_content()).decode()}"
            body = body.replace("cid:" + part["Content-ID"].strip("<>"), uri)
    head = (
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#444;border-bottom:1px solid #ddd;'
        'padding:0 0 12px 0;margin-bottom:16px">'
        f'<div style="font-size:20px;color:#222;margin-bottom:8px">{html.escape(msg["Subject"])}</div>'
        f'<div><b>From:</b> you@example.com &nbsp; <b>To:</b> {html.escape(msg["To"])}</div></div>'
    )
    page.set_viewport_size({"width": 760, "height": 200})  # grows to the content with full_page
    page.set_content(
        '<html><body style="margin:24px;background:#fff">' + head
        + body.split("<body", 1)[1].split(">", 1)[1].rsplit("</body>", 1)[0] + "</body></html>"
    )
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "email.png"), full_page=True)
    print("saved", (OUT / "email.png").relative_to(REPO))
    page.set_viewport_size(VIEWPORT)


def main():
    if healthy():
        raise SystemExit("Something already runs on port 8502. Stop it first.")
    OUT.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix="giftx-shots-"))
    seed(data_dir)
    proc = start_app(data_dir)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)

            button = lambda label: page.get_by_role("button", name=label, exact=True)  # noqa: E731
            send_heading = lambda: page.get_by_role("heading", name="Send", exact=True)  # noqa: E731
            tables = page.locator('[data-testid="stDataFrame"]')

            # People: the group, its people and partners, and the "Add a person" form
            open_page(page, "people", "Smith family")
            shot(page, "people", bottom=button("Add person"))

            # Message: the editor and the whole preview, down to its caption
            open_page(page, "message", "Preview")
            shot(page, "message", bottom=page.get_by_text("Send a test email to see it."), pad=16)

            # Images: the uploader and the library
            open_page(page, "images", "Pictures")
            shot(page, "images", bottom=button("Delete"), pad=20)

            # Send, after drawing: the hidden draw table
            open_page(page, "send", "Draw again")
            shot(page, "send-draw", bottom=tables.first, pad=20)

            # More features: Fixed matches and Saved draws opened
            page.get_by_text("Fixed matches").first.click()
            settle(page)
            page.get_by_text("Saved draws").first.click()
            settle(page)
            shot(page, "send-options", bottom=button("Save this draw"))
            page.get_by_text("Fixed matches").first.click()
            page.get_by_text("Saved draws").first.click()
            settle(page)

            # Confirm step: from the Send heading to the bottom of the confirm box
            button("Send all unsent").click()
            settle(page, "Confirm and send")
            shot(page, "send-confirm", top=send_heading(), bottom=button("Cancel"), main_only=True)

            # After a practice run: the status table. (The message at the top names the practice
            # folder, a path with the local user name, so it is left out of the pictures.)
            button("Confirm and send").click()
            settle(page, "practice emails")
            shot(page, "send-status", top=send_heading(), bottom=tables.last, pad=12, main_only=True)

            render_email(page, data_dir)

            open_page(page, "", "Email account")  # the default page lives at /
            page.get_by_label("Your email address").fill("you@example.com")
            page.get_by_label("App password", exact=True).fill("abcdefghijklmnop")
            page.evaluate("document.activeElement.blur()")  # no focus outline in the picture
            settle(page)
            shot(page, "setup", bottom=button("Save and test the connection"), pad=20)

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
