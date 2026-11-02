"""Match standardized visits to high-school demographics and build the panel.

Input:  data/derived/visits_standardized.csv (from code/standardize.py)

Steps
  1. Keep events from Aug 2021 through Jul 2026; drop exact duplicates.
  2. Mark eligible events (category in config.ELIGIBLE_CATEGORIES).
  3. Match each event to a high school, trying in order:
       NCES ID in the file -> hand-coded crosswalk -> name + ZIP -> name + city + state
       -> name unique within state -> closest name within the same ZIP
       -> (no location given) name unique in the university's home state, then nationally
  4. Attach the URM share of residents in each visit's ZIP (Census ACS).
  5. Aggregate to university x cycle and university x semester:
       y_50     = eligible visits to schools with URM share > 50% / matched eligible visits
       y_zip_50 = eligible visits in ZIPs with resident URM share > 50% / visits with ZIP data

Outputs
  data/derived/visits_clean.csv    one row per event with its match (check match_method)
  data/derived/panel_cycle.csv     one row per university x recruitment cycle
  data/derived/panel_semester.csv  one row per university x semester
  output/unmatched_schools.csv          schools to hand-code into data/manual/hs_crosswalk.csv
"""

import difflib
import re
import sys

import pandas as pd

import config

THRESHOLDS = sorted({config.URM_THRESHOLD, *config.ROBUST_THRESHOLDS})
FUZZY_MIN = 0.80   # minimum name similarity for a same-ZIP fuzzy match
GENERIC_WORDS = {"jr", "sr", "senior", "junior", "middle", "upper", "secondary", "academy",
                 "prep", "college", "catholic", "charter", "magnet", "regional", "township", "day",
                 "and", "at", "for", "campus", "state", "inc", "ltd", "academic", "visit"}


def ycol(t):
    return f"y_{round(t * 100)}"


def norm_text(s):
    if pd.isna(s):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s).lower())).strip()


def norm_name(s):
    """Lower-case a school name and collapse common variants so names match across sources:
    'Coral Gables Senior HS' and 'CORAL GABLES SENIOR HIGH SCHOOL' -> 'coral gables sr hs'."""
    if pd.isna(s):
        return ""
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"\bst\b\.?\s*", "saint ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\bjunior\b", "jr", s)
    s = re.sub(r"\bsenior\b", "sr", s)
    s = re.sub(r"\b(high school|high sch|high schol|hs|h s|high)\b", " hs ", s)
    s = re.sub(r"\bsch\b", "school", s)
    s = re.sub(r"\b(preparatory)\b", "prep", s)
    s = re.sub(r"\b(the|school|of)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_id(s):
    """Strip an ID; pad all-digit NCES IDs to 12 digits (Excel often drops leading zeros)."""
    if pd.isna(s) or str(s).strip() == "":
        return pd.NA
    s = str(s).strip().removesuffix(".0")
    return s.zfill(12) if s.isdigit() else s


def add_timing(v):
    yr, mo = v["date"].dt.year, v["date"].dt.month
    v["cycle"] = yr.where(mo >= 8, yr - 1)
    v["semester"] = yr.astype(str) + mo.ge(8).map({True: "F", False: "S"})
    v["sem_index"] = (yr - config.FIRST_CYCLE) * 2 + mo.ge(8).astype(int) - 1   # 2021F = 0
    keep = v["cycle"].between(config.FIRST_CYCLE, config.LAST_CYCLE)
    print(f"  {(~keep).sum():,} events outside cycles {config.FIRST_CYCLE}-{config.LAST_CYCLE} dropped")
    return v[keep].copy()


def lookup(v, todo, table, keys, method):
    """Fill nces_id for rows in `todo` using an exact match on `keys` against a unique-key table."""
    t = table.drop_duplicates(keys, keep=False).set_index(keys)["nces_id"]
    hit = pd.Series(t.reindex(pd.MultiIndex.from_frame(v[keys])).to_numpy(), index=v.index)
    ok = todo & v["nces_id"].isna() & hit.notna()
    for k in keys:   # don't match on empty keys
        ok &= v[k].ne("")
    v.loc[ok, "nces_id"], v.loc[ok, "match_method"] = hit[ok], method


def fuzzy_within(v, hs, keys, label, min_score=FUZZY_MIN, strip_city=False):
    """Closest name among schools sharing `keys` (the same ZIP, or the same city + state).
    With strip_city, words of the city name are removed from both names before comparing,
    so "Santa Barbara Area" is not matched to "Santa Barbara High" just for sharing a city."""
    ok_hs = hs[(hs[keys] != "").all(axis=1)]
    groups = {k if isinstance(k, tuple) else (k,): g for k, g in ok_hs.groupby(keys)}
    rows = v.index[v["nces_id"].isna() & (v[keys] != "").all(axis=1) & v["name_n"].ne("")]
    for i in rows:
        cand = groups.get(tuple(v.loc[i, keys]))
        if cand is None:
            continue
        city_words = set(v.at[i, "city_n"].split())

        def clean(n):
            return " ".join(w for w in n.split() if w not in city_words) if strip_city else n

        name = clean(v.at[i, "name_n"])
        if strip_city and not (set(name.split()) - {"hs"}):
            continue                               # the name is just the city: too ambiguous
        scores = cand["name_n"].map(lambda n: difflib.SequenceMatcher(None, clean(n), name).ratio())
        best = scores.idxmax()
        if (scores == scores[best]).sum() > 1:     # tie between schools: leave for hand-coding
            continue
        cname = clean(cand.at[best, "name_n"])
        # One name's words are all inside the other's, and every extra word is either
        # generic ("senior", "jr", "charter", ...), a number, a single initial, or part of
        # the city name: "Pueblo East HS" (Pueblo) = "East High School", "Limon" =
        # "Limon Junior-Senior High School". This rejects "Avon Old Farms" -> "Avon High"
        # and "Dwight-Englewood" -> "Dwight Morrow High".
        w1, w2 = set(name.split()) - {"hs"}, set(cname.split()) - {"hs"}
        contained = False
        if w1 and w2 and (w1 <= w2 or w2 <= w1):
            extra = (w1 | w2) - (w1 & w2)
            contained = all(w in GENERIC_WORDS or w in city_words or w.isdigit() for w in extra)
        if scores[best] >= min_score or contained:
            v.at[i, "nces_id"] = cand.at[best, "nces_id"]
            v.at[i, "match_method"] = f"{label}:{scores[best]:.2f}"


def match_schools(v, unis):
    if config.HIGH_SCHOOLS.exists():
        hs = pd.read_csv(config.HIGH_SCHOOLS, dtype={"nces_id": str, "zip": str})
    else:
        print("  no high-school demographics yet: skipping school matching (school-level outcome empty)")
        hs = pd.DataFrame(columns=["nces_id", "school_name", "city", "state", "zip", "urm_share"], dtype=str)
        hs["urm_share"] = hs["urm_share"].astype(float)
    if "zip" not in hs.columns:
        hs["zip"] = ""
    hs["nces_id"] = hs["nces_id"].map(norm_id)
    hs["name_n"], hs["city_n"], hs["state_n"] = (
        hs["school_name"].map(norm_name), hs["city"].map(norm_text), hs["state"].map(norm_text))
    hs["zip"] = hs["zip"].fillna("").str[:5]

    v["name_n"], v["city_n"], v["state_n"] = (
        v["school_name"].map(norm_name), v["city"].map(norm_text), v["state"].map(norm_text))
    v["zip"] = v["zip"].fillna("").astype(str).str[:5]
    v["nces_id"] = v["nces_id"].map(norm_id)
    v["match_method"] = pd.Series(pd.NA, index=v.index, dtype="string")
    v.loc[v["nces_id"].notna(), "match_method"] = "nces_id_in_file"
    todo = v["eligible"] | v["eligible_alt"]

    # 1. Hand-coded crosswalk: columns school_name, city, state, nces_id (city/state may be
    #    blank). Use nces_id = EXCLUDE for records that are not high schools.
    if config.MANUAL_CROSSWALK.exists():
        cw = pd.read_csv(config.MANUAL_CROSSWALK, dtype=str).dropna(subset=["nces_id"])
        cw["nces_id"] = cw["nces_id"].map(norm_id)
        cw["name_n"], cw["city_n"], cw["state_n"] = (
            cw["school_name"].map(norm_name), cw["city"].map(norm_text), cw["state"].map(norm_text))
        t = cw.drop_duplicates(["name_n", "city_n", "state_n"]).set_index(["name_n", "city_n", "state_n"])["nces_id"]
        hit = pd.Series(t.reindex(pd.MultiIndex.from_frame(v[["name_n", "city_n", "state_n"]])).to_numpy(), index=v.index)
        ok = todo & v["nces_id"].isna() & hit.notna()
        v.loc[ok, "nces_id"], v.loc[ok, "match_method"] = hit[ok], "manual_crosswalk"

    # 2-4. Exact name matches, most specific first
    lookup(v, todo, hs, ["name_n", "zip"], "name_zip")
    lookup(v, todo, hs, ["name_n", "city_n", "state_n"], "name_city_state")
    # Name unique within the state: only if the school is in the same 3-digit ZIP area
    # (or the record gives no ZIP), so "Liberty HS, Renton" never lands on a Liberty HS
    # across the state.
    before = v["nces_id"].copy()
    lookup(v, todo, hs, ["name_n", "state_n"], "name_state")
    new_hit = before.isna() & v["nces_id"].notna() & v["match_method"].eq("name_state")
    zip3_hs = v["nces_id"].map(hs.drop_duplicates("nces_id").set_index("nces_id")["zip"]).fillna("").str[:3]
    far = new_hit & v["zip"].ne("") & (zip3_hs != v["zip"].str[:3])
    v.loc[far, ["nces_id", "match_method"]] = pd.NA

    # 5. Closest name among schools in the same ZIP code
    fuzzy_within(v, hs, ["zip"], "fuzzy_zip")
    # Same, within the same city and state (for sources without ZIPs, e.g. scraped pages)
    fuzzy_within(v, hs, ["city_n", "state_n"], "fuzzy_city", min_score=0.90, strip_city=True)

    # 6. No location in the record (often virtual visits): the university's home
    #    state first, then anywhere, only if the name is unique there.
    home = v["univ_id"].map(unis.set_index("univ_id")["state"]).map(norm_text)
    no_loc = v["state_n"].eq("")
    v.loc[no_loc, "state_n"] = home[no_loc]
    lookup(v, todo & no_loc, hs, ["name_n", "state_n"], "name_home_state")
    # Anywhere in the country only for distinctive names (two or more words besides
    # "hs"); "The Benjamin School" or "Marist HS" are too generic to place this way.
    distinctive = v["name_n"].str.replace(r"\bhs\b", "", regex=True).str.split().str.len() >= 2
    lookup(v, todo & no_loc & distinctive, hs, ["name_n"], "name_national_unique")
    v.loc[no_loc, "state_n"] = ""

    v["excluded_by_hand"] = v["nces_id"].eq("EXCLUDE")
    v.loc[v["excluded_by_hand"], ["eligible", "eligible_alt"]] = False
    v = v.merge(hs[["nces_id", "urm_share", "zip"]].drop_duplicates("nces_id")
                .rename(columns={"zip": "school_zip"}),
                on="nces_id", how="left")
    v["matched"] = v["urm_share"].notna()

    need = v[(v["eligible"] | v["eligible_alt"]) & ~v["matched"]]
    unmatched = (need.groupby(["univ_id", "school_name", "city", "state", "zip"], dropna=False)
                 .agg(n_events=("title", "size"), example_title=("title", "first"),
                      main_outcome=("eligible", "any"))
                 .reset_index().sort_values(["main_outcome", "n_events"], ascending=False))
    unmatched["nces_id"] = ""
    unmatched.to_csv(config.UNMATCHED, index=False)

    e = v["eligible"]
    if not hs.empty:
        print(f"  matched {v.loc[e, 'matched'].mean():.1%} of eligible visits")
    print("  match methods (eligible visits):",
          v.loc[e, "match_method"].fillna("unmatched").str.split(":").str[0].value_counts().to_dict())
    print(f"  {unmatched['main_outcome'].sum():,} unmatched schools for the main outcome listed in "
          f"{config.UNMATCHED.relative_to(config.ROOT)}")
    return v.drop(columns=["name_n", "city_n", "state_n"])


def add_zip_demographics(v):
    """ZIP-level URM share for each event: the event's own ZIP, else its matched school's ZIP."""
    v["demo_zip"] = v["zip"].where(v["zip"].ne(""), v["school_zip"].fillna(""))
    if not config.ZIP_DEMOGRAPHICS.exists():
        print("  no zip_demographics.csv; skipping the ZIP-level outcome")
        v["zip_urm_share"] = float("nan")
        return v
    z = pd.read_csv(config.ZIP_DEMOGRAPHICS, dtype={"zip": str}).set_index("zip")[config.ZIP_MEASURE]
    v["zip_urm_share"] = v["demo_zip"].map(z)
    e = v["eligible"]
    print(f"  ZIP demographics found for {v.loc[e, 'zip_urm_share'].notna().mean():.1%} of eligible visits")
    return v


def aggregate(v, unis, time_cols):
    def one(flag, suffix):
        e = v[v[flag]].copy()
        extra = {}
        for t in THRESHOLDS:
            e[ycol(t) + suffix] = (e["urm_share"] > t).where(e["matched"])
        ys = [ycol(t) + suffix for t in THRESHOLDS] if not suffix else [ycol(config.URM_THRESHOLD) + suffix]
        if not suffix:   # ZIP-level outcome for the main set of eligible visits
            zy = "y_zip_" + str(round(config.URM_THRESHOLD * 100))
            e[zy] = (e["zip_urm_share"] > config.URM_THRESHOLD).where(e["zip_urm_share"].notna())
            extra.update({zy: (zy, "mean"), "n_zip": ("zip_urm_share", "count")})
        return (e.groupby(["univ_id", *time_cols])
                .agg(**{f"n_eligible{suffix}": (flag, "size"), f"n_matched{suffix}": ("matched", "sum")},
                     **{y: (y, "mean") for y in ys}, **extra))

    panel = one("eligible", "").join(one("eligible_alt", "_alt"), how="outer").reset_index()
    for c in ["n_eligible", "n_matched", "n_eligible_alt", "n_matched_alt", "n_zip"]:
        panel[c] = panel[c].fillna(0).astype(int)
    panel["match_rate"] = panel["n_matched"] / panel["n_eligible"].where(panel["n_eligible"] > 0)
    panel = panel.merge(unis, on="univ_id", how="left", validate="many_to_one")
    panel["post"] = (panel["cycle"] >= config.FIRST_POST_CYCLE).astype(int)
    panel["post_x_exposed"] = panel["post"] * panel["exposed"]
    return panel


def main():
    unis = pd.read_csv(config.UNIVERSITIES)
    need = ["univ_id", "name", "state", "exposed", "admit_rate_2021", "rep_share_2020", "complete_records"]
    missing = [c for c in need if c not in unis.columns]
    if missing:
        sys.exit(f"data/raw/universities.csv is missing columns {missing}")

    v = pd.read_csv(config.VISITS_STANDARDIZED, dtype=str, parse_dates=["date"])
    unknown = sorted(set(v["univ_id"]) - set(unis["univ_id"]))
    if unknown:
        sys.exit(f"data/raw/universities.csv has no row for {unknown}")

    before = len(v)
    v = v.drop_duplicates()
    print(f"  {before - len(v):,} exact duplicate rows dropped")
    v = add_timing(v)
    v["eligible"] = v["category"].isin(config.ELIGIBLE_CATEGORIES)
    v["eligible_alt"] = v["category"].isin(config.ALT_ELIGIBLE_CATEGORIES)
    print(f"  {v['eligible'].sum():,} of {len(v):,} events are eligible ({', '.join(config.ELIGIBLE_CATEGORIES)})")
    v = match_schools(v, unis)
    v = add_zip_demographics(v)

    v.to_csv(config.VISITS_CLEAN, index=False)
    aggregate(v, unis, ["cycle"]).to_csv(config.PANEL_CYCLE, index=False)
    aggregate(v, unis, ["cycle", "semester", "sem_index"]).to_csv(config.PANEL_SEMESTER, index=False)
    print(f"Wrote {config.PANEL_CYCLE.relative_to(config.ROOT)} and {config.PANEL_SEMESTER.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
