"""captures.py: list the saved copies of a page that fall in each fall window.

Does in code what you did in the browser: asks the Wayback Machine's index (the "CDX" API)
for every saved copy of one page, keeps only Aug 1 - Nov 30 of the chosen year, and drops
copies identical to one we already have (same digest = same content).
"""
import json

from fetch import fetch

CDX = "https://web.archive.org/cdx/search/cdx"


def captures(page, year):
    """Timestamps of distinct saved copies of `page` from Aug 1 to Nov 30 of `year`.
    Returns None if the archive did not answer (unknown), [] if it has no copies."""
    url = (f"{CDX}?url={page}&from={year}0801&to={year}1130"
           "&output=json&fl=timestamp,digest&filter=statuscode:200")  # 200 = saved without error
    text = fetch(url)
    if text is None:
        return None
    rows = json.loads(text)[1:]          # JSON list of rows; row 0 is the column names
    seen, keep = set(), []
    for timestamp, digest in rows:
        if digest not in seen:           # skip exact repeats of a version we already have
            seen.add(digest)
            keep.append(timestamp)
    return keep


def replay_url(page, timestamp):
    """Address of one saved copy, raw (id_ = without the archive's toolbar)."""
    return f"https://web.archive.org/web/{timestamp}id_/{page}"


if __name__ == "__main__":
    page = "https://apply.uga.edu/portal/fairs"
    for year in (2022, 2023):
        stamps = captures(page, year)
        print(year, "->", stamps)
