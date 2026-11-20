"""test_extra_sites.py: checks the page readers in extra_sites.py on small example pages
written in the layouts the five universities use. No internet needed.

Run from scraper/:   python3 test_extra_sites.py
"""
from datetime import date

from bs4 import BeautifulSoup

import extra_sites as x

SAVED = date(2022, 9, 15)          # pretend the page was saved on Sep 15, 2022
soup = lambda html: BeautifulSoup(html, "html.parser")

# Oklahoma: an "Upcoming Events" table on a counselor profile
ou = soup("""<h1>Bri Trone, Admissions Counselor</h1><table>
<tr><th>Date</th><th>Time</th><th>Event</th><th>Location</th></tr>
<tr><td>10/04/2022</td><td>9:00 AM</td><td>Norman High School Visit</td><td>Norman, OK</td></tr>
<tr><td>October 6</td><td>6 PM</td><td>Tulsa Area College Fair</td><td>Tulsa, OK</td></tr></table>""")
r = x.rows_from_tables(ou, SAVED, None)
assert [(e["date"], e["date_basis"]) for e in r] == [
    (date(2022, 10, 4), "stated"), (date(2022, 10, 6), "saved 2022-09-15, listed as upcoming")]
assert x.counselor_of(ou) == "Bri Trone"

# SUNY Delhi: month headings, then "day  event time" lines; the page states its term
delhi = soup("""<body><p><b>My travel schedule for Fall 2023</b></p><h3>September</h3>
<p>28   Catskill H.S. Visit 10:40-11:20 a.m.<br/>29    Cambridge H.S. Visit 8:00-8:45 a.m.</p>
<h3>October</h3><p>3      Potsdam College Night 5:00 - 8:00 p.m.<br/>
21    SUNY DELHI OPEN HOUSE, 9 a.m. - 2 p.m.</p></body>""")
term = x.page_term(delhi)
assert term == ("fall", 2023)
# A copy saved in 2025 still shows the Fall 2023 schedule: the stated term wins
r = x.rows_from_text(delhi, date(2025, 3, 1), term)
assert [(e["date"], e["title"]) for e in r] == [
    (date(2023, 9, 28), "Catskill H.S. Visit"), (date(2023, 9, 29), "Cambridge H.S. Visit"),
    (date(2023, 10, 3), "Potsdam College Night"), (date(2023, 10, 21), "SUNY DELHI OPEN HOUSE")]
kinds = [x.classify(dict(title=e["title"], type_raw=""))[0] for e in r]
assert kinds == ["School Visit", "School Visit", "College Fair", "Other"]

# Keene State: one event page per visit, kept only on an Admissions calendar
keene = soup("""<h1>Ossining High School</h1><p>Thursday, October 23, 2025</p>
<p>8:49 a.m. - 9:30 a.m.</p><p>Ossining, NY</p><p>Part of the Admissions High School Visits calendar.</p>""")
r = x.rows_from_keene(keene, date(2025, 10, 1))
assert len(r) == 1 and r[0]["date"] == date(2025, 10, 23) and (r[0]["city"], r[0]["state"]) == ("Ossining", "NY")
assert x.rows_from_keene(soup("<h1>Concert</h1><p>Friday, May 2, 2025</p><p>Music calendar</p>"), SAVED) == []

# A weekday that disagrees with the inferred year is not guessed
assert x.to_date("Monday, October 4", SAVED, None) == (None, "")      # Oct 4, 2022 is a Tuesday
assert x.to_date("Tuesday, October 4", SAVED, None)[0] == date(2022, 10, 4)

# Slate list (Portland State / Delhi portal pages) goes through parse.py, unchanged
slate = """<p>United States—Oregon</p><ul><li><a href="?id=abc">Lincoln High School</a><br/>
Tuesday, October 4 at 9:00 AM<br/>Portland, OR</li></ul>"""
assert x.parse_slate(slate, "20220915000000")[0]["date"] == "2022-10-04"

# Same event on two saved copies is kept once; a repeat visit on another date is kept
import pandas as pd
rows = pd.DataFrame([dict(date=date(2022, 10, 4), title="Norman HS Visit", counselor="A", saved="1"),
                     dict(date=date(2022, 10, 4), title="Norman HS visit", counselor="A", saved="2"),
                     dict(date=date(2023, 3, 1), title="Norman HS Visit", counselor="A", saved="3")])
key = rows["title"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
assert len(rows.assign(_k=key).drop_duplicates(["date", "_k", "counselor"])) == 2

# Ohio State: the 2021-22 layout (heading, then type) and today's (type, then heading)
osu = soup("""<h2>Ohio State is coming to you</h2><p>Oct</p><p>2021</p>
<h3>J S Morton High School East</h3><p>High School Visit</p><p><em>October 18, 2021, midnight to midnight</em></p>
<p><a href="#">2423 S Austin Blvd</a></p><p>Cicero, IL 60804</p>
<p>Nov 23</p><p>In-Person College Fair</p><h3>Central Florida Virtual College Fair</h3>
<p>February 22, 2022, 6 -8:45 p.m.</p><p><a href="#">Strive Scan Virtual</a></p><p>WInter Park, FL 32792</p>""")
r = x.rows_from_osu(osu, date(2021, 10, 15))
assert [(e["date"], e["title"], e["type_raw"], e["city"], e["state"]) for e in r] == [
    (date(2021, 10, 18), "J S Morton High School East", "High School Visit", "Cicero", "IL"),
    (date(2022, 2, 22), "Central Florida Virtual College Fair", "In-Person College Fair", "WInter Park", "FL")]
assert [x.classify(e)[0] for e in r] == ["School Visit", "Other"]   # a virtual fair is left out

print("All extra_sites tests passed.")
