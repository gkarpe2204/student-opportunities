from datetime import date

from tracker.sources import next_deadline

T = date(2026, 11, 7)


def test_picks_next_upcoming_and_skips_past():
    e = {"deadlines": [
        {"date": "2026-11-01", "label": "Old"},
        {"date": "2027-01-29", "label": "Early registration"},
        {"date": "2026-12-04", "label": "Abstracts", "url": "https://x"},
    ]}
    assert next_deadline(e, T) == (date(2026, 12, 4), "Abstracts", "https://x")


def test_single_deadline_field_still_works():
    e = {"deadline": "2027-01-04", "deadline_label": "Early-bird", "deadline_url": "https://y"}
    assert next_deadline(e, T) == (date(2027, 1, 4), "Early-bird", "https://y")


def test_all_past_gives_none():
    assert next_deadline({"deadlines": [{"date": "2026-01-01"}]}, T) == (None, "", "")
