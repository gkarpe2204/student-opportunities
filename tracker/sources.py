"""Each source returns a list of Conference objects. A failing source is logged and skipped."""
from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import unquote, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from .dates import find_ranges, parse_range, to_date
from .geo import country_of
from .models import Conference

log = logging.getLogger(__name__)
# "Today" in Boston time, so a run at 11pm ET (already tomorrow in UTC) still uses today's date.
TODAY = datetime.now(ZoneInfo("America/New_York")).date()
HORIZON = TODAY + timedelta(days=540)  # ~18 months ahead
UA = "Mozilla/5.0 (compatible; student-conference-tracker/1.0; +https://github.com)"

session = requests.Session()
session.headers["User-Agent"] = UA


def get(url: str, **kw) -> requests.Response:
    r = session.get(url, timeout=kw.pop("timeout", 25), **kw)
    r.raise_for_status()
    return r


def is_upcoming(c: Conference) -> bool:
    """Only events that start today or later; anything already under way is dropped."""
    start = c.start or c.end
    if start is None:
        return c.source == "watchlist"   # keep curated entries with TBA dates
    return TODAY <= start <= HORIZON


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
                    country=country_of(loc, bool(it.get("online")), hint=it.get("country", "")),
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


# ---------------------------------------------------------------- hackathons
MLH_SEASON_URL = "https://www.mlh.com/seasons/{season}/events?upcoming_page={page}"
ISO_COUNTRIES = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom", "IE": "Ireland", "FI": "Finland",
    "ES": "Spain", "RO": "Romania", "DE": "Germany", "FR": "France", "NL": "Netherlands", "IT": "Italy",
    "PT": "Portugal", "CH": "Switzerland", "SE": "Sweden", "PL": "Poland", "MX": "Mexico", "BR": "Brazil",
    "IN": "India", "SG": "Singapore", "JP": "Japan", "AU": "Australia", "NZ": "New Zealand", "NG": "Nigeria",
}
MLH_FORMATS = {"physical": "In-person", "digital": "Online", "hybrid_physical": "Hybrid", "hybrid_digital": "Hybrid"}


def mlh_events(items: list[dict]) -> list[Conference]:
    """Turn MLH event records (from the season page's Inertia JSON) into Conferences."""
    out = []
    for e in items:
        start, end = to_date(e.get("startsAt")), to_date(e.get("endsAt"))
        fmt = MLH_FORMATS.get(e.get("formatType", ""), "")
        online = fmt == "Online"
        loc = "" if online or (e.get("location") or "").startswith("Everywhere") else (e.get("location") or "")
        focus = (e.get("customFields") or {}).get("hackathon_focus") or []
        url = e.get("websiteUrl") or ("https://www.mlh.com" + e.get("url", ""))
        code = ((e.get("venueAddress") or {}).get("country") or "").upper()
        out.append(Conference(
            name=e["name"], url=url, category="hackathon", source="mlh", start=start, end=end,
            location=loc, online=online or fmt == "Hybrid",
            country="" if online or not loc else ISO_COUNTRIES.get(code, ""),
            topics=[t for t in [fmt, *focus, "MLH"] if t],
        ))
    return out


def mlh() -> list[Conference]:
    """All upcoming Major League Hacking events for this season and the next."""
    season = TODAY.year + (1 if TODAY.month >= 8 else 0)      # MLH seasons run Aug -> Jul
    items = []
    for s in (season, season + 1):
        page = 1
        while page and page <= 25:
            try:
                html = get(MLH_SEASON_URL.format(season=s, page=page)).text
            except requests.HTTPError:
                if s == season:
                    raise
                break                                           # next season not published yet
            m = re.search(r'<script data-page="app" type="application/json">(.*?)</script>', html, re.S)
            if not m:
                break
            data = json.loads(m.group(1))
            items += data["props"].get("upcomingEvents") or []
            page = ((data.get("scrollProps") or {}).get("upcomingEvents") or {}).get("nextPage")
    seen, uniq = set(), []
    for e in items:
        if e.get("id") not in seen:
            seen.add(e.get("id"))
            uniq.append(e)
    return mlh_events(uniq)


def _devpost_prize(raw: str) -> str:
    amount = re.sub(r"<[^>]+>", "", raw or "").strip()
    return f"{amount} in prizes" if amount and re.search(r"[1-9]", amount) else ""


def devpost_events(items: list[dict]) -> list[Conference]:
    """Turn Devpost API hackathon records into Conferences (skips invite-only events)."""
    out = []
    for h in items:
        if h.get("invite_only"):
            continue
        start, end = parse_range(h.get("submission_period_dates"))
        place = (h.get("displayed_location") or {})
        online = place.get("icon") == "globe" or place.get("location", "").lower() == "online"
        themes = [t["name"] for t in (h.get("themes") or [])][:2]
        prize = _devpost_prize(h.get("prize_amount"))
        org = h.get("organization_name") or ""
        out.append(Conference(
            name=h["title"], url=h["url"], category="hackathon", source="devpost", start=start, end=end,
            location="" if online else place.get("location", ""), online=online,
            topics=[t for t in ["Online" if online else "In-person", *themes, prize] if t],
            notes=f"Hosted by {org}" if org else "",
        ))
    return out


def devpost_place(page_html: str, venue: str) -> tuple[str, bool]:
    """(location, invite_only) from a Devpost hackathon page.

    The list API only gives a venue name ("WPI - Campus Center"); the page links the full address
    to Google Maps, e.g. "4480 2nd Ave, Sacramento, CA 95817, USA" -> "Sacramento, CA (Aggie Square)".
    """
    invite_only = bool(re.search(r'<div class="info">\s*Invite only\s*</div>', page_html))
    m = re.search(r'href="https://maps\.google\.com/\?q=([^"]+)"', page_html)
    if not m:
        return venue, invite_only
    parts = [p.strip() for p in unquote(html_lib.unescape(m.group(1))).split(",") if p.strip()]
    parts = [re.sub(r"\s*\b\d[\d\s-]*$", "", p).strip() for p in parts[-3:]]   # drop zip codes
    parts = [p for p in parts if p and not re.match(r"^\d", p)]
    if parts and parts[-1] in ("USA", "United States"):
        parts = parts[:-1]
    place = ", ".join(parts)
    if venue and venue.split(",")[0].strip() not in place:
        place = f"{place} ({venue.strip()})" if place else venue
    return place or venue, invite_only


def devpost() -> list[Conference]:
    """Every upcoming (not yet started) hackathon on Devpost."""
    items, page = [], 1
    while page <= 40:
        r = get(f"https://devpost.com/api/hackathons?status[]=upcoming&page={page}").json()
        batch = r.get("hackathons") or []
        if not batch:
            break
        items += batch
        page += 1
    out = []
    for c in devpost_events(items):
        if not c.online:
            try:
                c.location, invite_only = devpost_place(get(c.url).text, c.location)
                if invite_only:
                    continue
            except Exception as exc:  # noqa: BLE001 - keep the venue name if the page fails
                log.warning("devpost: could not read %s (%s)", c.url, exc)
        out.append(c)
    return out


# ---------------------------------------------------------------- watchlist
def next_deadline(e: dict, today) -> tuple:
    """Earliest deadline on or after today from `deadlines:` (list) or the single `deadline:` field."""
    items = list(e.get("deadlines") or [])
    if e.get("deadline"):
        items.append({"date": e["deadline"], "label": e.get("deadline_label", ""), "url": e.get("deadline_url", "")})
    upcoming = sorted(
        ((to_date(d.get("date")), d.get("label", ""), d.get("url", "") or e.get("deadline_url", "")) for d in items),
        key=lambda t: t[0] or today,
    )
    for d, label, url in upcoming:
        if d and d >= today:
            return d, label, url
    return None, "", ""


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
            topics=e.get("topics", []), notes=e.get("notes", ""),
        )
        c.deadline, c.deadline_label, c.deadline_url = next_deadline(e, TODAY)
        if c.end and c.end < TODAY:      # manual dates are stale -> re-scrape
            c.start = c.end = None
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
