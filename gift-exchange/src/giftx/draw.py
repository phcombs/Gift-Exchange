"""The draw: who buys for whom. Pure; imports nothing from giftx.

Shuffle the recipients and keep the first order where nobody has themselves or their partner.
Every valid draw is equally likely, because each shuffle is uniform and invalid ones are thrown away.
"""

EMPTY = "Add people to this group before drawing."
ONE_PERSON = "A draw needs at least two people."
TWO_COUPLE = "Two people who are a couple cannot draw each other. Add more people."
THREE_WITH_COUPLE = (
    "With three people and one couple, someone would have to draw their own partner. "
    "Add a fourth person or remove the couple."
)
FAILED = "The draw failed unexpectedly. Try again."

MAX_TRIES = 10_000


class DrawImpossible(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _has_couple(people, partner_of):
    members = set(people)
    return any(partner_of.get(p) in members for p in people)


def make_draw(people, partner_of, rng):
    """Return {giver: recipient}. Raises DrawImpossible with one of the module's messages."""
    people = list(people)
    if not people:
        raise DrawImpossible(EMPTY)
    if len(people) == 1:
        raise DrawImpossible(ONE_PERSON)
    if len(people) == 2 and _has_couple(people, partner_of):
        raise DrawImpossible(TWO_COUPLE)
    if len(people) == 3 and _has_couple(people, partner_of):
        raise DrawImpossible(THREE_WITH_COUPLE)

    recipients = list(people)
    for _ in range(MAX_TRIES):
        rng.shuffle(recipients)
        if all(r != g and partner_of.get(g) != r for g, r in zip(people, recipients)):
            return dict(zip(people, recipients))
    raise DrawImpossible(FAILED)
