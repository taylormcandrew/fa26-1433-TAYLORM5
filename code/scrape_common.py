"""Shared helpers for the scraping scripts: a polite HTTP session and Wayback Machine queries.

Why the Wayback Machine: admissions travel pages only list *upcoming* visits, so
scraping them today cannot recover 2021-2023. The Internet Archive's Wayback
Machine has saved copies ("snapshots") of many of these pages over time. Each
snapshot shows the visits that were upcoming on the day it was saved, so stitching
snapshots together rebuilds a (partial) history of a university's visits.

CDX API docs: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
"""

import time

import requests

import config

CDX = "https://web.archive.org/cdx/search/cdx"
_last_request = [0.0]


def session():
    s = requests.Session()
    who = f" (contact: {config.SCRAPE_CONTACT_EMAIL})" if config.SCRAPE_CONTACT_EMAIL else ""
    s.headers["User-Agent"] = f"14.33 MIT undergraduate research project{who}"
    return s


def polite_get(s, url, params=None, tries=4, timeout=60):
    """GET with a fixed pause between requests and backoff on errors/rate limits."""
    for attempt in range(tries):
        wait = config.SCRAPE_DELAY_SECONDS - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()
        try:
            r = s.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(10 * (attempt + 1))
                continue
            return r                      # 404 etc.: not worth retrying
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
    return None


def cdx(s, **params):
    """Query the Wayback CDX API; returns a list of dicts (one per row)."""
    params = {"output": "json", **params}
    r = polite_get(s, CDX, params=params, timeout=180)
    if r is None or r.status_code != 200 or not r.text.strip():
        return []
    rows = r.json()
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    return [dict(zip(header, row)) for row in body]


def snapshot_url(timestamp, original):
    """Raw archived page (the 'id_' flag returns the page without the Wayback toolbar)."""
    return f"https://web.archive.org/web/{timestamp}id_/{original}"
