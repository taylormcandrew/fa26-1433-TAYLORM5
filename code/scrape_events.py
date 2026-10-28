"""Step 2 of scraping: download archived travel-schedule pages and extract the visits.

Input:  data/manual/travel_pages.csv   univ_id, url, notes
        (url can be exact, or end in * to include every page under that path, which
         catches Slate pages whose address changes, e.g. .../portal/travel?region=...)

For every distinct saved version of each page between config.SCRAPE_FROM and
config.SCRAPE_TO, this downloads the page once (cached in data/raw/scrape/<univ_id>/,
so re-runs are fast and do not hit the Archive again), pulls out each listed event,
and stitches all versions together, dropping events seen in more than one version.

Output: data/raw/visits/<univ_id>_scraped.csv with columns
        date, title, city_state, event_type, first_seen, source_url
        This has the same kind of columns as the CU Boulder records, so it plugs into
        the pipeline with a VISIT_FILES entry in code/config.py (see PIPELINE.md).
        output/scrape_parse_log.csv lists how many events each snapshot produced;
        a snapshot with 0 events usually means a page layout the parser does not read.

Add --live to also save today's version of each page directly from the university
site (run it every week or two through the 2026-27 cycle to build up post-period data).

Usage:  python code/scrape_events.py                (all universities in travel_pages.csv)
        python code/scrape_events.py cu_boulder     (one university)
        python code/scrape_events.py --parse-only   (re-parse cached pages, no downloads)
"""

import datetime as dt
import hashlib
import re
import sys

import pandas as pd
from bs4 import BeautifulSoup

import config
from scrape_common import cdx, polite_get, session, snapshot_url

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DAY = r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?"
# "Monday, November 2 at 8:30 AM", "Nov 2, 2026", "Mon, Nov 2", "11/02/2026", "11/2"
DATE_WORDS = re.compile(rf"\b(?:{DAY}\s+)?{MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?\b", re.I)
DATE_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d\d|\d\d))?\b")
CITY_ST = re.compile(r"^\s*([A-Za-z][A-Za-z .'\-]+),\s*([A-Z]{2})\b(?:\s+\d{5})?\s*$")
TIME_ONLY = re.compile(r"^\s*(\d{1,2}(:\d\d)?\s*(am|pm|a\.m\.|p\.m\.)\s*(-|–|to)?\s*)+$", re.I)
NOISE = re.compile(r"^(register|details|more info|learn more|map|rsvp|view|sign up|\||-|–)$", re.I)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def load_pages(only):
    pages = pd.read_csv(config.TRAVEL_PAGES, dtype=str).dropna(subset=["univ_id", "url"])
    return pages[pages["univ_id"].isin(only)] if only else pages


def list_snapshots(s, url):
    params = {"fl": "timestamp,original", "filter": ["statuscode:200"], "collapse": "digest",
              "from": config.SCRAPE_FROM, "to": config.SCRAPE_TO}
    if url.endswith("*"):
        params.update(url=url[:-1], matchType="prefix")
    else:
        params.update(url=url)
    return cdx(s, **params)


def cache_path(univ_id, timestamp, original):
    h = hashlib.md5(original.encode()).hexdigest()[:10]
    return config.SCRAPE_CACHE / univ_id / f"{timestamp}_{h}.html"


def download(univ_ids, live):
    s = session()
    for _, p in load_pages(univ_ids).iterrows():
        snaps = list_snapshots(s, p["url"])
        print(f"{p['univ_id']}: {len(snaps)} saved versions of {p['url']}")
        new = 0
        for snap in snaps:
            path = cache_path(p["univ_id"], snap["timestamp"], snap["original"])
            if path.exists():
                continue
            r = polite_get(s, snapshot_url(snap["timestamp"], snap["original"]))
            if r is not None and r.status_code == 200:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                (path.with_suffix(".url")).write_text(snap["original"])
                new += 1
        if live and not p["url"].endswith("*"):
            r = polite_get(s, p["url"])
            if r is not None and r.status_code == 200:
                ts = dt.datetime.now().strftime("%Y%m%d%H%M%S")
                path = cache_path(p["univ_id"], ts, p["url"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                path.with_suffix(".url").write_text(p["url"])
                new += 1
        print(f"  downloaded {new} new")


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
def resolve_year(month, day, weekday, seen):
    """Pages usually omit the year. The listed event is on or after the day the page was
    saved (allow 10 days of slack for stale listings), within the next ~13 months. If the
    page names the weekday, pick the year where that date falls on that weekday."""
    options = []
    for y in (seen.year - 1, seen.year, seen.year + 1):
        try:
            d = dt.date(y, month, day)
        except ValueError:
            continue
        if seen - dt.timedelta(days=10) <= d <= seen + dt.timedelta(days=400):
            options.append(d)
    if weekday is not None:
        matching = [d for d in options if d.weekday() == weekday]
        if matching:
            return matching[0]
    return options[0] if options else None


def find_date(text, seen):
    m = DATE_WORDS.search(text)
    if m:
        key = m.group(2).lower().rstrip(".")
        month = MONTHS.get(key) or MONTHS.get(key[:3])
        day = int(m.group(3))
        wd = None
        if m.group(1):
            wd = next((i for i, w in enumerate(WEEKDAYS) if w.startswith(m.group(1).lower()[:3])), None)
        if m.group(4):
            try:
                return dt.date(int(m.group(4)), month, day), m
            except ValueError:
                return None, None
        return resolve_year(month, day, wd, seen), m
    m = DATE_NUM.search(text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None, None
        if year:
            year = int(year) + (2000 if len(year) == 2 else 0)
            try:
                return dt.date(year, month, day), m
            except ValueError:
                return None, None
        return resolve_year(month, day, None, seen), m
    return None, None


def parse_tables(soup, seen):
    """Pages that list visits in a table with a 'Date' column (and School/Location/City)."""
    events = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        if not any("date" in h for h in header):
            continue
        idx = {k: next((i for i, h in enumerate(header) if any(w in h for w in words)), None)
               for k, words in {"date": ["date"], "title": ["school", "location", "event", "name", "visit"],
                                "city": ["city", "town"], "state": ["state"]}.items()}
        for r in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
            if idx["date"] is None or idx["date"] >= len(cells):
                continue
            d, _ = find_date(cells[idx["date"]], seen)
            title = cells[idx["title"]] if idx["title"] is not None and idx["title"] < len(cells) else ""
            city = cells[idx["city"]] if idx["city"] is not None and idx["city"] < len(cells) else ""
            state = cells[idx["state"]] if idx["state"] is not None and idx["state"] < len(cells) else ""
            city_state = f"{city}, {state}" if city and state else (city or "")
            if d and title:
                events.append({"date": d, "title": title, "city_state": city_state})
    return events


def parse_text(soup, seen):
    """Listing layouts (typical Slate portals): each event is a few lines such as
         Arvada West High School Visit
         Monday, November 2 at 8:30 AM
         Arvada, CO
    or a single line such as '11/02/2026 | Arvada West High School | Arvada, CO'."""
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    lines = [re.sub(r"\s+", " ", x).strip() for x in soup.get_text("\n").split("\n")]
    lines = [x for x in lines if x and not NOISE.match(x)]
    events, used = [], set()
    for i, line in enumerate(lines):
        d, m = find_date(line, seen)
        if not d or len(line) > 160:
            continue
        rest = (line[:m.start()] + " " + line[m.end():]).strip(" |-–,:")
        rest = re.sub(r"\bat\s+\d{1,2}(:\d\d)?\s*(am|pm)\b.*$", "", rest, flags=re.I).strip(" |-–,:")
        parts = [p.strip() for p in re.split(r"\s*[|•·]\s*|\s+[-–—]\s+", rest) if p.strip()]
        title, city_state = "", ""
        for p in parts:                                  # single-line layout
            if CITY_ST.match(p):
                city_state = p
            elif len(p) > 3 and not TIME_ONLY.match(p):
                title = title or p
        if not title:                                    # multi-line layout: title above the date
            for j in range(i - 1, max(i - 3, -1), -1):
                if j in used:
                    break
                cand = lines[j]
                if find_date(cand, seen)[0] or TIME_ONLY.match(cand) or CITY_ST.match(cand):
                    continue
                if 3 < len(cand) <= 140:
                    title = cand
                    used.add(j)
                    break
        if not city_state:                               # location usually just below
            for j in range(i + 1, min(i + 4, len(lines))):
                if CITY_ST.match(lines[j]):
                    city_state = lines[j].strip()
                    break
                if find_date(lines[j], seen)[0]:
                    break
        if title:
            events.append({"date": d, "title": title, "city_state": city_state})
    return events


def parse_file(path):
    seen = dt.datetime.strptime(path.stem.split("_")[0][:8], "%Y%m%d").date()
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    events = parse_tables(soup, seen) or parse_text(soup, seen)
    for e in events:
        e["first_seen"] = seen
        e["source_url"] = path.with_suffix(".url").read_text() if path.with_suffix(".url").exists() else ""
    return events, seen


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def parse_all(univ_ids):
    dirs = [d for d in sorted(config.SCRAPE_CACHE.glob("*")) if d.is_dir()]
    if univ_ids:
        dirs = [d for d in dirs if d.name in univ_ids]
    log = []
    for d in dirs:
        rows = []
        for path in sorted(d.glob("*.html")):
            events, seen = parse_file(path)
            rows += events
            log.append({"univ_id": d.name, "snapshot": path.name, "saved_on": seen, "events": len(events)})
        if not rows:
            print(f"{d.name}: no events parsed from {len(list(d.glob('*.html')))} pages")
            continue
        ev = pd.DataFrame(rows)
        ev["key"] = ev["date"].astype(str) + "|" + ev["title"].map(norm)
        ev = ev.sort_values("first_seen").drop_duplicates("key").drop(columns="key")
        ev["event_type"] = ""
        ev = ev.sort_values("date")[["date", "title", "city_state", "event_type", "first_seen", "source_url"]]
        out = config.VISITS_DIR / f"{d.name}_scraped.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        ev.to_csv(out, index=False)
        cyc = pd.to_datetime(ev["date"]).pipe(lambda x: x.dt.year.where(x.dt.month >= 8, x.dt.year - 1))
        print(f"{d.name}: {len(ev):,} distinct events -> {out.relative_to(config.ROOT)}; "
              f"by cycle {cyc.value_counts().sort_index().to_dict()}")
    if log:
        pd.DataFrame(log).to_csv(config.SCRAPE_EVENTS_LOG, index=False)
        zero = sum(1 for x in log if x["events"] == 0)
        print(f"Parse log: {config.SCRAPE_EVENTS_LOG.relative_to(config.ROOT)} "
              f"({zero} of {len(log)} saved pages gave no events)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--parse-only" not in sys.argv:
        download(args, live="--live" in sys.argv)
    parse_all(args)


if __name__ == "__main__":
    main()
