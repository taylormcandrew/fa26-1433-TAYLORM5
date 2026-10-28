"""Put every university's raw records into one common format.

Records offices export different spreadsheets. This script never edits the raw
files. It reads each one using its entry in config.VISIT_FILES and produces
one row per event with the same columns for every university:

    univ_id, date, title, school_name, city, state, zip, nces_id, event_type, category

`category` comes from rules in config.EVENT_RULES applied to the event title,
so that, for example, a "College Fair" row titled "Erie High School Virtual
Visit" is still treated as a school visit, and a "High School Visit" row titled
"Cheyenne Mountain Admitted Student 1:1s" is not.

Outputs
  data/derived/visits_standardized.csv
  output/event_categories.csv   every distinct title with its category, to audit by eye
"""

import re
import sys

import pandas as pd

import config

OUT_COLS = ["univ_id", "date", "title", "school_name", "city", "state", "zip",
            "nces_id", "event_type", "category"]


def read_raw(path, spec):
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=spec.get("sheet") or 0, dtype=str,
                             header=spec.get("header_row", 0))
    return pd.read_csv(path, dtype=str, header=spec.get("header_row", 0))


def col(raw, spec, key):
    """Return the raw column named in spec[key], or an empty column if not given."""
    name = spec.get(key)
    if not name:
        return pd.Series(pd.NA, index=raw.index, dtype="string")
    if name not in raw.columns:
        sys.exit(f"Column '{name}' (for '{key}') is not in the file. Columns are: {list(raw.columns)}. "
                 f"Fix VISIT_FILES in code/config.py.")
    return raw[name].astype("string").str.strip()


def split_city_state(s):
    """'Hghlnds Ranch, CO' -> ('Hghlnds Ranch', 'CO')."""
    parts = s.str.rsplit(",", n=1, expand=True)
    if parts.shape[1] < 2:
        return parts[0], pd.Series(pd.NA, index=s.index, dtype="string")
    return parts[0].str.strip(), parts[1].str.strip().str.upper()


def classify(title, event_type):
    """First matching rule in config.EVENT_RULES wins; otherwise fall back on the event type."""
    t = "" if pd.isna(title) else str(title).lower()
    for category, pattern in config.EVENT_RULES:
        if re.search(pattern, t):
            return category
    et = "" if pd.isna(event_type) else str(event_type).lower().strip()
    if "visit" in et or re.search(config.VISIT_WORDS, t):
        return "hs_visit"
    # Scraped travel pages often list just the school ("Loveland High School") with no
    # event type; with no type to go on, a bare school name is treated as a school visit.
    if not et and re.search(config.SCHOOL_NAME_WORDS, t):
        return "hs_visit"
    return "other"


def school_from_title(title):
    """Strip event words from a title to leave the school name:
    'Charlotte Christian HS visit / Materials drop-off' -> 'Charlotte Christian HS'."""
    if pd.isna(title):
        return pd.NA
    s = str(title).strip()
    for pat in config.TITLE_PREFIXES:
        s = re.sub(pat, "", s, flags=re.I).strip()
    changed = True
    while changed and s:
        before = s
        for pat in config.TITLE_SUFFIXES:
            s = re.sub(pat, "", s, flags=re.I).strip(" -/:,")
        changed = s != before
    return s or pd.NA


def standardize_one(univ_id, spec):
    path = config.VISITS_DIR / spec["file"]
    if not path.exists():
        print(f"  skip {univ_id}: {path.relative_to(config.ROOT)} not found")
        return None
    raw = read_raw(path, spec)

    out = pd.DataFrame(index=raw.index)
    out["univ_id"] = univ_id
    out["date"] = pd.to_datetime(col(raw, spec, "date"), format=spec.get("date_format"), errors="coerce")
    out["title"] = col(raw, spec, "title")
    out["event_type"] = col(raw, spec, "event_type")
    out["nces_id"] = col(raw, spec, "nces_id")
    out["zip"] = col(raw, spec, "zip").str.extract(r"(\d{5})", expand=False)

    if spec.get("city_state"):
        out["city"], out["state"] = split_city_state(col(raw, spec, "city_state"))
    else:
        out["city"], out["state"] = col(raw, spec, "city"), col(raw, spec, "state").str.upper()

    if spec.get("school_name"):
        out["school_name"] = col(raw, spec, "school_name")
        out["title"] = out["title"].fillna(out["school_name"])
    else:
        out["school_name"] = out["title"].map(school_from_title)

    out["category"] = [classify(t, e) for t, e in zip(out["title"], out["event_type"])]

    bad = out["date"].isna().sum()
    if bad:
        print(f"  {univ_id}: {bad} rows with unreadable dates dropped")
    out = out.dropna(subset=["date"])
    counts = out["category"].value_counts().to_dict()
    print(f"  {univ_id}: {len(out):,} events  {counts}")
    return out[OUT_COLS]


def main():
    frames = [standardize_one(u, s) for u, s in config.VISIT_FILES.items()]
    frames = [f for f in frames if f is not None]
    if not frames:
        sys.exit("No visit files found. Put each university's file in data/raw/visits/ "
                 "and describe it in VISIT_FILES in code/config.py.")
    v = pd.concat(frames, ignore_index=True)
    v.to_csv(config.VISITS_STANDARDIZED, index=False)

    audit = (v.groupby(["univ_id", "category", "event_type", "title", "school_name"], dropna=False)
             .size().rename("n").reset_index().sort_values(["univ_id", "category", "n"], ascending=[True, True, False]))
    audit.to_csv(config.EVENT_AUDIT, index=False)
    print(f"Wrote {config.VISITS_STANDARDIZED.relative_to(config.ROOT)}; "
          f"check categories in {config.EVENT_AUDIT.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
