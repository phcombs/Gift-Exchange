"""Checks on a group's people, and the paste box parser. Pure."""

import re
from collections import defaultdict

from giftx.model import Problem

# "something, one @, something, a dot, something", no spaces. Catches blanks and obvious typos only.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_name(name):
    return " ".join((name or "").split())


def clean_email(email):
    return (email or "").strip()


def is_valid_email(email):
    return bool(_EMAIL.match(clean_email(email)))


def name_problem(name, existing_names=()):
    """The reason a name can't be used, or None. existing_names: other names in the group."""
    name = clean_name(name)
    if not name:
        return "The name is blank."
    if name.casefold() in {clean_name(n).casefold() for n in existing_names}:
        return f"There is already someone called {name} in this group."
    return None


def email_problem(email):
    email = clean_email(email)
    if not email:
        return "The email address is blank."
    if not is_valid_email(email):
        return f"{email} doesn't look like an email address."
    return None


def check_group(people):
    """Problems that keep the Draw button disabled: bad addresses and duplicate names."""
    problems = []
    for p in people:
        reason = email_problem(p.email)
        if reason:
            problems.append(Problem("bad_email", f"{p.name}: {reason}"))
    by_name = defaultdict(list)
    for p in people:
        by_name[clean_name(p.name).casefold()].append(p.name)
    for names in by_name.values():
        if len(names) > 1:
            problems.append(
                Problem("duplicate_name", f"{names[0]} appears {len(names)} times. Names must differ.")
            )
    return problems


def shared_addresses(people):
    """[(names, address)] for every address used by more than one person."""
    by_email = defaultdict(list)
    for p in people:
        by_email[clean_email(p.email).lower()].append(p)
    return [
        ([p.name for p in group], clean_email(group[0].email))
        for group in by_email.values()
        if len(group) > 1
    ]


def shared_notice(names, address):
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"{listed} share {address}. Each can read the other's match."


def parse_pasted(text, existing_names=()):
    """Parse one "name, email" per line, split at the last comma.

    Returns (good: [(name, email)], bad: [(line_no, line, reason)]). Blank lines are skipped.
    A name that repeats an existing name, or one earlier in the paste, is bad.
    """
    good, bad = [], []
    taken = list(existing_names)
    for line_no, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if "," not in line:
            bad.append((line_no, line, 'Expected "name, email".'))
            continue
        name, email = line.rsplit(",", 1)
        name, email = clean_name(name), clean_email(email)
        reason = name_problem(name, taken) or email_problem(email)
        if reason:
            bad.append((line_no, line, reason))
            continue
        good.append((name, email))
        taken.append(name)
    return good, bad
