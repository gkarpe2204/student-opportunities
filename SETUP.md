# Setup (≈5 minutes)

1. **Repo:** https://github.com/gkarpe2204/student-conferences (already created).
2. **Let the Action commit.** Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save.
3. **Turn on the website.** Settings → Pages → Source: **Deploy from a branch** → Branch `main`, folder **`/docs`** → Save.
   Your site goes live at `https://gkarpe2204.github.io/student-conferences/`.
4. **Run it once.** Actions tab → *Update conference list* → **Run workflow**. After that it runs every day at 11:17 UTC.

## Optional: web search ("googling")

Google's own Custom Search JSON API is closed to new sign-ups and shuts down on Jan 1, 2027, so the tracker uses a search API instead. Add **one** of these as a repo secret (Settings → Secrets and variables → Actions → New repository secret):

| Secret | Service | Notes |
|---|---|---|
| `SERPER_API_KEY` | [serper.dev](https://serper.dev) | Returns Google results. Free starter credits. |
| `BRAVE_API_KEY` | [Brave Search API](https://brave.com/search/api/) | Independent index. |

Each run does 20 searches (10 queries × this year and next), visits up to 40 new pages, and lists what it finds under **🔍 Auto-discovered (unverified)**. Edit `SEARCH_QUERIES` and `BLOCKED_DOMAINS` in `tracker/sources.py` to tune it. Known predatory "conference" mills (WASET, conferenceseries, etc.) are already blocked.

## Maintaining the list

- **Add or verify a student conference:** edit `data/watchlist.yml`. Adding `start`/`end` removes the ⚠️ badge. Once those dates pass, the tracker goes back to reading the site, so next year's edition gets picked up automatically.
- **Promote an auto-discovered conference:** copy it into `watchlist.yml`.
- **Run locally:** `pip install -r requirements.txt && python -m tracker` (or `--no-scrape` for a quick run).
- **Tests:** `python -m pytest`.

## How it works

```
tracker/
  sources.py   ccfddl (academic) · confs.tech (industry) · watchlist (scrapes each site) · web search
  dates.py     parses "Oct 6–9, 2027", "30 June – 4 July 2027", ISO dates, etc.
  render.py    writes the README tables between the TABLES markers
  __main__.py  collect → dedupe → drop past events → write data/conferences.json, docs/conferences.json, README.md
```
If any source fails (site down, format change), it's logged and skipped, so the daily run still finishes.
