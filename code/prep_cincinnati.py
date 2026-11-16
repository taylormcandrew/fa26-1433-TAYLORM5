"""prep_cincinnati.py: turn the University of Cincinnati's records (a 169-page PDF) into a table.

Cincinnati answered the records request with a printed table, one row per event:

    Event Date   Location                         City          State  Type               Status
    8/23/2021    Bishop Chatard High School       Indianapolis  IN     High School Visit  CONFIRMED

A long location wraps onto extra lines above its row, e.g.
                 Cincinnati State Technical and Community
    8/30/2021    College                          Cincinnati    OH     College Visit      CONFIRMED

This script reads the words on each page with their positions. Every row starts with a date
in the first column; each other word belongs to the column it sits under and to the first
date at or below it (so wrapped lines join their row). The table is copied as it is; which
events count (confirmed school visits) is decided in code/config.py, like for every school.

The original PDF is never changed. Put it in data/raw/visits/ as cincinnati.pdf and run
from the project folder:
    python3 code/prep_cincinnati.py
It writes data/raw/visits/cincinnati.csv (read by ./run.sh through config.py).
Needs: pip install pdfplumber
"""
import re

import pandas as pd
import pdfplumber

import config

PDF = config.VISITS_DIR / "cincinnati.pdf"
OUT = config.VISITS_DIR / "cincinnati.csv"
# Left edge (in points) of each column on the page, from the header row of the PDF
COLUMNS = [("date", 0), ("location", 100), ("city", 300), ("state", 398), ("type", 454),
           ("status", 566)]
DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def column(x):
    """Name of the column a word starting at position x belongs to."""
    return [name for name, left in COLUMNS if x >= left][-1]


rows = []
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages:
        words = page.extract_words()
        # One row per date in the first column, in order down the page
        dates = sorted((w for w in words if w["x0"] < 100 and DATE.match(w["text"])),
                       key=lambda w: w["top"])
        page_rows = [{"top": d["top"], "date": d["text"], "location": [], "city": [],
                      "state": [], "type": [], "status": []} for d in dates]
        # The header line ("Event Date  Location  City ...") is not data
        header = [w["top"] for w in words if w["text"] == "Status" and column(w["x0"]) == "status"]
        for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
            name = column(w["x0"])
            if name == "date" or any(abs(w["top"] - h) < 3 for h in header):
                continue                                   # dates done; skip the header
            # The word belongs to the first row whose date is level with it or below it
            row = next((r for r in page_rows if r["top"] >= w["top"] - 3), None)
            if row is not None:
                row[name].append(w["text"])
        rows += page_rows

table = pd.DataFrame([{k: (" ".join(v) if isinstance(v, list) else v)
                       for k, v in r.items() if k != "top"} for r in rows])
table["date"] = pd.to_datetime(table["date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
table.to_csv(OUT, index=False)
print(f"Wrote {len(table):,} events to {OUT.relative_to(config.ROOT)} "
      f"({table['date'].min()} to {table['date'].max()})")
print("Type:", table["type"].value_counts().to_dict())
print("Status:", table["status"].value_counts().to_dict())
