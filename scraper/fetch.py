"""fetch.py: download a web page once and keep a copy on disk.

Every page is saved in scraper/cache/. If we ask for the same URL again, we read the saved
copy instead of downloading it again. This (1) is polite to the Wayback Machine,
(2) makes reruns fast, and (3) keeps the exact pages our data came from (our evidence).
"""
import hashlib
import time
from pathlib import Path

import requests

CACHE = Path(__file__).parent / "cache"   # folder for saved pages, next to this file
CACHE.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "MIT 14.33 student research (taylorm5@mit.edu)"}  # say who we are


def fetch(url):
    """Return the text of `url`, or None if it could not be downloaded."""
    # File name = a short fingerprint of the URL (URLs contain characters files can't have).
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")
    if path.exists():                                   # already downloaded: reuse it
        return path.read_text(encoding="utf-8")

    for attempt in range(3):                            # try up to 3 times
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                path.write_text(r.text, encoding="utf-8")   # save for next time
                time.sleep(1.5)                             # pause: don't overload the archive
                return r.text
            print(f"  HTTP {r.status_code} for {url}")
            if r.status_code == 404:                    # page doesn't exist: no point retrying
                return None
        except requests.RequestException as err:       # timeout, no connection, ...
            print(f"  {type(err).__name__} for {url}")
        time.sleep(10 * (attempt + 1))                  # wait longer before each retry
    return None                                         # gave up: a failure, NOT "no events"


if __name__ == "__main__":
    # Test: download UGA's event page as the archive saved it on Oct 1, 2022.
    # "id_" after the timestamp asks for the original page, without the archive's toolbar.
    url = "https://web.archive.org/web/20221001081826id_/https://apply.uga.edu/portal/fairs"
    html = fetch(url)
    print("downloaded" if html else "failed", len(html or ""), "characters")
    print(html[html.find("<title>"):html.find("</title>") + 8] if html else "")
