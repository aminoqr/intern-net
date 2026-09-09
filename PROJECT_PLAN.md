# Job Radar — Project Plan

## 1. Goal
An automated agent that monitors multiple Polish/Warsaw job sources plus a target-company list for entry-level, intern, trainee, and junior software engineering postings, and pushes new matches to Telegram. Built to genuinely replace daily manual site-checking, not just a toy demo.

## 2. Scope decisions, and why
- **No LinkedIn.** Already checked manually daily — adding it would mean building the most fragile piece (IMAP + HTML email parsing) for a source that doesn't need automating.
- **No LLM calls at runtime.** Filtering is keyword-based (title, seniority, location), since the actual behavior is "apply to basically everything matching entry-level/intern/junior/trainee," not a nuanced per-posting fit judgment. Keeps the bot free to run, simple to debug, and fast to build.
- **No paid scraping services** (Apify etc.). Every chosen source has either a public JSON API or a plain, cleanly-renderable HTML page.
- **No server or VPS.** Runs on GitHub Actions cron — free, and independent of whether any personal machine is on.

## 3. Sources — Tier 1, build these four first
| Source | Method | Confidence |
|---|---|---|
| NoFluffJobs | Public JSON endpoints (`/api/search/posting`, `/api/posting/`), no login required | High |
| Target-company ATS feeds | Public JSON APIs of Greenhouse / Ashby / Lever, per company board slug | High |
| Pracuj.pl | Plain HTTP + BeautifulSoup — pages render cleanly, headless browser likely not needed | Medium-high |
| Just Join IT | Probable internal JSON endpoint (check Network tab in dev tools first); HTML parsing as fallback | Medium |

## 4. Target company list
Verify each company's actual ATS board slug from their live careers page before coding against it — slugs below are best guesses and need confirming.
- Saily / Nord Security — Ashby
- Point72 — Greenhouse
- Starburst — Ashby
- Snowflake, Box, Visa, ING Hubs Poland, Accenture — ATS type unconfirmed, check careers page

## 5. Backlog — add only after Tier 1 is solid and proven
- Bulldogjob.pl
- theprotocol.it
- (Confirmed scrapable with plain requests/BeautifulSoup by existing open-source projects — low risk once the core pattern exists.)

## 6. Repo structure
```
job-radar/
  config.py              # target companies + ATS type/slug, keywords, location filters
  fetchers/
    nofluffjobs.py
    pracujpl.py
    justjoinit.py
    ats.py                # generic greenhouse/ashby/lever fetcher, board slug as param
  dedupe.py                # SQLite seen-URL store + company+title cross-source match
  filter.py                 # keyword + seniority + location matching
  notify.py                  # Telegram push, includes fail-loud alerts
  main.py                     # fetch -> normalize -> filter -> dedupe -> notify
  .github/workflows/radar.yml # cron schedule
  README.md
```

## 7. Normalized job record schema
- `id` — source + slug, used for dedup
- `title`
- `company`
- `location`
- `seniority`
- `url`
- `source` (e.g. `nofluffjobs`, `greenhouse:point72`, `ashby:nord-security`)
- `posted_at`

## 8. Design principles (non-negotiable)
- **Fail loud, not silent.** If any fetcher returns zero results when it normally returns dozens, or throws an error, send a separate "X might be broken" Telegram alert instead of swallowing it. This is what makes the bot trustworthy enough to actually stop checking sites manually.
- **Two-layer dedup.** Per-URL (SQLite, don't renotify the same link) and cross-source (normalize company+title so the same job cross-posted on two boards collapses into one ping).
- **Keep fetchers dumb.** One HTTP call + parse per source. No browser automation (Selenium/Playwright) anywhere — if a source needs that, it's not worth the fragility for this project.

## 9. Ops
- GitHub Actions cron, every 1–2 hours.
- Keep the repo **public** — unlimited free Actions minutes on every plan, and it's a live, visible portfolio piece.
- Secrets stored as repo secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- State persistence: the workflow commits the updated SQLite file back to the repo at the end of each run (containers don't persist state between scheduled runs otherwise).

## 10. Build order

**Day 1**
1. Scaffold repo + `config.py` (target companies/slugs, keyword/location filters).
2. Build the NoFluffJobs fetcher (clean JSON, fastest first win).
3. Build the generic ATS fetcher (one function, parameterized by ATS type + board slug, covers Greenhouse/Ashby/Lever).
4. Build the dedup store: SQLite seen-URL table + company+title cross-source normalization.

**Day 2**
5. Build the Pracuj.pl fetcher (plain requests + BeautifulSoup; confirm no headless browser needed before writing the rest of the parser).
6. Build the Just Join IT fetcher (check dev tools Network tab for the internal JSON endpoint first).
7. Build the Telegram notifier with fail-loud alerts baked in; wire `main.py` end-to-end; test locally.
8. Add the GitHub Actions cron workflow (commit SQLite back each run); write the README.

## 11. README requirements
Document the Cursor-driven build process explicitly: what you specified up front, how you steered iterations, what you personally tested and can explain. Framed this way, "built in 2 days with Cursor" reads as proof of the exact AI-native engineering skill companies like Saily are hiring for, not a shortcut to justify.

## 12. First prompt for Cursor
Paste this as your opening message in Cursor's Agent panel, after saving this file into the repo as `PROJECT_PLAN.md`:

```
Read @PROJECT_PLAN.md in full.

We're building this step by step, not all at once. Right now, only implement
Step 1 from the "Build order" section: scaffold the repo structure from
section 6 and write config.py with the target companies, keywords, and
location filters from sections 3-4.

Don't build any fetchers yet. When you're done, stop and summarize what you
built so I can review it before we move to Step 2.
```

Repeat the same pattern for each subsequent step: reference `@PROJECT_PLAN.md`, name the step number, and review before moving on. Don't ask it to build the whole project in one prompt — reviewing after each step is what lets you actually explain every part of this later.
