"""scrape_cu.py: scrape CU Boulder's public event calendar, for validation only.

The regression uses CU Boulder's records-request data. This script collects CU's public
calendar separately, to check whether scraped calendars give similar URM measures to the
real data (compare_cu.py). It reuses the scraper's tools but keeps its own list and output,
so nothing here enters the regression.

Writes validation/output/cu_calendar_events.csv and cu_calendar_coverage.csv.
Run from the project folder:   python3 validation/scrape_cu.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scraper"))     # borrow the scraper's tools
from harvest import YEARS, harvest                   # noqa: E402

PAGE = "https://ugrad.apply.colorado.edu/portal/upcoming-off-campus-events"  # CU's calendar
OUT = HERE / "output"

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    events, coverage = [], []
    for year in YEARS:
        ev, cover = harvest("cub_web", PAGE, "", year)
        print(f"CU calendar {year}-{year + 1}: {cover['events']} events from {cover['copies']} "
              f"copies (first saved {cover['first_saved'] or '-'}) -> {cover['status']}")
        events.append(ev)
        coverage.append(cover)
    pd.concat(events).to_csv(OUT / "cu_calendar_events.csv", index=False)
    pd.DataFrame(coverage).to_csv(OUT / "cu_calendar_coverage.csv", index=False)
    print(f"Wrote {OUT / 'cu_calendar_events.csv'}")
