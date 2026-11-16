"""prep_montana_state.py: turn Montana State's FOIA travel schedules into one visit table.

Montana State sent one file per recruiting trip (2021-2026), in a few layouts that all list,
day by day, the stops of the trip:

  * Word documents (.doc/.docx, mostly 2021-22): a "TRAVEL SCHEDULE" form whose table has one
    row per stop (date | time | location | notes); a blank date means "same day as above".

        Thursday, December 16 |         | Jefferson High School / 312 S Main St. / Boulder, MT 59632
                              | 11:00am | Butte High School / 401 S Wyoming St. / Butte, MT 59701

  * PDFs (later years): a weekday line followed by its stops, with the school (or fair) name
    on the left and its address on the right:

        Monday, October 5
            8:00 - 9:00AM
               Telluride High School                725 W. Colorado Ave.
                                                    Telluride, CO 81435

For each stop this script keeps:
  date        the stop's day. The files usually omit the year ("Saturday, October 9"); between
              Aug 2021 and Jul 2027 each (weekday, month, day) falls in exactly one year, so the
              weekday fixes the year. Without a weekday, the year in the file name is used.
  title       the school or fair name (first line of the location)
  city_state  from the "City, ST 12345" line (state names like "Montana" are accepted), + ZIP
  event_type  "School Visit"; standardize.py still classifies fairs ("... PNACAC College
              Fair") from the title, as for every other university.
Times, street addresses, contacts and notes are not needed and are skipped.

The original files are never changed. Put them, as received, in
    data/raw/visits/montana_state/          (subfolders are fine)
and run from the project folder:
    python3 code/prep_montana_state.py
It writes data/raw/visits/montana_state.csv (read by ./run.sh through config.py) and lists
every file it could not read, so nothing is dropped silently. Stops after July 2026 are
kept here; the regression drops them by cycle.

Needs: pip install python-docx pdfplumber beautifulsoup4
"""
import re
import shutil
import statistics
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import docx
import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

import config

RAW = config.VISITS_DIR / "montana_state"           # FOIA files, as received
OUT = config.VISITS_DIR / "montana_state.csv"
FIRST, LAST = date(2021, 8, 1), date(2027, 7, 31)    # window in which weekday -> year is unique
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# A day heading: "Monday, October 5", "Saturday, April 18th" or "June 7th, 2025"
DAY = re.compile(r"^\s*((" + "|".join(WEEKDAYS) + r"),?\s+)?(" + "|".join(MONTHS) + r")\.?\s+\d", re.I)
TIME = re.compile(r"^(tbd|\d{1,2}(:\d\d)?(am|pm)?|am|pm|-|–|to)$", re.I)   # "9:00", "AM", "-"
STATES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
          "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
          "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
          "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
          "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
          "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
          "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND",
          "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
          "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
          "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
          "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"}


STATE = "|".join(sorted(STATES, key=len, reverse=True)) + "|" + "|".join(STATES.values())
PLACE = [re.compile(r"^\s*([^,\d]+),\s*(" + STATE + r")\.?,?\s*(\d{4,5})?(-\d{4})?\s*$", re.I),
         re.compile(r"^\s*([^,\d]+?)\s+(" + STATE + r")\.?,?\s+(\d{5})(-\d{4})?\s*$", re.I)]  # no comma


def place(text):
    """'Boulder, MT 59632', 'Fromberg, Montana 59029', 'Columbus OH 43210', 'ROBERTS MT, 59070'
    -> ('Boulder', 'MT', '59632'); anything else -> None."""
    m = PLACE[0].match(text) or PLACE[1].match(text)
    if not m or (len(m.group(2)) == 2 and m.group(2).islower()):       # "in", "or" are not states
        return None
    st = m.group(2).upper() if len(m.group(2)) == 2 else STATES[m.group(2).lower()]
    zip5 = m.group(3) if m.group(3) and len(m.group(3)) == 5 else ""   # a 4-digit typo is dropped
    return m.group(1).strip(), st, zip5


def year_hint(text):
    """A year mentioned in a file name: "2021", "S22", "F23" (spring/fall)."""
    m = re.search(r"(20[2-3]\d)", text) or re.search(r"(?<![a-z])[sf](2\d)\b", text, re.I)
    return int(m.group(1)) if m and len(m.group(1)) == 4 else (2000 + int(m.group(1)) if m else None)


def event_date(text, hint):
    """'Saturday, October 9' -> date: the year in the text if any, else the one year in the
    window whose calendar matches the weekday, else the year from the file name."""
    m = re.search(r"(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:\D+(20\d\d))?", text.lower())
    if not m:
        return None
    month, day = MONTHS[m.group(1)], int(m.group(2))
    if m.group(3):
        return date(int(m.group(3)), month, day)
    weekday = next((i for i, w in enumerate(WEEKDAYS) if w in text.lower()), None)
    options = [date(y, month, day) for y in range(FIRST.year, LAST.year + 1)
               if FIRST <= date(y, month, day) <= LAST]
    if weekday is not None:
        options = [d for d in options if d.weekday() == weekday]
    elif hint:
        options = [d for d in options if d.year == hint]
    return options[0] if len(options) == 1 else None


def row(path, day, title, where):
    return {"date": day, "title": title, "city_state": f"{where[0]}, {where[1]}", "zip": where[2],
            "event_type": "School Visit", "source_file": path.name}


# ---- Word documents: read the schedule table cell by cell -------------------------------------
def word_tables(path, tmp):
    """The tables of a Word file as lists of rows of cell texts (lines joined by newlines).
    .docx is read directly; an old .doc is converted to HTML by macOS's textutil (which keeps
    tables), or to .docx by LibreOffice where textutil does not exist."""
    if path.suffix.lower() == ".docx":
        return [[[c.text for c in r.cells] for r in t.rows] for t in docx.Document(path).tables]
    if shutil.which("textutil"):
        html = subprocess.run(["textutil", "-convert", "html", "-stdout", str(path)],
                              check=True, capture_output=True).stdout.decode("utf-8", "ignore")
        soup = BeautifulSoup(html, "html.parser")
        return [[[td.get_text("\n") for td in tr.find_all(["td", "th"])] for tr in t.find_all("tr")]
                for t in soup.find_all("table")]
    subprocess.run(["soffice", "--headless", "--convert-to", "docx", "--outdir", tmp, str(path)],
                   check=True, capture_output=True)
    return word_tables(Path(tmp) / (path.stem + ".docx"), tmp)


def read_text(path, lines):
    """Fallback for a Word file whose table did not come through: the same reading as for
    PDFs, on its plain text (one cell line per text line): a day heading sets the day, the
    next name opens a stop, the next "City, ST" closes it."""
    hint, rows, day, title = year_hint(path.name), [], None, None
    for t in (x.strip() for x in lines):
        if DAY.match(t):
            day, title = event_date(t, hint), None
        elif day is None or not t:
            continue
        elif place(t) and title:
            rows.append(row(path, day, title, place(t)))
            title = None
        elif title is None and re.match(r"[A-Za-z]", t) and "@" not in t \
                and not re.match(r"(fair hours|contact|main counselor|phone|tbd)", t, re.I):
            title = t                                                  # name of the next stop
    return rows


def read_word(path, tmp):
    """Stops from the table whose header starts with "Day" or "Date" (or, if no such table
    came through the conversion, from the file's plain text)."""
    hint, rows = year_hint(path.name), []
    for table in word_tables(path, tmp):
        head = [c.strip().lower() for c in table[0]] if table else []
        if not head or not re.match(r"(day|date)", head[0]):
            continue                                                   # e.g. the poster list
        loc = next((i for i, c in enumerate(head) if "location" in c or "school" in c), 2)
        day = None
        for cells in table[1:]:
            if len(cells) <= loc:
                continue
            if cells[0].strip():                                       # blank = same day as above
                day = event_date(cells[0], hint) or day
            lines = [x.strip() for x in cells[loc].splitlines() if x.strip()]
            where = next((place(x) for x in reversed(lines) if place(x)), None)
            if lines and where:
                rows.append(row(path, day, lines[0], where))
    if not rows and path.suffix.lower() == ".doc" and shutil.which("textutil"):
        text = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                              check=True, capture_output=True).stdout.decode("utf-8", "ignore")
        rows = read_text(path, text.splitlines())
    return rows


# ---- PDFs: split each line into a name column and an address column --------------------------
def pdf_lines(page):
    """Words of a page grouped into lines (tops within 4 points, so a raised "20th" stays on
    its line), each line left to right."""
    lines = []
    for w in sorted(page.extract_words(), key=lambda w: w["top"]):
        if lines and abs(w["top"] - lines[-1][0]) <= 4:
            lines[-1][1].append(w)
        else:
            lines.append((w["top"], [w]))
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in lines]


def address_column(lines):
    """Where the address column starts on a page: the left edge of its "City, ST" entries.
    On a line holding both a name and a city ("Boise State University   Boise, ID 83725"),
    the city starts after a wide gap (> 10 points) between words."""
    starts = []
    for ws in lines:
        cands = [i for i in range(len(ws)) if place(" ".join(w["text"] for w in ws[i:]))]
        gap = {i: ws[i]["x0"] - ws[i - 1]["x1"] for i in cands if i}
        wide = max(gap, key=gap.get) if gap and max(gap.values()) > 10 else None
        if wide or 0 in cands:
            starts.append(ws[wide or 0]["x0"])
    return statistics.median(starts) if starts else None


def read_pdf(path):
    """A weekday line sets the day; the first name (left column) after it opens a stop and the
    next "City, ST" (right column) closes it."""
    hint, rows, day, title = year_hint(path.name), [], None, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = pdf_lines(page)
            x = address_column(lines)
            for ws in lines:
                text = " ".join(w["text"] for w in ws)
                if DAY.match(text):
                    day, title = event_date(text, hint), None
                    continue
                if day is None or x is None:
                    continue                                           # title block above the days
                left = [w["text"] for w in ws if w["x0"] < x - 3]
                right = " ".join(w["text"] for w in ws if w["x0"] >= x - 3)
                while left and TIME.match(left[0]):                    # drop the time
                    left.pop(0)
                name = " ".join(left)
                if title is None and re.match(r"[A-Za-z]", name) and not re.match(r"fair hours", name, re.I):
                    title = name                                       # first line of a new stop
                if place(right) and title:
                    rows.append(row(path, day, title, place(right)))
                    title = None
    return rows


if __name__ == "__main__":
    files = sorted(p for p in RAW.rglob("*") if p.suffix.lower() in (".doc", ".docx", ".pdf")
                   and not p.name.startswith(("~$", "._")))            # skip Word/Mac helper files
    rows, problems = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            try:
                found = read_pdf(f) if f.suffix.lower() == ".pdf" else read_word(f, tmp)
            except Exception as e:                                     # unreadable file: report it
                problems.append(f"{f.name}: {e}")
                continue
            if not found:
                problems.append(f"{f.name}: no stops found")
            elif any(r["date"] is None for r in found):
                problems.append(f"{f.name}: some dates could not be read")
            rows += found
    out = pd.DataFrame(rows, columns=["date", "title", "city_state", "zip", "event_type", "source_file"])
    out = out.dropna(subset=["date"]).drop_duplicates().sort_values(["date", "title"])
    out.to_csv(OUT, index=False)

    cycle = pd.to_datetime(out["date"]).map(lambda d: d.year if d.month >= 8 else d.year - 1)
    print(f"Read {len(files)} files -> {len(out)} stops in {OUT.relative_to(config.ROOT)}")
    print("Stops per cycle (2021 = 2021-22):", cycle.value_counts().sort_index().to_dict())
    print(f"{len(problems)} files to check:" if problems else "All files read.")
    for p in problems:
        print("  check:", p)
