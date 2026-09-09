# Job Radar

An automated agent that watches Polish and Warsaw-area job sources plus a list of target
companies for intern, trainee and junior software engineering roles, and pushes new matches
to Telegram. It runs on GitHub Actions cron, has no runtime dependencies, and costs nothing
to operate.

It was built to actually replace checking six job sites by hand every morning, which is a
higher bar than a demo: if a scraper quietly breaks, a silent bot looks exactly like "no new
jobs today". Everything below about fail-loud alerting exists because of that.

## Sources

All four are reached with a single plain HTTP request each. No headless browser, no paid
scraping service, no API keys.

| Source | Method | Status |
|---|---|---|
| NoFluffJobs | Public JSON search API | Verified, ~39 Warsaw trainee/junior postings |
| Target company ATS boards | Greenhouse / Ashby / Lever public board APIs | Verified for 3 boards, ~730 postings |
| Pracuj.pl | React Query cache embedded in `__NEXT_DATA__` | Verified, ~197 postings |
| Just Join IT | Offer array embedded in the streamed RSC payload | Verified, ~311 postings |

Target company boards currently enabled: Nord Security / Saily (`ashby:nord-security`),
Snowflake (`ashby:snowflake`), Point72 (`greenhouse:point72`). Starburst, Box, Visa,
ING Hubs Poland and Accenture are listed but disabled in [config.py](config.py) because their
board slugs could not be confirmed from their careers pages, and Accenture runs Workday, which
the generic ATS fetcher does not support. A wrong slug is a 404, which would fire a false
alert on every run, so unconfirmed boards stay off rather than guessed at.

## Quick start

Requires Python 3.9 or newer. There is nothing to install.

```bash
git clone https://github.com/aminoqr/intern-net.git
cd intern-net

# See what it would send, without needing a Telegram bot
python main.py --dry-run
```

On a fresh database the first real run would send every currently-matching posting, which is
roughly 150 messages' worth of backlog. To start from "only tell me about new things":

```bash
python main.py --seed     # adopt the current backlog silently
python main.py --dry-run  # now reports 0 new
```

### Telegram setup

1. In Telegram, message [@BotFather](https://t.me/BotFather) and send `/newbot`. Choose a
   display name, then a username ending in `bot`. BotFather replies with a token.
2. Send any message to your new bot. A bot cannot message you first, so this step is what
   creates the conversation.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and copy
   `result[0].message.chat.id`.
4. Save both values in a `.env` file next to `main.py`:

   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-your-token
   TELEGRAM_CHAT_ID=987654321
   ```

`.env` is gitignored. Without it the bot runs in dry-run mode and prints to the console, so
the pipeline stays testable before the bot exists.

### Running it on GitHub Actions

1. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` under Settings, Secrets and variables,
   Actions.
2. Keep the repository public. Scheduled Actions minutes are unlimited on public repos.
3. Run the workflow manually once from the Actions tab with the **seed** input checked, so
   the first scheduled run reports only genuinely new postings.

The workflow then runs every two hours and commits the updated `seen_jobs.db` back to the
repo, because an Actions runner's filesystem does not survive between scheduled runs.

## How it works

```
fetchers/*  ->  filter.py  ->  dedupe.py  ->  notify.py
  6 sources     3 gates       2 layers      Telegram

  1278 fetched -> 200 matched -> 150 new -> 12 messages
```

Every fetcher returns the same normalized `Job` record, so `main.py` never knows where a
posting came from. A representative run: 1278 postings fetched, 200 pass the filters, 150 are
new after deduplication.

### Filtering

Three gates, applied to lowercased and diacritic-stripped text so Polish and English postings
match the same keyword lists:

1. **Role** — is it actually software engineering? Without this, "Junior" alone pulls in
   junior accountants, recruiters and marketing specialists.
2. **Seniority** — entry-level, and not secretly a mid or senior ask. A senior marker in the
   title always wins, so `Junior/Mid/Senior` range postings are dropped while `Junior-Mid` is
   kept.
3. **Location** — Warsaw, or remote.

Matching is whole-word by default, not substring, because substring matching is wrong in ways
that matter here: `intern` appears inside "International" and "Internal Auditor". Keywords
ending in `*` are prefix matches, which is how Polish inflection is handled (`staz*` covers
"staż", "stażysta", "stażu"). See the convention comment in [config.py](config.py).

### Deduplication

Two layers, both in [dedupe.py](dedupe.py):

- **Per URL.** A link that has been notified is never notified again.
- **Per company and title fingerprint.** Legal forms (`Sp. z o.o.`, `GmbH`, `Ltd`) and Polish
  gender markers (`(K/M)`, `(czka)`, `/-ka`) are stripped before comparing, so one role
  cross-posted to two boards, or listed once per city on one board, collapses into a single
  ping. This removed 50 duplicate notifications out of 200 matches on a live run.

### Fail-loud alerting

Every run records each source's result count in a `source_stats` table. A source is reported
as suspect when it raises, returns zero having previously returned more, or drops below 25%
of its trailing median. That alert is sent as its own message, precisely because the failure
mode being guarded against is an absence of messages.

## Configuration

Everything tunable is in [config.py](config.py): target company boards, the keyword lists for
all three filter gates, accepted locations, and the fail-loud thresholds.

Each module is runnable on its own for inspecting live data, which is how the filters were
tuned:

```bash
python -m fetchers.nofluffjobs   # or pracujpl, justjoinit, ats
python -m filter                 # fetch everything, show what is kept and why
python -m dedupe                 # show fingerprint normalization and collapsing
python -m health                 # walk through the fail-loud scenarios
```

## Repository layout

```
config.py                   target companies, keywords, location filters, thresholds
models.py                   the normalized Job record and text normalization
filter.py                   keyword, seniority and location gates
dedupe.py                   SQLite store, both dedup layers, source statistics
health.py                   fail-loud source health verdicts
notify.py                   Telegram delivery, batching, dry-run mode
main.py                     fetch -> filter -> dedupe -> notify
fetchers/base.py            shared HTTP with browser headers and retries
fetchers/nofluffjobs.py     public JSON search API
fetchers/ats.py             generic Greenhouse / Ashby / Lever fetcher
fetchers/pracujpl.py        __NEXT_DATA__ React Query cache
fetchers/justjoinit.py      embedded RSC payload
.github/workflows/radar.yml two-hourly cron, commits state back
PROJECT_PLAN.md             the specification this was built from
```

## How this was built with Cursor

This project was written in two days using Cursor's agent, and the process is worth
documenting because it is the reason the result is explainable rather than a pile of
generated code.

**The specification came first.** [PROJECT_PLAN.md](PROJECT_PLAN.md) was written before any
code: the goal, the scope decisions and their justifications, the four Tier 1 sources, the
normalized record schema, the non-negotiable design principles, and an explicit build order.
Notably it also records what was deliberately *excluded* and why — no LinkedIn, no LLM calls
at runtime, no paid scraping, no browser automation, no VPS. Constraints stated up front are
what keep an agent from wandering.

**It was built one step at a time, not in one prompt.** The build order was split into 16
commits across two days, each one logical unit that leaves the repo working, each reviewed
before starting the next. The commit history is the actual sequence: config, then the shared
HTTP layer, then one fetcher at a time, then filtering, then dedup, then notification, then
CI.

**Every source was verified against the live endpoint before code was written for it**, and
this is where the plan turned out to be wrong in ways that mattered:

- NoFluffJobs requires a `salaryCurrency` query parameter that is not obvious from the
  endpoint alone. Without it, every request is a 400.
- The plan's guessed ATS board slugs were mostly wrong. `nord-security` is correct;
  `nordsecurity`, `saily`, `starburst` and `starburstdata` all 404. Snowflake turned out to be
  on Ashby, which the plan had listed as unconfirmed.
- The plan assumed Pracuj.pl would need BeautifulSoup HTML parsing. It actually returns 403 to
  a bare request, and 200 with a full browser header set — and then ships every offer as clean
  JSON in `__NEXT_DATA__`, so there is no HTML parsing at all.
- Just Join IT's internal JSON API, which the plan hoped to use, returns 503 to every header
  combination tried. The page itself embeds the complete offer list in its streamed RSC
  payload, so that is what the fetcher reads.
- Pracuj.pl blocks `requests`/`urllib3` at the client-fingerprint level even with
  byte-identical headers and a stock SSL context, while stdlib `urllib` gets 200. Chasing that
  down is why this project has zero third-party dependencies: `urllib` handles all six
  endpoints, so the Actions job needs no install step and cannot break from an upstream
  package release.

**What was tested, and how.** Each fetcher has a `__main__` block that hits the live source
and prints normalized records, which is how each one was checked before moving on. The keyword
matcher was tested against the specific edge cases that break naive substring matching
(`intern` vs "International", `lead` vs "Machine Learning", `.NET` inside "ASP.NET", Polish
inflection). Dedup was verified by running the same input twice and confirming zero
notifications the second time, and the schema migration was tested against a hand-built legacy
database to confirm it backfills instead of resurfacing every job. Fail-loud alerting was
walked through its full range — first run, healthy runs, collapse, zero, exception, mild dip —
to confirm it neither cries wolf nor stays quiet when it matters. Failure isolation was tested
by injecting a raising fetcher and confirming the other sources still delivered.

**Known rough edges**, kept honest rather than hidden: the filters are tuned to over-include,
since a missed internship costs more than a junk notification. Pracuj.pl and Just Join IT both
tag "Junior/Mid/Senior talent pool" postings as junior, and some slip through. The location
gate accepts any remote posting, including remote roles based outside Poland.
