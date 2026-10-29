"""parse.py: turn one saved event page into rows (one row per event) with BeautifulSoup.

Many universities build their event pages with the same software, Slate. A Slate event
list looks like this in the HTML:

    <p>United States—Georgia</p>                    <- group heading (state, or "Online")
    <ul>
      <li><a href="?id=5ae2...">Centennial High School</a><br/>   <- event name + unique id
          Monday, October 3 at 12:15 PM<br/>                     <- date (no year!)
          Roswell, GA</li>                                       <- city, state
    </ul>
"""
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

DATE = re.compile(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
                  r"(January|February|March|April|May|June|July|August|September|"
                  r"October|November|December) (\d{1,2})")


def event_date(text, saved_on):
    """'Monday, October 3 at 9:30 AM' -> date(2022, 10, 3). The page shows no year, so we
    use the year the page was saved, or the next year if only that matches the weekday
    (a page saved in December can list January events)."""
    m = DATE.search(text)
    if not m:
        return None
    weekday, month, day = m.groups()
    for year in (saved_on.year, saved_on.year + 1):
        try:
            d = datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()
        except ValueError:                       # e.g. February 29 in a non-leap year
            continue
        if d.strftime("%A") == weekday and d >= saved_on.replace(day=1):
            return d
    return None                                  # no year fits: leave it out, don't guess


def parse(html, timestamp):
    """All events listed on one saved page. `timestamp` = when the archive saved it."""
    saved_on = datetime.strptime(timestamp[:8], "%Y%m%d").date()
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for link in soup.find_all("a", href=re.compile(r"\?id=")):   # every link to an event
        item = link.find_parent("li")
        if item is None:                         # links outside a list are menus, not events
            continue
        lines = list(item.stripped_strings)      # ['Centennial High School', 'Monday, ...', 'Roswell, GA']
        d = event_date(" ".join(lines), saved_on)
        if d is None:
            continue
        heading = item.find_previous("p")        # nearest group heading above this event
        rows.append({
            "event_id": link["href"].split("id=")[1],      # Slate's id: same event = same id
            "title": link.get_text(strip=True),
            "date": d.isoformat(),
            "location": lines[2] if len(lines) > 2 else "",  # missing for online events
            "group": heading.get_text(strip=True) if heading else "",
            "saved": timestamp,
        })
    return rows + parse_widget(soup, timestamp)

def parse_widget(soup, timestamp):
    """Events from Slate's newer event widget (UGA since 2025), which looks like this:

        <div class="item_header">United States - Georgia</div>       <- group heading
        <div class="item"><div class="event" data-date="2026-10-29T18:00:00" ...>
            <p><a href="...?id=...">Clarke Central High School Dual Enrollment Night</a>
               10/29/2026 06:00 PM<br/> Clarke Central High School</p></div></div>

    Here the date comes WITH its year (data-date), so no guessing is needed."""
    rows = []
    for event in soup.find_all("div", class_="event"):
        lines = list(event.stripped_strings)          # visible text pieces, in order
        if not lines:
            continue
        stamp = event.get("data-date", "")            # e.g. "2026-10-29T18:00:00"
        if not stamp:                                 # fallback: a "10/29/2026" in the text
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", " ".join(lines))
            if not m:
                continue
            stamp = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        link = event.find("a", href=re.compile(r"id="))
        title = link.get_text(strip=True) if link else lines[0]
        heading = event.find_previous("div", class_="item_header")
        # Location: the line that looks like "City, ST"; if none, the venue (last line)
        city = next((x for x in lines if re.search(r", [A-Z]{2}\b", x)),
                    lines[-1] if len(lines) > 2 else "")
        rows.append({
            # Slate's id if the event links to one; otherwise name + date identify it
            "event_id": link["href"].split("id=")[1].split("&")[0] if link else f"{title}|{stamp[:10]}",
            "title": title,
            "date": stamp[:10],
            "location": city,
            "group": heading.get_text(strip=True) if heading else "",
            "saved": timestamp,
        })
    return rows

if __name__ == "__main__":
    from captures import replay_url
    from fetch import fetch

    page, stamp = "https://apply.uga.edu/portal/fairs", "20221001081826"
    rows = parse(fetch(replay_url(page, stamp)), stamp)
    print(len(rows), "events")
    for r in rows[:5]:
        print(r)
