import random
import time
from collections import Counter

import pytest

from giftx import draw
from giftx.draw import DrawImpossible, make_draw


def couples_map(pairs):
    partner_of = {}
    for a, b in pairs:
        partner_of[a] = b
        partner_of[b] = a
    return partner_of


def layouts(size):
    people = list(range(1, size + 1))
    yield "none", people, {}
    if size >= 4:
        yield "some", people, couples_map([(1, 2)])
        yield "all", people, couples_map(zip(people[0::2], people[1::2]))


def check_valid(people, partner_of, result):
    assert sorted(result) == sorted(people)
    assert sorted(result.values()) == sorted(people)
    for giver, recipient in result.items():
        assert giver != recipient
        assert partner_of.get(giver) != recipient


@pytest.mark.parametrize("size", range(2, 21))
def test_every_draw_is_valid(size):
    for _, people, partner_of in layouts(size):
        for seed in range(200):
            check_valid(people, partner_of, make_draw(people, partner_of, random.Random(seed)))


@pytest.mark.parametrize(
    "people,pairs,message",
    [
        ([], [], draw.EMPTY),
        ([1], [], draw.ONE_PERSON),
        ([1, 2], [(1, 2)], draw.TWO_COUPLE),
        ([1, 2, 3], [(1, 2)], draw.THREE_WITH_COUPLE),
    ],
)
def test_impossible_cases_fail_fast_with_their_message(people, pairs, message):
    start = time.monotonic()
    with pytest.raises(DrawImpossible) as err:
        make_draw(people, couples_map(pairs), random.Random(1))
    assert err.value.message == message
    assert time.monotonic() - start < 1


def test_two_people_not_a_couple_draw_each_other():
    assert make_draw([1, 2], {}, random.Random(0)) == {1: 2, 2: 1}


def test_partner_outside_the_list_is_ignored():
    # a partner who is not in this draw does not make three people impossible
    result = make_draw([1, 2, 3], {1: 99, 99: 1}, random.Random(0))
    check_valid([1, 2, 3], {}, result)


def test_seeded_draw_is_repeatable():
    people = list(range(1, 11))
    partners = couples_map([(1, 2), (3, 4)])
    first = make_draw(people, partners, random.Random(42))
    assert make_draw(people, partners, random.Random(42)) == first


def test_draws_are_uniform_over_valid_outcomes():
    people = [1, 2, 3, 4]
    partners = couples_map([(1, 2), (3, 4)])
    rng = random.Random(7)
    counts = Counter(
        tuple(sorted(make_draw(people, partners, rng).items())) for _ in range(6000)
    )
    assert len(counts) == 4
    for outcome, n in counts.items():
        assert 1300 <= n <= 1700, (outcome, n)


def test_never_valid_shuffle_raises_instead_of_looping():
    class Stuck:
        def shuffle(self, items):
            pass  # identity order: everyone draws themselves

    with pytest.raises(DrawImpossible) as err:
        make_draw([1, 2, 3, 4], {}, Stuck())
    assert err.value.message == draw.FAILED


def test_seeded_table(capsys):
    # demo: pytest tests/unit/test_draw.py -s prints this (ids only)
    people = list(range(1, 7))
    partners = couples_map([(1, 2), (3, 4), (5, 6)])
    with capsys.disabled():
        print()
        for seed in range(3):
            result = make_draw(people, partners, random.Random(seed))
            print(f"seed {seed}: " + "  ".join(f"{g}->{r}" for g, r in sorted(result.items())))


# ---------------------------------------------------------------- fixed matches (pins)

@pytest.mark.parametrize("size", [4, 6, 9, 15])
def test_pins_are_kept_and_the_rest_is_valid(size):
    people = list(range(1, size + 1))
    partners = couples_map([(1, 2), (3, 4)])
    pins = {1: 3, 5 if size > 4 else 4: 1}
    for seed in range(100):
        result = make_draw(people, partners, random.Random(seed), pins)
        assert all(result[g] == r for g, r in pins.items())
        assert sorted(result.values()) == people
        for giver, recipient in result.items():
            if giver not in pins:
                assert giver != recipient and partners.get(giver) != recipient


def test_a_pin_may_join_a_couple():
    result = make_draw([1, 2, 3, 4], couples_map([(1, 2)]), random.Random(0), {1: 2})
    assert result[1] == 2


def test_two_person_couple_can_be_fully_pinned():
    assert make_draw([1, 2], couples_map([(1, 2)]), random.Random(0), {1: 2, 2: 1}) == {1: 2, 2: 1}


def test_pins_that_leave_no_valid_rest_say_so():
    # 1->2 and 2->3 are fixed; 3 must buy for 1 but they're a couple
    with pytest.raises(DrawImpossible) as err:
        make_draw([1, 2, 3], couples_map([(3, 1)]), random.Random(0), {1: 2, 2: 3})
    assert err.value.message == draw.PINS_BLOCK


def test_bad_pins_are_refused():
    with pytest.raises(DrawImpossible) as err:
        make_draw([1, 2, 3], {}, random.Random(0), {1: 1})
    assert err.value.message == draw.SELF_PIN
    with pytest.raises(DrawImpossible) as err:
        make_draw([1, 2, 3], {}, random.Random(0), {1: 99})
    assert err.value.message == draw.BAD_PIN


def test_pinned_draws_are_uniform_over_the_rest():
    # 5 people, 1->2 fixed: the other four (2,3,4,5 giving to 1,3,4,5) have 11 valid ways
    rng = random.Random(11)
    counts = Counter(
        tuple(sorted(make_draw([1, 2, 3, 4, 5], {}, rng, {1: 2}).items())) for _ in range(5500)
    )
    assert len(counts) == 11
    for n in counts.values():
        assert 400 <= n <= 600
