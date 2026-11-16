"""export.py: hand the event data to the regression code, for every university at once.

Two sources of advertised recruiting events are combined:
  1. our own scraper:            scraper/output/events.csv   (made by harvest.py)
  2. Professor Cohen's package:  data/raw/college-recruitment-data/data/events.csv
A university found in both gets the events of both, with identical events (same date and
same title) kept once.

Then:
  * Only universities with events both before SFFA (2021-22 or 2022-23 cycle) and after it
    (2023-24 to 2025-26) are exported: the others can't help a before/after comparison.
  * One file per university is written to data/raw/visits/<univ>_scraped.csv (code/config.py
    picks these up automatically); old files of universities that no longer qualify are deleted.
  * data/raw/universities.csv gets any new university, and `exposed` is set for every
    university from one rule (the control group definition below).
"""
import re
from pathlib import Path

import pandas as pd

SCRAPER = Path(__file__).resolve().parent
RAW = SCRAPER.parent / "data" / "raw"
VISITS = RAW / "visits"                                  # where the regression looks for files
UNIVERSITIES = RAW / "universities.csv"
PACKAGE = RAW / "college-recruitment-data"               # Professor Cohen's data package
INCLUDE_ONLINE = False   # virtual visits don't send a recruiter to the school: left out
# Our calendars give no event type. A title that is a school's name ("Centennial High
# School") is a school visit; standardize.py still recognizes fairs from their titles first.
SCHOOL = re.compile(r"high school|\bhs\b|\bhigh\b|academy|school|prep\b|preparatory|"
                    r"collegiate|secondary", re.I)

# ---- Control group: universities that did NOT use race in admissions before SFFA ----------
# (a) Public universities in states that banned race-conscious admissions before 2023
#     (Bloem et al., footnote 19).
BAN_STATES = {"AZ", "CA", "FL", "ID", "MI", "NE", "NH", "OK", "WA"}
# (b) Universities that had ended race-conscious admissions themselves, with the evidence.
INSTITUTION_BANS = {
    "uga": "Johnson v. Board of Regents (11th Cir. 2001) struck down UGA's race-conscious "
           "policy; UGA's 2022-23 Common Data Set (C7) reports race not considered",
    "ipeds_139940": "Georgia State: race not considered before SFFA per Prof. Cohen's source "
                    "-- TO VERIFY in its 2022-23 Common Data Set, item C7",
}
# Package colleges whose collected pages cover different territories in different years, so
# their before/after counts aren't comparable (see SAMPLE_NOTES.md in the package).
EXCLUDE = {"ipeds_180461": "Montana State: regional itineraries differ across years",
           "ipeds_196024": "SUNY Delhi: pre and post schedules cover different staff/regions",
           "cu_boulder": "CU Boulder comes from the records request, never from scraping"}
# Package ids of universities our own scraper also covers -> our ids, so they are merged.
SAME_UNIVERSITY = {"ipeds_139959": "uga", "ipeds_110635": "berkeley", "ipeds_142285": "uidaho",
                   "ipeds_170976": "umich", "ipeds_199193": "ncsu", "ipeds_201885": "cincinnati"}

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


def scraped_events():
    """Our scraper's events, in the export format."""
    ev = pd.read_csv(SCRAPER / "output" / "events.csv", dtype=str).fillna("")
    if not INCLUDE_ONLINE:
        ev = ev[ev["group"] != "Online"]
    return pd.DataFrame({
        "univ_id": ev["univ_id"], "date": ev["date"], "title": ev["title"],
        "city_state": [city_state(l, g) for l, g in zip(ev["location"], ev["group"])],
        "zip": "",                              # the pages don't show ZIP codes
        "event_type": ["School Visit" if SCHOOL.search(t) else "" for t in ev["title"]],
        "source": "own scraper"})


def package_events():
    """Professor Cohen's events: school visits and college fairs that aren't virtual
    (his `first_year_candidate == 1`), in the export format."""
    if not (PACKAGE / "data" / "events.csv").exists():
        print(f"(No package found at {PACKAGE}; using our scraper only.)")
        return pd.DataFrame()
    ev = pd.read_csv(PACKAGE / "data" / "events.csv", dtype=str).fillna("")
    ev = ev[ev["first_year_candidate"] == "1"]
    city = ev["destination_city"].str.strip()
    state = ev["destination_state"].str.strip()
    return pd.DataFrame({
        "univ_id": ("ipeds_" + ev["unitid"]).replace(SAME_UNIVERSITY),
        "date": ev["event_date"], "title": ev["title"],
        "city_state": [f"{c}, {s}" if c and s else (f", {s}" if s else "")
                       for c, s in zip(city, state)],
        "zip": ev["postal_code"].str[:5],
        # His labels, worded so standardize.py reads them ("visit" -> hs_visit)
        "event_type": ev["event_type"].map({"school_visit": "School Visit",
                                            "college_fair": "College Fair"}).fillna(""),
        "source": "professor package"})


def names():
    """univ_id -> (name, state), from the package's colleges.csv and our calendars.csv."""
    out = {}
    if (PACKAGE / "data" / "colleges.csv").exists():
        for r in pd.read_csv(PACKAGE / "data" / "colleges.csv", dtype=str).itertuples():
            out[SAME_UNIVERSITY.get(r.univ_id, r.univ_id)] = (r.university, r.institution_state)
    for r in pd.read_csv(SCRAPER / "calendars.csv", dtype=str).itertuples():
        out[r.univ_id] = (r.name, r.state)
    return out


def exposed(univ, state):
    """0 = control (no race-conscious admissions before SFFA), 1 = exposed to SFFA."""
    return "0" if state in BAN_STATES or univ in INSTITUTION_BANS else "1"


if __name__ == "__main__":
    events = pd.concat([scraped_events(), package_events()], ignore_index=True)
    events = events[~events["univ_id"].isin(EXCLUDE)]
    # The same event found by both sources (same university, date and title) is kept once.
    key = events["title"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    events = events[~pd.DataFrame({"u": events["univ_id"], "d": events["date"], "k": key})
                    .duplicated()]

    # Keep universities seen both before and after SFFA. Cycle = start year of Aug-Jul.
    d = pd.to_datetime(events["date"])
    cycle = d.dt.year.where(d.dt.month >= 8, d.dt.year - 1)
    pre = set(events.loc[cycle.between(2021, 2022), "univ_id"])
    # "After" = the cycles the regression uses (2023-24 to 2025-26), as in code/config.py.
    post = set(events.loc[cycle.between(2023, 2025), "univ_id"])
    keep = pre & post
    skipped = sorted(set(events["univ_id"]) - keep)
    print("Not exported (no events before AND after SFFA):", ", ".join(skipped) or "-")
    VISITS.mkdir(parents=True, exist_ok=True)
    for univ in skipped:                     # remove files left over from earlier runs
        (VISITS / f"{univ}_scraped.csv").unlink(missing_ok=True)

    lookup = names()
    for univ, ev in events[events["univ_id"].isin(keep)].sort_values("date").groupby("univ_id"):
        ev.drop(columns=["univ_id", "source"]).to_csv(VISITS / f"{univ}_scraped.csv", index=False)
        state = lookup.get(univ, ("", ""))[1]
        group = "control" if exposed(univ, state) == "0" else "exposed"
        print(f"Wrote {univ}_scraped.csv: {len(ev)} events ({group}; "
              f"{' + '.join(sorted(ev['source'].unique()))})")

    # universities.csv: add new universities, then set `exposed` for all from one rule.
    unis = pd.read_csv(UNIVERSITIES, dtype=str)
    new = sorted(keep - set(unis["univ_id"]))
    rows = pd.DataFrame({"univ_id": new,
                         "name": [lookup.get(u, ("", ""))[0] for u in new],
                         "state": [lookup.get(u, ("", ""))[1] for u in new],
                         "complete_records": "0"})   # a calendar shows only what was advertised
    unis = pd.concat([unis, rows], ignore_index=True)
    unis["exposed"] = [exposed(u, s) for u, s in zip(unis["univ_id"], unis["state"])]
    unis.to_csv(UNIVERSITIES, index=False)
    if new:
        print("Added to universities.csv:", ", ".join(new))
    for univ, why in INSTITUTION_BANS.items():
        if univ in set(unis["univ_id"]):
            print(f"Control by institution-level ban: {univ} -- {why}")
