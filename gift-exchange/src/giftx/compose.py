"""Message templates and email building. Pure.

Placeholders are filled by literal text replacement, so any other brace ("{", "{{name}}", "{}") is left
exactly as typed and can never crash a send.
"""

import re
from email.message import EmailMessage
from email.policy import default

from giftx.model import Problem

GIVER = "{giver}"
RECIPIENT = "{recipient}"

DEFAULT_SUBJECT = "Gift exchange: your match, {giver}"
DEFAULT_BODY = (
    "Hi {giver},\n\n"
    "This email tells you who you are buying a gift for in this year's gift exchange. The name is "
    "further down, so it does not show up in inbox or Sent-folder previews where someone else might "
    "see it. Scroll down when you are ready to read it.\n\n\n\n\n"
    "You are buying a gift for {recipient}."
)

# earlier defaults: a group still holding one of these unchanged is moved to DEFAULT_BODY
OLD_DEFAULT_BODIES = (
    DEFAULT_BODY + "\n\nPlease keep it a secret!",
)

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


def build_email(to, subject, body, image=None):
    """A plain-text UTF-8 email as bytes. image: (bytes, ext) or None. No From header: Gmail adds it.

    Subject and body must already be filled in.
    """
    msg = EmailMessage(policy=default)
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body, subtype="plain", charset="utf-8")
    if image is not None:
        data, ext = image
        ext = ext.lower().lstrip(".")
        subtype = IMAGE_TYPES.get(ext)
        if subtype is None:
            raise ValueError(f"unsupported image type: {ext}")
        msg.add_attachment(data, maintype="image", subtype=subtype, filename=f"picture.{ext}")
    return msg.as_bytes()
