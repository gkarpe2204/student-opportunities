from __future__ import annotations

from datetime import date, timedelta

from .models import CATEGORIES, Conference

START, END = "<!-- TABLES:START -->", "<!-- TABLES:END -->"


def fmt_dates(c: Conference) -> str:
    if not c.start:
        return "TBA"
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
    return f"**[{esc(c.name)}]({c.url})**" + (" 🆕" if new else "")


def location_cell(c: Conference) -> str:
    loc = esc(c.location) or "—"
    return "🌐 Online" if c.online and loc in ("—", "Online") else loc + (" 🌐" if c.online else "")


TABLES = {
    "student": (["Conference", "Dates", "Location", "Deadline", "Focus"],
                lambda c, t: [name_cell(c, t), fmt_dates(c), location_cell(c), fmt_deadline(c, t),
                              esc(", ".join(c.topics))]),
    "academic": (["Conference", "Area", "Rank", "Dates", "Location", "Next deadline"],
                 lambda c, t: [name_cell(c, t), esc(", ".join(c.topics)), esc(c.rank) or "—",
                               fmt_dates(c), location_cell(c), fmt_deadline(c, t)]),
    "industry": (["Conference", "Topics", "Dates", "Location", "CFP closes"],
                 lambda c, t: [name_cell(c, t), esc(", ".join(c.topics)), fmt_dates(c),
                               location_cell(c), fmt_deadline(c, t)]),
    "discovered": (["Conference", "Dates", "Found"],
                   lambda c, t: [name_cell(c, t), fmt_dates(c), c.first_seen]),
}
TABLES["premed"] = TABLES["student"]


def sort_key(c: Conference):
    return (c.start or date.max, c.name.lower())


def render_tables(confs: list[Conference], today: date) -> str:
    parts = []
    counts = {k: sum(c.category == k for c in confs) for k in CATEGORIES}
    parts.append("### Browse " + str(len(confs)) + " upcoming conferences\n")
    for key, title in CATEGORIES.items():
        if counts[key]:
            anchor = title.lower().encode("ascii", "ignore").decode()
            anchor = "".join(ch if ch.isalnum() or ch in " -" else "" for ch in anchor).replace(" ", "-")
            parts.append(f"- **[{title}](#{anchor})** — {counts[key]}")
    parts.append(f"\n_Last updated: {today.strftime('%B %-d, %Y')}_\n")

    for key, title in CATEGORIES.items():
        rows = sorted((c for c in confs if c.category == key), key=sort_key)
        if not rows:
            continue
        header, row = TABLES[key]
        parts.append(f"## {title}\n")
        if key == "discovered":
            parts.append("> Found automatically by web search. **Verify before you register** — "
                         "and open an issue to promote good ones to the curated list.\n")
        parts.append("| " + " | ".join(header) + " |")
        parts.append("|" + "---|" * len(header))
        for c in rows:
            parts.append("| " + " | ".join(row(c, today)) + " |")
        parts.append("\n[⬆️ Back to top](#)\n")
    return "\n".join(parts)


def update_readme(path: str, confs: list[Conference], today: date) -> None:
    with open(path) as f:
        text = f.read()
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    with open(path, "w") as f:
        f.write(f"{head}{START}\n{render_tables(confs, today)}\n{END}{tail}")
