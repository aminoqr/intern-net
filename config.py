"""Central configuration: target companies, keyword filters, location filters.

Everything tunable lives here so the fetchers and filter stay dumb.
"""

# --- Target company ATS boards -------------------------------------------
#
# Slugs below were verified against the live posting APIs (see README).
# Anything unverified is left disabled rather than guessed at, because a wrong
# slug returns 404 and would trip the fail-loud alerts on every single run.
#
# ats: "greenhouse" | "ashby" | "lever"

ATS_BOARDS = [
    # Verified: 200 OK with a non-empty job list.
    {"company": "Nord Security / Saily", "ats": "ashby", "slug": "nord-security", "enabled": True},
    {"company": "Snowflake", "ats": "ashby", "slug": "snowflake", "enabled": True},
    {"company": "Point72", "ats": "greenhouse", "slug": "point72", "enabled": True},
    {"company": "Starburst", "ats": "greenhouse", "slug": "starburst", "enabled": True},
    {"company": "Box", "ats": "greenhouse", "slug": "boxinc", "enabled": True},
    # Unverified. Careers pages are JS-rendered or header-blocked, so the board
    # slug could not be read off them. Confirm from the live careers page (look
    # for a boards.greenhouse.io / jobs.ashbyhq.com / jobs.lever.co link) and
    # flip enabled to True.
    {"company": "Visa", "ats": None, "slug": None, "enabled": False},
    {"company": "ING Hubs Poland", "ats": None, "slug": None, "enabled": False},
    # Accenture runs Workday, which the generic ATS fetcher does not support.
    # Out of scope per the "keep fetchers dumb" principle.
    {"company": "Accenture", "ats": "workday", "slug": None, "enabled": False},
]


def enabled_boards():
    """ATS boards that are safe to fetch (have both a type and a slug)."""
    return [b for b in ATS_BOARDS if b["enabled"] and b["slug"] and b["ats"]]


# --- Keyword matching convention -----------------------------------------
#
# All keyword lists below are matched on text that has been lowercased and had
# its Polish diacritics stripped (see models.normalize_text).
#
#   "junior"    -> whole-word match. Does NOT match "juniors" or "xjunior".
#   "praktyk*"  -> prefix match. Matches "praktyki", "praktykant", "praktykanta".
#
# Whole-word is the default because plain substring matching is actively wrong
# here: "intern" would match "International" and "Internal Auditor". The prefix
# form exists for Polish, which inflects heavily ("staz", "stazu", "stazysta").


# --- Seniority filtering --------------------------------------------------
#
# The behaviour being automated is "apply to basically everything entry-level",
# so this list is deliberately broad and includes the Polish terms, since
# Pracuj.pl and NoFluffJobs both post in Polish.

ENTRY_LEVEL_KEYWORDS = [
    "intern",  # deliberately not "intern*" -- that matches "international"
    "internship",
    "interns",
    "trainee",
    "trainees",
    "junior",
    "entry level",
    "entry-level",
    "graduate",
    "apprentice",
    "apprenticeship",
    "praktyk*",  # praktyki, praktykant, praktykanta
    "staz*",  # staż, stażysta, stażu
    "mlodsz*",  # młodszy, młodsza (= junior)
    "absolwen*",  # absolwent (= graduate)
]

# Subset of the entry-level vocabulary that means "not a regular employment
# contract": internships, traineeships, working-student and graduate programs.
# Used to pick which Telegram channel a match is routed to, not to filter.
INTERNSHIP_KEYWORDS = [
    "intern",
    "internship",
    "interns",
    "trainee",
    "trainees",
    "apprentice",
    "apprenticeship",
    "working student",
    "graduate",
    "praktyk*",
    "staz*",
    "absolwen*",
]

# Titles containing these are rejected even if they also match an entry-level
# keyword. Catches "Senior Engineer (Junior team)" and, more commonly,
# "Junior/Mid/Senior" range postings that are really mid-level asks.
#
# "specjalista" is deliberately absent: it means "specialist", not "senior",
# and would wrongly reject "Mlodszy Specjalista ds. IT".
SENIOR_KEYWORDS = [
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "leader",
    "head of",
    "manager",
    "director",
    "architect",
    "expert",
    "chief",
    "vp",
    "starsz*",  # starszy (= senior)
]

# Mid-level markers. Unlike SENIOR_KEYWORDS these are not an outright veto:
# "Junior/Mid Java Developer" is worth applying to, "Mid .Net Engineer" is not.
# So these only reject when the title carries no entry-level keyword of its own.
#
# Roman numerals are here because Pracuj.pl and Just Join IT both tag
# "Performance Engineer II" as junior in their structured data, and level II is
# consistently a mid-level ask.
MID_LEVEL_KEYWORDS = ["mid", "regular", "ii", "iii"]

# Structured seniority values as the sources themselves report them. Cheaper
# and more reliable than title matching when a source provides it.
ACCEPTED_SENIORITY = ["trainee", "intern", "junior", "entry", "graduate", "assistant"]
REJECTED_SENIORITY = ["mid", "senior", "expert", "lead", "manager", "c-level", "director"]


# --- Role filtering ------------------------------------------------------
#
# Keeps the radar on software engineering. Without this, "Junior" alone pulls in
# junior accountants, junior recruiters and junior marketing specialists, which
# is the main source of noise on the general-purpose boards.

ROLE_KEYWORDS = [
    "software",
    "developer",
    "develop*",
    "programist*",  # programista, programisty
    "programmer",
    "engineer",
    "engineering",
    "inzynier*",  # inżynier, inżyniera
    "backend",
    "back-end",
    "frontend",
    "front-end",
    "fullstack",
    "full-stack",
    "full stack",
    "android",
    "ios",
    "python",
    "java",
    "javascript",
    "typescript",
    "golang",
    "go",
    "rust",
    "c++",
    "c#",
    ".net",
    "php",
    "ruby",
    "scala",
    "kotlin",
    "swift",
    "react",
    "node",
    "devops",
    "sre",
    "site reliability",
    "platform engineer",
    "cloud engineer",
    "data engineer",
    "data scientist",
    "machine learning",
    "deep learning",
    "ai",
    "ml",
    "qa",
    "tester",
    "testing",
    "automation",
    "cybersecurity",
    "embedded",
    "it",
    "web",
    "mobile",
]

# Explicitly non-engineering roles that sneak through on shared vocabulary
# ("Junior Data Analyst", "Junior IT Recruiter", "Junior Project Manager").
ROLE_EXCLUSIONS = [
    "recruit*",  # recruiter, recruitment
    "rekrutacj*",
    "sales",
    "sprzedaz*",
    "marketing",
    "accountant",
    "accounting",
    "ksiegow*",  # księgowy (= accountant)
    "hr",
    "people partner",
    "talent",
    "customer support",
    "customer success",
    "customer service",
    "content writer",
    "copywriter",
    "graphic design*",
    "project manager",
    "product owner",
    "scrum master",
    "business analyst",
    "business development",
    "business operations",
    "analityk biznesowy",
    # HR and workforce systems roles that match on shared IT vocabulary.
    "hris",
    "workforce",
    "coordinator",
    # IT project/contract administration, not engineering.
    "project specialist",
    "projektow",  # "ds. Projektów IT"
    "umowami",  # "ds. Zarządzania Umowami IT"
    "financial",
    "finance",
    "payroll",
    "recepcj*",  # recepcja (= reception)
    "outreach",
    "consultant",
    "consulting",
    "aml",
    "kyc",
]


# --- Location filtering --------------------------------------------------
#
# Warsaw first, plus remote roles in Poland.

POLISH_LOCATIONS = [
    "warszawa",
    "warsaw",
    "mazowieckie",
    "masovian",
    "poland",
    "polska",
    "pl",
]

REMOTE_LOCATIONS = [
    "remote",
    "zdalnie",
    "zdalna",
    "praca zdalna",
]

ACCEPTED_LOCATIONS = POLISH_LOCATIONS + REMOTE_LOCATIONS

# Foreign locations reject a posting even when it is also marked remote, since
# "Vilnius, Remote" is a Lithuanian role. A Polish location anywhere in the
# same field overrides this, so "Warszawa, Vilnius, Remote" still matches.
#
# Deliberately does NOT contain "praga": Praga-Polnoc and Praga-Poludnie are
# Warsaw districts and appear in real postings. Prague is listed in English
# only. Foreign locations are mostly caught by the country-prefix rule in
# filter.py (Snowflake formats locations as "US-CA-Menlo Park"), so this list
# only needs to cover bare foreign city names.
REJECTED_LOCATIONS = [
    "vilnius",
    "kaunas",
    "klaipeda",
    "riga",
    "tallinn",
    "wegry",  # "Węgry" = Hungary
    "hungary",
    "budapest",
    "prague",
    "praha",
    "brno",
    "bratislava",
    "london",
    "manchester",
    "berlin",
    "munich",
    "hamburg",
    "frankfurt",
    "madrid",
    "barcelona",
    "lisbon",
    "porto",
    "amsterdam",
    "dublin",
    "paris",
    "vienna",
    "zurich",
    "geneva",
    "brussels",
    "stockholm",
    "oslo",
    "copenhagen",
    "helsinki",
    "milan",
    "rome",
    "athens",
    "bucharest",
    "sofia",
    "belgrade",
    "zagreb",
    "kyiv",
    "kiev",
    "lviv",
    "istanbul",
    "tel aviv",
    "dubai",
    "bangalore",
    "bengaluru",
    "hyderabad",
    "pune",
    "mumbai",
    "chennai",
    "noida",
    "gurgaon",
    "singapore",
    "tokyo",
    "seoul",
    "shanghai",
    "beijing",
    "sydney",
    "melbourne",
    "toronto",
    "vancouver",
    "new york",
    "san francisco",
    "san jose",
    "san mateo",
    "menlo park",
    "mountain view",
    "bellevue",
    "redmond",
    "seattle",
    "austin",
    "chicago",
    "boston",
    "atlanta",
    "denver",
    "dallas",
    "houston",
    "los angeles",
    "sao paulo",
    "mexico city",
]

# Set False to accept postings whose location could not be determined, rather
# than dropping them. Kept strict by default to hold the signal-to-noise ratio.
ALLOW_UNKNOWN_LOCATION = False


# --- Source query parameters --------------------------------------------

NOFLUFFJOBS_CITIES = ["warszawa"]
NOFLUFFJOBS_SENIORITY = ["trainee", "junior"]

PRACUJPL_SEARCH_URLS = [
    # et=1,17 -> trainee/internship contract types; wp=warszawa
    "https://it.pracuj.pl/praca/warszawa;wp?et=1%2C17",
    "https://it.pracuj.pl/praca/junior;kw/warszawa;wp",
]

JUSTJOINIT_SEARCH_URLS = [
    "https://justjoin.it/job-offers/warszawa?keyword=junior",
    "https://justjoin.it/job-offers/warszawa?keyword=intern",
]


# --- Telegram routing ----------------------------------------------------
#
# Every match lands in exactly one category. Each category can have its own
# chat -- point the env var at a channel/group id -- and any category whose
# env var is unset falls back to TELEGRAM_CHAT_ID, so with no extra setup
# everything still arrives in the main chat. Alerts always go to the main chat.

CATEGORY_CHAT_ENV = {
    "internship": "TELEGRAM_CHAT_ID_INTERNSHIPS",
    "junior": "TELEGRAM_CHAT_ID_JUNIOR",
}

# Telegram allows ~1 msg/sec sustained per chat; with one message per job this
# pause keeps a big run (e.g. after reseeding) from tripping 429s.
TELEGRAM_SEND_INTERVAL = 1.0


# --- Runtime -------------------------------------------------------------

DB_PATH = "seen_jobs.db"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# Fail-loud: alert when a source returns fewer than this fraction of its
# trailing median result count. Live counts per source sit between 23 and 369
# and are stable run to run, so 0.4 catches a real breakage well before it
# looks like a quiet day, without firing on normal churn.
SOURCE_DROP_THRESHOLD = 0.4
# Ignore the threshold until we have this many historical runs to compare to.
SOURCE_HISTORY_MIN_RUNS = 3
