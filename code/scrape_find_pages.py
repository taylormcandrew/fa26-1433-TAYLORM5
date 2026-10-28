"""Step 1 of scraping: find archived pages that look like admissions travel schedules.

For each university in data/manual/scrape_targets.csv (univ_id, name, domain), this
asks the Wayback Machine for every archived URL on that domain (including subdomains
such as apply.colorado.edu or slate.<school>.edu) whose address contains a travel
keyword (config.SCRAPE_URL_KEYWORDS), then counts how many distinct versions of each
page were saved in each recruitment cycle.

Output: output/scrape_candidate_pages.csv, one row per candidate URL, with
        snapshots per cycle (snap_2021 ... snap_2025). Open each promising URL in a
        browser, and copy the real travel schedules into data/manual/travel_pages.csv.

A page is only useful for the difference-in-differences if it has snapshots in BOTH
pre-SFFA cycles (2021, 2022) and post cycles (2023+).

Usage:  python code/scrape_find_pages.py            (all targets)
        python code/scrape_find_pages.py cu_boulder (one university)
"""

import sys

import pandas as pd

import config
from scrape_common import cdx, session


def cycle_of(ts):
    y, m = int(ts[:4]), int(ts[4:6])
    return y if m >= 8 else y - 1


def find_for_domain(s, domain):
    keywords = "|".join(config.SCRAPE_URL_KEYWORDS)
    rows = cdx(s, url=domain, matchType="domain", collapse="urlkey",
               fl="urlkey,original,timestamp", limit=5000,
               filter=["statuscode:200", "mimetype:text/html", f"original:(?i).*({keywords}).*"],
               **{"from": config.SCRAPE_FROM, "to": config.SCRAPE_TO})
    return pd.DataFrame(rows)


def score(url):
    u = url.lower()
    strong = ["travel", "on-the-road", "near-you", "nearyou", "in-your-area", "counselor-visit",
              "high-school-visit", "hsvisit"]
    s = 3 * sum(k in u for k in strong) + sum(k in u for k in config.SCRAPE_URL_KEYWORDS)
    s += 2 * ("/portal/" in u or "/register/" in u)      # Slate pages
    s -= 3 * any(k in u for k in ("campus-visit", "visit-campus", "virtual-tour", "tour",
                                  "/news/", "/blog/", ".pdf", "athletics", "alumni"))
    return s


def snapshot_counts(s, original):
    # collapse=digest keeps only snapshots whose content changed: those are the useful ones
    rows = cdx(s, url=original, fl="timestamp", filter=["statuscode:200"], collapse="digest",
               **{"from": config.SCRAPE_FROM, "to": config.SCRAPE_TO})
    counts = {}
    for r in rows:
        c = cycle_of(r["timestamp"])
        counts[c] = counts.get(c, 0) + 1
    return counts


def main():
    targets = pd.read_csv(config.SCRAPE_TARGETS)
    if len(sys.argv) > 1:
        targets = targets[targets["univ_id"].isin(sys.argv[1:])]
    s = session()
    out = []
    for _, t in targets.iterrows():
        print(f"{t['univ_id']}: searching archived URLs on {t['domain']} ...")
        found = find_for_domain(s, t["domain"])
        if found.empty:
            print("  nothing archived with travel keywords")
            continue
        found["score"] = found["original"].map(score)
        found = found[found["score"] > 0].sort_values("score", ascending=False).head(25)
        print(f"  {len(found)} candidate pages; counting snapshots ...")
        for _, f in found.iterrows():
            counts = snapshot_counts(s, f["original"])
            row = {"univ_id": t["univ_id"], "url": f["original"], "score": f["score"]}
            for c in range(config.FIRST_CYCLE, config.LAST_CYCLE + 1):
                row[f"snap_{c}"] = counts.get(c, 0)
            row["has_pre_and_post"] = (row.get("snap_2021", 0) + row.get("snap_2022", 0) > 0
                                       and sum(row.get(f"snap_{c}", 0) for c in range(2023, 2026)) > 0)
            out.append(row)

    if not out:
        print("No candidate pages found.")
        return
    res = pd.DataFrame(out).sort_values(["univ_id", "has_pre_and_post", "score"],
                                        ascending=[True, False, False])
    config.SCRAPE_CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(config.SCRAPE_CANDIDATES, index=False)
    good = res.groupby("univ_id")["has_pre_and_post"].any()
    print(f"\nWrote {config.SCRAPE_CANDIDATES.relative_to(config.ROOT)}")
    print(f"Universities with at least one page archived before AND after SFFA: "
          f"{int(good.sum())} of {len(good)}")


if __name__ == "__main__":
    main()
