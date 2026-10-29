"""harvest.py: collect every event from every saved copy of each calendar, for each fall.

For each university and year: list the saved copies (captures.py), download each one
(fetch.py), read its events (parse.py), then combine them. For the current fall we also
read the live page as it is today, since the archive may not have saved it yet.
The same event appears in several copies, so we keep one row per event id (latest copy).

Writes two files in scraper/output/:
  events.csv    one row per event, Sep 1 - Nov 30 of each year from 2022 to now
  coverage.csv  one row per university x year: how many copies, which weeks we can see.
                A year with no copies is recorded as missing, never as zero events.
"""
from datetime import date
from pathlib import Path

import pandas as pd

from captures import captures, replay_url
from fetch import fetch
from parse import parse

# University id -> address of its event calendar. Add more universities here.
CALENDARS = {"uga": "https://apply.uga.edu/portal/fairs"}
# Calendars that now load events with JavaScript: the address the events actually come from
# (found with Chrome's Inspect -> Network panel). Used to read the current fall live.
WIDGETS = {"uga": "https://apply.uga.edu/portal/widget/event?portal_id=db46973a-0340-4bb1-af60-"
                  "04077af6167b&part=037772b5-699f-4ca9-ab0e-2eaaee828568&cmd=event_list"
                  "&group_by=country&query=&online=1"}
YEARS = range(2022, date.today().year + 1)           # every fall from 2022 (pre-SFFA) to now
OUT = Path(__file__).parent / "output"


def harvest(univ, page, year):
    """Events for one university and year, plus one coverage row describing what we saw."""
    stamps = captures(page, year)
    cover = {"univ_id": univ, "year": year, "page": page, "copies": 0, "failed": 0, "events": 0,
             "first_saved": "", "last_saved": "", "live": False}
    # Each copy = (when it was saved, where to download it from).
    copies = [(s, replay_url(page, s)) for s in stamps or []]
    if year == date.today().year:
        # This fall is happening now: also read the live page. The "#live-<date>" ending is
        # ignored by the website but gives today's copy its own cache file, so each day's
        # version is kept (a rerun tomorrow downloads it again; a rerun today does not).
        today = date.today().strftime("%Y%m%d")
        live = WIDGETS.get(univ, page)               # the widget if there is one, else the page
        copies.append((today + "000000", f"{live}#live-{today}"))
        cover["live"] = True
    if stamps is None and not copies:
        return pd.DataFrame(), dict(cover, status="archive did not answer: rerun later")
    if not copies:
        return pd.DataFrame(), dict(cover, status="no copies saved: missing")

    rows = []
    for stamp, url in copies:
        html = fetch(url)
        if html is None:                              # download failed: count it, carry on
            cover["failed"] += 1
            continue
        rows += parse(html, stamp)
    events = pd.DataFrame(rows, columns=["event_id", "title", "date", "location", "group", "saved"])

    # Same event in several copies -> keep the copy saved last (most up to date).
    events = events.sort_values("saved").drop_duplicates("event_id", keep="last")
    # Keep only events held Sep 1 - Nov 30 of this year (copies also list later events).
    events = events[events["date"].between(f"{year}-09-01", f"{year}-11-30")]
    events.insert(0, "univ_id", univ)

    first, last = copies[0][0], copies[-1][0]
    cover.update(copies=len(copies), events=len(events),
                 # A copy shows UPCOMING events, so we only see from the first copy onward:
                 first_saved=f"{first[:4]}-{first[4:6]}-{first[6:8]}",
                 last_saved=f"{last[:4]}-{last[4:6]}-{last[6:8]}",
                 status="ok" if len(events) else "copies saved, but no events found in Sep-Nov")
    return events, cover


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    all_events, coverage = [], []
    for univ, page in CALENDARS.items():
        for year in YEARS:
            events, cover = harvest(univ, page, year)
            print(f"{univ} {year}: {cover['events']} events from {cover['copies']} copies "
                  f"(first saved {cover['first_saved'] or '-'}{', + live page' if cover['live'] else ''})"
                  f" -> {cover['status']}")
            all_events.append(events)
            coverage.append(cover)
    pd.concat(all_events).to_csv(OUT / "events.csv", index=False)
    pd.DataFrame(coverage).to_csv(OUT / "coverage.csv", index=False)
    print(f"Wrote {OUT / 'events.csv'} and {OUT / 'coverage.csv'}")
