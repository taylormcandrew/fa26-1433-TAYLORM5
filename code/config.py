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
    # recruiting at a community college (Cincinnati's "College Visit"): not a high school
    ("college_visit", r"^college visit$"),
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
    r"^[a-z.]+ day at\s+",                              # "UW Day at Liberty High School"
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
    r"(?<=high school)\s*-.*$",                          # "Lincoln High School - Thrive Thursdays"
    r"(?<=\bhs)\s*-.*$",                                 # "Pine HS - Fall Visit"
    r"\b(admissions\s+)?presentation\s*$",               # "Timberline High School Admissions Presentation"
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
# "date_format" (e.g. "%m/%d/%Y"; omit to let pandas infer),
# "keep" ({column: [values]}: keep only rows with these values, e.g. confirmed events),
# "default_type" (event type for rows whose file gives none).
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
    # FOIA request. One Word/PDF travel schedule per recruiting trip, converted to one table
    # by code/prep_montana_state.py (rerun it whenever files are added).
    "montana_state": {
        "file": "montana_state.csv",
        "date": "date",
        "date_format": "%Y-%m-%d",
        "title": "title",               # school or fair name
        "school_name": None,
        "city_state": "city_state",
        "city": None,
        "state": None,
        "zip": "zip",
        "nces_id": None,
        "event_type": "event_type",
    },
    # Public records request. Slate event export, one row per event. "Form Template" says
    # what kind of event it was ("High School Visit", "College Fair", ...), so it is used as
    # the title that sets the category; the school is in its own column. Only events with
    # Status CONFIRMED are kept (cancelled, tentative and declined events did not happen).
    "umass_amherst": {
        "file": "umass.xlsx",
        "sheet": "Export",
        "date": "Form Start Date/Time",
        "title": "Form Template",
        "school_name": "Location (school name)",
        "city_state": None,
        "city": "City",
        "state": "Region",
        "zip": None,
        "nces_id": None,
        "event_type": "Form Template",
        "keep": {"Status": ["CONFIRMED"]},
    },
    # Public records request. A 169-page PDF table, converted to one table by
    # code/prep_cincinnati.py. "type" says what kind of event it was, so it is used as the
    # title that sets the category; the school is in its own column. Only CONFIRMED events.
    "uc_cincinnati": {
        "file": "cincinnati.csv",
        "date": "date",
        "date_format": "%Y-%m-%d",
        "title": "type",
        "school_name": "location",
        "city_state": None,
        "city": "city",
        "state": "state",
        "zip": None,
        "nces_id": None,
        "event_type": "type",
        "keep": {"status": ["CONFIRMED"]},
    },
    # Public records request (NextRequest 26-2380). Slate export, one row per event.
    # "Event Type" says what kind of event it was, so it is used as the title that sets the
    # category; the school is in its own column. Only CONFIRMED events in the United States
    # (schools abroad cannot be matched to NCES data).
    "umn_twin_cities": {
        "file": "umn.xlsx",
        "sheet": "Export",
        "date": "Event Date",
        "date_format": "%m/%d/%Y",
        "title": "Event Type",
        "school_name": "Location Name",
        "city_state": None,
        "city": "City",
        "state": "State/Region",
        "zip": None,
        "nces_id": None,
        "event_type": "Event Type",
        "keep": {"Event Status": ["CONFIRMED"], "Country": ["United States"]},
    },
    # Public records request (Texas Public Information Act, L006734). Slate export, one row
    # per event; the school is in its own column. Only CONFIRMED events of type "High School
    # Visit" or "College Fair" (visits to colleges and events at A&M's own Prospective Student
    # Centers are not high-school recruiting). The event title sets the category, so e.g. an
    # "Application Workshop" at a school is treated like a fair, as for other universities.
    "tamu": {
        "file": "tamu.xlsx",
        "sheet": "Export",
        "date": "Date",
        "date_format": "%m/%d/%Y",
        "title": "Title",
        "school_name": "Location",
        "city_state": None,
        "city": "City",
        "state": "Region",
        "zip": None,
        "nces_id": None,
        "event_type": "Type",
        "keep": {"Status": ["CONFIRMED"], "Type": ["High School Visit", "College Fair"]},
    },
    # Public records request (Virginia FOIA, NextRequest 26-500): "HS Visits and College Fairs",
    # all confirmed. No event type column, so the title sets the category ("... Visit",
    # "... College Fair", "... Panel"); a title that is only a school's name is a visit.
    "vcu": {
        "file": "vcu.xlsx",
        "sheet": "Export",
        "date": "Event Date",
        "title": "Title",
        "school_name": "Location",
        "city_state": None,
        "city": "City",
        "state": "State",
        "zip": None,
        "nces_id": None,
        "event_type": None,
        "default_type": "School Visit",
    },
    # Public records request (UCDPRA260944). Slate export, one row per event; the file has no
    # useful type ("event"), so the title sets the category and a title that is only a school's
    # name is a visit. Only CONFIRMED events in the United States. Records start January 2022.
    "uc_davis": {
        "file": "ucdavis.xlsx",
        "sheet": "Export",
        "date": "Start Date",
        "title": "Event Title",
        "school_name": "Location",
        "city_state": None,
        "city": "City",
        "state": "Region",
        "zip": None,
        "nces_id": None,
        "event_type": None,
        "default_type": "School Visit",
        "keep": {"Status": ["CONFIRMED"], "Country": ["United States"]},
    },
    # Public records request (P002681-102826). Two sheets (CRM + pre-CRM archive), combined by
    # code/prep_wwu.py. The title sets the category, with the CRM template (e.g. "High School
    # Visit | In Person") as the event type; an archived title that is only a school's name
    # is a visit. Only events that took place (status CONFIRMED).
    "wwu": {
        "file": "wwu.csv",
        "date": "date",
        "date_format": "%Y-%m-%d",
        "title": "title",
        "school_name": "school",
        "city_state": None,
        "city": "city",
        "state": "state",
        "zip": None,
        "nces_id": None,
        "event_type": "type",
        "default_type": "School Visit",
        "keep": {"status": ["CONFIRMED"]},
    },    # Public records request (ORR2026-275). TargetX export, one row per event; the school
    # (with ZIP) comes from the linked school record. Event types that are not high-school
    # recruiting (community-college and transfer visits, counselor events, receptions,
    # virtual events) are dropped. The 3 events named "canceled" are dropped.
    "ttu": {
        "file": "ttu.xlsx",
        "sheet": "TTU Recruitment Events 2021-202",
        "date": "Event Date",
        "title": "Event Name",
        "school_name": "School Name",
        "city_state": None,
        "city": "City",
        "state": "State",
        "zip": "ZIP Code",
        "nces_id": None,
        "event_type": "Event Type",
        "keep": {"Event Status": ["Not marked canceled"],
                 "Event Type": ["High School Visit", "College Fair/Day", "Application Workshop",
                                "TACRAO Fair", "NMCAC Fair", "NACAC Fair", "WACAC Fair",
                                "RMACAC Fair", "VACRAO Fair"]},
    },
    # Public records request (R014862-102826). CRM export with no location column, converted
    # by code/prep_utaustin.py (keeps high-school visits and fairs; school name from title).
    "ut_austin": {
        "file": "utaustin.csv",
        "date": "date",
        "date_format": "%Y-%m-%d",
        "title": "title",
        "school_name": "school",
        "city_state": None,
        "city": None,
        "state": "state",
        "zip": None,
        "nces_id": None,
        "event_type": "type",
        "keep": {"status": ["CONFIRMED"]},
    },    # CORA request no. 911. Same Slate export format as CU Boulder's; only CONFIRMED events.
    "cu_denver": {
        "file": "cudenver.xlsx",
        "sheet": "Export",
        "date": "Start Date - MM/dd/yyyy",
        "date_format": "%m/%d/%Y",
        "title": "Title",
        "school_name": None,            # taken from the title
        "city_state": "City, State",
        "city": None,
        "state": None,
        "zip": "5-digit ZIP",
        "nces_id": None,
        "event_type": "Event Type",
        "keep": {"Form Status": ["CONFIRMED"]},
    },    # Public records request (NextRequest 26-1003): "Events Attended", Aug 2022 - Jul 2026
    # (no 2021-22 records). The school or venue is in "Location"; there is no city column, so
    # schools are matched by name within the state. In-person high-school visits and fairs only.
    "fsu": {
        "file": "fsu.xlsx",
        "sheet": "Export",
        "date": "Start Date",
        "title": "Event",
        "school_name": "Location",
        "city_state": None,
        "city": None,
        "state": "State",
        "zip": None,
        "nces_id": None,
        "event_type": "Type",
        "keep": {"Type": ["High School Visit", "College Fair"], "Event Format": ["In-person"]},
    },    # Florida public records request (UNF Office of the General Counsel). Slate export; the
    # title ("Wakulla High School College Fair with UNF") sets the category, the school is in
    # "Form Location". Only CONFIRMED events. Virtual events have no location, so they do not
    # match a high school and drop out of the outcome.
    "unf": {
        "file": "unf.xlsx",
        "sheet": "Export",
        "date": "Form Start Date/Time",
        "date_format": "%m/%d/%Y",
        "title": "Form Title",
        "school_name": "Form Location",
        "city_state": None,
        "city": "Form City",
        "state": "Form Region",
        "zip": None,
        "nces_id": None,
        "event_type": None,
        "default_type": "School Visit",
        "keep": {"Form Status": ["CONFIRMED"], "Form Type": ["event"]},
    },
}

# Scraped calendars (scraper/export.py) all share one format, so every
# data/raw/visits/<univ>_scraped.csv file is added here automatically.
SCRAPED_FORMAT = {"date": "date", "date_format": "%Y-%m-%d", "title": "title",
                  "school_name": None, "city_state": "city_state", "city": None,
                  "state": None, "zip": "zip", "nces_id": None, "event_type": "event_type"}
for _f in sorted(VISITS_DIR.glob("*_scraped.csv")):
    VISIT_FILES[_f.stem.removesuffix("_scraped")] = dict(SCRAPED_FORMAT, file=_f.name)
