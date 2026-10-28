"""Project settings: every analysis choice lives here so it is visible and versioned.

Edit this file (not the other scripts) when you add a university's records or
change a definition. Paths are relative to the repository root, so run every
script from the root: `bash run.sh`.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW = ROOT / "data" / "raw"
VISITS_DIR = RAW / "visits"                    # one file per university (as returned)
UNIVERSITIES = RAW / "universities.csv"        # one row per university
NCES = RAW / "nces"
ELSI_PUBLIC = NCES / "elsi_public_2021_22.csv"   # ElSi export, public schools 2021-22
# Private School Survey files: (path, year label, highest-grade variable), in priority order
PSS_FILES = [
    (NCES / "pss2122_pu.csv", "2021-22", "HIGR2022"),
    (NCES / "pss2324_pu.csv", "2023-24", "HIGR2024"),
]

ACS_YEAR = 2021                                # ACS 5-year 2017-2021: pre-period, held fixed
ACS_RAW = RAW / f"acs_zcta_{ACS_YEAR}.csv"     # saved on first download, then reused

MANUAL_CROSSWALK = ROOT / "data" / "manual" / "hs_crosswalk.csv"

INTERMEDIATE = ROOT / "data" / "derived"
HIGH_SCHOOLS = INTERMEDIATE / "high_schools.csv"
VISITS_STANDARDIZED = INTERMEDIATE / "visits_standardized.csv"
ZIP_DEMOGRAPHICS = INTERMEDIATE / "zip_demographics.csv"
VISITS_CLEAN = INTERMEDIATE / "visits_clean.csv"
PANEL_CYCLE = INTERMEDIATE / "panel_cycle.csv"
PANEL_SEMESTER = INTERMEDIATE / "panel_semester.csv"

OUTPUT = ROOT / "output"
TABLES = OUTPUT / "tables"
FIGURES = OUTPUT / "figures"
UNMATCHED = OUTPUT / "unmatched_schools.csv"
EVENT_AUDIT = OUTPUT / "event_categories.csv"

# ---------------------------------------------------------------------------
# Sample window and timing
# ---------------------------------------------------------------------------
# A recruitment cycle runs August through July and is labeled by its start year:
# cycle 2021 = Aug 2021 - Jul 2022.
FIRST_CYCLE = 2021
LAST_CYCLE = 2025          # Aug 2025 - Jul 2026; the partial Aug-Sep 2026 data is dropped
FIRST_POST_CYCLE = 2023    # SFFA decided June 29, 2023 -> 2023-24 is the first post cycle
EVENT_STUDY_REF_CYCLE = 2022          # omitted (reference) cycle: 2022-23
EVENT_STUDY_REF_SEMESTER = "2023S"    # omitted semester: spring 2023 (Jan-Jul 2023)

# ---------------------------------------------------------------------------
# Outcome definition
# ---------------------------------------------------------------------------
URM_THRESHOLD = 0.50                  # main definition of a high-URM high school
ROBUST_THRESHOLDS = [0.40, 0.60]      # robustness columns
SCHOOL_DEMOGRAPHICS_YEAR = "2021-22"  # pre-period demographics, held fixed

# ZIP-level robustness outcome: share of visits located in ZIPs whose residents
# are > URM_THRESHOLD URM. "urm_share_all" (all ages, exact definition) or
# "urm_share_15_19" (high-school ages, approximate; see prep_zip_demographics.py).
ZIP_MEASURE = "urm_share_all"

# URM = American Indian/Alaska Native, Black, Hispanic, Native Hawaiian/Pacific
# Islander (see code/prep_high_schools.py for how each source reports these).

# ---------------------------------------------------------------------------
# Which events count (code/standardize.py assigns each event a category)
# ---------------------------------------------------------------------------
# Rules are checked in order against the lower-cased event title; the first
# match sets the category. Titles matching none of them are "hs_visit" if the
# event type or title says visit/virtual, else "other".
EVENT_RULES = [
    # after students apply, so not recruitment of applicants
    ("admitted_student", r"admitted student|admit(ted)? (day|event|reception)|accepted student"),
    # materials left at a school with no event (unless the title also says visit)
    ("materials_dropoff", r"^(?!.*visit).*drop[- ]?off"),
    # anything titled as a visit to one school (including AVID / GEAR UP group visits)
    ("hs_visit", r"^(?!.*(fair|panel|breakfast|night)).*(\bvisit\b|\bhsv\b)"),
    # fairs and events serving many schools or a whole region/district
    # (any "...ACAC" association, district/consortium fairs, conferences, programs)
    ("regional_event", r"\b\w*acac\b|\bracc\b|consortium|consortia|district|unified|city-?wide|"
                       r"conference|counselor|exhibit|circuit|college fairs of|college previews|"
                       r"independent schools?|catholic schools?|private (high )?schools|public schools|"
                       r"gear up|foundation|\bpanel\b|case studies|upward bound|\bavid\b|undocu|"
                       r"on the road|area college fair|county college fair"),
    # fairs, nights and workshops hosted at one school (often open to nearby schools too)
    ("school_fair", r"fair|night|\bd/n\b|college day|expo|showcase|free app day|workshop|bootcamp|"
                    r"series|presentation|program|symposium|application day|opportunity day|"
                    r"career day|college week|lock-in|\bevent\b"),
]
VISIT_WORDS = r"visit|\bhsv\b|virtual|zoom"

# Main outcome uses these categories. The robustness column also counts
# fairs hosted at a single school.
ELIGIBLE_CATEGORIES = ["hs_visit"]
ALT_ELIGIBLE_CATEGORIES = ["hs_visit", "school_fair"]

# Used only when a file has an event title instead of a school-name column:
# these are removed from the title to leave the school's name.
TITLE_PREFIXES = [
    r"^(high school visit|hs visit|school visit|visit)\s*[-:]\s*",
    r"^drop[- ]?off\s*:\s*",
    r"^d/n\s+",
]
TITLE_SUFFIXES = [
    r"\([^)]*\)\s*$",                                   # (virtual), (Girls/Boys)
    r"[-/]?\s*materials? drop[- ]?off\s*$",
    r"\bdrop[- ]?off\s*$",
    r"\badmitted student 1:1s?\s*$",
    r"\b(day/night|d/n|mini|spring|fall|district)?\s*(college|college and career|college & career)?\s*"
    r"(fair|night|(?<=college )day|showcase|series day)\s*(fall|spring)?\s*(20\d\d)?\s*$",
    r"\b(virtual visit|spring visit|fall visit|visit|hsv|virtual|event|free app day)\s*$",
    r"\b(avid|gear up)\s*$",
    r"-\s*[^-]*public schools\s*$",
]
# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
CLUSTER = "state"
BOOTSTRAP_REPS = 9999
SEED = 1433

# ---------------------------------------------------------------------------
# Per-university raw-file layouts
# ---------------------------------------------------------------------------
# Every records office sends a different spreadsheet. For each file, name the
# column that holds each field; leave a field as None if the file lacks it.
#   date          required
#   school_name   a column with just the school's name, OR
#   title         an event title containing the school name (it is cleaned)
#   city, state   separate columns, OR city_state for one "City, ST" column
#   zip           optional, but makes matching much more reliable
#   nces_id       optional; if present, schools match exactly
#   event_type    optional; used when the title does not settle the category
# Optional: "sheet" (Excel sheet name), "header_row" (0 = first row),
# "date_format" (e.g. "%m/%d/%Y"; omit to let pandas infer).
VISIT_FILES = {
    # CORA request no. 879. Event export with one row per event; the school name
    # is inside the event title. "Cycle" in the file is the END year of the
    # cycle; the code recomputes cycles from the date instead.
    "cu_boulder": {
        "file": "cu_boulder.xlsx",
        "sheet": "Export",
        "date": "Start Date - MM/dd/yyyy",
        "date_format": "%m/%d/%Y",
        "title": "Title",
        "school_name": None,            # no separate school column: taken from the title
        "city_state": "City, State",    # combined "City, ST"
        "city": None,
        "state": None,
        "zip": "5-digit ZIP",
        "nces_id": None,
        "event_type": "Event Type",
    },
}
