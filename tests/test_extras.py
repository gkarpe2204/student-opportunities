from datetime import date

from tracker.__main__ import dedupe
from tracker.extras import digest_markdown, feed_items
from tracker.geo import us_state_of
from tracker.models import Conference

T = date(2026, 11, 9)


def _c(name, **kw):
    kw.setdefault("category", "student")
    kw.setdefault("source", "watchlist")
    return Conference(name=name, url="https://x.org", **kw)


def test_us_state_of():
    assert us_state_of("Cambridge, MA", "United States") == "Massachusetts"
    assert us_state_of("Sacramento, CA 95817 (Aggie Square)", "United States") == "California"
    assert us_state_of("Amherst, Massachusetts", "United States") == "Massachusetts"
    assert us_state_of("Toronto, ON", "Canada") == ""


def test_feed_has_new_events_and_close_deadlines_only():
    confs = [
        _c("Fresh Conf", start=date(2027, 3, 1), first_seen="2026-11-05"),
        _c("Old Conf", start=date(2027, 3, 1), first_seen="2026-09-01"),
        _c("Soon Deadline", start=date(2027, 2, 1), first_seen="2026-09-01",
           deadline=date(2026, 11, 15), deadline_label="Travel grant"),
        _c("Far Deadline", start=date(2027, 2, 1), first_seen="2026-09-01", deadline=date(2027, 1, 4)),
    ]
    titles = [i["title"] for i in feed_items(confs, T)]
    assert "New: Fresh Conf" in titles
    assert "Travel grant deadline Nov 15: Soon Deadline" in titles
    assert not any("Old Conf" in t or "Far Deadline" in t for t in titles)


def test_digest_lists_deadlines_new_and_funded():
    confs = [_c("Tapia", start=date(2027, 9, 15), first_seen="2026-11-08", funding="Scholarships",
                deadline=date(2026, 11, 20), deadline_label="Scholarship")]
    md = digest_markdown(confs, T)
    assert "Nov 20** · Scholarship: [Tapia]" in md
    assert "## 🆕 Added this week (1)" in md and "## 💰 Events that fund students" in md


def test_dedupe_moves_funding_to_dated_twin():
    tba = _c("TreeHacks", category="hackathon", funding="Travel reimbursed")
    dated = _c("TreeHacks 2027", category="hackathon", source="devpost", start=date(2027, 2, 12))
    (only,) = dedupe([tba, dated])
    assert only.start == date(2027, 2, 12) and only.funding == "Travel reimbursed"
