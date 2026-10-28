"""Step 3 of scraping: check the scraper against records you already have.

CU Boulder's public-records file is a full list of its visits, so it is the yardstick.
After running the scraper for cu_boulder (data/raw/visits/cu_boulder_scraped.csv),
this script runs the scraped events through the same cleaning and school matching
as the records, then reports by recruitment cycle:

  records_visits   eligible high-school visits in the records
  scraped_visits   eligible high-school visits the scraper found
  recall           share of record visits that the scraper also found (same school, same date)
  y50_records      share of record visits going to >50% URM high schools
  y50_scraped      the same share computed from scraped visits only

What matters for the paper is not that recall is 100% (Salazar, Jaquette and Han's
scraped data also missed events) but that y50_scraped tracks y50_records: if the
scraper misses visits at random with respect to school demographics, the share is
still measured correctly. A gap between the two columns, or recall that differs a lot
between pre and post cycles, is a warning sign to report.

Must run after `bash run.sh` (it uses data/derived/visits_clean.csv and high_schools.csv).

Usage:  python code/scrape_validate.py              (cu_boulder)
        python code/scrape_validate.py <univ_id>    (any university with both files)
"""

import sys

import pandas as pd

import build_panel
import config
from standardize import standardize_one


def main():
    univ = sys.argv[1] if len(sys.argv) > 1 else "cu_boulder"
    scraped_file = config.VISITS_DIR / f"{univ}_scraped.csv"
    if not scraped_file.exists():
        sys.exit(f"{scraped_file.relative_to(config.ROOT)} not found; run code/scrape_events.py {univ} first.")
    if not config.VISITS_CLEAN.exists():
        sys.exit("Run `bash run.sh` first (needs data/derived/visits_clean.csv).")

    spec = {"file": scraped_file.name, "date": "date", "date_format": "%Y-%m-%d", "title": "title",
            "city_state": "city_state", "event_type": "event_type"}
    s = standardize_one(univ, spec)
    s = build_panel.add_timing(s)
    s["eligible"] = s["category"].isin(config.ELIGIBLE_CATEGORIES)
    s["eligible_alt"] = s["category"].isin(config.ALT_ELIGIBLE_CATEGORIES)

    unis = pd.read_csv(config.UNIVERSITIES)
    config.UNMATCHED = config.OUTPUT / f"scrape_unmatched_{univ}.csv"    # keep the main list intact
    s = build_panel.match_schools(s, unis)

    rec = pd.read_csv(config.VISITS_CLEAN, dtype={"nces_id": str}, parse_dates=["date"])
    rec = rec[(rec["univ_id"] == univ) & rec["eligible"]]
    s = s[s["eligible"]].copy()
    if rec.empty:
        sys.exit(f"No record visits for {univ} in visits_clean.csv.")

    def key(df):
        school = df["nces_id"].fillna("name:" + df["school_name"].fillna("").str.lower().str.replace(r"\W", "", regex=True))
        return df["date"].dt.date.astype(str) + "|" + school

    rec["key"], s["key"] = key(rec), key(s)
    rec["found"] = rec["key"].isin(set(s["key"]))
    thr = config.URM_THRESHOLD

    rows = []
    for c in range(config.FIRST_CYCLE, config.LAST_CYCLE + 1):
        r, x = rec[rec["cycle"] == c], s[s["cycle"] == c]
        rm, xm = r[r["urm_share"].notna()], x[x["urm_share"].notna()]
        rows.append({"cycle": f"{c}-{str(c + 1)[-2:]}", "records_visits": len(r), "scraped_visits": len(x),
                     "recall": r["found"].mean() if len(r) else None,
                     "y50_records": (rm["urm_share"] > thr).mean() if len(rm) else None,
                     "y50_scraped": (xm["urm_share"] > thr).mean() if len(xm) else None})
    out = pd.DataFrame(rows)
    out.to_csv(config.SCRAPE_VALIDATION.with_name(f"scrape_validation_{univ}.csv"), index=False)
    print(out.round(3).to_string(index=False))
    print(f"\nScraped visits not in the records (possible extra or mis-dated events): "
          f"{(~s['key'].isin(set(rec['key']))).sum():,} of {len(s):,}")


if __name__ == "__main__":
    main()
