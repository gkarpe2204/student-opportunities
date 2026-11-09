from __future__ import annotations

from datetime import date, timedelta

import os
import re

from .geo import REGION_ORDER, region_of
from .models import CATEGORIES, Conference

START, END = "<!-- TABLES:START -->", "<!-- TABLES:END -->"


def fmt_dates(c: Conference) -> str:
    if not c.start:
        return "TBA" + (f" · {c.notes}" if c.notes and c.source == "watchlist" else "")
    s, e = c.start, c.end or c.start
    if s == e:
        out = s.strftime("%b %-d, %Y")
    elif (s.year, s.month) == (e.year, e.month):
        out = f"{s.strftime('%b %-d')}–{e.day}, {e.year}"
    elif s.year == e.year:
        out = f"{s.strftime('%b %-d')} – {e.strftime('%b %-d')}, {e.year}"
    else:
        out = f"{s.strftime('%b %-d, %Y')} – {e.strftime('%b %-d, %Y')}"
    return out + (" ⚠️" if c.dates_auto else "")


def fmt_deadline(c: Conference, today: date) -> str:
    if not c.deadline:
        return "—"
    days = (c.deadline - today).days
    txt = f"{c.deadline_label + ': ' if c.deadline_label else ''}{c.deadline.strftime('%b %-d')}"
    if c.deadline_url:
        txt = f"[{txt}]({c.deadline_url})"
    return txt + (f" ⏰ {days}d" if days <= 14 else "")


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def name_cell(c: Conference, today: date) -> str:
    new = c.first_seen and (today - date.fromisoformat(c.first_seen)) <= timedelta(days=7)
    return f"**[{esc(c.name)}]({c.url})**" + (" 🆕" if new else "") + (" 💰" if c.funding else "")


def location_cell(c: Conference) -> str:
    loc = esc(c.location) or "—"
    return "🌐 Online" if c.online and loc in ("—", "Online") else loc + (" 🌐" if c.online else "")


TABLES = {
    "student": (["Conference", "Dates", "Location", "Deadline", "Focus"],
                lambda c, t: [name_cell(c, t), fmt_dates(c), location_cell(c), fmt_deadline(c, t),
                              esc(", ".join(c.topics)) + (f"<br>💰 {esc(c.funding)}" if c.funding else "")]),
    "academic": (["Conference", "Area", "Rank", "Dates", "Location", "Next deadline"],
                 lambda c, t: [name_cell(c, t), esc(", ".join(c.topics)), esc(c.rank) or "—",
                               fmt_dates(c), location_cell(c), fmt_deadline(c, t)]),
    "industry": (["Conference", "Topics", "Dates", "Location", "CFP closes"],
                 lambda c, t: [name_cell(c, t), esc(", ".join(c.topics)), fmt_dates(c),
                               location_cell(c), fmt_deadline(c, t)]),
    "discovered": (["Conference", "Dates", "Found"],
                   lambda c, t: [name_cell(c, t), fmt_dates(c), c.first_seen]),
}
TABLES["premed"] = TABLES["business"] = TABLES["tech"] = TABLES["student"]
TABLES["hackathon"] = (["Hackathon", "Dates", "Location", "Deadline", "Format & focus"], TABLES["student"][1])


def sort_key(c: Conference):
    return (c.start or date.max, c.name.lower())


def _anchor(title: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation/emoji, spaces -> hyphens."""
    a = title.lower().encode("ascii", "ignore").decode()
    return "".join(ch if ch.isalnum() or ch in " -" else "" for ch in a).replace(" ", "-")


def region_slug(region: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", region.lower()).strip("-")


def region_links(confs: list[Conference], prefix: str = "regions/") -> str:
    counts = {}
    for c in confs:
        counts[region_of(c.country)] = counts.get(region_of(c.country), 0) + 1
    order = [r for r in REGION_ORDER if counts.get(r)] + sorted(r for r in counts if r not in REGION_ORDER)
    return " \u00b7 ".join(f"[{r}]({prefix}{region_slug(r)}.md) ({counts[r]})" for r in order)


def render_sections(confs: list[Conference], today: date) -> str:
    parts = []
    for key, title in CATEGORIES.items():
        rows = sorted((c for c in confs if c.category == key), key=sort_key)
        if not rows:
            continue
        header, row = TABLES[key]
        parts.append(f"## {title}\n")
        if key == "discovered":
            parts.append("> Found automatically by web search. **Verify before you register** \u2014 "
                         "and open an issue to promote good ones to the curated list.\n")
        parts.append("| " + " | ".join(header) + " |")
        parts.append("|" + "---|" * len(header))
        for c in rows:
            parts.append("| " + " | ".join(row(c, today)) + " |")
        parts.append("\n[\u2b06\ufe0f Back to top](#)\n")
    return "\n".join(parts)


def render_tables(confs: list[Conference], today: date) -> str:
    parts = ["### Browse " + str(len(confs)) + " upcoming opportunities\n"]
    counts = {k: sum(c.category == k for c in confs) for k in CATEGORIES}
    for key, title in CATEGORIES.items():
        if counts[key]:
            parts.append(f"- **[{title}](#{_anchor(title)})** \u2014 {counts[key]}")
    parts.append(f"\n\U0001f30d **Only want one part of the world?** {region_links(confs)}")
    parts.append(f"\n_Last updated: {today.strftime('%B %-d, %Y')}_\n")
    parts.append(render_sections(confs, today))
    return "\n".join(parts)


def write_region_pages(folder: str, confs: list[Conference], today: date) -> None:
    os.makedirs(folder, exist_ok=True)
    regions = {region_of(c.country) for c in confs} | set(REGION_ORDER)
    for region in regions:
        mine = [c for c in confs if region_of(c.country) == region]
        body = render_sections(mine, today) if mine else "_Nothing upcoming here right now._\n"
        with open(os.path.join(folder, f"{region_slug(region)}.md"), "w") as f:
            f.write(f"# \U0001f30d Student opportunities \u2014 {region}\n\n"
                    f"{len(mine)} upcoming \u00b7 [\u2190 All regions](../README.md) \u00b7 "
                    f"Other regions: {region_links(confs, prefix='')}\n\n"
                    f"_Last updated: {today.strftime('%B %-d, %Y')}_\n\n{body}")


def update_readme(path: str, confs: list[Conference], today: date) -> None:
    with open(path) as f:
        text = f.read()
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    with open(path, "w") as f:
        f.write(f"{head}{START}\n{render_tables(confs, today)}\n{END}{tail}")
