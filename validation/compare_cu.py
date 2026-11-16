"""compare_cu.py: does a scraped calendar measure the same thing as the records request?

CU Boulder is the one university for which we have both:
  * its complete records-request data (all visits it made), and
  * its public event calendar, scraped by validation/scrape_cu.py (only visits it
    advertised and the archive happened to save).
Both are put through the same steps as the regression data (classify event, keep school
visits, match to NCES high schools), then compared over the same dates.

A calendar copy shows only UPCOMING events, so the scraped data can only "see" from its
first saved copy in a cycle to the last event it lists. The records-request visits are
restricted to those same windows, so both describe the same period.

Writes validation/output/validation_cu.csv and validation_cu.html (paste into the draft).
Run from the project folder after ./run.sh and validation/scrape_cu.py:
    python3 validation/compare_cu.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "code"))        # borrow the regression code's steps
import config                                        # noqa: E402
from build_panel import add_timing, match_schools                  # noqa: E402
from standardize import classify, school_from_title, split_city_state  # noqa: E402

SCRAPED = HERE / "output"                        # all validation files live here
T = config.URM_THRESHOLD

# ---- 1. Scraped CU calendar, put through the same steps as every other source -------------
s = pd.read_csv(SCRAPED / "cu_calendar_events.csv", dtype=str).fillna("")
s = s[s["group"] != "Online"].copy()
if s.empty:
    raise SystemExit("No scraped CU events yet: run validation/scrape_cu.py (the archive must be up).")
s["date"] = pd.to_datetime(s["date"])
s["city"], s["state"] = split_city_state(s["location"].astype("string"))
s["zip"], s["nces_id"] = pd.NA, pd.NA
s["school_name"] = s["title"].map(school_from_title)
s["event_type"] = "School Visit"          # titles are school names, as in export.py
s["category"] = [classify(t, e) for t, e in zip(s["title"], s["event_type"])]
s = add_timing(s)
s["eligible"] = s["category"].isin(config.ELIGIBLE_CATEGORIES)
s["eligible_alt"] = s["category"].isin(config.ALT_ELIGIBLE_CATEGORIES)
unis = pd.read_csv(config.UNIVERSITIES)
unis = pd.concat([unis, pd.DataFrame([{"univ_id": "cub_web", "state": "CO"}])])
config.UNMATCHED = SCRAPED / "validation_cu_unmatched.csv"   # don't overwrite the main list
s = match_schools(s, unis)

# ---- 2. The windows the calendar could see, per cycle -------------------------------------
cov = pd.read_csv(SCRAPED / "cu_calendar_coverage.csv", dtype=str)
cov = cov[cov["first_saved"].fillna("") != ""]
first = cov.groupby("year")["first_saved"].min()                    # first saved copy
last = s.groupby("cycle")["date"].max()                             # last event listed
windows = {int(y): (pd.Timestamp(d), last[int(y)]) for y, d in first.items() if int(y) in last}

# ---- 3. Records-request CU visits in the same windows -------------------------------------
f = pd.read_csv(config.VISITS_CLEAN, low_memory=False, parse_dates=["date"])
f = f[f["univ_id"] == "cu_boulder"]
inside = lambda d: pd.Series([any(a <= x <= b for a, b in windows.values()) for x in d], index=d.index)
f, s = f[inside(f["date"])], s[inside(s["date"])]


def describe(d, label):
    v = d[d["eligible"]]
    m = v[v["matched"]]
    return {"Source": label, "School visits": len(v), "Matched": len(m),
            "Match rate": round(len(m) / max(len(v), 1), 2),
            "Mean URM share": round(m["urm_share"].mean(), 3),
            "Median URM share": round(m["urm_share"].median(), 3),
            "Share to >50% URM": round((m["urm_share"] > T).mean(), 3)}


table = pd.DataFrame([describe(f, "Records request (all visits)"),
                      describe(s, "Scraped public calendar")])
# Overlap: the same school (NCES ID) on the same date in both sources
fk = set(zip(f.loc[f["eligible"] & f["matched"], "nces_id"], f.loc[f["eligible"] & f["matched"], "date"]))
sk = set(zip(s.loc[s["eligible"] & s["matched"], "nces_id"], s.loc[s["eligible"] & s["matched"], "date"]))
both = len(fk & sk)
overlap = (f"Of {len(fk)} matched records-request visits in these windows, {both} "
           f"({both / max(len(fk), 1):.0%}) also appear on the scraped calendar (same school, same "
           f"date); of {len(sk)} matched scraped visits, {both / max(len(sk), 1):.0%} appear in "
           f"the records request.")
span = "; ".join(f"{a:%b %d, %Y} to {b:%b %d, %Y}" for a, b in windows.values())

table.to_csv(SCRAPED / "validation_cu.csv", index=False)
note = (f"Notes: University of Colorado Boulder only. Both sources restricted to the dates the "
        f"archived calendar covers: {span}. School visits exclude fairs and virtual events; "
        f"both sources use the same event classification and NCES matching. {overlap}")
style = ("body{font-family:Georgia,serif;max-width:1000px;margin:2em auto}"
         "table{border-collapse:collapse;font-size:14px}th,td{padding:4px 10px;"
         "border-bottom:1px solid #ccc;text-align:right}th:first-child,td:first-child"
         "{text-align:left}th{border-bottom:2px solid #000}p{font-size:12px;color:#444}")
(SCRAPED / "validation_cu.html").write_text(
    f"<html><head><meta charset='utf-8'><style>{style}</style></head><body>"
    f"<h3>Table 4. Scraped calendar vs. records request, CU Boulder</h3>"
    f"{table.to_html(index=False)}<p>{note}</p></body></html>", encoding="utf-8")
print(table.to_string(index=False))
print("\n" + note + "\nSaved validation/output/validation_cu.csv and validation_cu.html")
