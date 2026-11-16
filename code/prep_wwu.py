"""prep_wwu.py: combine Western Washington University's two event sheets into one table.

WWU's records request returned one Excel file with two sheets, because WWU changed systems:
  Events_CRM                 events in its CRM (Sep 2021 on; few before 2023)
  Events_Archived (Pre-CRM)  an older spreadsheet (Aug 2021 - May 2023), mostly fairs
Both are needed to cover the years before SFFA. This script stacks them in one format:

    date, title, school, city, state, type, status, sheet

  * CRM rows keep their own status (only CONFIRMED is used, set in code/config.py).
  * Archived rows have no status, only a free-text comment; rows whose comment says the
    event did not happen ("not attending", "cancelled", "missed", ...) get status
    NOT HELD, all others CONFIRMED.
  * school: the event's location column; in the archive, the location or venue, else the
    school named in the title (as for every other file without a school column).

The original file is never changed. Put it in data/raw/visits/ as wwu.xlsx and run from the
project folder:   python3 code/prep_wwu.py   -> data/raw/visits/wwu.csv
"""
import re

import pandas as pd

import config
from standardize import school_from_title

RAW = config.VISITS_DIR / "wwu.xlsx"
OUT = config.VISITS_DIR / "wwu.csv"
NOT_HELD = re.compile(r"not attend|not going|cancel|missed|declin", re.I)

crm = pd.read_excel(RAW, sheet_name="Events_CRM", dtype=str)
crm = pd.DataFrame({"date": crm["Start Date"], "title": crm["Title"], "school": crm["Location"],
                    "city": crm["City"], "state": crm["Region"], "type": crm["Template"],
                    "status": crm["Status"], "sheet": "CRM"})

old = pd.read_excel(RAW, sheet_name="Events_Archived (Pre-CRM)", dtype=str)
held = ~old["Comments"].fillna("").str.contains(NOT_HELD)
old = pd.DataFrame({"date": old["Date of Event"], "title": old["Title"],
                    "school": old["Location"].fillna(old["Venue"]),
                    "city": old["City/Region"], "state": old["State"], "type": old["Type"],
                    "status": held.map({True: "CONFIRMED", False: "NOT HELD"}),
                    "sheet": "Archived"})

table = pd.concat([crm, old], ignore_index=True)
table["school"] = table["school"].fillna(table["title"].map(school_from_title))
table["date"] = pd.to_datetime(table["date"], errors="coerce").dt.strftime("%Y-%m-%d")
table = table.dropna(subset=["date"]).sort_values("date")
table.to_csv(OUT, index=False)
print(f"Wrote {len(table):,} events to {OUT.relative_to(config.ROOT)} "
      f"({table['date'].min()} to {table['date'].max()})")
print(table.groupby(["sheet", "status"]).size().to_string())
