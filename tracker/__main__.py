"""Daily run: collect -> dedupe -> keep upcoming -> write JSON, README and site data.

    python -m tracker            # full run
    python -m tracker --no-scrape   # skip slow watchlist/search page fetches (for testing)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date
from urllib.parse import urlparse

from . import sources
from .geo import country_of
from .models import SOURCE_PRIORITY, Conference, slugify
from .render import update_readme, write_region_pages

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("tracker")
DATA = "data/conferences.json"


def load_previous() -> dict[str, dict]:
    if not os.path.exists(DATA):
        return {}
    with open(DATA) as f:
        return {c["id"]: c for c in json.load(f)["conferences"]}


def run_source(name, fn, *args) -> list[Conference]:
    try:
        items = fn(*args)
        log.info("%-10s %d entries", name, len(items))
        return items
    except Exception as exc:  # noqa: BLE001 - one broken source must not kill the run
        log.error("%s failed: %s", name, exc)
        return []


def dedupe(confs: list[Conference]) -> list[Conference]:
    best: dict[tuple, Conference] = {}
    for c in confs:
        key = (slugify(c.name), c.start.year if c.start else None)
        cur = best.get(key)
        if cur is None or SOURCE_PRIORITY[c.source] > SOURCE_PRIORITY[cur.source]:
            best[key] = c
    return list(best.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scrape", action="store_true")
    args = ap.parse_args()
    today = date.today()

    confs: list[Conference] = []
    confs += run_source("ccfddl", sources.ccfddl)
    confs += run_source("confs.tech", sources.confs_tech)
    if not args.no_scrape:
        confs += run_source("watchlist", sources.watchlist)
        known = {urlparse(c.url).netloc.lower().removeprefix("www.") for c in confs}
        confs += run_source("search", sources.web_search, known)

    confs = [c for c in dedupe(confs) if c.url and sources.is_upcoming(c)]

    for c in confs:
        c.country = c.country or country_of(c.location, c.online)

    prev = load_previous()
    for c in confs:
        c.first_seen = prev.get(c.id, {}).get("first_seen") or today.isoformat()

    confs.sort(key=lambda c: (c.start or date.max, c.name.lower()))
    payload = {"updated": today.isoformat(), "count": len(confs),
               "conferences": [c.to_json() for c in confs]}
    for path in (DATA, "docs/conferences.json"):
        with open(path, "w") as f:
            json.dump(payload, f, indent=1, ensure_ascii=False)
    update_readme("README.md", confs, today)
    write_region_pages("regions", confs, today)
    log.info("wrote %d upcoming conferences", len(confs))


if __name__ == "__main__":
    main()
