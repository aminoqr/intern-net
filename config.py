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
    # Unverified. Careers pages are JS-rendered or header-blocked, so the board
    # slug could not be read off them. Confirm from the live careers page (look
    # for a boards.greenhouse.io / jobs.ashbyhq.com / jobs.lever.co link) and
    # flip enabled to True.
    {"company": "Starburst", "ats": "ashby", "slug": None, "enabled": False},
    {"company": "Box", "ats": None, "slug": None, "enabled": False},
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
# Warsaw first, plus remote roles anywhere in Poland.

ACCEPTED_LOCATIONS = [
    "warszawa",
    "warsaw",
    "mazowieckie",
    "masovian",
    "remote",
    "zdalnie",
    "zdalna",
    "praca zdalna",
    "poland",
    "polska",
    "pl",
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


# --- Runtime -------------------------------------------------------------

DB_PATH = "seen_jobs.db"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# Fail-loud: alert when a source returns fewer than this fraction of its
# trailing median result count.
SOURCE_DROP_THRESHOLD = 0.25
# Ignore the threshold until we have this many historical runs to compare to.
SOURCE_HISTORY_MIN_RUNS = 3
