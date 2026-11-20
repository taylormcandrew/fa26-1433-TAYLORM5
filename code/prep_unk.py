"""prep_unk.py: read the University of Nebraska at Kearney's scanned event report into a table.

UNK answered the public records request (NextRequest 26-667) with a 17-page PDF that is a
picture of a spreadsheet (no text layer), one row per event:

    Organization Event: Event Name | Start Date-Time | Event Type | City | State | Event Status
    Adams Central HSV              | 12/6/2022, 3:00 PM | High School Visit | Hastings | Ne | Attended

So the text has to be read with OCR (tesseract). For each page this script:
  1. renders the page at 300 dpi and erases the table's grid lines (full-width/height dark
     lines), which otherwise confuse the OCR;
  2. reads every word with its position (tesseract "tsv" output);
  3. puts each word in the column whose vertical grid line is to its left, and each line of
     words in one row; rows without a date (e.g. the header) are dropped.

The original PDF is never changed. Put it in data/raw/visits/ as unk.pdf and run from the
project folder:   python3 code/prep_unk.py   -> data/raw/visits/unk.csv
Needs the OCR programs (Mac: brew install tesseract poppler) and: pip install pillow
"""
import io
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

import config

PDF = config.VISITS_DIR / "unk.pdf"
OUT = config.VISITS_DIR / "unk.csv"
COLS = ["title", "date", "type", "city", "state", "status"]
DATE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")


def page_rows(png):
    """Rows of one page image as lists of 6 cell texts."""
    im = np.array(Image.open(png).convert("L"))
    dark = im < 200
    rows, cols = dark.mean(1) > 0.6, dark.mean(0) > 0.8         # grid lines
    im[rows, :], im[:, cols] = 255, 255                           # erase them
    edges = [x for x in np.where(cols)[0] if x > 5]               # vertical lines
    starts = [0] + [x for i, x in enumerate(edges) if i == 0 or x - edges[i - 1] > 5]
    clean = Path(png).with_suffix(".clean.png")
    Image.fromarray(im).save(clean)
    tsv = subprocess.run(["tesseract", str(clean), "-", "--psm", "6", "tsv"],
                         capture_output=True, text=True).stdout
    w = pd.read_csv(io.StringIO(tsv), sep="\t", quoting=3)
    w = w[w["conf"] > -1].dropna(subset=["text"])
    out = []
    for _, line in w.groupby(["block_num", "par_num", "line_num"]):
        cells = [""] * len(COLS)
        for text, x in zip(line["text"], line["left"]):
            i = min(sum(x >= s for s in starts) - 1, len(COLS) - 1)  # column of this word
            cells[i] = (cells[i] + " " + str(text)).strip()
        out.append(cells)
    return out


rows = []
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(["pdftoppm", "-r", "300", "-png", str(PDF), f"{tmp}/p"], check=True)
    for png in sorted(Path(tmp).glob("p-*.png")):
        rows += page_rows(png)

t = pd.DataFrame(rows, columns=COLS)
t["date"] = t["date"].str.extract(DATE, expand=False)            # keep the date, drop the time
t = t.dropna(subset=["date"])
t["date"] = pd.to_datetime(t["date"], format="%m/%d/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
t["state"] = t["state"].str.upper().str.replace(r"[^A-Z]", "", regex=True).str[:2]
t["state"] = t["state"].where(t["state"] != "", "NE")             # OCR sometimes misses "Ne"
t["status"] = t["status"].str.extract(r"(Attended|Cancel\w*|Pass)", flags=re.I, expand=False)
t = t.dropna(subset=["date"])
# School name: titles use "HSV" for "high school visit" ("Adams Central HSV"), so the school is
# the name before it plus "High School" (as NCES names most schools); other titles are kept as
# they are and cleaned like every other title by standardize.py.
t["school"] = t["title"].str.replace(r"\s*\bHSV\b.*$", " High School", regex=True)
t.to_csv(OUT, index=False)
print(f"Wrote {len(t):,} events to {OUT.relative_to(config.ROOT)} ({t['date'].min()} to {t['date'].max()})")
print(t["type"].value_counts().head(8).to_dict())
print(t["status"].value_counts(dropna=False).to_dict())
