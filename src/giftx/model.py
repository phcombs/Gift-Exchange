"""Shared types. Imports nothing from the rest of giftx."""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

PersonId = int


@dataclass(frozen=True)
class Problem:
    code: str
    message: str  # shown on the page


@dataclass(frozen=True)
class Person:
    id: PersonId
    group_id: int
    name: str
    email: str
    partner_id: Optional[PersonId]


@dataclass(frozen=True)
class Outgoing:
    key: str  # "<group id>/<send id>" or "test/<UTC time>"; never a name
    to: str
    raw: bytes  # the finished email


# send results; reasons never hold names or addresses
@dataclass(frozen=True)
class Sent:
    pass


@dataclass(frozen=True)
class Rejected:
    reason: str


@dataclass(frozen=True)
class Unknown:
    reason: str


Clock = Callable[[], datetime]  # returns an aware UTC datetime


@dataclass(frozen=True)
class NewRecord:
    """A composed email for one giver, not yet stored."""

    giver_id: PersonId
    subject: str
    body: str
    image_name: Optional[str]


@dataclass(frozen=True)
class SendRecord:
    id: int
    draw_id: int
    group_id: int
    giver_id: PersonId
    giver_name: str
    mode: str  # "practice" | "real"
    status: str  # "pending" | "sending" | "sent" | "failed" | "unknown"
    to_address: Optional[str]
    subject: str
    body: str
    image_name: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    error: Optional[str]


@dataclass(frozen=True)
class Summary:
    sent: int
    failed: int
    unknown: int
    stopped_at: Optional[str]  # the giver name the page shows
    remaining: int


ProgressFn = Callable[[int, int], None]  # (done, total)
