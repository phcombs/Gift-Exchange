from giftx.model import Person
from giftx.people import (
    check_group,
    clean_name,
    is_valid_email,
    parse_pasted,
    shared_addresses,
    shared_notice,
)


def person(pid, name, email, partner=None):
    return Person(pid, 1, name, email, partner)


def test_clean_name_trims_and_collapses_spaces():
    assert clean_name("  Ann   Lee ") == "Ann Lee"
    assert clean_name(None) == ""


def test_email_check_catches_blanks_and_obvious_typos():
    assert is_valid_email("ann@example.com")
    assert is_valid_email("  ann.lee+gifts@example.org ")
    for bad in ["", "ann", "ann@", "ann@example", "ann @example.com", "a@b@example.com"]:
        assert not is_valid_email(bad), bad


def test_paste_splits_at_last_comma():
    good, bad = parse_pasted("Smith, Jr., John, john@example.com")
    assert good == [("Smith, Jr., John", "john@example.com")]
    assert bad == []


def test_paste_lists_bad_lines_and_keeps_good_ones():
    text = "\n".join([
        "Ann, ann@example.com",
        "",
        "no comma here",
        "Bob, not-an-address",
        ", blank@example.com",
        "ann, other@example.com",
        "Cy, cy@example.com",
    ])
    good, bad = parse_pasted(text, existing_names=["Dee"])
    assert good == [("Ann", "ann@example.com"), ("Cy", "cy@example.com")]
    assert [line_no for line_no, _, _ in bad] == [3, 4, 5, 6]
    assert "already someone called ann" in bad[3][2]


def test_paste_refuses_existing_names_ignoring_case():
    good, bad = parse_pasted("DEE, dee2@example.com", existing_names=["Dee"])
    assert good == [] and len(bad) == 1


def test_check_group_lists_bad_addresses_and_duplicate_names():
    people = [
        person(1, "Ann", "ann@example.com"),
        person(2, "ann", "ann2@example.com"),
        person(3, "Bob", "bob@"),
        person(4, "Cy", ""),
    ]
    codes = sorted(p.code for p in check_group(people))
    assert codes == ["bad_email", "bad_email", "duplicate_name"]


def test_check_group_passes_a_good_group():
    assert check_group([person(1, "Ann", "a@example.com"), person(2, "Bob", "b@example.com")]) == []


def test_shared_addresses_and_notice():
    people = [
        person(1, "Ann", "family@example.com"),
        person(2, "Bob", "Family@example.com "),
        person(3, "Cy", "cy@example.com"),
    ]
    shared = shared_addresses(people)
    assert shared == [(["Ann", "Bob"], "family@example.com")]
    assert shared_notice(*shared[0]) == (
        "Ann and Bob share family@example.com. Each can read the other's match."
    )
