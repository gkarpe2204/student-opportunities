"""Turn an approved "Add an event" issue into a watchlist entry.

Run by .github/workflows/add-event.yml with the issue body in $ISSUE_BODY. Prints the event name;
exits non-zero with a message (shown on the issue) when the submission can't be added.
"""
from __future__ import annotations

import os
import re
import sys

import yaml

from .dates import to_date
from .models import slugify

WATCHLIST = "data/watchlist.yml"
CATEGORY_KEYS = {
    "student & diversity conference": "student", "cs & tech conference": "tech",
    "pre-med / health conference": "premed", "business conference": "business", "hackathon": "hackathon",
}
FIELDS = {"event name": "name", "website": "url", "category": "category", "start date": "start",
          "end date": "end", "location": "location", "format": "format",
          "next deadline (registration, scholarship, abstracts)": "deadline",
          "what is that deadline for?": "deadline_label",
          "does it fund students to attend? (travel grants, scholarships)": "funding",
          "topics (comma-separated)": "topics"}


class Invalid(Exception):
    pass


def parse_form(body: str) -> dict:
    """GitHub issue forms render as '### Label\\n\\nvalue' blocks; '_No response_' means empty."""
    out = {}
    for block in re.split(r"^###\s+", body or "", flags=re.M)[1:]:
        label, _, value = block.partition("\n")
        key = FIELDS.get(label.strip().lower())
        value = value.strip()
        if key and value and value != "_No response_":
            out[key] = value
    return out


def _text(v: str, limit: int) -> str:
    v = re.sub(r"\s+", " ", v or "").strip()
    if len(v) > limit:
        raise Invalid(f"'{v[:40]}…' is longer than {limit} characters.")
    return v


def build_entry(form: dict, existing: list[dict]) -> dict:
    name = _text(form.get("name", ""), 120)
    url = _text(form.get("url", ""), 300)
    if not name:
        raise Invalid("The event name is missing.")
    if not re.match(r"^https?://[^\s/$.?#][^\s]*$", url):
        raise Invalid("The website must be a full link starting with http:// or https://.")
    category = CATEGORY_KEYS.get(form.get("category", "").strip().lower())
    if not category:
        raise Invalid("Pick a category from the list.")
    if any(slugify(e.get("name", "")) == slugify(name) for e in existing):
        raise Invalid(f"**{name}** is already on the list.")

    entry: dict = {"name": name, "category": category, "url": url}
    for key in ("start", "end", "deadline"):
        if form.get(key):
            d = to_date(form[key])
            if not d:
                raise Invalid(f"Couldn't read the {key} date '{form[key][:30]}'. Use a format like 2027-03-14.")
            entry[key] = d
    if "start" in entry and "end" not in entry:
        entry["end"] = entry["start"]
    if "start" in entry and entry["end"] < entry["start"]:
        raise Invalid("The end date is before the start date.")
    fmt = form.get("format", "")
    if form.get("location"):
        entry["location"] = _text(form["location"], 100)
    if fmt in ("Online", "Hybrid"):
        entry["online"] = True
    if "deadline" in entry:
        entry["deadline_label"] = _text(form.get("deadline_label", "") or "Deadline", 40)
    if form.get("funding"):
        entry["funding"] = _text(form["funding"], 160)
    topics = [_text(t, 40) for t in (form.get("topics") or "").split(",") if t.strip()][:5]
    if fmt and category == "hackathon":
        topics.insert(0, fmt)
    if topics:
        entry["topics"] = topics
    return entry


def append_entry(entry: dict, path: str = WATCHLIST) -> None:
    text = open(path, encoding="utf-8").read()
    marker = "# ---------------------------------------------------------------- added from issues"
    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=1000)
    with open(path, "a", encoding="utf-8") as f:
        if marker not in text:
            f.write(f"\n{marker}\n")
        f.write("\n" + block)


def main() -> int:
    try:
        existing = yaml.safe_load(open(WATCHLIST, encoding="utf-8")) or []
        entry = build_entry(parse_form(os.environ.get("ISSUE_BODY", "")), existing)
    except Invalid as exc:
        print(str(exc))
        return 1
    append_entry(entry)
    print(entry["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
