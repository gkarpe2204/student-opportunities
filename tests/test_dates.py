from datetime import date

import pytest

from tracker.dates import find_ranges, parse_range, to_date


@pytest.mark.parametrize("text,start,end", [
    ("February 4-7, 2027", date(2027, 2, 4), date(2027, 2, 7)),
    ("May 03-05, 2027", date(2027, 5, 3), date(2027, 5, 5)),
    ("June 30 - July 4, 2027", date(2027, 6, 30), date(2027, 7, 4)),
    ("Sept. 29 – Oct. 2, 2027", date(2027, 9, 29), date(2027, 10, 2)),
    ("Dec 30 - Jan 2, 2028", date(2027, 12, 30), date(2028, 1, 2)),
    ("March 3, 2027", date(2027, 3, 3), date(2027, 3, 3)),
    ("6-9 October 2027", date(2027, 10, 6), date(2027, 10, 9)),
    ("30 June – 4 July 2027", date(2027, 6, 30), date(2027, 7, 4)),
    ("Wednesday, October 6 to Saturday, October 9, 2027", date(2027, 10, 6), date(2027, 10, 9)),
    ("Join us at GHC 27, Oct 6th–9th, 2027 in Boston", date(2027, 10, 6), date(2027, 10, 9)),
])
def test_parse_range(text, start, end):
    assert parse_range(text) == (start, end)


def test_no_date():
    assert parse_range("Coming soon") == (None, None)
    assert parse_range(None) == (None, None)


def test_invalid_day_ignored():
    assert parse_range("February 30, 2027") == (None, None)


def test_find_multiple_in_order():
    found = find_ranges("Abstracts due Jan 15, 2027. Conference April 8-10, 2027.")
    assert [(s, e) for s, e, _ in found] == [
        (date(2027, 1, 15), date(2027, 1, 15)), (date(2027, 4, 8), date(2027, 4, 10))]


def test_to_date():
    assert to_date("2027-03-05 23:59:59") == date(2027, 3, 5)
    assert to_date("") is None
