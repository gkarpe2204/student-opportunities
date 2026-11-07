"""Find and parse human-written date ranges like 'October 6-9, 2027'."""
from __future__ import annotations

import re
from datetime import date

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_M = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_D = r"\d{1,2}(?:st|nd|rd|th)?"
_DASH = r"\s*(?:-|–|—|to|through|until)\s*"
_WD = r"(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?"

# Month-first: "Oct 6-9, 2027", "June 30 - July 4, 2027", "March 3, 2027", "Sept. 29 – Oct. 2 2027"
_MONTH_FIRST = re.compile(
    rf"{_WD}(?P<m1>{_M})\s+(?P<d1>{_D})(?:,?\s*(?P<y1>\d{{4}}))?"
    rf"(?:{_DASH}{_WD}(?:(?P<m2>{_M})\s+)?(?P<d2>{_D}))?,?\s+(?P<y2>\d{{4}})",
    re.I,
)
# Day-first: "6-9 October 2027", "30 June - 4 July 2027", "3 March 2027"
_DAY_FIRST = re.compile(
    rf"{_WD}(?P<d1>{_D})(?:\s+(?P<m1>{_M}))?(?:,?\s*(?P<y1>\d{{4}}))?"
    rf"(?:{_DASH}(?P<d2>{_D}))?\s+(?P<m2>{_M}),?\s+(?P<y2>\d{{4}})",
    re.I,
)
_ISO = re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})\b")


def _month(s: str | None) -> int | None:
    if not s:
        return None
    return MONTHS.get(s.lower().rstrip("."))


def _day(s: str | None) -> int | None:
    return int(re.sub(r"\D", "", s)) if s else None


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_ranges(text: str) -> list[tuple[date, date, int]]:
    """Return every (start, end, position) date range found in text."""
    out: list[tuple[date, date, int]] = []
    for m in _MONTH_FIRST.finditer(text):
        m1, m2 = _month(m["m1"]), _month(m["m2"])
        d1, d2 = _day(m["d1"]), _day(m["d2"])
        y2 = int(m["y2"])
        y1 = int(m["y1"]) if m["y1"] else y2
        if m1 is None:
            continue
        end_month = m2 or m1
        if m["y1"] is None and end_month < m1:  # "Dec 30 - Jan 2, 2028"
            y1 = y2 - 1
        start = _safe(y1, m1, d1)
        end = _safe(y2, end_month, d2) if d2 else start
        if start and end and start <= end:
            out.append((start, end, m.start()))
    for m in _DAY_FIRST.finditer(text):
        m2 = _month(m["m2"])
        m1 = _month(m["m1"]) or m2
        d1, d2 = _day(m["d1"]), _day(m["d2"])
        y2 = int(m["y2"])
        y1 = int(m["y1"]) if m["y1"] else (y2 - 1 if m1 and m2 and m1 > m2 else y2)
        if m1 is None or m2 is None:
            continue
        start = _safe(y1, m1, d1)
        end = _safe(y2, m2, d2) if d2 else _safe(y2, m2, d1)
        if start and end and start <= end:
            out.append((start, end, m.start()))
    for m in _ISO.finditer(text):
        d = _safe(int(m["y"]), int(m["m"]), int(m["d"]))
        if d:
            out.append((d, d, m.start()))
    out.sort(key=lambda r: r[2])
    return out


def parse_range(text: str | None) -> tuple[date | None, date | None]:
    """Parse the first date range in a short string such as 'May 03-05, 2025'."""
    if not text:
        return None, None
    found = find_ranges(text)
    if not found:
        return None, None
    s, e, _ = found[0]
    return s, e


def to_date(value) -> date | None:
    """Coerce '2027-03-05', '2027-03-05 23:59:59', '2027-03-05T00:00' or a date."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    m = _ISO.search(str(value))
    return _safe(int(m["y"]), int(m["m"]), int(m["d"])) if m else None
