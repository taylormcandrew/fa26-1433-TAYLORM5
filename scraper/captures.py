"""captures.py: list the saved copies of a page in one recruitment cycle.

Does in code what you did in the browser: asks the Wayback Machine's index (the "CDX" API)
for every saved copy of one page during a recruitment cycle (Aug 1 - Jul 31, labeled by the
year it starts, the same way as the regression code), and drops copies identical to one we
already have (same digest = same content).
"""
import json
from urllib.parse import quote

from fetch import fetch

CDX = "https://web.archive.org/cdx/search/cdx"


def captures(page, year):
    """Timestamps of distinct saved copies of `page` from Aug 1 of `year` to Jul 31 of `year`+1.
    Returns None if the archive did not answer (unknown), [] if it has no copies."""
    # quote() turns any ? & = inside the page address into %3F %26 %3D, so they aren't
    # confused with the archive's own settings (a plain address stays unchanged).
    url = (f"{CDX}?url={quote(page, safe=':/')}&from={year}0801&to={year + 1}0731"
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
        print(f"{year}-{year + 1}:", stamps)
