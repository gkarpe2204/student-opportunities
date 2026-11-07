"""Each source returns a list of Conference objects. A failing source is logged and skipped."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, timedelta
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from .dates import find_ranges, parse_range, to_date
from .models import Conference

log = logging.getLogger(__name__)
TODAY = date.today()
HORIZON = TODAY + timedelta(days=540)  # ~18 months ahead
UA = "Mozilla/5.0 (compatible; student-conference-tracker/1.0; +https://github.com)"

session = requests.Session()
session.headers["User-Agent"] = UA


def get(url: str, **kw) -> requests.Response:
    r = session.get(url, timeout=kw.pop("timeout", 25), **kw)
    r.raise_for_status()
    return r


def is_upcoming(c: Conference) -> bool:
    end = c.end or c.start
    if end is None:
        return c.source == "watchlist"   # keep curated entries with TBA dates
    return TODAY <= end and (c.start or end) <= HORIZON


# ---------------------------------------------------------------- ccfddl
# Academic CS venues with paper deadlines: https://github.com/ccfddl/ccf-deadlines
CCF_AREAS = {
    "AI": "AI/ML", "CG": "Graphics/Multimedia", "CT": "Theory", "DB": "Databases/Data Mining",
    "DS": "Systems/Architecture", "HI": "HCI", "MX": "Interdisciplinary",
    "NW": "Networking", "SC": "Security", "SE": "Software Eng.",
}


def ccfddl() -> list[Conference]:
    raw = get("https://ccfddl.github.io/conference/allconf.yml").text
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", raw)  # stray control chars break PyYAML
    data = yaml.safe_load(raw)
    out = []
    for venue in data:
        rank = venue.get("rank") or {}
        rank_str = " · ".join(f"{k.upper()} {v}" for k, v in rank.items()
                              if k in ("core", "ccf") and v and v != "N")
        for conf in venue.get("confs", []):
            if (conf.get("year") or 0) < TODAY.year - 1:
                continue
            start, end = parse_range(str(conf.get("date") or ""))
            deadlines = sorted(
                d for t in conf.get("timeline") or []
                if (d := to_date(t.get("deadline"))) is not None
            )
            upcoming = [d for d in deadlines if d >= TODAY]
            place = str(conf.get("place") or "")
            out.append(Conference(
                name=f"{venue['title']} {conf['year']}",
                url=conf.get("link") or "",
                category="academic",
                source="ccfddl",
                start=start, end=end,
                location=place,
                online=place.lower() in ("virtual", "online"),
                deadline=upcoming[0] if upcoming else None,
                deadline_label="Paper" if upcoming else "",
                topics=[CCF_AREAS.get(venue.get("sub", ""), venue.get("sub", ""))],
                rank=rank_str,
                notes=venue.get("description", ""),
            ))
    return out


# ---------------------------------------------------------------- confs.tech
# Industry/dev conferences: https://github.com/tech-conferences/conference-data
CONFS_TECH_TOPICS = [
    "general", "data", "security", "python", "javascript", "devops", "ux", "android",
    "ios", "java", "api", "dotnet", "golang", "tech-comm", "product", "leadership",
    "networking", "opensource",
]


def confs_tech() -> list[Conference]:
    merged: dict[tuple, Conference] = {}
    for year in (TODAY.year, TODAY.year + 1):
        for topic in CONFS_TECH_TOPICS:
            url = (f"https://raw.githubusercontent.com/tech-conferences/conference-data/"
                   f"main/conferences/{year}/{topic}.json")
            try:
                items = get(url).json()
            except requests.HTTPError:
                continue
            for it in items:
                key = (it.get("url"), it.get("startDate"))
                if key in merged:
                    merged[key].topics.append(topic)
                    continue
                cfp_end = to_date(it.get("cfpEndDate"))
                loc = ", ".join(x for x in (it.get("city"), it.get("country")) if x)
                merged[key] = Conference(
                    name=it["name"], url=it.get("url", ""),
                    category="industry", source="confs.tech",
                    start=to_date(it.get("startDate")), end=to_date(it.get("endDate")),
                    location=loc or ("Online" if it.get("online") else ""),
                    online=bool(it.get("online")),
                    deadline=cfp_end if cfp_end and cfp_end >= TODAY else None,
                    deadline_label="CFP" if cfp_end and cfp_end >= TODAY else "",
                    deadline_url=it.get("cfpUrl", ""),
                    topics=[topic],
                )
    return list(merged.values())


# ---------------------------------------------------------------- page scraping
def extract_event(url: str) -> dict:
    """Best-effort: pull dates/location from a conference page.

    1) schema.org Event JSON-LD, 2) the first future date range in title/headings,
    3) the first future date range in body text.
    """
    html = get(url).text
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in blob if isinstance(blob, list) else blob.get("@graph", [blob]):
            if not isinstance(node, dict) or "Event" not in str(node.get("@type", "")):
                continue
            start, end = to_date(node.get("startDate")), to_date(node.get("endDate"))
            if start and start >= TODAY - timedelta(days=7):
                loc = node.get("location") or {}
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address", {}) if isinstance(loc, dict) else {}
                place = (", ".join(x for x in (addr.get("addressLocality"), addr.get("addressRegion"))
                                   if x) if isinstance(addr, dict) else str(addr))
                return {"start": start, "end": end or start,
                        "location": place or (loc.get("name", "") if isinstance(loc, dict) else ""),
                        "title": node.get("name", "")}

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = " | ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])[:30])
    meta = " | ".join(m.get("content", "") for m in soup.find_all("meta")
                      if m.get("name") in ("description", "og:description")
                      or m.get("property") in ("og:description", "og:title"))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = soup.get_text(" ", strip=True)[:60000]

    return pick_event_dates(f"{title} | {meta} | {headings}", body) | {"title": title}


EVENT_WORDS = re.compile(r"conference|convention|summit|celebration|symposium|congress|expo|"
                         r"takes? place|will be held|join us", re.I)
DEADLINE_WORDS = re.compile(r"deadline|due|submi|apply|applications?|register|registration|"
                            r"early[- ]bird|scholarship|closes|proposals?|abstracts?", re.I)


def pick_event_dates(head: str, body: str) -> dict:
    """Score every future date range and return the most likely event dates (+ a deadline).

    Single-day dates in body text are usually news/blog post dates, so they only count
    if they appear in the title/headings. Ranges score higher when repeated, when they
    appear in the title/headings, and when they sit near words like "conference".
    """
    scores: dict[tuple, float] = {}
    for text, in_head in ((head, True), (body, False)):
        for start, end, pos in find_ranges(text):
            if not (TODAY <= end <= HORIZON) or (end - start).days > 14:
                continue
            if start == end and not in_head:
                continue
            ctx = text[max(0, pos - 100): pos + 60]
            score = 1 + (3 if in_head else 0) + (2 if EVENT_WORDS.search(ctx) else 0)
            scores[(start, end)] = scores.get((start, end), 0) + score
    if not scores:
        return {}
    start, end = max(scores, key=lambda k: (scores[k], -k[0].toordinal()))

    deadline = None
    for d, _, pos in find_ranges(body):
        if TODAY <= d < start and DEADLINE_WORDS.search(body[max(0, pos - 80): pos]):
            deadline = d if deadline is None else min(deadline, d)
    return {"start": start, "end": end, "location": "", "deadline": deadline}


# ---------------------------------------------------------------- watchlist
def watchlist(path: str = "data/watchlist.yml") -> list[Conference]:
    """Hand-curated student conferences. Manual dates win; otherwise scrape the site."""
    with open(path) as f:
        entries = yaml.safe_load(f) or []
    out = []
    for e in entries:
        c = Conference(
            name=e["name"], url=e["url"], category=e.get("category", "student"), source="watchlist",
            start=to_date(e.get("start")), end=to_date(e.get("end")),
            location=e.get("location", ""), online=bool(e.get("online", False)),
            deadline=to_date(e.get("deadline")), deadline_label=e.get("deadline_label", ""),
            deadline_url=e.get("deadline_url", ""), topics=e.get("topics", []),
            notes=e.get("notes", ""),
        )
        if c.end and c.end < TODAY:      # manual dates are stale -> re-scrape
            c.start = c.end = None
        if c.deadline and c.deadline < TODAY:
            c.deadline, c.deadline_label = None, ""
        if not c.start:
            try:
                ev = extract_event(e.get("dates_url") or c.url)
                if ev.get("start"):
                    c.start, c.end, c.dates_auto = ev["start"], ev["end"], True
                    c.location = c.location or ev.get("location", "")
                    if not c.deadline and ev.get("deadline"):
                        c.deadline, c.deadline_label = ev["deadline"], "Deadline ⚠️"
            except Exception as exc:  # noqa: BLE001
                log.warning("watchlist: could not scrape %s (%s)", c.url, exc)
        out.append(c)
    return out


# ---------------------------------------------------------------- web search
SEARCH_QUERIES = [
    "student conference {y} computer science travel scholarship",
    "undergraduate research conference {y}",
    "student leadership conference {y} STEM",
    "graduate student conference {y} call for papers",
    "diversity in computing conference {y} students",
    "women in tech conference {y} student scholarship",
    "student AI conference {y}",
    "student hackathon conference {y} registration",
    "biomedical engineering student conference {y}",
    "healthcare innovation student conference {y}",
]
# Known predatory "conference" mills and listing aggregators.
BLOCKED_DOMAINS = {
    "waset.org", "conferenceindex.org", "allconferencealert.com", "conferencealerts.com",
    "internationalconferencealerts.com", "conferencealerts.co.in", "researchconferences.org",
    "iser.co", "ocean-conference.org", "theiier.org", "omicsonline.org", "conferenceseries.com",
    "allconferencealert.net", "eventbrite.com", "facebook.com", "linkedin.com", "instagram.com",
    "x.com", "twitter.com", "youtube.com", "reddit.com", "wikipedia.org", "10times.com",
}
CONF_WORDS = re.compile(r"conference|summit|symposium|convention|congress|forum|celebration|workshop", re.I)


def _search(query: str) -> list[dict]:
    """Return [{title, url, snippet}] from whichever search API has a key configured."""
    if key := os.getenv("SERPER_API_KEY"):           # Google results via serper.dev
        r = session.post("https://google.serper.dev/search", timeout=25,
                         headers={"X-API-KEY": key}, json={"q": query, "num": 10})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("link", ""), "snippet": x.get("snippet", "")}
                for x in r.json().get("organic", [])]
    if key := os.getenv("BRAVE_API_KEY"):            # Brave Search API
        r = session.get("https://api.search.brave.com/res/v1/web/search", timeout=25,
                        headers={"X-Subscription-Token": key, "Accept": "application/json"},
                        params={"q": query, "count": 10})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("description", "")}
                for x in r.json().get("web", {}).get("results", [])]
    return []


def web_search(known_domains: set[str], max_pages: int = 40) -> list[Conference]:
    if not (os.getenv("SERPER_API_KEY") or os.getenv("BRAVE_API_KEY")):
        log.info("search: no SERPER_API_KEY / BRAVE_API_KEY set, skipping")
        return []
    seen, out, fetched = set(), [], 0
    for q in SEARCH_QUERIES:
        for year in (TODAY.year, TODAY.year + 1):
            try:
                results = _search(q.format(y=year))
            except Exception as exc:  # noqa: BLE001
                log.warning("search failed for %r: %s", q, exc)
                continue
            for res in results:
                domain = urlparse(res["url"]).netloc.lower().removeprefix("www.")
                if (not domain or domain in seen or domain in known_domains
                        or any(domain == b or domain.endswith("." + b) for b in BLOCKED_DOMAINS)
                        or not CONF_WORDS.search(res["title"])):
                    continue
                seen.add(domain)
                start = end = None
                for s, e, _ in find_ranges(f"{res['title']} {res['snippet']}"):
                    if TODAY <= e <= HORIZON and (e - s).days <= 14:
                        start, end = s, e
                        break
                if not start and fetched < max_pages:
                    fetched += 1
                    try:
                        ev = extract_event(res["url"])
                        start, end = ev.get("start"), ev.get("end")
                    except Exception:  # noqa: BLE001
                        pass
                if not start:
                    continue
                name = re.split(r"\s+[|\-–—:]\s+", res["title"])[0].strip()
                out.append(Conference(
                    name=name or res["title"], url=res["url"], category="discovered",
                    source="search", start=start, end=end, dates_auto=True,
                    notes=res["snippet"][:200],
                ))
    return out
