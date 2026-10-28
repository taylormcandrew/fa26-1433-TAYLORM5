"""Download Census ACS race/ethnicity counts for every ZIP Code Tabulation Area (ZCTA)
and compute each ZIP's URM share. Used for the ZIP-level robustness outcome.

Source: ACS 5-year estimates, 2017-2021 (config.ACS_YEAR), via the Census API.
  B03002  Hispanic or Latino origin by race (all ages):
          URM = non-Hispanic Black (004) + non-Hispanic AIAN (005)
                + non-Hispanic NHPI (007) + Hispanic of any race (012); total = 001
  B01001* Sex by age, by race group, ages 15-19:
          URM ~= Black alone (B) + AIAN alone (C) + NHPI alone (E) + Hispanic (I).
          These groups can overlap (e.g. a Hispanic AIAN teen is counted twice),
          so this version is approximate and capped at 1.

The raw download is saved to data/raw/acs_zcta_<year>.csv and reused on later
runs, so the analysis does not depend on the API after the first run.
An API key is optional for one request; if you have one, set CENSUS_API_KEY.

Output: data/intermediate/zip_demographics.csv
        columns zip, pop_all, urm_share_all, pop_15_19, urm_share_15_19
"""

import json
import os
import urllib.parse
import urllib.request

import pandas as pd

import config

ALL_AGES = {"B03002_001E": "pop_all", "B03002_004E": "nh_black", "B03002_005E": "nh_aian",
            "B03002_007E": "nh_nhpi", "B03002_012E": "hispanic"}
# Male 15-17, 18-19 are lines 006, 007; female 15-17, 18-19 are 021, 022 in the
# race-specific tables and 030, 031 in the all-races table.
TEEN_TOTAL = ["B01001_006E", "B01001_007E", "B01001_030E", "B01001_031E"]
TEEN_URM = [f"B01001{g}_{n}E" for g in "BCEI" for n in ("006", "007", "021", "022")]


def api_url():
    variables = ["NAME", *ALL_AGES, *TEEN_TOTAL, *TEEN_URM]
    params = {"get": ",".join(variables), "for": "zip code tabulation area:*"}
    if os.environ.get("CENSUS_API_KEY"):
        params["key"] = os.environ["CENSUS_API_KEY"]
    return f"https://api.census.gov/data/{config.ACS_YEAR}/acs/acs5?" + urllib.parse.urlencode(params)


def download():
    """Fetch from the Census API, or read a copy saved by hand from a browser
    (data/raw/acs_zcta_<year>.json). Returns None if neither works."""
    manual = config.ACS_RAW.with_suffix(".json")
    if manual.exists():
        print(f"  reading {manual.relative_to(config.ROOT)} (saved from a browser)")
        rows = json.loads(manual.read_text())
    else:
        print(f"  downloading ACS {config.ACS_YEAR} 5-year ZCTA data from the Census API ...")
        try:
            with urllib.request.urlopen(api_url(), timeout=120) as r:
                rows = json.loads(r.read().decode())
        except Exception as e:
            print(f"WARNING: Census download failed ({e}). The ZIP-level outcome will be empty; "
                  f"everything else still runs. To get the data, open this link in a browser and save "
                  f"the page as {manual.relative_to(config.ROOT)}:\n  {api_url()}")
            return None
    raw = pd.DataFrame(rows[1:], columns=rows[0])
    raw.to_csv(config.ACS_RAW, index=False)
    print(f"  saved {len(raw):,} ZCTAs to {config.ACS_RAW.relative_to(config.ROOT)}")
    return raw


def main():
    raw = pd.read_csv(config.ACS_RAW, dtype=str) if config.ACS_RAW.exists() else download()
    if raw is None:
        return

    num = raw.drop(columns=["NAME", "zip code tabulation area"]).apply(pd.to_numeric, errors="coerce")
    num = num.where(num >= 0)          # Census uses large negative codes for missing values
    out = pd.DataFrame({"zip": raw["zip code tabulation area"].str.zfill(5)})

    out["pop_all"] = num["B03002_001E"]
    urm_all = num[["B03002_004E", "B03002_005E", "B03002_007E", "B03002_012E"]].sum(axis=1)
    out["urm_share_all"] = (urm_all / out["pop_all"]).where(out["pop_all"] > 0)

    out["pop_15_19"] = num[TEEN_TOTAL].sum(axis=1)
    urm_teen = num[TEEN_URM].sum(axis=1)
    out["urm_share_15_19"] = (urm_teen / out["pop_15_19"]).where(out["pop_15_19"] > 0).clip(upper=1)

    out.to_csv(config.ZIP_DEMOGRAPHICS, index=False)
    print(f"Wrote {len(out):,} ZIPs to {config.ZIP_DEMOGRAPHICS.relative_to(config.ROOT)} "
          f"(median URM share, all ages: {out['urm_share_all'].median():.2f})")


if __name__ == "__main__":
    main()
