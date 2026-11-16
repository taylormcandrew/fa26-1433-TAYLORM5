"""harvest.py: collect every event from every saved copy of each calendar, for each cycle.

For each university and year: list the saved copies (captures.py), download each one
(fetch.py), read its events (parse.py), then combine them. For the current fall we also
read the live page as it is today, since the archive may not have saved it yet.
Cycles run Aug 1 - Jul 31 and are labeled by the year they start (2022 = Aug 2022-Jul 2023),
exactly as in the regression code.
The same event appears in several copies, so we keep one row per event id (latest copy).

Writes two files in scraper/output/:
  events.csv    one row per event, every cycle from 2021-22 to now
  coverage.csv  one row per university x cycle: how many copies, from when we can see.
                A year with no copies is recorded as missing, never as zero events.
"""
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from captures import captures, replay_url
from fetch import fetch
from parse import parse

# One row per university: id, name, state, calendar page, and (optional) widget address.
# To add a university, add a row to calendars.csv; no code changes needed.
CALENDARS = pd.read_csv(Path(__file__).parent / "calendars.csv", dtype=str).fillna("")
# The cycle we are in now (Aug-Dec belongs to this year's cycle, Jan-Jul to last year's).
NOW = date.today().year if date.today().month >= 8 else date.today().year - 1
YEARS = range(2021, NOW + 1)              # 2021-22 and 2022-23 are pre-SFFA, 2023-24 on post
OUT = Path(__file__).parent / "output"


def widget_from(html, page):
    """Pages that load events with JavaScript name the address the events come from inside
    their HTML, e.g. data-service="/portal/widget/event?portal_id=...&amp;part=...".
    Return that full address (as the page's JavaScript requests it), or "" if there is none."""
    m = re.search(r'data-service="(/portal/widget/event\?[^"]+)"', html)
    return urljoin(page, m.group(1).replace("&amp;", "&")) + "&cmd=event_list" if m else ""


def read_copies(address, year, cover):
    """Events from every saved copy of `address` in this cycle, plus today's live version if
    this cycle is happening now. Also returns any widget address found in those pages."""
    stamps = captures(address, year)
    if stamps is None:
        cover["failed"] += 1                          # archive did not answer: unknown
    copies = [(s, replay_url(address, s)) for s in stamps or []]
    if year == NOW:
        # The "#live-<date>" ending is ignored by the website but gives today's copy its own
        # cache file, so each day's version is kept (rerun tomorrow = new download).
        today = date.today().strftime("%Y%m%d")
        copies.append((today + "000000", f"{address}#live-{today}"))
        cover["live"] = True
    rows, widget = [], ""
    for stamp, url in copies:
        html = fetch(url)
        if html is None:                              # download failed: count it, carry on
            cover["failed"] += 1
            continue
        rows += parse(html, stamp)
        widget = widget or widget_from(html, address)
    cover["copies"] += len(copies)
    if copies:
        cover["first_saved"] = min(cover["first_saved"] or "9", copies[0][0][:8])
    return rows, widget


def harvest(univ, page, widget, year):
    """Events for one university and year, plus one coverage row describing what we saw."""
    cover = {"univ_id": univ, "year": year, "page": page, "widget": "", "copies": 0,
             "failed": 0, "events": 0, "first_saved": "", "live": False}
    rows, found = read_copies(page, year, cover)
    # Many Slate calendars list events only after "Browse All" is clicked, which opens the
    # same page with "?c=&country=" added (e.g. apply.berkeley.edu/portal/outreach?c=&country=).
    # The archive saved some of those separately, so read them too.
    if "?" not in page:
        rows += read_copies(page + "?c=&country=", year, cover)[0]
    # If the page loads its events with JavaScript, the saved page has none; read the widget
    # it names (or the one given in calendars.csv) the same way: saved copies + live.
    widget = widget or found
    if widget:
        cover["widget"] = widget
        rows += read_copies(widget, year, cover)[0]

    if not cover["copies"]:
        status = "archive did not answer: rerun later" if cover["failed"] else "no copies saved: missing"
        return pd.DataFrame(), dict(cover, status=status)
    events = pd.DataFrame(rows, columns=["event_id", "title", "date", "location", "group", "saved"])
    # Same event in several copies -> keep the copy saved last (most up to date).
    events = events.sort_values("saved").drop_duplicates("event_id", keep="last")
    # Keep only events held in this cycle (a copy saved in July can list August events).
    events = events[events["date"].between(f"{year}-08-01", f"{year + 1}-07-31")]
    events.insert(0, "univ_id", univ)
    f = cover["first_saved"]                          # a copy shows UPCOMING events only, so
    cover.update(events=len(events),                  # we see this cycle from this date onward
                 first_saved=f"{f[:4]}-{f[4:6]}-{f[6:8]}",
                 status="ok" if len(events) else "copies saved, but no events found")
    return events, cover


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    all_events, coverage = [], []
    for cal in CALENDARS.itertuples():              # one university (one row) at a time
        for year in YEARS:
            events, cover = harvest(cal.univ_id, cal.page, cal.widget, year)
            print(f"{cal.univ_id} {year}-{year + 1}: {cover['events']} events from {cover['copies']} copies "
                  f"(first saved {cover['first_saved'] or '-'}{', + live' if cover['live'] else ''}"
                  f"{', + widget' if cover['widget'] else ''})"
                  f" -> {cover['status']}")
            all_events.append(events)
            coverage.append(cover)
    pd.concat(all_events).to_csv(OUT / "events.csv", index=False)
    pd.DataFrame(coverage).to_csv(OUT / "coverage.csv", index=False)
    print(f"Wrote {OUT / 'events.csv'} and {OUT / 'coverage.csv'}")
