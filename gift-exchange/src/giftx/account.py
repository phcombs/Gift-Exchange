"""The email account real mode sends from: SMTP server settings and the app password.

Settings live in the data folder (email.json, outside the repo). The app password is written there
only when the organizer ticks "Remember"; otherwise the page keeps it in memory until the app stops.
"""

import json
import os
from dataclasses import asdict, dataclass, replace
from typing import Optional

from giftx import paths
from giftx.people import clean_email, is_valid_email


@dataclass(frozen=True)
class Preset:
    label: str
    host: str
    port: int
    security: str  # "ssl" (implicit TLS) or "starttls"
    help: str


PRESETS = {
    "gmail": Preset(
        "Gmail", "smtp.gmail.com", 465, "ssl",
        "Turn on 2-Step Verification for your Google account, then create an app password at "
        "https://myaccount.google.com/apppasswords and paste the 16 letters here.",
    ),
    "icloud": Preset(
        "iCloud Mail", "smtp.mail.me.com", 587, "starttls",
        "Create an app-specific password at https://account.apple.com (Sign-In and Security) and paste "
        "it here.",
    ),
    "yahoo": Preset(
        "Yahoo Mail", "smtp.mail.yahoo.com", 465, "ssl",
        "Generate an app password in your Yahoo account's security settings and paste it here.",
    ),
    "other": Preset(
        "Other", "", 587, "starttls",
        "Enter your provider's SMTP server, port and security. Use an app password if your provider "
        "offers one.",
    ),
}
SECURITY = {"ssl": "SSL/TLS (usually port 465)", "starttls": "STARTTLS (usually port 587)"}


@dataclass(frozen=True)
class EmailSettings:
    provider: str
    host: str
    port: int
    security: str
    address: str
    password: Optional[str] = None  # set only when remembered on this computer


def clean_password(password):
    # app passwords are shown in groups ("abcd efgh ijkl mnop"); the spaces are not part of them
    return "".join((password or "").split())


def settings_problem(settings):
    """The reason these settings can't be used, or None."""
    if settings.provider not in PRESETS:
        return "Choose an email provider."
    if not settings.host.strip():
        return "Enter the SMTP server name."
    if not (0 < int(settings.port) < 65536):
        return "The port must be a number between 1 and 65535."
    if settings.security not in SECURITY:
        return "Choose the connection security."
    if not is_valid_email(settings.address):
        return "Enter the email address you send from."
    return None


def load():
    """The saved settings, or None if real mode hasn't been set up."""
    path = paths.email_settings_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return EmailSettings(**data)
    except (OSError, ValueError, TypeError):
        return None


def save(settings, remember_password):
    """Write the settings; the password only if remember_password. File mode 0600 where supported."""
    paths.data_dir()
    settings = replace(
        settings,
        address=clean_email(settings.address),
        host=settings.host.strip(),
        port=int(settings.port),
        password=clean_password(settings.password) if remember_password else None,
    )
    path = paths.email_settings_file()
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, indent=2)
    os.replace(tmp, path)
    return settings


def forget():
    """Delete the saved settings and any remembered password."""
    try:
        paths.email_settings_file().unlink()
    except FileNotFoundError:
        pass
