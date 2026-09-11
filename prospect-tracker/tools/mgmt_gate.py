"""M-MWAR-4: the gate battery for the In-Game Management running-game family.

Runs the four legs frozen in docs/IN_GAME_MANAGEMENT_GATE.md and writes
data/management_gate_eval.json. It REFUSES TO RUN if that document is missing or carries no
frozen_at stamp, because a battery whose policies were chosen after the numbers were seen is
not a battery.

WHAT IT IS ASKING. Not whether the decision pricing is right, which management.py's own tests
cover. Whether the resulting per-agent number is a REPEATABLE PROPERTY OF THE AGENT. A decision
metric that cannot survive a split-half is measuring the schedule.

THE SERIES THAT IS PUBLISHED IS SEASON-CONTROLLED, decided and recorded before this ran. The
raw series correlates at +0.78 across split halves and that is not the agent: season alone
explains 0.7961 of the variance in team-season summed decision value and team identity alone
explains 0.0223. Both halves of a team-season sit in the same season, so a league-wide year
effect reads as split-half agreement. Both series are reported; the raw one carries its
decomposition so a reader who meets the larger number elsewhere can see why it is not the answer.

Offline. Reads .cache/pbp_corpus, .cache/war_daily, data/win_expectancy.json.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GATE_DOC = ROOT / "docs" / "IN_GAME_MANAGEMENT_GATE.md"
OUT = ROOT / "data" / "management_gate_eval.json"

SEED = 20260906
N_PERM = 2000
MIN_HALF = 10

log = logging.getLogger("mgmt_gate")


def frozen_at() -> str:
    """The gate document's freeze stamp, or a refusal."""
    if not GATE_DOC.exists():
        raise FileNotFoundError(
            f"{GATE_DOC} does not exist. The heuristic policy and the choice of "
            "published series must be frozen in writing BEFORE any gate number "
            "is computed; a battery whose policies were chosen after the "
            "numbers were seen is not a battery.")
    txt = GATE_DOC.read_text(encoding="utf-8")
    m = re.search(r"Frozen (\d{4}-\d{2}-\d{2})", txt)
    if not m:
        raise ValueError(
            f"{GATE_DOC} carries no 'Frozen YYYY-MM-DD' stamp, so there is no "
            "evidence its policies predate the numbers.")
    return m.group(1)


def _corr(np, a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _spearman(np, pd, a, b):
    return _corr(np, pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy())


def _icc(np, frame, col, agent="agent"):
    """One-way random-effects ICC with the unequal-group k0 correction."""
    grp = frame.groupby(agent)[col]
    ni = grp.size()
    k, N = len(ni), int(ni.sum())
    if k < 2 or N <= k:
        return float("nan")
    gm = frame[col].mean()
    msb = float(((grp.mean() - gm) ** 2 * ni).sum() / (k - 1))
    msw = float(((frame[col] - frame[agent].map(grp.mean())) ** 2).sum() / (N - k))
    k0 = float((N - (ni ** 2).sum() / N) / (k - 1))
    den = msb + (k0 - 1) * msw
    return float((msb - msw) / den) if den else float("nan")


def _half_split(pd, frame, col):
    f = frame.sort_values(["agent", "game_pk", "at_bat_index"]).copy()
    f["parity"] = f.groupby("agent").cumcount() % 2
    agg = f.groupby(["agent", "parity"])[col].agg(["mean", "sum", "size"]).unstack("parity")
    keep = (agg[("size", 0)] >= MIN_HALF) & (agg[("size", 1)] >= MIN_HALF)
    return agg[keep]


def _leg_split_half(np, pd, df, col, label):
    agg = _half_split(pd, df, col)
    return {
        "series": label,
        "column": col,
        "n_agent_seasons": int(len(agg)),
        "pearson_mean_dv": _corr(np, agg[("mean", 0)], agg[("mean", 1)]),
        "spearman_mean_dv": _spearman(np, pd, agg[("mean", 0)], agg[("mean", 1)]),
        "pearson_sum_dv": _corr(np, agg[("sum", 0)], agg[("sum", 1)]),
        "icc_one_way": _icc(np, df, col),
    }


def _null_band(np, pd, df, col, n_perm=N_PERM):
    """OPPORTUNITY-PRESERVING permutation null.

    Decision value is permuted WITHIN season across all attempts, which holds
    every agent-season's attempt count and every season's mean fixed and
    destroys only the agent-to-value link. A null that reassigns attempt counts
    destroys the structure being tested and produces a band anything clears;
    the census's first reading of this gate was exactly that error.
    """
    rng = np.random.default_rng(SEED)
    vals = df[col].to_numpy(copy=True)
    seasons = df["season"].astype(str).to_numpy()
    idx_by_season = {s: np.where(seasons == s)[0] for s in np.unique(seasons)}
    work = df.copy()
    out = []
    for _ in range(n_perm):
        v = vals.copy()
        for _s, idx in idx_by_season.items():
            v[idx] = rng.permutation(v[idx])
        work["_perm"] = v
        agg = _half_split(pd, work, "_perm")
        out.append(_corr(np, agg[("mean", 0)], agg[("mean", 1)]))
    arr = np.array([x for x in out if x == x])
    return {
        "n_perm": int(len(arr)),
        "lo95": float(np.percentile(arr, 2.5)),
        "hi95": float(np.percentile(arr, 97.5)),
        "mean": float(arr.mean()),
        "construction": (
            "decision value permuted WITHIN season, holding every agent-season's "
            "attempt count and every season mean fixed. A null that reassigns "
            "attempt counts destroys the structure under test and yields a band "
            "anything clears."),
    }


def _leg_placebo(np, pd, df, col, n_perm=400):
    """Shuffle within matched state cells and re-run the split-half.

    If the metric survives a within-state shuffle it is measuring the states an
    agent happened to face rather than what it did in them.
    """
    rng = np.random.default_rng(SEED + 7)
    cell = (df["season"].astype(str) + "|" + df["target"].astype(str) + "|"
            + df["inning"].clip(upper=9).astype(str) + "|"
            + df["outs_before"].astype(str) + "|" + df["base_before"].astype(str))
    df = df.assign(_cell=cell)
    sizes = df.groupby("_cell").size()
    vals = df[col].to_numpy(copy=True)
    work = df.copy()
    out = []
    groups = [np.asarray(v) for v in df.groupby("_cell").indices.values()]
    for _ in range(n_perm):
        v = vals.copy()
        for idx in groups:
            if len(idx) > 1:
                v[idx] = rng.permutation(v[idx])
        work["_perm"] = v
        agg = _half_split(pd, work, "_perm")
        out.append(_corr(np, agg[("mean", 0)], agg[("mean", 1)]))
    arr = np.array([x for x in out if x == x])
    return {
        "n_perm": int(len(arr)),
        "placebo_mean_r": float(arr.mean()),
        "placebo_lo95": float(np.percentile(arr, 2.5)),
        "placebo_hi95": float(np.percentile(arr, 97.5)),
        "n_cells": int(len(sizes)),
        "median_cell_size": int(sizes.median()),
        "degeneracy_warning": (
            "a cell of size 1 cannot be shuffled, so at a thin cell resolution "
            "this test approaches an identity and its band understates the "
            "false-positive rate. The median cell size is published so the "
            "reader can judge that rather than take the band on trust."),
    }


def _leg_persistence(np, pd, df):
    """Year over year on season-demeaned agent numbers.

    A TEAM proxy for manager persistence, and an UPPER BOUND on it: managers
    change and teams do not, so whatever repeats here is at least as much as
    would repeat for a manager.
    """
    ts = df.groupby(["team", "season"], as_index=False).agg(
        n=("dv", "size"), sum_dv=("dv", "sum"), mean_dv=("dv", "mean"))
    ts["season"] = ts["season"].astype(int)
    for c in ("n", "sum_dv", "mean_dv"):
        ts[c + "_d"] = ts[c] - ts.groupby("season")[c].transform("mean")
    nxt = ts.copy()
    nxt["season"] = nxt["season"] - 1
    j = ts.merge(nxt, on=["team", "season"], suffixes=("", "_next"))
    out = {"n_pairs": int(len(j)),
           "is_a_team_proxy_and_an_upper_bound": (
               "managers change and teams do not, so team-season persistence is "
               "an upper bound on manager persistence. A null here cannot be "
               "rescued by attributing to managers instead.")}
    for c in ("n", "sum_dv", "mean_dv"):
        out[f"spearman_{c}"] = _spearman(np, pd, j[c + "_d"], j[c + "_d_next"])
    return out


def _leg_captured_share(np, pd, df, corpus):
    """Captured share under the three NAMED policies, all three published.

    (actual - heuristic) / (optimal - heuristic). The heuristic term is in both
    numerator and denominator, so this quantity can change SIGN between
    policies. That is why the gate document names all three and why all three
    ship: a captured share quoted without its policy string is meaningless.
    """
    import win_expectancy as wx
    W = wx.WinExpectancy.load()

    frames = []
    for season_dir in sorted((Path(corpus) / "plays").iterdir()):
        if not season_dir.is_dir():
            continue
        season = season_dir.name
        pl = pd.concat([pd.read_parquet(f, columns=[
            "game_pk", "at_bat_index", "inning", "half", "outs_before",
            "on_first", "on_second", "on_third", "home_score", "away_score",
            "runs_scored_on_play"])
            for f in sorted(season_dir.glob("*.parquet"))], ignore_index=True)
        # THE OPPORTUNITY SET, exactly the population management.py prices:
        # fewer than two out, a runner on first, second base empty.
        m = ((pl["outs_before"] < 2) & pl["on_first"].notna()
             & pl["on_second"].isna())
        pl = pl[m].copy()
        pl["season"] = season
        frames.append(pl)
    opp = pd.concat(frames, ignore_index=True)
    opp["base_before"] = (opp["on_first"].notna().astype(int)
                          + 2 * opp["on_second"].notna().astype(int)
                          + 4 * opp["on_third"].notna().astype(int))
    # PRE-PLAY, the same convention management.py prices from (audit F07-02).
    # This site was not in the finding's table of four and is the fifth: the
    # captured-share opportunity set is priced through W.offense_we exactly as
    # an attempt is, so a post-play score here would compare a corrected actual
    # against a leaked optimum.
    opp["score_diff"] = wx.pre_play_score_diff(opp)

    lg = df[df["target"] == "2B"].groupby("season")["success"].mean().to_dict()

    # Price every opportunity once. No boundary handling is needed: at 0 or 1
    # out the fail state has 1 or 2 outs and stays mid-inning, and a steal of
    # second scores no run.
    rows = []
    for r in opp.itertuples(index=False):
        p = lg.get(str(r.season))
        if p is None:
            continue
        b = int(r.base_before)
        h = W.offense_we(r.inning, r.half, r.score_diff, r.outs_before, b)
        s = W.offense_we(r.inning, r.half, r.score_diff, r.outs_before,
                         (b & ~1) | 2)
        f = W.offense_we(r.inning, r.half, r.score_diff, r.outs_before + 1, b & ~1)
        if h is None or s is None or f is None or s == f:
            continue
        rows.append((str(r.season), (h - f) / (s - f), p * s + (1 - p) * f - h))
    o = pd.DataFrame(rows, columns=["season", "p_star", "dv"])

    actual = float(df[df["target"] == "2B"]["dv"].sum())
    rng = np.random.default_rng(SEED + 11)
    n_attempts = df[df["target"] == "2B"].groupby("season").size().to_dict()
    n_total = int(sum(n_attempts.values()))

    # TWO OPTIMA, AND ONLY ONE OF THEM BELONGS IN THE RATIO.
    #
    # "Attempt every opportunity with positive decision value" is an upper bound
    # taken at roughly EIGHT TIMES the real attempt volume: 211,191 opportunities
    # exist and managers attempt on 5.67 percent of them. Putting that number in
    # the denominator while the heuristic is budget-matched to the real attempt
    # count compares two different games, and the resulting share is not
    # interpretable as "how much of the available value was captured".
    #
    # The BUDGET-MATCHED optimum takes the best n opportunities where n is the
    # attempt count managers actually spent, season by season. That is the
    # denominator the captured share is defined against, and it is the one the
    # headline uses. The unlimited figure is published beside it, labelled.
    optimal_unlimited = float(o[o["dv"] > 0]["dv"].sum())
    optimal_budget = 0.0
    for season, g in o.groupby("season"):
        k = n_attempts.get(season, 0)
        if k:
            optimal_budget += float(g["dv"].nlargest(k).sum())
    optimal = optimal_budget

    def policy_random_qualifying():
        tot = 0.0
        for season, g in o.groupby("season"):
            k = n_attempts.get(season, 0)
            q = g[g["p_star"] <= lg.get(season, 1.0)]
            if not len(q) or not k:
                continue
            take = rng.choice(len(q), size=min(k, len(q)), replace=False)
            tot += float(q.iloc[take]["dv"].sum())
        return tot

    def policy_random_all():
        tot = 0.0
        for season, g in o.groupby("season"):
            k = n_attempts.get(season, 0)
            if not len(g) or not k:
                continue
            take = rng.choice(len(g), size=min(k, len(g)), replace=False)
            tot += float(g.iloc[take]["dv"].sum())
        return tot

    def policy_margin(margin=0.05):
        tot = 0.0
        for season, g in o.groupby("season"):
            k = n_attempts.get(season, 0)
            q = g[g["p_star"] <= lg.get(season, 1.0) - margin]
            if not len(q) or not k:
                continue
            take = rng.choice(len(q), size=min(k, len(q)), replace=False)
            tot += float(q.iloc[take]["dv"].sum())
        return tot

    out = {
        "n_opportunities": int(len(o)),
        "n_attempts_actual": n_total,
        "attempt_rate": (n_total / len(o)) if len(o) else None,
        "actual_dv_wins": actual,
        "optimal_dv_wins_budget_matched": optimal_budget,
        "optimal_dv_wins_unlimited": optimal_unlimited,
        "which_optimum_the_share_uses": (
            "the BUDGET-MATCHED one. The unlimited optimum attempts on every "
            "positive-value opportunity, which is about eight times the real "
            "attempt volume, and dividing a budget-matched numerator by it "
            "compares two different games. The unlimited figure is published "
            "because it bounds the family's total headroom, and it is not the "
            "denominator."),
        "policies": {},
        "reading": (
            "a NEGATIVE captured share means the observed attempts produced less "
            "decision value than the heuristic policy would have. Read it as a "
            "bound on available value, not as a verdict on managers: the "
            "heuristic is allowed to see p* exactly and is credited with the "
            "league-average success rate in every spot it picks, while a real "
            "manager sends runners on matchup information this model cannot "
            "see (a slow delivery, a weak throwing arm) and would not achieve "
            "the league rate in an arbitrary spot. The heuristic is a fantasy "
            "baseline in that specific sense, and it is still the right "
            "baseline, because it is the only one a reader can argue with."),
        "sign_warning": (
            "the heuristic term appears in both numerator and denominator, so "
            "the captured share can change SIGN between policies. All three "
            "frozen policies are published with their policy strings; a "
            "captured share quoted without its policy is meaningless."),
    }
    for name, fn, desc in (
        ("random_among_qualifying", policy_random_qualifying,
         "attempt at the league rate, chosen at random among opportunities whose "
         "break-even p* is at or below the season league success rate. THE FROZEN HEADLINE."),
        ("random_among_all", policy_random_all,
         "attempt at the league rate, chosen at random among ALL opportunities, ignoring p*"),
        ("margin_5pct", policy_margin,
         "attempt only where p* is cleared by 5 percentage points"),
    ):
        h = fn()
        den = optimal - h
        out["policies"][name] = {
            "policy": desc,
            "heuristic_dv_wins": h,
            "captured_share": (actual - h) / den if den else None,
        }
    return out


def _detection_floor(np, pd, df, col, band_hi):
    """The smallest true per-agent effect this battery could have SEEN.

    A null with no floor is unbounded and says nothing. This injects a known
    per-agent effect into a permuted frame and finds the smallest one detected
    at 80 percent power, which converts the null into a ceiling.
    """
    rng = np.random.default_rng(SEED + 23)
    seasons = df["season"].astype(str).to_numpy()
    idx_by_season = {s: np.where(seasons == s)[0] for s in np.unique(seasons)}
    agents = df["agent"].astype(str).to_numpy()
    uniq = np.unique(agents)
    vals = df[col].to_numpy(copy=True)
    work = df.copy()
    grid = [0.0001, 0.0002, 0.0003, 0.0005, 0.0008, 0.0012]
    out = []
    for delta in grid:
        hits = 0
        reps = 60
        for _ in range(reps):
            v = vals.copy()
            for _s, idx in idx_by_season.items():
                v[idx] = rng.permutation(v[idx])
            eff = dict(zip(uniq, rng.normal(0.0, delta, size=len(uniq))))
            v = v + np.array([eff[a] for a in agents])
            work["_inj"] = v
            agg = _half_split(pd, work, "_inj")
            if _corr(np, agg[("mean", 0)], agg[("mean", 1)]) > band_hi:
                hits += 1
        out.append({"per_attempt_effect_sd": delta, "power": hits / reps})
        if hits / reps >= 0.8:
            break
    detected = next((d["per_attempt_effect_sd"] for d in out if d["power"] >= 0.8), None)
    return {
        "grid": out,
        "smallest_detectable_per_attempt_sd": detected,
        "reading": (
            "the smallest true per-agent per-attempt effect this battery would "
            "have detected at 80 percent power. A null without this number is "
            "unbounded and says nothing; with it, the null is a ceiling."),
    }


def run(*, corpus=None, n_perm=N_PERM, write=True) -> dict:
    import numpy as np
    import pandas as pd

    import management as M
    import mgmt_teams

    stamp = frozen_at()
    corpus = Path(corpus or (ROOT / ".cache" / "pbp_corpus"))

    tmap = mgmt_teams.build_map(corpus=corpus)
    truth = mgmt_teams.validate_against_ground_truth(tmap)

    df = M.attempts(corpus=corpus)
    df = df[df["dv"].notna()].copy()
    n_priced = len(df)
    gp = df["game_pk"].astype(int)
    df["home"] = gp.map(lambda k: (tmap.get(k) or {}).get("home"))
    df["away"] = gp.map(lambda k: (tmap.get(k) or {}).get("away"))
    df["team"] = np.where(df["half"].astype(str).str.startswith("bot"),
                          df["home"], df["away"])
    df = df[df["team"].notna()].copy()
    df["agent"] = df["team"].astype(str) + "|" + df["season"].astype(str)
    df["dv_resid"] = df["dv"] - df.groupby(["season", "target"])["dv"].transform("mean")

    # WHY THE PUBLISHED SERIES IS SEASON-CONTROLLED, as a measurement rather
    # than an assertion.
    tot = df.groupby("agent")["dv"].sum()
    seas = df.groupby("agent")["season"].first().astype(str)
    team = df.groupby("agent")["team"].first().astype(str)

    def r2(labels, y):
        lab = pd.Series(labels.values, index=labels.index).astype(str)
        m = pd.Series(y.values, index=y.index).groupby(lab.values).transform("mean")
        return float(1 - ((y.values - m.values) ** 2).sum()
                     / ((y.values - y.values.mean()) ** 2).sum())

    published = _leg_split_half(np, pd, df, "dv_resid", "season-controlled (PUBLISHED)")
    raw = _leg_split_half(np, pd, df, "dv", "raw (NOT the agent, see decomposition)")
    band = _null_band(np, pd, df, "dv_resid", n_perm=n_perm)
    published["null_band_lo95"] = band["lo95"]
    published["null_band_hi95"] = band["hi95"]
    published["clears_null"] = bool(published["pearson_mean_dv"] > band["hi95"])

    art = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/mgmt_gate.py",
        "gate_doc": "docs/IN_GAME_MANAGEMENT_GATE.md",
        "gate_doc_frozen_at": stamp,
        "seed": SEED,
        "population": {
            "attempts_priced": int(n_priced),
            "attempts_attributed": int(len(df)),
            "agent_seasons": int(df["agent"].nunique()),
            "mean_attempts_per_agent_season": float(df.groupby("agent").size().mean()),
            "median_attempts_per_agent_season": float(df.groupby("agent").size().median()),
        },
        "team_attribution": {
            "games": len(tmap),
            "ground_truth": truth,
            "season_shape": mgmt_teams.season_shape(tmap),
        },
        "why_the_published_series_is_season_controlled": {
            "variance_of_agent_summed_dv_explained_by_season": r2(seas, tot),
            "variance_of_agent_summed_dv_explained_by_team": r2(team, tot),
            "note": (
                "both halves of an agent-season sit in the same season, so a "
                "league-wide year effect reads as split-half agreement while "
                "saying nothing about the agent. A prior design note guessed "
                "the driver was target mix; that guess was wrong and the "
                "correlation between an agent's summed decision value and its "
                "share of steals of second is near zero."),
        },
        "gate_1_split_half": {"published": published, "raw_for_comparison": raw,
                              "null": band},
        "gate_2_persistence": _leg_persistence(np, pd, df),
        "gate_3_placebo": _leg_placebo(np, pd, df, "dv_resid"),
        "gate_4_captured_share": _leg_captured_share(np, pd, df, corpus),
        "detection_floor": _detection_floor(np, pd, df, "dv_resid", band["hi95"]),
    }

    icc = published["icc_one_way"]
    sd_wins = float(np.sqrt(max(icc, 0.0) * df["dv_resid"].var())
                    * df.groupby("agent").size().mean())
    art["headline"] = {
        "implied_true_between_agent_sd_of_summed_dv_wins": sd_wins,
        "net_dv_all_seasons_wins": float(df["dv"].sum()),
        "redistributable_pool_abs_dv_wins": float(df["dv"].abs().sum()),
    }
    art["verdict"] = (
        ("DESCRIPTIVE ONLY. The season-controlled split-half correlation of "
         f"{published['pearson_mean_dv']:.4f} sits INSIDE its permutation null "
         f"band [{band['lo95']:.4f}, {band['hi95']:.4f}], so per-agent decision "
         "value in the running game is not a repeatable property of the agent. "
         "The board may render and be sorted by attempt VOLUME, which is a "
         "style axis; the plus metric is WITHHELD, exactly as leverage_board "
         "does today.")
        if not published["clears_null"] else
        ("CLEARS. The season-controlled split-half correlation of "
         f"{published['pearson_mean_dv']:.4f} exceeds its null band. This is a "
         "real result and it contradicts the pre-registered expectation; "
         "confirm the null construction before publishing anything from it."))
    art["what_a_null_decides_about_the_manager_entity"] = (
        "a team-season is an UPPER BOUND on a manager: managers change and teams "
        "do not. If a team-season carries no repeatable decision signal in this "
        "family, fetching the manager entity to attribute that signal is not "
        "worth building FOR THIS FAMILY. It says nothing about the bullpen or "
        "the pinch hit, which have more room and have not been measured.")
    if write:
        OUT.write_text(json.dumps(art, indent=1, default=str) + "\n", encoding="utf-8")
    return art


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
    n = 300 if "--fast" in argv else N_PERM
    a = run(n_perm=n, write="--dry-run" not in argv)
    p = a["gate_1_split_half"]["published"]
    b = a["gate_1_split_half"]["null"]
    print(f"agent-seasons {a['population']['agent_seasons']}, "
          f"attempts {a['population']['attempts_attributed']:,}")
    print(f"team attribution agreement {a['team_attribution']['ground_truth']['agreement']}")
    print(f"\nGATE 1 published ({p['series']}): r={p['pearson_mean_dv']:+.4f} "
          f"null [{b['lo95']:+.4f}, {b['hi95']:+.4f}] clears={p['clears_null']}")
    print(f"   raw for comparison: r={a['gate_1_split_half']['raw_for_comparison']['pearson_mean_dv']:+.4f}")
    d = a["why_the_published_series_is_season_controlled"]
    print(f"   variance explained: season {d['variance_of_agent_summed_dv_explained_by_season']:.4f}, "
          f"team {d['variance_of_agent_summed_dv_explained_by_team']:.4f}")
    print(f"GATE 2 persistence: {a['gate_2_persistence']['spearman_mean_dv']:+.4f} "
          f"(n={a['gate_2_persistence']['n_pairs']} pairs)")
    g3 = a["gate_3_placebo"]
    print(f"GATE 3 placebo: mean r {g3['placebo_mean_r']:+.4f}, "
          f"{g3['n_cells']} cells, median size {g3['median_cell_size']}")
    g4 = a["gate_4_captured_share"]
    print(f"GATE 4 captured share ({g4['n_attempts_actual']:,} attempts on "
          f"{g4['n_opportunities']:,} opportunities, rate {g4['attempt_rate']:.4f}):")
    print(f"   actual {g4['actual_dv_wins']:+.3f} wins, optimal budget-matched "
          f"{g4['optimal_dv_wins_budget_matched']:+.3f}, unlimited "
          f"{g4['optimal_dv_wins_unlimited']:+.3f}")
    for k, v in g4["policies"].items():
        cs = v["captured_share"]
        print(f"   {k:26s} heuristic {v['heuristic_dv_wins']:+8.3f} wins  "
              f"captured share {cs:+.4f}" if cs is not None else f"   {k}: undefined")
    print(f"\ndetection floor: {a['detection_floor']['smallest_detectable_per_attempt_sd']}")
    print(f"implied true between-agent SD: "
          f"{a['headline']['implied_true_between_agent_sd_of_summed_dv_wins']:.4f} wins")
    print(f"\nVERDICT: {a['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
