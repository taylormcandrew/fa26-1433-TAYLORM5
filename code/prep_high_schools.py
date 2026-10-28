"""Build one row per high school (public and private) with its URM share.

Inputs (data/raw/nces/)
  elsi_public_2021_22.csv  ElSi table generator export, Public School, 2021-22:
                           school name, 12-digit NCES ID, location city/state/ZIP,
                           lowest/highest grade, total students and counts of
                           AIAN, Hispanic, Black and NHPI students
  pss2122_pu.csv           NCES Private School Survey public-use file, 2021-22
  pss2324_pu.csv           NCES Private School Survey public-use file, 2023-24
                           (used only for private schools missing from 2021-22)

Definitions
  URM share = (American Indian/Alaska Native + Hispanic + Black + Native Hawaiian/
              Pacific Islander students) / total students
  High school = highest grade offered is 12th (or 13th) grade. Public schools whose
              grade span is missing are kept if their name contains "HIGH".
  Public: ElSi marks a missing count with "–". When the school's total is reported,
              a missing count for one group is treated as 0 (these are almost always
              small groups); "‡" (fails NCES quality standards) is treated as missing.
  Private: the PSS reports percentages by race for K-12 students (P_INDIAN, P_HISP,
              P_BLACK, P_PACIFIC). Location ZIP/city (PL_ZIP, PL_CIT) are used when
              given, otherwise the mailing ZIP/city (PZIP, PCITY). Private-school IDs
              are written as "PSS_<PPIN>" so they never collide with public NCES IDs.

Output: data/intermediate/high_schools.csv
        nces_id, school_name, city, state, zip, urm_share, enrollment, source, data_year
"""

import sys

import pandas as pd

import config

COLS = ["nces_id", "school_name", "city", "state", "zip", "urm_share", "enrollment", "source", "data_year"]


def find_col(df, starts):
    hits = [c for c in df.columns if c.startswith(starts)]
    if not hits:
        sys.exit(f"ElSi file has no column starting with '{starts}'. Columns: {list(df.columns)}")
    return hits[0]


def load_public():
    path = config.ELSI_PUBLIC
    # ElSi exports start with a few title lines; find the header row.
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("School Name,"))
    d = pd.read_csv(path, skiprows=header, dtype=str, encoding="utf-8-sig")

    c = {k: find_col(d, s) for k, s in {
        "id": "School ID (12-digit)", "name": "School Name [Public School]",
        "city": "Location City", "state": "Location State Abbr", "zip": "Location ZIP",
        "high": "Highest Grade Offered", "total": "Total Students",
        "aian": "American Indian/Alaska Native Students", "hisp": "Hispanic Students",
        "black": "Black or African American Students", "nhpi": "Nat. Hawaiian or Other Pacific Isl.",
    }.items()}
    d = d[d[c["id"]].notna() & d[c["id"]].str.fullmatch(r"\d{12}")]

    high = d[c["high"]].fillna("")
    unknown_grade = high.isin(["–", "†", "Ungraded", ""])
    is_hs = high.isin(["12th Grade", "13th Grade"]) | (
        unknown_grade & d[c["name"]].str.contains(r"\bHIGH\b", case=False, na=False))
    d = d[is_hs]

    def num(col, missing_as_zero):
        s = d[col].str.strip().replace({"†": None, "‡": None})
        s = s.replace({"–": "0" if missing_as_zero else None})
        return pd.to_numeric(s, errors="coerce")

    total = num(c["total"], missing_as_zero=False)
    parts = [num(c[k], missing_as_zero=True) for k in ("aian", "hisp", "black", "nhpi")]
    urm = sum(parts)
    out = pd.DataFrame({
        "nces_id": d[c["id"]],
        "school_name": d[c["name"]],
        "city": d[c["city"]],
        "state": d[c["state"]].str.strip(),
        "zip": d[c["zip"]].str.strip().str[:5],
        "enrollment": total,
        "urm_share": (urm / total).where(total > 0),
        "source": "public_ccd",
        "data_year": "2021-22",
    })
    out = out[out["urm_share"].notna()]
    print(f"  public: {len(out):,} high schools with demographics (2021-22)")
    return out


def load_private_year(path, year_tag, high_col):
    use = ["PPIN", "PINST", "PCITY", "PSTABB", "PZIP", "PL_CIT", "PL_ZIP", high_col, "NUMSTUDS",
           "P_INDIAN", "P_HISP", "P_BLACK", "P_PACIFIC"]
    d = pd.read_csv(path, dtype=str, encoding="latin-1", usecols=use)
    d = d[pd.to_numeric(d[high_col], errors="coerce") == 17]          # 17 = highest grade is 12th
    pct = d[["P_INDIAN", "P_HISP", "P_BLACK", "P_PACIFIC"]].apply(pd.to_numeric, errors="coerce")
    out = pd.DataFrame({
        "nces_id": "PSS_" + d["PPIN"].str.strip(),
        "school_name": d["PINST"],
        "city": d["PL_CIT"].fillna(d["PCITY"]),
        "state": d["PSTABB"].str.strip(),
        "zip": d["PL_ZIP"].fillna(d["PZIP"]).str.strip().str[:5],
        "enrollment": pd.to_numeric(d["NUMSTUDS"], errors="coerce"),
        "urm_share": pct.sum(axis=1, min_count=1) / 100,
        "source": "private_pss",
        "data_year": year_tag,
    })
    return out[out["urm_share"].notna()]


def load_private():
    frames = []
    for path, tag, high_col in config.PSS_FILES:
        if path.exists():
            frames.append(load_private_year(path, tag, high_col))
        else:
            print(f"  (no {path.relative_to(config.ROOT)})")
    if not frames:
        return None
    # 2021-22 first; later years only for schools not in 2021-22
    priv = pd.concat(frames, ignore_index=True).drop_duplicates("nces_id", keep="first")
    print(f"  private: {len(priv):,} high schools with demographics "
          f"({priv['data_year'].value_counts().to_dict()})")
    return priv


def main():
    parts = []
    if config.ELSI_PUBLIC.exists():
        parts.append(load_public())
    else:
        print(f"WARNING: {config.ELSI_PUBLIC.relative_to(config.ROOT)} not found; no public schools.")
    priv = load_private()
    if priv is not None:
        parts.append(priv)
    if not parts:
        print("WARNING: no NCES files found, so the school-level outcome will be empty. "
              "The ZIP-level outcome still runs.")
        return
    hs = pd.concat(parts, ignore_index=True).drop_duplicates("nces_id")
    hs["urm_share"] = hs["urm_share"].clip(0, 1)
    hs[COLS].to_csv(config.HIGH_SCHOOLS, index=False)
    print(f"Wrote {len(hs):,} high schools to {config.HIGH_SCHOOLS.relative_to(config.ROOT)} "
          f"({(hs['urm_share'] > config.URM_THRESHOLD).mean():.1%} above the "
          f"{config.URM_THRESHOLD:.0%} URM threshold)")


if __name__ == "__main__":
    main()
