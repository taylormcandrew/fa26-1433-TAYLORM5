"""compare_cu_map.py: do the places on CU Boulder's public calendar look like the schools CU
actually visited?

CU's archived calendar page (ugrad.apply.colorado.edu/portal/upcoming-off-campus-events) only
saved a MAP of upcoming events: a pin (latitude, longitude) per event, without names or dates.
Professor Cohen's package extracted those pins (data/raw/college-recruitment-data/data/
cu_boulder_locations.csv, saved Oct 2021 - Nov 2022, i.e. before SFFA). This script:

  1. gives each high school a location (NCES latitude/longitude),
  2. links each distinct calendar pin to the nearest high school within MAX_KM,
  3. compares the URM composition of those schools with the schools in CU's records request
     visited over the same months, and reports how many visited schools had a pin nearby.

Pins that appear in several saved copies are counted once per cycle (they are the same
advertised event, not repeat visits).

Needs: data/raw/nces/elsi_public_coords_2021_22.csv, a small ElSi export (Public School,
2021-22) with columns School ID (12-digit), Latitude, Longitude. Private schools' locations
come from the PSS file already in data/raw/nces.

Writes validation/output/validation_cu_map.csv and .html.
Run from the project folder after ./run.sh:   python3 validation/compare_cu_map.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "code"))        # borrow the regression code's settings
import config                                        # noqa: E402

OUT = HERE / "output"
PINS = config.RAW / "college-recruitment-data" / "data" / "cu_boulder_locations.csv"
PUBLIC_COORDS = config.RAW / "nces" / "elsi_public_coords_2021_22.csv"
PRIVATE = config.RAW / "nces" / "pss2122_pu.csv"
MAX_KM = 1.0              # a pin counts as a school if a high school is within 1 km
T = config.URM_THRESHOLD


def km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (works on whole arrays at once)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def cycle(d):
    return d.dt.year.where(d.dt.month >= 8, d.dt.year - 1)          # Aug-Jul, labeled by start


# ---- 1. High schools with their URM share and location ------------------------------------
hs = pd.read_csv(config.HIGH_SCHOOLS, dtype={"nces_id": str})
lines = PUBLIC_COORDS.read_text(encoding="utf-8-sig").splitlines()
header = next(i for i, line in enumerate(lines) if "School ID" in line)   # skip ElSi title lines
pub = pd.read_csv(PUBLIC_COORDS, skiprows=header, dtype=str, encoding="utf-8-sig")
col = lambda start: next(c for c in pub.columns if c.startswith(start))
pub = pd.DataFrame({"nces_id": pub[col("School ID (12-digit)")].str.strip(),
                    "lat": pd.to_numeric(pub[col("Latitude")], errors="coerce"),
                    "lon": pd.to_numeric(pub[col("Longitude")], errors="coerce")})
pss = pd.read_csv(PRIVATE, dtype=str, usecols=["PPIN", "LATITUDE22", "LONGITUDE22"])
pss = pd.DataFrame({"nces_id": "PSS_" + pss["PPIN"].str.strip(),
                    "lat": pd.to_numeric(pss["LATITUDE22"], errors="coerce"),
                    "lon": pd.to_numeric(pss["LONGITUDE22"], errors="coerce")})
hs = hs.merge(pd.concat([pub, pss]).dropna(), on="nces_id")           # schools with a location

# ---- 2. Calendar pins -> nearest high school ----------------------------------------------
pins = pd.read_csv(PINS, parse_dates=["capture_time_utc"])
pins["cycle"] = cycle(pins["capture_time_utc"].dt.tz_localize(None))
pins = pins.drop_duplicates(["cycle", "latitude", "longitude"])      # one per pin per cycle
lat, lon = hs["lat"].to_numpy(), hs["lon"].to_numpy()
dist, ids = [], []
for r in pins.itertuples():                   # one pin at a time, keeping only the nearest school
    d = km(r.latitude, r.longitude, lat, lon)
    dist.append(d.min())
    ids.append(hs["nces_id"].iat[d.argmin()])
pins["dist_km"], pins["nces_id"] = dist, ids
pins = pins.merge(hs[["nces_id", "urm_share"]], on="nces_id", how="left")
pins.loc[pins["dist_km"] > MAX_KM, "urm_share"] = np.nan              # not at a high school

# ---- 3. Records-request CU visits in the same months --------------------------------------
cap = pins.groupby("cycle")["capture_time_utc"].agg(["min", "max"])
v = pd.read_csv(config.VISITS_CLEAN, low_memory=False, parse_dates=["date"], dtype={"nces_id": str})
v = v[(v["univ_id"] == "cu_boulder") & v["eligible"]]
v["cycle"] = cycle(v["date"])
# A saved map shows upcoming events, so use each cycle's first save to 60 days after its last.
inside = [c in cap.index and cap.at[c, "min"].tz_localize(None) <= d
          <= cap.at[c, "max"].tz_localize(None) + pd.Timedelta(days=60)
          for c, d in zip(v["cycle"], v["date"])]
v = v[inside]
m = v[v["matched"]].merge(hs[["nces_id", "lat", "lon"]], on="nces_id", how="left")


def row(label, urm, n_all):
    urm = urm.dropna()
    return {"Source": label, "Observations": n_all, "Linked to a high school": len(urm),
            "Mean URM share": round(urm.mean(), 3), "Median URM share": round(urm.median(), 3),
            "Share to >50% URM": round((urm > T).mean(), 3)}


table = pd.DataFrame([row("Records request: school visits", m["urm_share"], len(v)),
                      row("Public calendar map: event pins", pins["urm_share"], len(pins))])

# Overlap: visited schools (with a location) that had a calendar pin within MAX_KM
schools = m.dropna(subset=["lat"]).drop_duplicates("nces_id")
pinned = [(km(s.lat, s.lon, pins["latitude"].to_numpy(), pins["longitude"].to_numpy()) <= MAX_KM).any()
          for s in schools.itertuples()]


def gap(a, b, f=lambda x: x):
    """Difference in means (b - a) with a 95% confidence interval: mean +/- 1.96 x SE."""
    a, b = f(a.dropna()).astype(float), f(b.dropna()).astype(float)
    d = b.mean() - a.mean()
    se = (a.var() / len(a) + b.var() / len(b)) ** 0.5
    return f"{d:+.3f} [{d - 1.96 * se:+.3f}, {d + 1.96 * se:+.3f}]"


# Third row: the difference between the two sources, with its 95% confidence interval
table.loc[len(table)] = {"Source": "Difference (calendar minus records), 95% CI",
                         "Mean URM share": gap(m["urm_share"], pins["urm_share"]),
                         "Share to >50% URM": gap(m["urm_share"], pins["urm_share"], lambda x: x > T)}
months = "; ".join(f"{a:%b %Y} to {b:%b %Y}" for a, b in zip(cap["min"], cap["max"]))
note = (f"Notes: University of Colorado Boulder, before SFFA. Calendar pins come from archived "
        f"copies of CU's public event map saved {months}; each distinct pin is counted once per "
        f"cycle and linked to the nearest NCES high school within {MAX_KM:g} km. Records-request "
        f"school visits are restricted to the same period (to 60 days after the last saved "
        f"copy). {sum(pinned)} of {len(pinned)} distinct schools CU visited "
        f"({sum(pinned) / max(len(pinned), 1):.0%}) had a calendar pin within {MAX_KM:g} km. "
        f"Confidence intervals: difference in means +/- 1.96 standard errors; the two sources "
        f"share many schools, so they are not independent samples and the intervals are approximate.")

OUT.mkdir(exist_ok=True)
table.to_csv(OUT / "validation_cu_map.csv", index=False)
style = ("body{font-family:Georgia,serif;max-width:1000px;margin:2em auto}"
         "table{border-collapse:collapse;font-size:14px}th,td{padding:4px 10px;"
         "border-bottom:1px solid #ccc;text-align:right}th:first-child,td:first-child"
         "{text-align:left}th{border-bottom:2px solid #000}p{font-size:12px;color:#444}")
(OUT / "validation_cu_map.html").write_text(
    f"<html><head><meta charset='utf-8'><style>{style}</style></head><body>"
    f"<h3>Table 4. CU Boulder's public calendar vs. its records request</h3>"
    f"{table.to_html(index=False, na_rep='')}<p>{note}</p></body></html>", encoding="utf-8")
print(table.to_string(index=False, na_rep=""))
print("\n" + note + "\nSaved validation/output/validation_cu_map.csv and .html")
