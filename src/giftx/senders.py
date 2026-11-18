"""Senders: the practice sender (writes files) and the SMTP sender (real email through an app password).

Result rules for SMTP (reasons never hold names, addresses or server text, which can echo addresses):
  connect / TLS / login fails            -> Rejected  (nothing was handed over)
  server refuses sender, recipient, data -> Rejected  (the server said no)
  anything else once sending has begun   -> Unknown   (the message may have been accepted)
"""

import smtplib
import ssl
from email.utils import formatdate, make_msgid
from typing import Protocol

from giftx import paths
from giftx.model import Outgoing, Rejected, Sent, Unknown

TIMEOUT = 30  # seconds, for connect and each server reply


class Sender(Protocol):
    def send(self, msg: Outgoing) -> "Sent | Rejected | Unknown": ...


class PracticeSender:
    """Writes practice/<msg.key>.eml in the data folder. Never contacts anything."""

    @staticmethod
    def path_for(key):
        return paths.practice_root() / f"{key}.eml"

    def send(self, msg):
        path = self.path_for(msg.key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "xb") as f:  # never overwrite an earlier practice email
                f.write(msg.raw)
        except OSError as err:
            return Rejected(f"could not write the practice file ({type(err).__name__})")
        return Sent()


def open_connection(host, port, security, timeout=TIMEOUT):
    """An SMTP connection with TLS. Tests replace this function; it is the only place that connects."""
    context = ssl.create_default_context()
    if security == "ssl":
        return smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    conn = smtplib.SMTP(host, port, timeout=timeout)
    try:
        conn.starttls(context=context)
    except BaseException:
        conn.close()
        raise
    return conn


def _close(conn):
    try:
        conn.quit()
    except Exception:
        conn.close()


def with_envelope_headers(raw, from_address):
    """Add From, Date and Message-ID (the stored email has none) and use CRLF line endings for SMTP."""
    domain = from_address.rsplit("@", 1)[-1]
    head = (
        f"From: {from_address}\nDate: {formatdate(localtime=True)}\n"
        f"Message-ID: {make_msgid(domain=domain)}\n"
    ).encode("ascii")
    return (head + raw).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def login_problem(host, port, security, address, password):
    """Connect and sign in, then disconnect. A sentence for the page, or None if it worked."""
    try:
        conn = open_connection(host, port, security)
    except (smtplib.SMTPException, OSError) as err:
        return f"Could not connect to {host}:{port} ({type(err).__name__}). Check the server, port and security."
    try:
        conn.login(address, password)
    except smtplib.SMTPAuthenticationError:
        return "The server refused the sign-in. Check the address and the app password."
    except (smtplib.SMTPException, OSError) as err:
        return f"Signing in failed ({type(err).__name__})."
    finally:
        _close(conn)
    return None


class SmtpSender:
    """Sends each email over its own SMTP connection, signed in with an app password."""

    def __init__(self, host, port, security, address, password):
        self.host, self.port, self.security = host, port, security
        self.address, self.password = address, password

    def send(self, msg):
        try:
            conn = open_connection(self.host, self.port, self.security)
        except (smtplib.SMTPException, OSError) as err:
            return Rejected(f"could not connect to the email server ({type(err).__name__})")
        try:
            try:
                conn.login(self.address, self.password)
            except smtplib.SMTPAuthenticationError:
                return Rejected("the email server refused the sign-in; check the app password")
            except (smtplib.SMTPException, OSError) as err:
                return Rejected(f"signing in failed ({type(err).__name__})")
            raw = with_envelope_headers(msg.raw, self.address)
            try:
                conn.sendmail(self.address, [msg.to], raw)
            except smtplib.SMTPRecipientsRefused:
                return Rejected("the email server refused the recipient address")
            except smtplib.SMTPSenderRefused as err:
                return Rejected(f"the email server refused the sender ({err.smtp_code})")
            except smtplib.SMTPDataError as err:
                return Rejected(f"the email server refused the message ({err.smtp_code})")
            except (smtplib.SMTPException, OSError) as err:
                return Unknown(f"the connection broke while sending ({type(err).__name__})")
            return Sent()
        finally:
            _close(conn)
