"""Shared types. Imports nothing from the rest of giftx."""

from dataclasses import dataclass
from typing import Optional

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
