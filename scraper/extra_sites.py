"""extra_sites.py: recruitment visits from six universities whose schedules are not the
Slate event calendars harvest.py reads.

    Westfield State (MA)  one travel-schedule page                     university-wide
    Keene State (NH)      one event page per visit on keene.edu         university-wide
    Oklahoma (OK)         an "Upcoming Events" table on each counselor's profile   counselor-specific
    SUNY Delhi (NY)       one travel page per counselor (old .php pages and Slate portal pages)
                                                                        counselor-specific
    Portland State (OR)   Slate counselor profiles and older regional visit-schedule pages
                                                                        counselor/region-specific
    Ohio State (OH)       one "Ohio State is coming to you" page listing every off-campus
                          event with its full date, type and city    university-wide

For every page, every distinct saved copy in the Wayback Machine since Aug 2021 is read, plus
today's live page. Pages are found only from links on the universities' own index pages or
from the archive's own index of saved addresses (a CDX "prefix" search): no address is guessed.

Years. Many schedules print dates without a year ("October 3"). The year is then taken, in
this order, from (1) the date itself, (2) a term the page states ("Fall 2023"), or (3) the date
the copy was saved, assuming the page lists upcoming events. Because an old page can stay
online unchanged for years, (3) uses only the FIRST time each version of a page was saved.
Every row says which rule gave its year (date_basis), so each can be checked.

Nothing is inferred beyond the page: a listed event is "scheduled" unless the page itself says
otherwise (status is left blank), and a year with no copies is missing, not zero events.

Writes (in scraper/output/):
  extra_events.csv    one row per event, raw and classified (event_type, excluded), with the
                      source page (source_url) and the saved copy (saved) it came from
  extra_coverage.csv  one row per page: copies read, errors, events found, dates covered
export.py adds the kept rows (school visits and college fairs) to the regression data.

Run from scraper/:   python3 extra_sites.py             (all six)
                     python3 extra_sites.py ou keene_state   (some)
Pages are cached in scraper/cache/, so a rerun continues where the last one stopped.
"""
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib import robotparser
from urllib.parse import quote, urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from captures import CDX, replay_url
from fetch import HEADERS, fetch
from harvest import widget_from
from parse import parse as parse_slate

OUT = Path(__file__).parent / "output"
FIRST, TODAY = date(2021, 8, 1), date.today()
SITES = [
    dict(univ_id="westfield_state", name="Westfield State University", state="MA", kind="page",
         coverage="university-wide",
         pages=["https://www.westfield.ma.edu/admissions/first-year/travel-schedule"]),
    dict(univ_id="keene_state", name="Keene State College", state="NH", kind="keene",
         coverage="university-wide", pages=["https://www.keene.edu/news/events/detail/21842/"],
         archive_prefix=["keene.edu/news/events/detail/"], link=r"/news/events/detail/\d+/?$"),
    dict(univ_id="ou", name="University of Oklahoma-Norman Campus", state="OK", kind="page",
         coverage="counselor-specific", pages=["https://www.ou.edu/admissions/contact/b-trone"],
         index="https://www.ou.edu/admissions/contact/staff.html",
         archive_prefix=["ou.edu/admissions/contact/"], link=r"/admissions/contact/[a-z]+-[a-z]+(\.html)?$"),
    dict(univ_id="suny_delhi", name="SUNY Delhi", state="NY", kind="page", coverage="counselor-specific",
         pages=[f"https://www.delhi.edu/admission/visit-delhi/staff/{n}-travel.php"
                for n in ("jutrzenka", "gregory", "mcclure", "williams", "wockasen")],
         index="https://www.delhi.edu/admission/visit-delhi/staff/",
         archive_prefix=["delhi.edu/admission/visit-delhi/staff/", "apply.delhi.edu/portal/travel_"],
         link=r"(-travel\.php$|/portal/travel_\w+$)"),
    dict(univ_id="portland_state", name="Portland State University", state="OR", kind="page",
         coverage="counselor-specific",
         pages=["https://apply.pdx.edu/portal/find_my_counselor?cmd=profile&user=5dd25ed4-7d62-400a-af75-40f359d675d5"],
         # also the older regional visit-schedule pages, which now redirect to the portal
         archive_prefix=["apply.pdx.edu/portal/find_my_counselor", "pdx.edu/undergraduate-admissions/visit-schedule/"],
         link=r"(cmd=profile&user=[0-9a-f-]{36}|/visit-schedule/[\w-]+/?$)"),
    dict(univ_id="ohio_state", name="Ohio State University-Main Campus", state="OH", kind="osu",
         coverage="university-wide", pages=["https://admissions.osu.edu/offcampus/"]),
]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
STATE = re.compile(r"\b([A-Z][A-Za-z .'-]+?),\s*([A-Z]{2})\b")
TERM = re.compile(r"\b(fall|spring|summer|winter)\s+(20\d\d)\b", re.I)
# What each event is. Excluded rows stay in extra_events.csv but are not exported.
EXCLUDE = re.compile(r"virtual|webinar|online|zoom|open house|on[- ]campus|campus (tour|visit)|"
                     r"information session|info session|directors meeting|accepted student|"
                     r"admitted student|office hours", re.I)
FAIR = re.compile(r"fair|college night|night fair|expo|college day|career day|higher ed (day|night)|"
                  r"consortium|nacac|acac|showcase", re.I)
VISIT = re.compile(r"visit|high school|\bh\.?\s?s\b|academy|school|prep\b|preparatory", re.I)


# ---- Finding pages ------------------------------------------------------------------------
def canonical(url):
    """Same page, one address: https, no :80 port, no fragment."""
    u = urlsplit(url.replace(":80/", "/"))
    return f"https://{u.netloc}{u.path}" + (f"?{u.query}" if u.query else "")


def archive_index(prefix, pattern):
    """Addresses the Wayback Machine has saved under `prefix` (its own index, not guesses)."""
    text = fetch(f"{CDX}?url={quote(prefix, safe=':/')}&matchType=prefix&output=json"
                 "&fl=original&collapse=urlkey&filter=statuscode:200&limit=50000")
    if text is None:
        print(f"  archive index did not answer for {prefix}: rerun later")
        return []
    return sorted({canonical(r[0]) for r in json.loads(text)[1:] if re.search(pattern, r[0])})


def links_on(url, pattern):
    """Links matching `pattern` on a live index page."""
    html = fetch(url) if allowed(url) else None
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return sorted({canonical(urljoin(url, a["href"])) for a in soup.find_all("a", href=True)
                   if re.search(pattern, urljoin(url, a["href"]))})


ROBOTS = {}


def allowed(url):
    """Respect the website's robots.txt (live pages only; archive copies are the archive's)."""
    host = urlsplit(url).netloc
    if host not in ROBOTS:
        rp = robotparser.RobotFileParser(f"https://{host}/robots.txt")
        try:
            rp.read()
        except Exception:                       # no robots.txt reachable: no stated limits
            rp = None
        ROBOTS[host] = rp
    rp = ROBOTS[host]
    return rp is None or rp.can_fetch(HEADERS["User-Agent"], url)


def first_copies(page):
    """[(timestamp, url)]: the first saved copy of each distinct version of `page` since
    FIRST, then today's live page. None if the archive did not answer."""
    text = fetch(f"{CDX}?url={quote(page, safe=':/')}&from={FIRST:%Y%m%d}&output=json"
                 "&fl=timestamp,digest&filter=statuscode:200")
    if text is None:
        return None
    seen, out = set(), []
    for ts, digest in json.loads(text)[1:]:    # in time order: first copy of each version
        if digest not in seen:
            seen.add(digest)
            out.append((ts, replay_url(page, ts)))
    if allowed(page):
        out.append((f"{TODAY:%Y%m%d}000000", f"{page}#live-{TODAY:%Y%m%d}"))
    return out


# ---- Reading one page ---------------------------------------------------------------------
def page_term(soup):
    """A term the page states in its body text ("Fall 2023"), if exactly one is stated."""
    body = soup.body.get_text(" ") if soup.body else soup.get_text(" ")
    terms = {(s.lower(), int(y)) for s, y in TERM.findall(body)}
    return terms.pop() if len(terms) == 1 else None


def to_date(text, saved, term):
    """(date, basis) for a date written in `text`, or (None, '') if there is none."""
    t = text.strip()
    for pat, fmt in [(r"(\d{1,2})/(\d{1,2})/(\d{4})", "mdy"), (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
                     (rf"{MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", "Mdy")]:
        m = re.search(pat, t, re.I)
        if m:
            g = m.groups()
            try:
                if fmt == "mdy":
                    return date(int(g[2]), int(g[0]), int(g[1])), "stated"
                if fmt == "ymd":
                    return date(int(g[0]), int(g[1]), int(g[2])), "stated"
                return date(int(g[2]), month_no(g[0]), int(g[1])), "stated"
            except ValueError:
                return None, ""
    m = re.search(rf"{MON}\s+(\d{{1,2}})\b", t, re.I) or re.search(r"\b(\d{1,2})/(\d{1,2})\b(?!/)", t)
    if not m:
        return None, ""
    month, day = (month_no(m.group(1)), int(m.group(2))) if m.group(1).isalpha() else (int(m.group(1)), int(m.group(2)))
    return year_for(month, day, saved, term, t)


def month_no(word):
    return [m[:3] for m in MONTHS].index(word.lower()[:3]) + 1


def year_for(month, day, saved, term, text=""):
    """Year for a date printed without one: the page's stated term, else the copy's save date
    (the page lists upcoming events). A weekday in the text, if any, must agree."""
    weekday = next((i for i, w in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
                    if re.search(rf"\b{w}", text, re.I)), None)
    if term:
        season, y = term
        year = y + 1 if season == "fall" and month < 8 else y
        basis = f"stated term ({season.title()} {y})"
    else:
        year = saved.year + (1 if (month, day) < (saved.month, max(saved.day - 31, 1)) else 0)
        basis = f"saved {saved:%Y-%m-%d}, listed as upcoming"
    try:
        d = date(year, month, day)
    except ValueError:
        return None, ""
    if weekday is not None and d.weekday() != weekday:
        return None, ""                          # weekday disagrees: don't guess
    return d, basis


def counselor_of(soup):
    """Counselor's name on a profile page: the page heading, without the job title."""
    h = soup.find("h1") or soup.find("title")
    return re.split(r"[,|–-]", h.get_text(" ", strip=True))[0].strip() if h else ""


def rows_from_tables(soup, saved, term):
    """Events in HTML tables whose header names a date and an event/school/location."""
    rows = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        head = [c.get_text(" ", strip=True).lower() for c in trs[0].find_all(["th", "td"])]
        col = lambda *keys: next((i for i, h in enumerate(head) if any(k in h for k in keys)), None)
        i_date, i_name = col("date"), col("event", "school", "name", "high school")
        if i_date is None or i_name is None:
            continue
        i_loc, i_city, i_state = col("location", "venue"), col("city"), col("state")
        i_type, i_status, i_time = col("type"), col("status"), col("time")
        for tr in trs[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(i_date, i_name):
                continue
            get = lambda i: cells[i] if i is not None and i < len(cells) else ""
            d, basis = to_date(get(i_date), saved, term)
            if d:
                rows.append(dict(date=d, date_basis=basis, title=get(i_name), location=get(i_loc),
                                 city=get(i_city), state=get(i_state), type_raw=get(i_type),
                                 status=get(i_status), time=get(i_time)))
    return rows


def rows_from_text(soup, saved, term):
    """Events written as lines of text: either a date then a name ("October 3, 2022 - Lincoln
    HS"), or a day number under a month heading ("September" ... "28  Catskill H.S. Visit")."""
    rows, month = [], None
    for line in (x.strip() for x in soup.get_text("\n").splitlines()):
        if not line:
            continue
        words = re.findall(r"[a-z]+", line.lower())
        if words and all(w in MONTHS for w in words):        # a month heading
            month = month_no(words[0])
            continue
        m = re.match(r"^(\d{1,2})\s+(.+)$", line)
        if month and m and 1 <= int(m.group(1)) <= 31:        # "28  Catskill H.S. Visit ..."
            d, basis = year_for(month, int(m.group(1)), saved, term)
            rest = m.group(2)
        else:
            d, basis = to_date(line[:40], saved, term) if re.match(rf"^(\w+day,?\s+)?({MON}|\d)", line, re.I) else (None, "")
            rest = re.sub(rf"^.*?({MON}\s+\d{{1,2}}(,?\s+\d{{4}})?|\d{{1,2}}/\d{{1,2}}(/\d{{4}})?)\s*[-–:|]?\s*",
                          "", line, count=1, flags=re.I)
        if d and len(re.sub(r"[^A-Za-z]", "", rest)) >= 3:
            loc = STATE.search(rest)
            rows.append(dict(date=d, date_basis=basis, title=clean_title(rest), location="",
                             city=loc.group(1).strip() if loc else "", state=loc.group(2) if loc else "",
                             type_raw="", status="", time=""))
    return rows


def clean_title(text):
    """Drop times like '8:00-8:45 a.m.' from an event line."""
    text = re.sub(r"\s*\d{1,2}(:\d\d)?\s*(a\.?m\.?|p\.?m\.?)?\s*[-–]\s*\d{1,2}(:+\d\d)?\s*(a\.?m\.?|p\.?m\.?)?.*$", "", text, flags=re.I)
    return re.sub(r"\s*\d{1,2}:\d\d\s*(a\.?m\.?|p\.?m\.?)?.*$", "", text, flags=re.I).strip(" ,-–")


def rows_from_keene(soup, saved):
    """One Keene event page: keep it only if it belongs to an Admissions calendar."""
    text = soup.get_text("\n")
    cal = re.search(r"(Admissions[^\n]*?)\s+calendar", text, re.I)
    if not cal:
        return []
    d, basis = to_date(text, saved, None)
    if d is None or basis != "stated":                # an event page must state its full date
        return []
    title = (soup.find("h1") or soup.find("title")).get_text(" ", strip=True)
    loc = STATE.search(text[text.find(title) + len(title):] if title in text else text)
    school = title
    if re.match(r"admissions? couns", title, re.I):   # "Admissions Counselor: X" -> the location
        m = re.search(r"\n\s*([^\n]*(high|school|academy)[^\n]*?),\s*[^,\n]+,\s*[A-Z]{2}\b", text, re.I)
        school = m.group(1).strip() if m else ""
    return [dict(date=d, date_basis=basis, title=school or title, location="",
                 city=loc.group(1).strip() if loc else "", state=loc.group(2) if loc else "",
                 type_raw=cal.group(1).strip(), status="", time="")]


def rows_from_osu(soup, saved):
    """Ohio State's off-campus page. Each event is a heading (the school or fair), a type line
    ("High School Visit", "In-Person College Fair"; before or after the heading, depending on
    the year) and a line with the full date ("October 18, 2021, midnight to midnight"),
    followed by the venue and "City, ST ZIP"."""
    heads = {h.get_text(" ", strip=True) for h in soup.find_all(["h2", "h3", "h4"])}
    lines = [x.strip() for x in soup.get_text("\n").splitlines() if x.strip()]
    rows = []
    for i, line in enumerate(lines):
        if i < 2 or not re.match(rf"^{MON}\s+\d{{1,2}},\s*\d{{4}}", line, re.I):
            continue                                   # not a date line
        before = lines[i - 2:i]                        # the heading and the type, either order
        title = next((x for x in before if x in heads), None)
        if title is None:
            continue                                   # layout not recognised: skip, don't guess
        kind = next(x for x in before if x != title)
        d, basis = to_date(line, saved, None)          # the date is always written in full
        after = lines[i + 1:i + 6]                     # venue/address lines, then "City, ST ZIP"
        k = next((j for j, x in enumerate(after) if re.match(r"^.+,\s*[A-Z]{2}\s+\d{5}", x)), None)
        loc = STATE.search(after[k]) if k is not None else None
        if d:
            rows.append(dict(date=d, date_basis=basis, title=title,
                             location=" | ".join(after[:k]) if k else "",
                             city=loc.group(1).strip() if loc else "", state=loc.group(2) if loc else "",
                             type_raw=kind, status="", time=""))
    return rows


def read_page(site, page, cover):
    """All events on every saved copy of one page (and its live version)."""
    copies = first_copies(page)
    if copies is None:
        cover["errors"] += 1
        return []
    rows = []
    for ts, url in copies:
        html = fetch(url)
        if html is None:
            cover["errors"] += 1
            continue
        cover["copies"] += 1
        saved = datetime.strptime(ts[:8], "%Y%m%d").date()
        soup = BeautifulSoup(html, "html.parser")
        if site["kind"] == "keene":
            found = rows_from_keene(soup, saved)
        elif site["kind"] == "osu":
            found = rows_from_osu(soup, saved)
        else:
            term = page_term(soup)
            found = rows_from_tables(soup, saved, term) or rows_from_text(soup, saved, term)
            for r in parse_slate(html, ts):           # Slate pages (Delhi portal, Portland State)
                found.append(dict(date=date.fromisoformat(r["date"]), date_basis="stated weekday + saved date",
                                  title=r["title"], location=r["location"], city="", state="",
                                  type_raw=r["group"], status="", time=""))
            w = widget_from(html, page)               # events loaded by a Slate widget
            if w and fetch(w):
                for r in parse_slate(fetch(w), ts):
                    found.append(dict(date=date.fromisoformat(r["date"]), date_basis="stated in widget",
                                      title=r["title"], location=r["location"], city="", state="",
                                      type_raw=r["group"], status="", time=""))
        counselor = counselor_of(soup) if site["coverage"] == "counselor-specific" else ""
        for r in found:
            r.update(counselor=counselor, source_url=page, saved=ts, page_term=" ".join(map(str, page_term(soup) or "")))
        rows += found
    return rows


# ---- Classifying, cleaning, combining -----------------------------------------------------
def classify(r):
    """(event_type, excluded reason). Excluded rows are kept in the file but not exported."""
    text = f"{r['title']} {r['type_raw']}"
    if EXCLUDE.search(text):
        return "Other", "virtual, on-campus or general session"
    if FAIR.search(text):
        return "College Fair", ""
    if VISIT.search(text):
        return "School Visit", ""
    return "Other", "not tied to a high school"


def run_site(site):
    pages = list(site.get("pages", []))
    if site.get("index"):
        pages += links_on(site["index"], site["link"])
    for prefix in site.get("archive_prefix", []):
        pages += archive_index(prefix, site["link"])
    pages = sorted(set(map(canonical, pages)))
    print(f"{site['univ_id']}: {len(pages)} pages")
    rows, covers = [], []
    for page in pages:
        cover = dict(univ_id=site["univ_id"], page=page, copies=0, errors=0)
        try:
            found = read_page(site, page, cover)
        except Exception as e:                        # one bad page must not stop the rest
            cover["errors"] += 1
            print(f"  {page}: {type(e).__name__}: {e}")
            found = []
        found = [r for r in found if FIRST <= r["date"] <= date(TODAY.year + 1, 7, 31)]
        dates = [r["date"] for r in found]
        cover.update(events=len(found), first_event=min(dates, default=""), last_event=max(dates, default=""))
        covers.append(cover)
        rows += found
    out = pd.DataFrame(rows, columns=["date", "date_basis", "title", "location", "city", "state", "type_raw",
                                      "status", "time", "counselor", "source_url", "saved", "page_term"])
    if out.empty:
        return out, pd.DataFrame(covers)
    out.insert(0, "univ_id", site["univ_id"])
    out.insert(1, "university", site["name"])
    out.insert(2, "univ_state", site["state"])
    out["coverage"] = site["coverage"]
    out["status"] = out["status"].where(out["status"] != "", out["title"].str.extract(
        r"(cancel+ed|postponed|rescheduled)", flags=re.I, expand=False).str.lower()).fillna("")
    out[["event_type", "excluded"]] = [classify(r) for r in out.to_dict("records")]
    # One event appears on several saved copies (and on several pages for the same counselor):
    # keep it once. Different dates, or different counselors, are different visits.
    key = out["title"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    out = (out.assign(_k=key).sort_values("saved")        # keep the first copy it appeared on
           .drop_duplicates(["univ_id", "date", "_k", "counselor"], keep="first").drop(columns="_k"))
    return out.sort_values(["date", "title"]), pd.DataFrame(covers)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    wanted = sys.argv[1:] or [s["univ_id"] for s in SITES]
    events, covers = [], []
    for site in (s for s in SITES if s["univ_id"] in wanted):
        try:
            e, c = run_site(site)
        except Exception as err:                      # one failing university must not stop the rest
            print(f"{site['univ_id']}: failed ({type(err).__name__}: {err})")
            continue
        events.append(e)
        covers.append(c)
        kept = e[e["excluded"] == ""] if not e.empty else e
        print(f"  {len(e)} events, {len(kept)} school visits or fairs"
              + (f", {e['date'].min()} to {e['date'].max()}" if not e.empty else ""))
    # Keep other universities' rows from earlier runs when only some are rerun
    old = OUT / "extra_events.csv"
    if old.exists() and sys.argv[1:]:
        prev = pd.read_csv(old, dtype=str)
        events.insert(0, prev[~prev["univ_id"].isin(wanted)])
    pd.concat(events, ignore_index=True).to_csv(old, index=False)
    old_cov = OUT / "extra_coverage.csv"
    if old_cov.exists() and sys.argv[1:]:
        prev = pd.read_csv(old_cov, dtype=str)
        covers.insert(0, prev[~prev["univ_id"].isin(wanted)])
    pd.concat(covers, ignore_index=True).to_csv(old_cov, index=False)
    print(f"Wrote {old} and {OUT / 'extra_coverage.csv'}")
