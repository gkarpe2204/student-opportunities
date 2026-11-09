"""Extra outputs built from the final list: an RSS feed, a link-preview image and a weekly digest."""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from .models import CATEGORIES, Conference

SITE_URL = "https://gkarpe2204.github.io/student-opportunities/"
REPO_URL = "https://github.com/gkarpe2204/student-opportunities"


def _when(c: Conference) -> str:
    if not c.start:
        return "dates TBA"
    s = c.start.strftime("%b %-d, %Y")
    return s if not c.end or c.end == c.start else f"{s} – {c.end.strftime('%b %-d, %Y')}"


def _rfc822(d: date) -> str:
    return format_datetime(datetime.combine(d, time(11, 0), tzinfo=timezone.utc))


def feed_items(confs: list[Conference], today: date, days: int = 14) -> list[dict]:
    """New events (first seen in the last `days`) and deadlines coming up in the next `days`."""
    items = []
    for c in confs:
        where = c.location or ("Online" if c.online else c.country or "Location TBA")
        cat = CATEGORIES.get(c.category, c.category)
        if c.first_seen:
            seen = date.fromisoformat(c.first_seen)
            if (today - seen).days <= days:
                desc = f"{cat} · {_when(c)} · {where}" + (f" · 💰 {c.funding}" if c.funding else "")
                items.append({"title": f"New: {c.name}", "link": c.url, "guid": f"new-{c.id}",
                              "date": seen, "description": desc})
        if c.deadline and 0 <= (c.deadline - today).days <= days:
            label = c.deadline_label or "Deadline"
            items.append({"title": f"{label} deadline {c.deadline.strftime('%b %-d')}: {c.name}",
                          "link": c.deadline_url or c.url, "guid": f"deadline-{c.id}-{c.deadline}",
                          "date": max(c.deadline - timedelta(days=days), date.fromisoformat(c.first_seen or str(today))),
                          "description": f"{cat} · event {_when(c)} · {where}"})
    items.sort(key=lambda i: (i["date"], i["title"]), reverse=True)
    return items[:150]


def write_feed(path: str, confs: list[Conference], today: date) -> None:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
           "<title>Student Opportunities: new conferences, hackathons and deadlines</title>",
           f"<link>{SITE_URL}</link>",
           f'<atom:link href="{SITE_URL}feed.xml" rel="self" type="application/rss+xml"/>',
           "<description>New student conferences and hackathons, and deadlines in the next two weeks. Updated daily.</description>",
           f"<lastBuildDate>{_rfc822(today)}</lastBuildDate>"]
    for i in feed_items(confs, today):
        out.append("<item>"
                   f"<title>{escape(i['title'])}</title><link>{escape(i['link'])}</link>"
                   f'<guid isPermaLink="false">{escape(i["guid"])}</guid>'
                   f"<pubDate>{_rfc822(i['date'])}</pubDate>"
                   f"<description>{escape(i['description'])}</description></item>")
    out.append("</channel></rss>")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


# ---------------------------------------------------------------- link preview image
_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


def _font(size: int, bold: bool = True):
    from PIL import ImageFont
    paths = _FONTS if bold else _FONTS[1:]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def write_og_image(path: str, confs: list[Conference], today: date) -> None:
    """1200x630 card shown when the site link is shared (LinkedIn, Slack, iMessage...)."""
    from PIL import Image, ImageDraw

    hack = sum(c.category == "hackathon" for c in confs)
    other = len(confs) - hack
    soon = sum(1 for c in confs if c.deadline and 0 <= (c.deadline - today).days <= 30)
    img = Image.new("RGB", (1200, 630), (15, 23, 42))
    g = ImageDraw.Draw(img)
    g.rectangle([0, 0, 1200, 12], fill=(56, 189, 248))
    g.text((80, 110), "Student Opportunities", font=_font(84), fill=(255, 255, 255))
    g.text((80, 220), "Conferences & hackathons for students, updated daily", font=_font(38, False), fill=(203, 213, 225))
    stats = [(f"{other}", "conferences"), (f"{hack}", "hackathons"), (f"{soon}", "deadlines in 30 days")]
    x = 80
    for num, label in stats:
        g.text((x, 330), num, font=_font(72), fill=(56, 189, 248))
        g.text((x, 415), label, font=_font(28, False), fill=(203, 213, 225))
        x += 360
    g.text((80, 535), "gkarpe2204.github.io/student-opportunities", font=_font(30, False), fill=(148, 163, 184))
    g.text((80, 575), f"Updated {today.strftime('%B %-d, %Y')}", font=_font(24, False), fill=(100, 116, 139))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, optimize=True)


# ---------------------------------------------------------------- weekly digest
def digest_markdown(confs: list[Conference], today: date) -> str:
    soon = sorted((c for c in confs if c.deadline and 0 <= (c.deadline - today).days <= 14),
                  key=lambda c: c.deadline)
    new = [c for c in confs if c.first_seen and (today - date.fromisoformat(c.first_seen)).days <= 7]
    lines = [f"Your weekly roundup of student conferences and hackathons, week of {today.strftime('%B %-d, %Y')}.",
             f"Browse and filter everything at {SITE_URL}", ""]
    student = [c for c in soon if c.category not in ("academic", "industry")]
    papers = len(soon) - len(student)
    lines.append(f"## ⏰ Deadlines in the next two weeks ({len(student)})")
    for c in student:
        lines.append(f"- **{c.deadline.strftime('%b %-d')}** · {c.deadline_label or 'Deadline'}: "
                     f"[{c.name}]({c.deadline_url or c.url})" + (" 💰" if c.funding else ""))
    if not student:
        lines.append("_No conference or hackathon deadlines in the next two weeks._")
    if papers:
        lines.append(f"\n_Plus {papers} paper / talk-proposal deadlines for academic and industry conferences; "
                     f"see the site sorted by deadline._")
    lines += ["", f"## 🆕 Added this week ({len(new)})"]
    if not new:
        lines.append("_Nothing new this week._")
    for key, title in CATEGORIES.items():
        mine = sorted((c for c in new if c.category == key), key=lambda c: (c.start or date.max, c.name))
        if not mine:
            continue
        lines += ["", f"**{title}** ({len(mine)})"]
        for c in mine[:15]:
            where = c.location or ("Online" if c.online else "")
            lines.append(f"- [{c.name}]({c.url}) · {_when(c)}" + (f" · {where}" if where else "") + (" 💰" if c.funding else ""))
        if len(mine) > 15:
            lines.append(f"- …and {len(mine) - 15} more on the site")
    funded = [c for c in confs if c.funding]
    if funded:
        lines += ["", f"## 💰 Events that fund students to attend ({len(funded)})"]
        for c in sorted(funded, key=lambda c: (c.start or date.max, c.name)):
            lines.append(f"- [{c.name}]({c.url}) · {_when(c)} · {c.funding}")
    lines += ["", "---", "You get this because you watch this repo's releases. "
              f"Manage it under **Watch → Custom → Releases** on {REPO_URL}."]
    return "\n".join(lines) + "\n"


def load(path: str = "data/conferences.json") -> list[Conference]:
    raw = json.load(open(path, encoding="utf-8"))
    out = []
    fields = Conference.__dataclass_fields__
    for d in raw["conferences"]:
        kw = {k: v for k, v in d.items() if k in fields}
        for k in ("start", "end", "deadline"):
            kw[k] = date.fromisoformat(kw[k]) if kw.get(k) else None
        out.append(Conference(**kw))
    return out


if __name__ == "__main__":       # python -m tracker.extras digest > digest.md
    from .sources import TODAY
    if sys.argv[1:] == ["digest"]:
        sys.stdout.write(digest_markdown(load(), TODAY))
    else:
        sys.exit("usage: python -m tracker.extras digest")
