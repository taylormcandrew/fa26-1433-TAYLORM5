"""Estimate the difference-in-differences and its robustness checks.

Main specification (university x recruitment cycle, weighted by matched eligible visits):

    Y_it = alpha_i + lambda_t + beta * (Post_t x Exposed_i) + e_it

    Y_it      share of university i's eligible visits in cycle t going to high schools
              with URM share > 50%
    alpha_i   university fixed effects (absorb Exposed_i)
    lambda_t  recruitment-cycle fixed effects (absorb Post_t)
    Exposed_i 1 if the university's state had no race-conscious admissions ban before SFFA

Standard errors are clustered by state. Because there are few states, the table
also reports a wild cluster bootstrap p-value (restricted, Webb weights).

Outputs (always, even with one university)
  output/tables/descriptives.csv
  output/tables/trends_by_university.csv  share by university x cycle
  output/tables/prepost_by_university.csv before/after SFFA within each university (descriptive)
  output/figures/trends.png               exposed vs control universities by cycle
Outputs (once both exposed and control universities are in)
  output/tables/did_results.csv        every specification
  output/tables/did_results.tex        main columns for the paper
  output/tables/event_study_cycle.csv  + output/figures/event_study_cycle.png
  output/tables/event_study_semester.csv + output/figures/event_study_semester.png
"""

import numpy as np
import pandas as pd
from scipy import stats

import config

MAIN_Y = f"y_{round(config.URM_THRESHOLD * 100)}"
ZIP_Y = f"y_zip_{round(config.URM_THRESHOLD * 100)}"
TREAT = "post_x_exposed"
INK, MUTED, GRID = "#1f2328", "#6e7781", "#d0d7de"
SERIES = ["#2a78d6", "#eb6834"]     # exposed, control (validated categorical pair)


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------
def design(df, x_cols, fe_cols):
    """Regressors plus fixed-effect dummies. The first FE gets a full set of
    dummies (it replaces the intercept); later FEs drop one category."""
    parts = []
    for j, fe in enumerate(fe_cols):
        d = pd.get_dummies(df[fe].astype(str), prefix=fe, drop_first=(j > 0), dtype=float)
        parts.append(d)
    parts.append(df[x_cols].astype(float))
    X = pd.concat(parts, axis=1)
    X = X.loc[:, (X.abs().sum() > 0) | X.columns.isin(x_cols)]
    # Drop fixed-effect dummies that are linear combinations of earlier ones
    # (e.g. one tier x cycle dummy per tier when university FE are included).
    # Regressors go last, so if one is absorbed by the fixed effects we stop
    # instead of silently reinterpreting it.
    keep, A = [], np.empty((len(X), 0))
    for c in X.columns:
        trial = np.column_stack([A, X[c].to_numpy()])
        if np.linalg.matrix_rank(trial) > A.shape[1]:
            keep.append(c)
            A = trial
        elif c in x_cols:
            raise np.linalg.LinAlgError(f"{c} is collinear with the fixed effects.")
    fe_keep = [c for c in keep if c not in x_cols]
    return X[list(x_cols) + fe_keep]


def fit(df, y, x_cols, fe_cols, weight=None, cluster=config.CLUSTER, nested_fe=("univ_id",),
        bootstrap=True, rng=None):
    """Weighted least squares with dummy fixed effects and cluster-robust SEs.

    Small-sample adjustment G/(G-1) * (N-1)/(N-K) follows fixest/reghdfe:
    fixed effects nested within clusters (university FE within state) are not
    counted in K.
    """
    d = df.dropna(subset=[y, *x_cols]).reset_index(drop=True)
    X = design(d, x_cols, fe_cols)
    Xa, ya = X.to_numpy(), d[y].to_numpy(float)
    w = d[weight].to_numpy(float) if weight else np.ones(len(d))
    g_codes, g_labels = pd.factorize(d[cluster])
    G, N = len(g_labels), len(d)

    XtWX = Xa.T @ (Xa * w[:, None])
    if np.linalg.matrix_rank(XtWX) < XtWX.shape[0]:
        raise np.linalg.LinAlgError("Regressors are collinear with the fixed effects.")
    M = np.linalg.solve(XtWX, (Xa * w[:, None]).T)          # K x N; beta = M @ y
    beta = M @ ya
    u = ya - Xa @ beta

    n_nested = sum(X.columns.str.startswith(f"{fe}_").sum() for fe in nested_fe if fe in fe_cols)
    K = Xa.shape[1] - n_nested
    adj = G / (G - 1) * (N - 1) / (N - K) if G > 1 else np.nan

    def cluster_se(resid, rows):
        """SE of the coefficients in `rows` for one or many residual vectors (N x B)."""
        resid = resid.reshape(N, -1)
        out = np.zeros((len(rows), resid.shape[1]))
        for g in range(G):
            idx = g_codes == g
            out += (M[rows][:, idx] @ resid[idx]) ** 2
        return np.sqrt(adj * out)

    x_idx = list(range(len(x_cols)))
    se = cluster_se(u, x_idx)[:, 0]
    t = beta[x_idx] / se
    p = 2 * stats.t.sf(np.abs(t), df=max(G - 1, 1))

    res = pd.DataFrame({"coef": beta[x_idx], "se": se, "t": t, "p_cluster": p}, index=x_cols)
    res["p_wild"] = np.nan
    if bootstrap and G >= 4:
        res.loc[x_cols[0], "p_wild"] = wild_bootstrap_p(
            d, y, x_cols, fe_cols, w, g_codes, G, M, cluster_se, abs(t[0]), rng)
    res.attrs.update(N=N, n_univ=d["univ_id"].nunique(), n_states=G)
    return res


def wild_bootstrap_p(d, y, x_cols, fe_cols, w, g_codes, G, M, cluster_se, t_obs, rng):
    """Restricted wild cluster bootstrap (WCR) p-value for H0: coef on x_cols[0] = 0,
    with Webb six-point weights, which behave well with few clusters."""
    rng = rng or np.random.default_rng(config.SEED)
    Xr = design(d, x_cols[1:], fe_cols).to_numpy()            # model with the null imposed
    ya = d[y].to_numpy(float)
    br = np.linalg.lstsq(Xr * np.sqrt(w)[:, None], ya * np.sqrt(w), rcond=None)[0]
    fitted_r, u_r = Xr @ br, ya - Xr @ br

    webb = np.array([-np.sqrt(1.5), -1, -np.sqrt(0.5), np.sqrt(0.5), 1, np.sqrt(1.5)])
    B = config.BOOTSTRAP_REPS
    v = rng.choice(webb, size=(G, B))[g_codes]                 # N x B, constant within cluster
    Y = fitted_r[:, None] + u_r[:, None] * v
    Xa = design(d, x_cols, fe_cols).to_numpy()
    b_star = M @ Y
    U = Y - Xa @ b_star
    t_star = b_star[0] / cluster_se(U, [0])[0]
    return float(np.mean(np.abs(t_star) >= t_obs))


# ---------------------------------------------------------------------------
# Specifications
# ---------------------------------------------------------------------------
def run_specs(full, rng):
    p = full[full["n_matched"] > 0].copy()
    median_admit = p.drop_duplicates("univ_id")["admit_rate_2021"].median()
    p["selective"] = (p["admit_rate_2021"] < median_admit).astype(int)
    p["tier_cycle"] = p["selective"].astype(str) + "_" + p["cycle"].astype(str)
    p["post_x_repshare"] = p["post"] * p["rep_share_2020"]
    p_alt = full[full["n_matched_alt"] > 0]
    p_zip = full[full["n_zip"] > 0]

    base = dict(y=MAIN_Y, x_cols=[TREAT], fe_cols=["univ_id", "cycle"], weight="n_matched")
    specs = [
        ("(1) Main", p, base),
        ("(2) Unweighted", p, {**base, "weight": None}),
        *[(f"(3) URM > {round(t * 100)}%", p, {**base, "y": f"y_{round(t * 100)}"})
          for t in config.ROBUST_THRESHOLDS],
        ("(4) Drop 2023-24 cycle", p[p["cycle"] != config.FIRST_POST_CYCLE], base),
        ("(5) Selectivity tier x cycle FE", p, {**base, "fe_cols": ["univ_id", "tier_cycle"]}),
        ("(6) + Post x GOP vote share 2020", p, {**base, "x_cols": [TREAT, "post_x_repshare"]}),
        ("(7) Complete records only", p[p["complete_records"] == 1], base),
        ("(8) Incl. school-hosted fairs", p_alt,
         {**base, "y": f"{MAIN_Y}_alt", "weight": "n_matched_alt"}),
        ("(9) ZIP-level URM share", p_zip, {**base, "y": ZIP_Y, "weight": "n_zip"}),
    ]

    rows = []
    for name, data, kw in specs:
        if data.empty or data[kw["y"]].isna().all():
            print(f"  {name}: skipped (no data for {kw['y']})")
            continue
        try:
            r = fit(data, rng=rng, **kw)
        except (np.linalg.LinAlgError, ValueError, ZeroDivisionError) as e:
            print(f"  {name}: skipped ({e})")
            continue
        rows.append({"spec": name, "outcome": kw["y"], **r.loc[TREAT].to_dict(), **r.attrs})
        print(f"  {name:<34} beta = {r.loc[TREAT, 'coef']: .3f}  (se {r.loc[TREAT, 'se']:.3f}, "
              f"wild p = {r.loc[TREAT, 'p_wild']:.3f})")
    return pd.DataFrame(rows)


def event_study(panel, time_col, ref, label_col=None):
    p = panel.dropna(subset=[MAIN_Y]).copy()
    periods = sorted(p[time_col].unique())
    others = [k for k in periods if k != ref]
    cols = []
    for k in others:
        c = f"exp_x_{k}"
        p[c] = ((p[time_col] == k) & (p["exposed"] == 1)).astype(int)
        cols.append(c)
    r = fit(p, MAIN_Y, cols, ["univ_id", time_col], weight="n_matched", bootstrap=False)
    out = pd.DataFrame({"period": others, "coef": r["coef"].to_numpy(), "se": r["se"].to_numpy()})
    out = pd.concat([out, pd.DataFrame({"period": [ref], "coef": [0.0], "se": [0.0]})])
    out = out.sort_values("period").reset_index(drop=True)
    if label_col:
        labels = p.drop_duplicates(time_col).set_index(time_col)[label_col]
        out["label"] = out["period"].map(labels)
    else:
        out["label"] = out["period"].map(lambda c: f"{c}-{str(c + 1)[-2:]}")
    crit = stats.t.ppf(0.975, df=max(r.attrs["n_states"] - 1, 1))
    out["ci_low"], out["ci_high"] = out["coef"] - crit * out["se"], out["coef"] + crit * out["se"]
    return out


def plot_event_study(es, ref_label, path, xlabel):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, mark = INK, MUTED, SERIES[0]
    fig, ax = plt.subplots(figsize=(6.5, 3.8), dpi=200)
    x = np.arange(len(es))
    ax.axhline(0, color=muted, lw=1)
    post_start = es.index[es["label"] == ref_label][0] + 0.5
    ax.axvline(post_start, color=muted, lw=1, ls="--")
    ax.text(post_start + 0.08, 0.98, "SFFA (June 2023)", transform=ax.get_xaxis_transform(),
            va="top", fontsize=8, color=muted)
    ax.errorbar(x, es["coef"], yerr=[es["coef"] - es["ci_low"], es["ci_high"] - es["coef"]],
                fmt="o", ms=5, color=mark, ecolor=mark, elinewidth=1.5, capsize=0)
    ax.set_xticks(x, es["label"], fontsize=8, color=ink)
    ax.set_xlabel(xlabel, fontsize=9, color=ink)
    ax.set_ylabel("Exposed - control, share of visits\nto high-URM high schools", fontsize=9, color=ink)
    ax.tick_params(colors=muted, labelsize=8)
    ax.grid(axis="y", color="#d0d7de", lw=0.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(muted)
    ax.set_title(f"Reference period: {ref_label}. Bars are 95% CIs clustered by state.",
                 fontsize=8, color=muted, loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_latex(results, path):
    keep = results[results["spec"].str.match(r"\((1|4|5|6)\)")]
    cols = " & ".join(f"({i + 1})" for i in range(len(keep)))
    lines = [
        r"\begin{tabular}{l" + "c" * len(keep) + "}", r"\hline",
        " & " + cols + r" \\", r"\hline",
        r"Post $\times$ Exposed & " + " & ".join(f"{c:.3f}" for c in keep["coef"]) + r" \\",
        " & " + " & ".join(f"({s:.3f})" for s in keep["se"]) + r" \\",
        "Wild bootstrap $p$ & " + " & ".join(
            "--" if pd.isna(x) else f"{x:.3f}" for x in keep["p_wild"]) + r" \\", r"\hline",
        "University FE & " + " & ".join(["Yes"] * len(keep)) + r" \\",
        "Cycle FE & " + " & ".join(
            "Tier $\\times$ cycle" if "(5)" in s else "Yes" for s in keep["spec"]) + r" \\",
        "Drops 2023--24 & " + " & ".join("Yes" if "(4)" in s else "No" for s in keep["spec"]) + r" \\",
        r"Post $\times$ GOP share & " + " & ".join("Yes" if "(6)" in s else "No" for s in keep["spec"]) + r" \\",
        "Observations & " + " & ".join(str(int(n)) for n in keep["N"]) + r" \\",
        "Universities & " + " & ".join(str(int(n)) for n in keep["n_univ"]) + r" \\",
        "States (clusters) & " + " & ".join(str(int(n)) for n in keep["n_states"]) + r" \\",
        r"\hline", r"\end{tabular}",
    ]
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Descriptive results: these run with any number of universities, including one
# ---------------------------------------------------------------------------
def ols_post(y, post, groups):
    """y = a + b*post, SE clustered by `groups`. Returns (b, se)."""
    X = np.column_stack([np.ones(len(y)), post])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    codes, labels = pd.factorize(groups)
    G, N = len(labels), len(y)
    meat = np.zeros((2, 2))
    for g in range(G):
        s = X[codes == g].T @ u[codes == g]
        meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv * (G / (G - 1)) * ((N - 1) / (N - 2))
    return b[1], np.sqrt(V[1, 1])


def prepost_by_university():
    """Before-after comparison within each university, at the visit level.
    Descriptive only: with no comparison group it cannot separate SFFA from any
    other change over time."""
    v = pd.read_csv(config.VISITS_CLEAN, dtype={"nces_id": str, "demo_zip": str})
    v = v[v["eligible"]]
    v["post"] = (v["cycle"] >= config.FIRST_POST_CYCLE).astype(int)
    rows = []
    outcomes = [("school", "urm_share", "nces_id"), ("zip", "zip_urm_share", "demo_zip")]
    for univ, d in v.groupby("univ_id"):
        for level, share, cluster in outcomes:
            x = d[d[share].notna()]
            if x["post"].nunique() < 2 or x[cluster].nunique() < 3:
                continue
            y = (x[share] > config.URM_THRESHOLD).astype(float).to_numpy()
            b, se = ols_post(y, x["post"].to_numpy(float), x[cluster])
            rows.append({"univ_id": univ, "outcome_level": level,
                         "share_pre": y[x["post"].to_numpy() == 0].mean(),
                         "share_post": y[x["post"].to_numpy() == 1].mean(),
                         "difference": b, "se_clustered": se,
                         "p_value": 2 * stats.norm.sf(abs(b / se)),
                         "visits_pre": int((x["post"] == 0).sum()), "visits_post": int((x["post"] == 1).sum()),
                         "clusters": x[cluster].nunique(), "clustered_by": cluster})
    return pd.DataFrame(rows)


def plot_trends(full, path):
    """Share of visits to high-URM schools (and ZIPs) by cycle, exposed vs control universities."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = [(MAIN_Y, "n_matched", "High schools with >50% URM students"),
              (ZIP_Y, "n_zip", "ZIPs with >50% URM residents")]
    panels = [p for p in panels if full[p[0]].notna().any()]
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels) + 0.6, 3.6), dpi=200,
                             sharey=True, squeeze=False)
    cycles = sorted(full["cycle"].unique())
    labels = {c: f"{c}-{str(c + 1)[-2:]}" for c in cycles}
    groups = [(1, "No prior ban (exposed)", SERIES[0]), (0, "Prior ban (control)", SERIES[1])]
    present = [g for g in groups if (full["exposed"] == g[0]).any()]
    ymax = 0
    for ax, (y, w, title) in zip(axes[0], panels):
        for exp, name, color in present:
            d = full[(full["exposed"] == exp) & full[y].notna() & (full[w] > 0)]
            m = d.groupby("cycle").apply(lambda g: np.average(g[y], weights=g[w]), include_groups=False)
            n = d["univ_id"].nunique()
            ax.plot(m.index, m.values, color=color, lw=2, marker="o", ms=5,
                    label=f"{name}, {n} univ.")
            ymax = max(ymax, m.max())
        ax.axvline(config.FIRST_POST_CYCLE - 0.5, color=MUTED, lw=1, ls="--")
        ax.text(config.FIRST_POST_CYCLE - 0.45, 0.02, "SFFA", transform=ax.get_xaxis_transform(),
                fontsize=8, color=MUTED)
        ax.set_xticks(cycles, [labels[c] for c in cycles], fontsize=7, rotation=0)
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        ax.grid(axis="y", color=GRID, lw=0.5)
        ax.tick_params(colors=MUTED, labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(MUTED)
    axes[0][0].set_ylim(0, min(1, ymax * 1.25 + 0.02))
    axes[0][0].set_ylabel("Share of eligible visits", fontsize=9, color=INK)
    note = "Recruitment cycles run August-July. Means weighted by visits."
    if len(present) > 1:
        axes[0][0].legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.08), ncol=2)
    else:   # one series: name it in the note instead of a legend
        exp, name, _ = present[0]
        note = f"{name}: {full.loc[full['exposed'] == exp, 'univ_id'].nunique()} university. " + note
    fig.text(0.01, 0.01, note, fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def write_descriptives(full):
    cols = ["univ_id", "name", "state", "exposed", "cycle", "n_eligible", "n_matched", "match_rate",
            MAIN_Y, "n_zip", ZIP_Y]
    full[cols].sort_values(["univ_id", "cycle"]).to_csv(config.TABLES / "trends_by_university.csv", index=False)
    plot_trends(full, config.FIGURES / "trends.png")

    pp = prepost_by_university()
    pp.to_csv(config.TABLES / "prepost_by_university.csv", index=False)
    if not pp.empty:
        print("\nBefore vs after SFFA within each university (descriptive, not causal):")
        show = pp[["univ_id", "outcome_level", "share_pre", "share_post", "difference", "se_clustered",
                   "visits_pre", "visits_post"]]
        print(show.round(3).to_string(index=False))


# ---------------------------------------------------------------------------
def main():
    full = pd.read_csv(config.PANEL_CYCLE)
    panel = full[full["n_matched"] > 0]

    desc = (full.groupby(["exposed", "post"])
            .agg(universities=("univ_id", "nunique"), univ_cycles=("univ_id", "size"),
                 mean_visits=("n_eligible", "mean"), match_rate=("match_rate", "mean"),
                 **{MAIN_Y: (MAIN_Y, "mean"), ZIP_Y: (ZIP_Y, "mean")})
            .reset_index())
    desc.to_csv(config.TABLES / "descriptives.csv", index=False)
    print("Descriptives (exposed x post):")
    print(desc.to_string(index=False))
    write_descriptives(full)

    n_states = panel.groupby("exposed")["state"].nunique()
    if panel["exposed"].nunique() < 2 or panel["post"].nunique() < 2:
        print("\nDifference-in-differences not run yet: it needs universities from both "
              "prior-ban and no-ban states. Descriptive tables and output/figures/trends.png "
              "are written; rerun once more universities' records are in.")
        return
    if n_states.min() < 2 or panel["state"].nunique() < 4:
        print("\nWarning: very few states. Clustered SEs and the wild bootstrap are unreliable "
              "until more states are in the sample.")

    rng = np.random.default_rng(config.SEED)
    print("\nDifference-in-differences:")
    results = run_specs(full, rng)
    results.to_csv(config.TABLES / "did_results.csv", index=False)
    write_latex(results, config.TABLES / "did_results.tex")

    es = event_study(panel, "cycle", config.EVENT_STUDY_REF_CYCLE)
    es.to_csv(config.TABLES / "event_study_cycle.csv", index=False)
    ref_label = f"{config.EVENT_STUDY_REF_CYCLE}-{str(config.EVENT_STUDY_REF_CYCLE + 1)[-2:]}"
    plot_event_study(es, ref_label, config.FIGURES / "event_study_cycle.png", "Recruitment cycle (Aug-Jul)")

    sem = pd.read_csv(config.PANEL_SEMESTER)
    sem = sem[sem["n_matched"] > 0]
    ref_idx = sem.loc[sem["semester"] == config.EVENT_STUDY_REF_SEMESTER, "sem_index"]
    if not ref_idx.empty:
        es_s = event_study(sem, "sem_index", int(ref_idx.iloc[0]), label_col="semester")
        es_s.to_csv(config.TABLES / "event_study_semester.csv", index=False)
        plot_event_study(es_s, config.EVENT_STUDY_REF_SEMESTER,
                         config.FIGURES / "event_study_semester.png", "Semester (F = Aug-Dec, S = Jan-Jul)")
    print(f"\nTables in {config.TABLES.relative_to(config.ROOT)}/, figures in {config.FIGURES.relative_to(config.ROOT)}/")


if __name__ == "__main__":
    main()
