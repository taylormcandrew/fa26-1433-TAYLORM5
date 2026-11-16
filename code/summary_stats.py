"""summary_stats.py: paper-ready summary tables for the data section.

Reads the files build_panel.py made (data/derived/visits_clean.csv) and writes to output/tables/:

  table1_sample.csv          Table 1: one row per university (group, source, cycles, visits,
                             match rate, URM measures)
  table2_by_group.csv        Table 2: treatment vs control, before vs after SFFA, with changes
  summary_tables.html        both tables, formatted with titles and notes. Open it in a
                             browser, select a table, copy, and paste into Google Docs.

Run from the project folder after ./run.sh:   python3 code/summary_stats.py
"""
import pandas as pd

import config

v = pd.read_csv(config.VISITS_CLEAN, low_memory=False)           # one row per event
unis = pd.read_csv(config.UNIVERSITIES, dtype={"exposed": int})
v = v[v["cycle"].between(config.FIRST_CYCLE, config.LAST_CYCLE)]  # same cycles as the regression
# (the visit file's own `state` column is the high school's state, so rename the university's)
v = v.merge(unis[["univ_id", "name", "state", "exposed"]].rename(columns={"state": "univ_state"}),
            on="univ_id")
v["group"] = v["exposed"].map({1: "Treatment", 0: "Control"})
v["post"] = v["cycle"] >= config.FIRST_POST_CYCLE
visits = v[v["eligible"]]                                          # school visits (main outcome)
m = visits[visits["matched"]]                                      # ... matched to an NCES school
T = config.URM_THRESHOLD                                           # 0.5
ALL = set(range(config.FIRST_CYCLE, config.LAST_CYCLE + 1))


def cycles(c):
    """Cycles a university is observed in: 'all 5', or start years like '2021, 2022, 2024'."""
    c = set(c)
    return f"all {len(ALL)}" if c == ALL else ", ".join(str(y) for y in sorted(c))


def over(s):
    return (s > T).mean()                                          # share of visits above 50% URM


# ---- Table 1: one row per university ------------------------------------------------------
t1 = v.groupby("univ_id").agg(University=("name", "first"), State=("univ_state", "first"),
                              Group=("group", "first"), Cycles=("cycle", cycles))
t1.insert(3, "Source", ["Records request" if u == "cu_boulder" else "Public calendar"
                        for u in t1.index])
t1["School visits"] = visits.groupby("univ_id").size()
t1["Matched"] = m.groupby("univ_id").size()
t1 = t1.fillna({"School visits": 0, "Matched": 0}).astype({"School visits": int, "Matched": int})
t1 = t1[t1["School visits"] > 0]                                   # fairs-only sources drop out
t1["Match rate"] = (t1["Matched"] / t1["School visits"]).round(2)
t1["Mean URM share"] = m.groupby("univ_id")["urm_share"].mean().round(2)
t1["Share to >50% URM"] = m.groupby("univ_id")["urm_share"].apply(over).round(2)
t1 = t1.sort_values(["Group", "School visits"], ascending=[False, False]).reset_index(drop=True)
dropped = sorted(set(v["name"]) - set(t1["University"]))           # e.g. Berkeley (fairs only)

# ---- Table 2: treatment vs control, before vs after, with the change ----------------------
rows = []
for g in ["Treatment", "Control"]:
    pre, post = [m[(m["group"] == g) & (m["post"] == p)] for p in (False, True)]
    n_univ = visits.loc[visits["group"] == g, "univ_id"].nunique()
    rows.append([f"{g} ({n_univ} universities): matched visits", f"{len(pre):,}", f"{len(post):,}", ""])
    for label, f in [("Share to >50% URM schools", over), ("Mean URM share of visited schools", "mean")]:
        a, b = pre["urm_share"].agg(f), post["urm_share"].agg(f)
        rows.append([f"   {label}", f"{a:.3f}", f"{b:.3f}", f"{b - a:+.3f}"])
t2 = pd.DataFrame(rows, columns=["", "Before SFFA", "After SFFA", "Change"])
# Raw difference in differences: (treatment change) - (control change), share above 50% URM
dd = float(t2.iloc[1, 3]) - float(t2.iloc[4, 3])

first, last = config.FIRST_CYCLE, config.LAST_CYCLE
span = f"{first}-{str(first + 1)[-2:]} to {last}-{str(last + 1)[-2:]}"
note1 = (f"Recruitment cycles run August-July and are labeled by start year (2021 = 2021-22); "
         f"{span}. School visits exclude fairs and virtual events. Matched = linked to a high "
         f"school in the NCES Common Core of Data or Private School Survey. URM share = share of "
         f"the school's students who are Black, Hispanic, American Indian/Alaska Native, or "
         f"Native Hawaiian/Pacific Islander."
         + (f" Excluded for having no school visits: {', '.join(dropped)}." if dropped else ""))
note2 = (f"Matched school visits, {span}. Before SFFA = cycles {first}-{str(first + 1)[-2:]} to "
         f"{config.FIRST_POST_CYCLE - 1}-{str(config.FIRST_POST_CYCLE)[-2:]}. Raw difference in "
         f"differences in the share to >50% URM schools: {dd:+.3f}. This comparison does not "
         f"account for which universities are observed in each cycle; the regression does, "
         f"through university fixed effects.")
summary = (f"{len(v):,} advertised events; {len(visits):,} school visits, of which {len(m):,} "
           f"({len(m) / len(visits):.1%}) matched; {t1.shape[0]} universities.")

# ---- Save: CSVs (for Google Sheets) and one formatted HTML page (for Google Docs) ---------
t1.to_csv(config.TABLES / "table1_sample.csv", index=False)
t2.to_csv(config.TABLES / "table2_by_group.csv", index=False)
style = ("body{font-family:Georgia,serif;max-width:1000px;margin:2em auto}"
         "table{border-collapse:collapse;margin:.5em 0;font-size:14px}"
         "th,td{padding:4px 10px;border-bottom:1px solid #ccc;text-align:right}"
         "th:first-child,td:first-child{text-align:left}th{border-bottom:2px solid #000}"
         "p.note{font-size:12px;color:#444;max-width:900px}")
html = (f"<html><head><meta charset='utf-8'><style>{style}</style></head><body>"
        f"<h3>Table 1. Sample by university</h3>{t1.to_html(index=False, na_rep='')}"
        f"<p class='note'>Notes: {note1}</p>"
        f"<h3>Table 2. Visits to high-URM high schools, before and after SFFA</h3>"
        f"{t2.to_html(index=False)}<p class='note'>Notes: {note2}</p>"
        f"<p class='note'>{summary}</p></body></html>")
(config.TABLES / "summary_tables.html").write_text(html, encoding="utf-8")

print("Table 1. Sample by university\n" + t1.to_string(index=False))
print("\nTable 2. Visits to high-URM high schools, before and after SFFA\n" + t2.to_string(index=False))
print(f"\n{summary}\nRaw difference in differences (share >50% URM): {dd:+.3f}")
print("\nSaved output/tables/table1_sample.csv, table2_by_group.csv and summary_tables.html")
