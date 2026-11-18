"""The draw: who buys for whom. Pure; imports nothing from giftx.

Fixed matches ("pins") are kept as chosen; everyone else is drawn around them. Among the valid ways to
draw the rest, every one is equally likely: small leftovers are enumerated, larger ones are shuffled
until valid (invalid shuffles are thrown away).
"""

from itertools import permutations

EMPTY = "Add people to this group before drawing."
ONE_PERSON = "A draw needs at least two people."
TWO_COUPLE = "Two people who are a couple cannot draw each other. Add more people."
THREE_WITH_COUPLE = (
    "With three people and one couple, someone would have to draw their own partner. "
    "Add a fourth person or remove the couple."
)
FAILED = "The draw failed unexpectedly. Try again."
PINS_BLOCK = (
    "The fixed matches leave no valid way to draw everyone else. Remove a fixed match or add people."
)
BAD_PIN = "A fixed match names someone who isn't in this group, or uses a person twice. Check the fixed matches."
SELF_PIN = "A fixed match has someone buying for themselves."

MAX_TRIES = 10_000
ENUMERATE_UP_TO = 8  # 8! = 40,320 orders: fast enough to list every valid one


class DrawImpossible(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _has_couple(people, partner_of):
    members = set(people)
    return any(partner_of.get(p) in members for p in people)


def _ok(giver, recipient, partner_of):
    return giver != recipient and partner_of.get(giver) != recipient


def make_draw(people, partner_of, rng, pins=None):
    """Return {giver: recipient}. pins: {giver: recipient} kept as given (a pin may join a couple:
    the organizer chose it). Raises DrawImpossible with one of the module's messages."""
    people = list(people)
    pins = dict(pins or {})
    if not people:
        raise DrawImpossible(EMPTY)
    if len(people) == 1:
        raise DrawImpossible(ONE_PERSON)
    members = set(people)
    if not pins:
        if len(people) == 2 and _has_couple(people, partner_of):
            raise DrawImpossible(TWO_COUPLE)
        if len(people) == 3 and _has_couple(people, partner_of):
            raise DrawImpossible(THREE_WITH_COUPLE)
    if not set(pins) <= members or not set(pins.values()) <= members or len(set(pins.values())) != len(pins):
        raise DrawImpossible(BAD_PIN)
    if any(g == r for g, r in pins.items()):
        raise DrawImpossible(SELF_PIN)

    givers = [p for p in people if p not in pins]
    recipients = [p for p in people if p not in set(pins.values())]

    # without pins the shuffle always finds a draw quickly (see the design); with pins the leftover
    # may be impossible, so small leftovers are listed in full to know for sure
    if pins and len(givers) <= ENUMERATE_UP_TO:
        valid = [
            order for order in permutations(recipients)
            if all(_ok(g, r, partner_of) for g, r in zip(givers, order))
        ]
        if not valid:
            raise DrawImpossible(PINS_BLOCK)
        chosen = valid[rng.randrange(len(valid))]
        return {**pins, **dict(zip(givers, chosen))}

    for _ in range(MAX_TRIES):
        rng.shuffle(recipients)
        if all(_ok(g, r, partner_of) for g, r in zip(givers, recipients)):
            return {**pins, **dict(zip(givers, recipients))}
    raise DrawImpossible(PINS_BLOCK if pins else FAILED)
