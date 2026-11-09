from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .geo import region_of, us_state_of

# Section keys, in the order they appear on the README / site.
CATEGORIES = {
    "student": "🎓 Student & Diversity Conferences",
    "tech": "🖥️ CS & Tech Student Conferences",
    "premed": "🩺 Pre-Med & Health Conferences",
    "business": "💼 Business & Entrepreneurship Conferences",
    "hackathon": "🏁 Hackathons",
    "academic": "📚 Academic CS Conferences (paper deadlines)",
    "industry": "💻 Industry & Developer Conferences",
    "discovered": "🔍 Auto-discovered (unverified)",
}

# When the same conference comes from two sources, the higher one wins.
SOURCE_PRIORITY = {"watchlist": 4, "mlh": 3, "ccfddl": 3, "devpost": 2, "confs.tech": 2, "search": 1}


def slugify(text: str) -> str:
    text = re.sub(r"\b(19|20)\d{2}\b", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


@dataclass
class Conference:
    name: str
    url: str
    category: str                      # key of CATEGORIES
    source: str                        # key of SOURCE_PRIORITY
    start: date | None = None
    end: date | None = None
    location: str = ""
    country: str = ""                  # normalized by tracker.geo
    online: bool = False
    deadline: date | None = None       # next paper / CFP / application deadline
    deadline_label: str = ""           # e.g. "Paper", "CFP", "Scholarship"
    deadline_url: str = ""
    topics: list[str] = field(default_factory=list)
    rank: str = ""                     # CORE / CCF rank for academic venues
    notes: str = ""
    funding: str = ""                  # how students get funded to attend, if they can
    dates_auto: bool = False           # dates were scraped from the site, not verified
    first_seen: str = ""               # ISO date the tracker first saw this entry

    @property
    def id(self) -> str:
        year = self.start.year if self.start else "tba"
        return f"{slugify(self.name)}-{year}"

    def to_json(self) -> dict:
        d = asdict(self)
        for k in ("start", "end", "deadline"):
            d[k] = d[k].isoformat() if d[k] else None
        d["id"] = self.id
        d["region"] = region_of(self.country)
        d["state"] = us_state_of(self.location, self.country)
        return d
