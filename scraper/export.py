"""export.py: hand the scraped events to the regression code, for every university at once.

1. Writes one file per university to data/raw/visits/<univ>_scraped.csv, all in the same
   format. code/config.py picks up every *_scraped.csv file automatically.
2. Adds any university that isn't there yet to data/raw/universities.csv, using the name
   and state from calendars.csv (rows already there are left as they are).
"""
import re
from pathlib import Path

import pandas as pd

SCRAPER = Path(__file__).resolve().parent
VISITS = SCRAPER.parent / "data" / "raw" / "visits"     # where the regression looks for files
UNIVERSITIES = SCRAPER.parent / "data" / "raw" / "universities.csv"
INCLUDE_ONLINE = False   # virtual visits don't send a recruiter to the school: left out
BAN_STATES = {"AZ", "CA", "FL", "GA", "ID", "MI", "NE", "NH", "OK", "WA"}  # control group
STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
          "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
          "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
          "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
          "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
          "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
          "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
          "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
          "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
          "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
          "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
          "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"}


def city_state(location, group):
    """'Roswell, GA' -> 'Roswell, GA'. If the location is only a venue name, use the state
    from the group heading ('United States—Georgia' -> ', GA'); the school is then matched
    by name within that state."""
    m = re.search(r"^(.*?), ([A-Z]{2})\b", str(location))
    if m:
        return f"{m.group(1)}, {m.group(2)}"
    state = next((abbr for name, abbr in STATES.items() if str(group).endswith(name)), "")
    return f", {state}" if state else ""


events = pd.read_csv(SCRAPER / "output" / "events.csv")
if not INCLUDE_ONLINE:
    events = events[events["group"] != "Online"]
VISITS.mkdir(parents=True, exist_ok=True)

# Keep universities seen both before and after SFFA. Cycle = start year of Aug-Jul.
d = pd.to_datetime(events["date"])
cycle = d.dt.year.where(d.dt.month >= 8, d.dt.year - 1)
pre = set(events.loc[cycle <= 2022, "univ_id"])
post = set(events.loc[cycle >= 2023, "univ_id"])
skipped = sorted(set(events["univ_id"]) - (pre & post))
if skipped:
    print("Not exported (no events before AND after SFFA):", ", ".join(skipped))
events = events[events["univ_id"].isin(pre & post)]

for univ, ev in events.sort_values("date").groupby("univ_id"):
    out = pd.DataFrame({
        "date": ev["date"],                     # YYYY-MM-DD
        "title": ev["title"],                   # school name / event name
        "city_state": [city_state(l, g) for l, g in zip(ev["location"], ev["group"])],
        "zip": "",                              # the pages don't show ZIP codes
        "event_type": "",                       # blank: standardize.py classifies from the title
    })
    path = VISITS / f"{univ}_scraped.csv"
    out.to_csv(path, index=False)
    print(f"Wrote {path.name}: {len(out)} events")

# Register new universities in universities.csv (the regression's list of universities).
calendars = pd.read_csv(SCRAPER / "calendars.csv", dtype=str).fillna("")
unis = pd.read_csv(UNIVERSITIES, dtype=str)
new = calendars[calendars["univ_id"].isin(events["univ_id"]) & ~calendars["univ_id"].isin(unis["univ_id"])]
rows = pd.DataFrame({
    "univ_id": new["univ_id"], "name": new["name"], "state": new["state"],
    "exposed": ["0" if s in BAN_STATES else "1" for s in new["state"]],  # 0 = control group
    "complete_records": "0",          # a scraped calendar only shows what was advertised
})
if len(rows):
    pd.concat([unis, rows]).to_csv(UNIVERSITIES, index=False)
    print(f"Added to universities.csv: {', '.join(rows['univ_id'])}")
