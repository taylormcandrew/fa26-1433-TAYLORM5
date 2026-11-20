"""summary_stats.py: paper-ready summary tables for the data section.

Reads the files build_panel.py made (data/derived/visits_clean.csv) and writes to output/tables/:

  table1_sample.csv          Table 1: one row per university in the regression (group, source,
                             cycles, visits, match rate, URM share of visited schools before and
                             after SFFA, and the ratio of the two = the main outcome after SFFA)
  table2_by_group.csv        Table 2: treatment vs control, before vs after SFFA, with changes
  summary_tables.html        both tables, formatted with titles and notes. Open it in a
                             browser, select a table, copy, and paste into Google Docs.

and to output/figures/:
  hist_urm_visits.png        Figure: URM share of the high schools visited, before vs after
                             SFFA, one panel per group (each bar = share of that period's visits)
  hist_urm_baseline.png      Figure: each university's pre-SFFA mean URM share, by group (why
                             the main outcome measures each university against its own baseline)

Run from the project folder after ./run.sh:   python3 code/summary_stats.py
"""
import matplotlib
import numpy as np
import pandas as pd

import config

matplotlib.use("Agg")                      # draw to files, no window
import matplotlib.pyplot as plt  # noqa: E402

v = pd.read_csv(config.VISITS_CLEAN, low_memory=False)           # one row per event
unis = pd.read_csv(config.UNIVERSITIES, dtype={"exposed": int})
v = v[v["cycle"].between(config.FIRST_CYCLE, config.LAST_CYCLE)]  # same cycles as the regression
# (the visit file's own `state` column is the high school's state, so rename the university's)
v = v.merge(unis[["univ_id", "name", "state", "exposed", "complete_records"]]
            .rename(columns={"state": "univ_state"}), on="univ_id")
v["group"] = v["exposed"].map({1: "Treatment", 0: "Control"})
v["post"] = v["cycle"] >= config.FIRST_POST_CYCLE
visits = v[v["eligible"]]                                          # school visits
m = visits[visits["matched"]]                                      # ... matched to an NCES school
# The regression needs matched visits both before and after SFFA (before = the baseline)
both = m.groupby("univ_id")["post"].nunique()
in_sample = set(both[both == 2].index)
dropped = sorted(set(v["name"]) - set(v.loc[v["univ_id"].isin(in_sample), "name"]))
v, visits, m = [d[d["univ_id"].isin(in_sample)] for d in (v, visits, m)]
m = m.assign(index=m["urm_share"] / m["pre_mean"])                 # main outcome, per visit
T = config.URM_THRESHOLD                                           # 0.5, robustness outcome
ALL = set(range(config.FIRST_CYCLE, config.LAST_CYCLE + 1))


def cycles(c):
    """Cycles a university is observed in: 'all 5', or start years like '2021, 2022, 2024'."""
    c = set(c)
    return f"all {len(ALL)}" if c == ALL else ", ".join(str(y) for y in sorted(c))


# ---- Table 1: one row per university ------------------------------------------------------
t1 = v.groupby("univ_id").agg(University=("name", "first"), State=("univ_state", "first"),
                              Group=("group", "first"), Records=("complete_records", "first"),
                              Cycles=("cycle", cycles))
t1["Source"] = t1.pop("Records").map({1: "Records request", 0: "Public calendar"})
t1["School visits"] = visits.groupby("univ_id").size()
t1["Matched"] = m.groupby("univ_id").size()
t1["Match rate"] = (t1["Matched"] / t1["School visits"]).round(2)
urm = m.groupby(["univ_id", "post"])["urm_share"].mean().unstack()
t1["URM share before"] = urm[False].round(3)
t1["URM share after"] = urm[True].round(3)
t1["After / before"] = (urm[True] / urm[False]).round(3)           # main outcome, post-SFFA
t1 = t1.sort_values(["Group", "School visits"], ascending=[False, False]).reset_index(drop=True)

# ---- Table 2: treatment vs control, before vs after, with the change ----------------------
rows = []
for g in ["Treatment", "Control"]:
    pre, post = [m[(m["group"] == g) & (m["post"] == p)] for p in (False, True)]
    n_univ = m.loc[m["group"] == g, "univ_id"].nunique()
    rows.append([f"{g} ({n_univ} universities): matched visits", f"{len(pre):,}", f"{len(post):,}", ""])
    for label, col, f in [("URM share relative to own pre-SFFA mean (main outcome)", "index", "mean"),
                          ("Mean URM share of visited schools", "urm_share", "mean"),
                          (f"Share of visits to schools >{T:.0%} URM", "urm_share", lambda s: (s > T).mean())]:
        a, b = pre[col].agg(f), post[col].agg(f)
        rows.append([f"   {label}", f"{a:.3f}", f"{b:.3f}", f"{b - a:+.3f}"])
t2 = pd.DataFrame(rows, columns=["", "Before SFFA", "After SFFA", "Change"])
# Raw difference in differences in the main outcome: (treatment change) - (control change)
dd = float(t2.iloc[1, 3]) - float(t2.iloc[5, 3])

first, last = config.FIRST_CYCLE, config.LAST_CYCLE
span = f"{first}-{str(first + 1)[-2:]} to {last}-{str(last + 1)[-2:]}"
note1 = (f"Universities with matched high school visits both before and after SFFA; recruitment "
         f"cycles run August-July and are labeled by start year (2021 = 2021-22), {span}. School "
         f"visits exclude fairs, regional and virtual events. Matched = linked to a high school in "
         f"the NCES Common Core of Data or Private School Survey. URM share = share of the school's "
         f"students who are Black, Hispanic, American Indian/Alaska Native, or Native "
         f"Hawaiian/Pacific Islander, averaged over matched visits. After / before = the main "
         f"outcome after SFFA (each university's pre-SFFA value is 1)."
         + (f" Not in the sample (no matched visits before and after SFFA): {', '.join(dropped)}."
            if dropped else ""))
note2 = (f"Matched school visits, {span}; before SFFA = cycles {first}-{str(first + 1)[-2:]} and "
         f"{config.FIRST_POST_CYCLE - 1}-{str(config.FIRST_POST_CYCLE)[-2:]}. The main outcome divides "
         f"each visited school's URM share by the visiting university's pre-SFFA mean, so it is 1 "
         f"before SFFA by construction. Raw difference in differences in the main outcome: {dd:+.3f}. "
         f"These are visit-weighted averages that do not account for which universities are "
         f"observed in each cycle; the regression does, through university and cycle fixed effects.")
summary = (f"{len(v):,} events; {len(visits):,} school visits, of which {len(m):,} "
           f"({len(m) / len(visits):.1%}) matched; {t1.shape[0]} universities "
           f"({(t1['Group'] == 'Treatment').sum()} treatment, {(t1['Group'] == 'Control').sum()} control; "
           f"{(t1['Source'] == 'Records request').sum()} from records requests).")

# ---- Save: CSVs (for Google Sheets) and one formatted HTML page (for Google Docs) ---------
t1.to_csv(config.TABLES / "table1_sample.csv", index=False)
t2.to_csv(config.TABLES / "table2_by_group.csv", index=False)
style = ("body{font-family:Georgia,serif;max-width:1100px;margin:2em auto}"
         "table{border-collapse:collapse;margin:.5em 0;font-size:13px}"
         "th,td{padding:4px 8px;border-bottom:1px solid #ccc;text-align:right}"
         "th:first-child,td:first-child{text-align:left}th{border-bottom:2px solid #000}"
         "p.note{font-size:12px;color:#444;max-width:1000px}")
html = (f"<html><head><meta charset='utf-8'><style>{style}</style></head><body>"
        f"<h3>Table 1. Sample by university</h3>{t1.to_html(index=False, na_rep='')}"
        f"<p class='note'>Notes: {note1}</p>"
        f"<h3>Table 2. URM composition of visited high schools, before and after SFFA</h3>"
        f"{t2.to_html(index=False)}<p class='note'>Notes: {note2}</p>"
        f"<p class='note'>{summary}</p></body></html>")
(config.TABLES / "summary_tables.html").write_text(html, encoding="utf-8")

# ---- Figures: histograms of URM share -----------------------------------------------------
COLORS = {False: "#9aa0a6", True: "#c0392b"}                  # before = grey, after = red
BINS = np.linspace(0, 1, 21)                                   # 5-point-wide URM-share bins


def style(ax, title):
    ax.set_title(title, fontsize=9, loc="left")
    ax.set_xlabel("URM share of high school", fontsize=8)
    ax.tick_params(labelsize=7)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


# Figure A: every matched visit's school URM share, before vs after, one panel per group.
# Bars are shares of that group's visits in that period, so before and after are comparable
# even though there are three post-SFFA cycles and two pre-SFFA cycles.
fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), dpi=200, sharey=True)
for ax, g in zip(axes, ["Treatment", "Control"]):
    for post, label in [(False, "Before SFFA"), (True, "After SFFA")]:
        x = m.loc[(m["group"] == g) & (m["post"] == post), "urm_share"]
        ax.hist(x, bins=BINS, weights=np.full(len(x), 1 / len(x)), histtype="step", lw=1.6,
                color=COLORS[post], label=f"{label} (mean {x.mean():.3f})")
        ax.axvline(x.mean(), color=COLORS[post], lw=1, ls="--")      # period mean
    style(ax, f"{g} ({m.loc[m['group'] == g, 'univ_id'].nunique()} universities)")
    ax.legend(frameon=False, fontsize=7)
axes[0].set_ylabel("Share of matched visits", fontsize=8)
fig.tight_layout()
fig.savefig(config.FIGURES / "hist_urm_visits.png")
plt.close(fig)

# Figure B: one value per university, its pre-SFFA mean URM share (the outcome's baseline)
base = m.groupby(["univ_id", "group"])["pre_mean"].first().reset_index()
fig, ax = plt.subplots(figsize=(5, 3), dpi=200)
ax.hist([base.loc[base["group"] == g, "pre_mean"] for g in ["Treatment", "Control"]],
        bins=np.linspace(0, 0.8, 17), color=["#2c6fbb", "#e69f00"], label=["Treatment", "Control"])
style(ax, "Pre-SFFA baseline by university")
ax.set_xlabel("University's mean URM share of visited schools before SFFA", fontsize=8)
ax.set_ylabel("Universities", fontsize=8)
ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))   # whole universities
ax.legend(frameon=False, fontsize=7)
fig.tight_layout()
fig.savefig(config.FIGURES / "hist_urm_baseline.png")
plt.close(fig)

print("Table 1. Sample by university\n" + t1.to_string(index=False))
print("\nTable 2. URM composition of visited high schools, before and after SFFA\n" + t2.to_string(index=False))
print(f"\n{summary}\nRaw difference in differences (main outcome): {dd:+.3f}")
print("\nSaved output/tables/table1_sample.csv, table2_by_group.csv and summary_tables.html")
print("Saved output/figures/hist_urm_visits.png and hist_urm_baseline.png")
