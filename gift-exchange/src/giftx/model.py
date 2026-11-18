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
