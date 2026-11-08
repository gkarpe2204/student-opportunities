from datetime import date

from tracker import sources
from tracker.models import Conference


def _c(start, end=None, source="ccfddl"):
    return Conference(name="x", url="https://x", category="academic", source=source, start=start, end=end)


def test_drops_events_already_under_way(monkeypatch):
    monkeypatch.setattr(sources, "TODAY", date(2026, 11, 7))
    monkeypatch.setattr(sources, "HORIZON", date(2028, 1, 1))
    assert not sources.is_upcoming(_c(date(2026, 11, 5), date(2026, 11, 8)))  # started Nov 5
    assert sources.is_upcoming(_c(date(2026, 11, 7), date(2026, 11, 9)))      # starts today
    assert sources.is_upcoming(_c(date(2026, 12, 1)))
    assert sources.is_upcoming(_c(None, source="watchlist"))                  # curated TBA kept
