"""Message templates and email building. Pure.

Placeholders are filled by literal text replacement, so any other brace ("{", "{{name}}", "{}") is left
exactly as typed and can never crash a send.
"""

import html
import re
from email.message import EmailMessage
from email.policy import default
from email.utils import make_msgid

from giftx.model import Problem

GIVER = "{giver}"
RECIPIENT = "{recipient}"
PICTURE = "{picture}"  # optional: where the picture goes; at the end without it

DEFAULT_SUBJECT = "Christmas Gift Exchange"
DEFAULT_BODY = (
    "Hi {giver}, happy Festivus.\n\n\n\n\n\n"
    "You are buying a gift for {recipient}."
)

# Earlier defaults. A group still holding one of these unchanged is moved to the current default when
# the database opens; a message someone edited is never touched.
_LEAD_IN_BODY = (
    "Hi {giver},\n\n"
    "This email tells you who you are buying a gift for in this year's gift exchange. The name is "
    "further down, so it does not show up in inbox or Sent-folder previews where someone else might "
    "see it. Scroll down when you are ready to read it.\n\n\n\n\n"
    "You are buying a gift for {recipient}."
)
OLD_DEFAULT_BODIES = (
    _LEAD_IN_BODY,
    _LEAD_IN_BODY + "\n\nPlease keep it a secret!",
)
OLD_DEFAULT_SUBJECTS = ("Gift exchange: your match, {giver}",)

PREVIEW_GIVER = "Alex"
PREVIEW_RECIPIENT = "Sam"

# refusals (the message is not saved) and the one warning (saved anyway)
RECIPIENT_IN_SUBJECT = Problem(
    "recipient_in_subject",
    "The subject can't contain {recipient}: subjects show in your Gmail Sent list, so you would see "
    "every match.",
)
BLANK_SUBJECT = Problem("blank_subject", "The subject is blank.")
NO_GIVER = Problem(
    "no_giver",
    "The message must contain {giver}, so people who share an email address can tell their emails apart.",
)
NO_RECIPIENT = Problem(
    "no_recipient",
    "The message doesn't contain {recipient}, so nobody will learn who they are buying for.",
)
WARNINGS = {NO_RECIPIENT.code}

_PLACEHOLDER = re.compile(re.escape(GIVER) + "|" + re.escape(RECIPIENT))

IMAGE_TYPES = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif"}


def fill(template, giver, recipient):
    # one pass, so a name that itself looks like a placeholder is never filled again
    values = {GIVER: giver, RECIPIENT: recipient}
    return _PLACEHOLDER.sub(lambda m: values[m.group(0)], template)


def check_template(subject, body):
    """Problems with a subject and body. Codes in WARNINGS allow saving; the rest refuse it."""
    problems = []
    if not subject.strip():
        problems.append(BLANK_SUBJECT)
    if RECIPIENT in subject:
        problems.append(RECIPIENT_IN_SUBJECT)
    if GIVER not in body:
        problems.append(NO_GIVER)
    if RECIPIENT not in body:
        problems.append(NO_RECIPIENT)
    return problems


def refusals(problems):
    return [p for p in problems if p.code not in WARNINGS]


def preview(subject, body):
    """The message filled with the made-up pair Alex and Sam. Never reads a draw."""
    return (
        fill(subject, PREVIEW_GIVER, PREVIEW_RECIPIENT),
        fill(body, PREVIEW_GIVER, PREVIEW_RECIPIENT),
    )


def preview_text(body):
    """The preview body as shown on the page: where the picture goes is marked."""
    return body.replace(PICTURE, "[picture]")


def plain_text(body):
    """The text version: the {picture} placeholder is removed."""
    return body.replace(PICTURE, "")


def html_body(body, cid):
    """The HTML version: the text kept as written (escaped, line breaks kept) with the picture shown
    where {picture} is, or at the end when there's no placeholder."""
    img = f'<img src="cid:{cid}" alt="" style="max-width:100%;height:auto;">'
    pieces = [html.escape(p).replace("\n", "<br>\n") for p in body.split(PICTURE)]
    content = img.join(pieces) if len(pieces) > 1 else pieces[0] + "<br>\n<br>\n" + img
    return (
        # styles sit on a <div>: many mail apps (Gmail among them) drop styles on <body>
        '<!DOCTYPE html><html><body>\n<div style="font-family:Arial,sans-serif;font-size:15px;'
        f'line-height:1.4">\n{content}\n</div>\n</body></html>\n'
    )


def build_email(to, subject, body, image=None):
    """A UTF-8 email as bytes. No From header (the sender adds it). Subject and body must already be
    filled in. image: (bytes, ext) or None.

    Without an image: plain text only. With one: plain text plus an HTML version that shows the
    picture inline (an animated GIF plays in the message), referenced by Content-ID.
    """
    msg = EmailMessage(policy=default)
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(plain_text(body), subtype="plain", charset="utf-8")
    if image is not None:
        data, ext = image
        ext = ext.lower().lstrip(".")
        subtype = IMAGE_TYPES.get(ext)
        if subtype is None:
            raise ValueError(f"unsupported image type: {ext}")
        cid = make_msgid(domain="giftx.invalid")
        msg.add_alternative(html_body(body, cid[1:-1]), subtype="html", charset="utf-8")
        msg.get_payload()[1].add_related(
            data, maintype="image", subtype=subtype, cid=cid,
            disposition="inline", filename=f"picture.{ext}",
        )
    return msg.as_bytes()


def inline_images(msg):
    """[(filename, content-type, bytes, content-id)] of the pictures shown inside a parsed message."""
    return [
        (part.get_filename(), part.get_content_type(), part.get_content(), part["Content-ID"])
        for part in msg.walk()
        if part.get_content_maintype() == "image"
    ]
