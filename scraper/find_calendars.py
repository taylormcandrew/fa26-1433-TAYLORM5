"""find_calendars.py: find the event calendar pages of many universities at once.

Most universities run their admissions events on Slate, at an address like
    https://apply.<university>.edu/portal/<name>        e.g. apply.uga.edu/portal/fairs
The <name> differs everywhere (fairs, travel, outreach, pack-on-the-prowl, ...), and so does
the start of the address (apply., admissions., enrollmentconnect., ...). So, per university:

  1. Collect the possible Slate addresses: common ones (apply.<domain>, admissions.<domain>, ...)
     plus every <something>.<domain> address linked from its admissions homepage.
  2. Ask the archive's index which /portal/ pages it saved on each (one small question each).
  3. Score each page: links to individual events (?id=...) archived under it are the best
     sign it's an event list; words like "fair", "travel", "visit" in its name help;
     "campus", "tour", "admitted", "graduate" pages are about other things.

Writes candidates.csv (every page found, best first) and adds each university's best page
to calendars.csv if it looks clearly like an event list. Check the rest by hand.
Safe to stop and rerun: answers already downloaded come from the cache.

Usage:  python3 find_calendars.py        all universities in targets.csv
        python3 find_calendars.py 52     only the first 52 (the ban-state schools come first)
"""
import json
import sys
import re
from pathlib import Path

import pandas as pd

from captures import CDX
from fetch import fetch

HERE = Path(__file__).parent
TARGETS = pd.read_csv(HERE / "targets.csv", dtype=str).fillna("")   # universities to search
if len(sys.argv) > 1:                                                # optional: only the first N
    TARGETS = TARGETS.head(int(sys.argv[1]))
GUESSES = ["apply", "admissions", "admission", "applyundergrad", "connect", "enroll",
           "go", "futurestudents", "visit", "join", "discover", "undergrad"]
ADMISSIONS_LIKE = re.compile(r"apply|admi|enroll|connect|visit|future|undergrad|join|discover|"
                             r"go$|slate|recruit|explore|choose", re.I)
GOOD = re.compile(r"fair|travel|visit|event|near|road|outreach|recruit|counsel|rep|meet|prowl", re.I)
BAD = re.compile(r"campus|tour|admit|grad|transfer|status|login|account|deposit|inquiry|"
                 r"info|apply|application|scholar|orientation|housing|parent|alumni", re.I)
EVENT_ID = re.compile(r"id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)


def hosts_for(uni):
    """Possible Slate addresses: common guesses + subdomains linked from the admissions page."""
    hosts = {f"{g}.{uni.domain}" for g in GUESSES}
    html = fetch(uni.admissions) or ""
    for host in re.findall(r"https?://([a-z0-9.-]+\." + re.escape(uni.domain) + r")\b", html, re.I):
        if ADMISSIONS_LIKE.search(host.split(".")[0]):   # skip library., accessibility., ...
            hosts.add(host.lower())
    return sorted(hosts)


def portal_pages(host):
    """{page address: set of event ids} for every /portal/ page the archive saved on `host`.
    None if the archive did not answer."""
    text = fetch(f"{CDX}?url={host}/portal/&matchType=prefix&from=2022&to=2024"
                 "&output=json&fl=original&collapse=urlkey&limit=5000")
    if text is None:
        return None
    pages = {}
    for (url,) in json.loads(text)[1:]:
        m = re.match(r"https?://([^/]+)/portal/([^/?#]+)", url)
        if m:
            page = f"https://{m.group(1).split(':')[0].lower()}/portal/{m.group(2)}"
            ids = pages.setdefault(page, set())
            ids.update(i.lower() for i in EVENT_ID.findall(url))
    return pages


def score(page, n_events):
    name = page.rsplit("/", 1)[1]
    if BAD.search(name):
        return -1                                      # not a recruiting calendar
    return min(n_events, 20) + (10 if GOOD.search(name) else 0)


if __name__ == "__main__":
    found, failed = [], []
    for i, uni in enumerate(TARGETS.itertuples(), 1):
        rows = []
        if uni.known_calendar:                         # already known (e.g. from the starter kit)
            rows.append({"page": uni.known_calendar, "event_links": "", "score": 99})
        for host in hosts_for(uni):
            pages = portal_pages(host)
            if pages is None:
                failed.append(f"{uni.univ_id} ({host})")
                continue
            rows += [{"page": p, "event_links": len(ids), "score": score(p, len(ids))}
                     for p, ids in pages.items()]
        rows = sorted(rows, key=lambda r: -r["score"])
        best = rows[0] if rows and rows[0]["score"] >= 0 else None
        print(f"[{i}/{len(TARGETS)}] {uni.name}: {len(rows)} pages; best: "
              f"{best['page'] + ' (score ' + str(best['score']) + ')' if best else '-'}", flush=True)
        found += [dict(univ_id=uni.univ_id, name=uni.name, state=uni.state, **r) for r in rows]

    cand = pd.DataFrame(found, columns=["univ_id", "name", "state", "page", "event_links", "score"])
    cand.to_csv(HERE / "candidates.csv", index=False)

    # Clearly an event list: some archived event links AND a recruiting word, or known already.
    strong = cand[cand["score"] >= 13].drop_duplicates("univ_id")
    calendars = pd.read_csv(HERE / "calendars.csv", dtype=str).fillna("")
    new = strong[~strong["univ_id"].isin(calendars["univ_id"])]
    new = new.assign(widget="")[["univ_id", "name", "state", "page", "widget"]]
    pd.concat([calendars, new]).to_csv(HERE / "calendars.csv", index=False)
    print(f"\nAdded {len(new)} universities to calendars.csv. All pages found: candidates.csv")
    if failed:
        print(f"The archive did not answer for {len(failed)} addresses; rerun later to retry:",
              ", ".join(failed[:10]), "..." if len(failed) > 10 else "")
