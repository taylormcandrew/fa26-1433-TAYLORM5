"""prep_utaustin.py: turn UT Austin's event export into a visit table.

UT Austin's records request returned 43,804 rows from its CRM, most of them individual
counseling appointments. There is no location column: each row has only a title
("Plano Senior High School Day Visit - Seniors"), a category and a date. This script:

  1. keeps the high-school recruiting categories: "Senior High School Visits",
     "Pre Senior High School Visits" and "HS College Fairs" (appointments, yield events,
     transfer fairs, counselor events, ... are dropped);
  2. takes the school's name from the title by removing staff prefixes ("ADM – VAC –",
     "TACRAO", "AP -") and everything after the school word ("High School", "HS",
     "Academy", ...), e.g. "Plano Senior High School Day Visit - Seniors" -> "Plano Senior
     High School";
  3. sets the state to TX for UT's Texas recruiting regions (Houston, Dallas, Valley,
     Central, East/West Texas, El Paso) and leaves it blank for National/International.
The event type is "School Visit" or "College Fair" from the category; the title still sets
the final category in standardize.py (e.g. an "Admitted Student Day Visit" is not counted).

The original file is never changed. Put it in data/raw/visits/ as utaustin.xlsx and run
from the project folder:   python3 code/prep_utaustin.py   -> data/raw/visits/utaustin.csv
"""
import re

import pandas as pd

import config

RAW = config.VISITS_DIR / "utaustin.xlsx"
OUT = config.VISITS_DIR / "utaustin.csv"
PREFIX = re.compile(r"^(adm\s*[-–]\s*((vac|hac|dac|centex|college fair)\s*[-–]\s*)?|tacrao\s*[-–]?\s*|"
                    r"starn\s*[-–]\s*|ap\s*[-–]\s*|rr\s*[-–]\s*)", re.I)
SCHOOL_WORD = re.compile(r"^(.*?\b(high school|hs|academy|school|prep(aratory)?|collegiate|"
                         r"early college))\b", re.I)


def school(title):
    """School name inside an event title (the whole cleaned title if no school word)."""
    t = PREFIX.sub("", str(title)).strip()
    m = SCHOOL_WORD.match(t)
    return (m.group(1) if m else t).strip(" -–:")


d = pd.read_excel(RAW, dtype=str)
d = d[d["Category"].str.contains(r"High School Visits|HS College Fairs", na=False)]
region = d["Category"].str.split("/").str[-1].str.strip()
table = pd.DataFrame({
    "date": pd.to_datetime(d["Start Date"]).dt.strftime("%Y-%m-%d"),
    "title": d["Title"],
    "school": d["Title"].map(school),
    "state": region.where(~region.isin(["National", "International"]), "").map(
        lambda r: "" if r == "" else "TX"),
    "type": d["Category"].str.contains("Fairs").map({True: "College Fair", False: "School Visit"}),
    "status": d["Status"]})
table = table.sort_values("date")
table.to_csv(OUT, index=False)
print(f"Wrote {len(table):,} events to {OUT.relative_to(config.ROOT)} "
      f"({table['date'].min()} to {table['date'].max()})")
print(table["type"].value_counts().to_dict())
