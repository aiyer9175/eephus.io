# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W11 stage 2: the runner-aware steal success model, as an additive split of ER. DARK.

The lab for docs/management-2026-10/STEAL_RUNNER_SPLIT_GATE.md (W11_3). It builds the
candidate the gate names (section 2), on the frame it names (section 3), and runs the
ONE read on 2025 (sections 4 to 6). Nothing here is served: no page, shard, payload or
glossary entry reads it, DV is never touched, and nothing in the Diamond reads it.

THE CANDIDATE. A ridge-penalized logistic regression of attempt success with the
incumbent's log-odds as a fixed OFFSET and no free intercept:

    logit P(success) = logit(league_p[season, target]) + sum_j beta_j * x_j

league_p is management.attempts()'s own column, the rate DV is priced with, so with
every beta at zero the candidate IS the incumbent. Eleven features, each a fixed
transform of a public number (FEATURES below); nothing is built from steal outcomes.

THE SPLIT IT WOULD SERVE, on a PASS and behind its own flip. With swing =
we_success - we_fail and p_runner the offset plus the runner terms only:

    ER_runner = swing * (p_runner - league_p)
    ER_other  = ER - ER_runner

so DV + ER_runner + ER_other = the realized win-probability change on every row.

ORDER OF THE LOOK. The fit seasons and the tuning season are read, fitted and frozen
(coefficients, lambdas and frame hashes written to the look directory) BEFORE the 2025
attempts are read at all; the read refuses to run a second time.

    python tools/mgmt_steal_runner_split.py --dry-run-fixtures   # whole path, fixtures with nulls
    python tools/mgmt_steal_runner_split.py --fit-only           # 2018-2024 only, prints, writes nothing
    python tools/mgmt_steal_runner_split.py --look [--owner-waived-early-read]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GATE_DOC = ROOT / "docs" / "management-2026-10" / "STEAL_RUNNER_SPLIT_GATE.md"
LOOK_DIR = ROOT / "docs" / "management-2026-10" / "look-steal-runner-split"
FROZEN = "frozen_fit.json"
RECORD = "look_record.json"
EVAL_OUT = ROOT / "data" / "steal_runner_split_eval.json"
CONTEXT = ROOT / "data" / "management_steal_context.json"
CORPUS = ROOT / ".cache" / "pbp_corpus"

#: The gate's own date (section 6). The owner waived registered dates on 2026-10-14
#: (EW3-5); a read before this date says so in its record.
LOOK_DATE = _dt.date(2026, 10, 20)

FIT_SEASONS = ("2018", "2019", "2021", "2022", "2023")
TUNE_SEASON = "2024"
SCORE_SEASON = "2025"

FEATURES = ("R1", "R2", "R3", "C1", "C2", "P1", "P2", "S1", "S2", "S3", "S4")
RUNNER_TERMS = ("R1", "R2", "R3")
TWIN_FEATURES = tuple(f for f in FEATURES if f not in RUNNER_TERMS)

LAMBDA_GRID = (0.0001, 0.001, 0.01, 0.1, 1.0)
LAMBDA_TIE = 1e-6
TOL = 1e-10
CLIP = 1e-6
POP_CENTRE = 2.00
PCT_CENTRE = 0.5
MARGIN_CLIP = 4
RULES_SEASON = 2023
LATE_INNING = 7

B = 2000
SEED = 20261020
MIN_SCORED = 1000

#: The columns an empty frame still carries, so the reporting path runs on it.
EMPTY_COLUMNS = ("season", "game_pk", "at_bat_index", "event_type", "target", "success",
                 "league_p", "we_success", "we_fail", "dv", "er", "realized_delta",
                 *FEATURES, "_runner_id", "_catcher_id", "_hand_known", "_margin_known")

ORIGIN_COL = {"2B": "on_first", "3B": "on_second", "HOME": "on_third"}
ORIGIN_BIT = {"2B": 1, "3B": 2, "HOME": 4}


# ----------------------------------------------------------------------------
# features (pure; the tests drive these on fixtures)
# ----------------------------------------------------------------------------

def _id(v):
    """A player id cell (float with NaN for empty in the plays table) as an int, or None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return int(f)


def feature_row(r: dict, block: dict | None) -> dict:
    """The eleven section 2.1 features of one attempt, plus the join facts behind them.

    `r` carries season, target, game_pk, at_bat_index, the origin-base runner columns,
    base_before, outs_before, inning, half, score_diff and pitch_hand; `block` is the
    season's block of the stage 1 context payload (None when the season has none)."""
    season = int(r["season"])
    target = str(r["target"])
    block = block or {}
    runners = block.get("runners") or {}
    rid = _id(r.get(ORIGIN_COL[target]))
    rec = runners.get(str(rid)) if rid is not None else None
    listed = rec is not None and rec[0] is not None
    r1 = (float(rec[0]) / 100.0 - PCT_CENTRE) if listed else 0.0
    r2 = 0.0 if listed else 1.0
    r3 = r1 if season >= RULES_SEASON else 0.0

    cid = (block.get("att") or {}).get(f"{int(r['game_pk'])}:{int(r['at_bat_index'])}")
    crec = (block.get("catchers") or {}).get(str(cid)) if cid is not None else None
    pop = crec[0] if crec is not None else None
    has_pop = pop is not None
    c1 = (float(pop) - POP_CENTRE) if has_pop else 0.0
    c2 = 0.0 if has_pop else 1.0

    hand = r.get("pitch_hand")
    p1 = 1.0 if (isinstance(hand, str) and hand == "L") else 0.0
    p2 = p1 if target == "2B" else 0.0

    outs = r.get("outs_before")
    s1 = 1.0 if (outs is not None and int(outs) == 1) else 0.0
    base = int(r["base_before"])
    s2 = 1.0 if (base & ~ORIGIN_BIT[target]) != 0 else 0.0
    sd = r.get("score_diff")
    sd_ok = sd is not None and not (isinstance(sd, float) and math.isnan(sd))
    margin = None
    if sd_ok:
        margin = float(sd) if str(r.get("half")).startswith("bot") else -float(sd)
    s3 = (max(-MARGIN_CLIP, min(MARGIN_CLIP, margin)) / MARGIN_CLIP) if margin is not None else 0.0
    inn = r.get("inning")
    s4 = 1.0 if (margin is not None and inn is not None and int(inn) >= LATE_INNING
                 and abs(margin) <= 1) else 0.0
    return {"R1": r1, "R2": r2, "R3": r3, "C1": c1, "C2": c2, "P1": p1, "P2": p2,
            "S1": s1, "S2": s2, "S3": s3, "S4": s4,
            "_runner_id": rid, "_catcher_id": cid, "_hand_known": isinstance(hand, str),
            "_margin_known": margin is not None}


def build_features(df, ctx: dict | None):
    """The frame's feature matrix as a DataFrame aligned to df's index."""
    import pandas as pd
    seasons = (ctx or {}).get("seasons") or {}
    rows = [feature_row(r, seasons.get(str(int(r["season"]))))
            for r in df.to_dict("records")]
    return pd.DataFrame(rows, index=df.index)


# ----------------------------------------------------------------------------
# the model
# ----------------------------------------------------------------------------

def logit(p):
    import numpy as np
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)
    return np.log(p) - np.log1p(-p)


def sigmoid(z):
    import numpy as np
    z = np.asarray(z, dtype=float)
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def objective(beta, X, y, offset, lam):
    """(1/n) sum NLL + (lam/2) sum beta^2, and its gradient."""
    import numpy as np
    eta = offset + X @ beta
    nll = np.logaddexp(0.0, eta) - y * eta
    n = len(y)
    f = float(nll.sum() / n + 0.5 * lam * float(beta @ beta))
    g = X.T @ (sigmoid(eta) - y) / n + lam * beta
    return f, g


def fit(X, y, offset, lam) -> dict:
    """Penalized ML with the offset, L-BFGS-B from beta = 0 at tolerance TOL."""
    import numpy as np
    from scipy.optimize import minimize
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    offset = np.asarray(offset, dtype=float)
    k = X.shape[1]
    if k == 0:
        return {"beta": [], "converged": True, "nit": 0, "objective": None}
    res = minimize(objective, np.zeros(k), args=(X, y, offset, float(lam)),
                   jac=True, method="L-BFGS-B", tol=TOL)
    return {"beta": [float(b) for b in res.x], "converged": bool(res.success),
            "nit": int(res.nit), "objective": float(res.fun), "message": str(res.message)}


def predict(beta, X, offset):
    import numpy as np
    X = np.asarray(X, dtype=float)
    b = np.asarray(beta, dtype=float)
    eta = np.asarray(offset, dtype=float) + (X @ b if X.shape[1] else 0.0)
    return sigmoid(eta)


def log_loss(p, y):
    import numpy as np
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1.0 - y) * np.log1p(-p))


def brier(p, y):
    import numpy as np
    return (np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2


def choose_lambda(fitX, fity, fito, tuneX, tuney, tuneo) -> dict:
    """Fit at every grid lambda on the fit frame, score mean log loss on the tuning
    frame; the minimum wins and a tie within LAMBDA_TIE goes to the larger lambda."""
    per = []
    for lam in LAMBDA_GRID:
        f = fit(fitX, fity, fito, lam)
        ll = float(log_loss(predict(f["beta"], tuneX, tuneo), tuney).mean())
        per.append({"lambda": lam, "tune_log_loss": ll, "fit": f})
    best = min(p["tune_log_loss"] for p in per)
    chosen = max((p for p in per if p["tune_log_loss"] <= best + LAMBDA_TIE),
                 key=lambda p: p["lambda"])
    return {"lambda": chosen["lambda"], "fit": chosen["fit"],
            "grid": [{"lambda": p["lambda"], "tune_log_loss": p["tune_log_loss"],
                      "converged": p["fit"]["converged"]} for p in per]}


# ----------------------------------------------------------------------------
# the statistic
# ----------------------------------------------------------------------------

def game_bootstrap(game_ids, stats: dict, *, b: int = B, seed: int = SEED) -> dict:
    """Paired bootstrap over GAMES. `stats` maps a name to a per-attempt array; each
    resample draws the game list with replacement and every statistic is recomputed as
    the mean over the drawn games' attempts, on the same draws. Returns per statistic
    the point mean, the one-sided 95% lower bound (5th percentile) and the two-sided
    90% interval (5th, 95th percentiles)."""
    import numpy as np
    g = np.asarray(game_ids)
    uniq, inv = np.unique(g, return_inverse=True)
    G = len(uniq)
    n_per = np.bincount(inv, minlength=G).astype(float)
    sums = {k: np.bincount(inv, weights=np.asarray(v, dtype=float), minlength=G)
            for k, v in stats.items()}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, G, size=(b, G))
    out = {}
    counts = np.zeros((b, G))
    for i in range(b):
        counts[i] = np.bincount(draws[i], minlength=G)
    denom = counts @ n_per
    for k, s in sums.items():
        means = (counts @ s) / denom
        point = float(s.sum() / n_per.sum())
        lo, hi = np.percentile(means, [5.0, 95.0])
        out[k] = {"point": point, "lower_95_one_sided": float(lo),
                  "interval_90": [float(lo), float(hi)],
                  "resolves": bool(lo > 0.0)}
    out["_games"] = int(G)
    out["_draw_method"] = ("numpy default_rng(seed).integers(0, G, size=(B, G)) over games "
                           "sorted by game_pk; each draw's statistic is the attempt-weighted "
                           "mean over the drawn games; percentiles by numpy's linear rule")
    return out


def verdict(n_scored: int, boot: dict) -> dict:
    """Section 5: all four conditions."""
    conds = {
        "1_n_scored_at_least_1000": n_scored >= MIN_SCORED,
        "2_dLL_lower_bound_above_0": bool(boot.get("dLL", {}).get("resolves")),
        "3_dBrier_lower_bound_above_0": bool(boot.get("dBrier", {}).get("resolves")),
        "4_dLL_runner_lower_bound_above_0": bool(boot.get("dLL_runner", {}).get("resolves")),
    }
    return {"conditions": conds, "result": "PASS" if all(conds.values()) else "NULL",
            "failed": [k for k, v in conds.items() if not v]}


def calibration_deciles(p, q, y) -> list:
    import numpy as np
    import pandas as pd
    p = np.asarray(p, dtype=float)
    order = pd.Series(p).rank(method="first").to_numpy()
    n = len(p)
    out = []
    if n == 0:
        return out
    dec = np.minimum((order - 1) * 10 // n, 9).astype(int)
    for d in range(10):
        m = dec == d
        if not m.any():
            continue
        out.append({"decile": d + 1, "n": int(m.sum()),
                    "mean_candidate_p": round(float(p[m].mean()), 6),
                    "mean_incumbent_q": round(float(np.asarray(q)[m].mean()), 6),
                    "success_rate": round(float(np.asarray(y)[m].mean()), 6)})
    return out


def split_er(swing, p_runner, league_p, er):
    """ER_runner = swing * (p_runner - league_p); ER_other = ER - ER_runner."""
    import numpy as np
    er_r = np.asarray(swing, dtype=float) * (np.asarray(p_runner, dtype=float)
                                             - np.asarray(league_p, dtype=float))
    return er_r, np.asarray(er, dtype=float) - er_r


# ----------------------------------------------------------------------------
# frames
# ----------------------------------------------------------------------------

def pitch_hands(seasons, corpus: Path | None = None):
    import pandas as pd
    out = []
    for s in seasons:
        for f in sorted((Path(corpus or CORPUS) / "plays" / str(s)).glob("*.parquet")):
            out.append(pd.read_parquet(f, columns=["game_pk", "at_bat_index", "pitch_hand"]))
    if not out:
        return pd.DataFrame(columns=["game_pk", "at_bat_index", "pitch_hand"])
    return pd.concat(out, ignore_index=True).drop_duplicates(["game_pk", "at_bat_index"])


def frame(seasons, ctx: dict, *, corpus: Path | None = None, we=None, attempts_df=None,
          hands=None):
    """The priced attempts of `seasons` (management.attempts() rows with a non-null dv)
    with pitch_hand joined and the feature columns built."""
    import pandas as pd
    if attempts_df is None:
        import management as M
        attempts_df = M.attempts(corpus=corpus, seasons=[str(s) for s in seasons], we=we)
    if attempts_df is None or len(attempts_df) == 0:
        return pd.DataFrame(columns=list(EMPTY_COLUMNS))
    df = attempts_df[attempts_df["dv"].notna()
                     & attempts_df["season"].astype(str).isin([str(s) for s in seasons])].copy()
    if hands is None:
        hands = pitch_hands(seasons, corpus)
    if "pitch_hand" not in df.columns:
        df = df.merge(hands, on=["game_pk", "at_bat_index"], how="left")
    if len(df) == 0:
        return pd.DataFrame(columns=list(EMPTY_COLUMNS))
    df = df.sort_values(["season", "game_pk", "at_bat_index", "event_type"]).reset_index(drop=True)
    feats = build_features(df, ctx)
    return pd.concat([df, feats], axis=1)


def matrix(df, cols):
    import numpy as np
    if len(df) == 0:
        return np.zeros((0, len(cols)))
    return df[list(cols)].to_numpy(dtype=float)


def frame_hash(df) -> str:
    """sha256 of the frame's identity, outcome, offset and features, canonical CSV."""
    cols = ["season", "game_pk", "at_bat_index", "event_type", "target", "success",
            "league_p", *FEATURES]
    if len(df) == 0:
        return hashlib.sha256(b"").hexdigest()
    sub = df[cols].copy()
    sub["success"] = sub["success"].astype(int)
    txt = sub.to_csv(index=False, float_format="%.10f", lineterminator="\n")
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def coverage(df) -> dict:
    if len(df) == 0:
        return {"attempts": 0}
    return {"attempts": int(len(df)),
            "runner_listed": int((df["R2"] == 0).sum()),
            "catcher_named": int(df["_catcher_id"].notna().sum()),
            "pop_on_file": int((df["C2"] == 0).sum()),
            "pitch_hand_known": int(df["_hand_known"].sum()),
            "lefty_pitcher": int((df["P1"] == 1).sum()),
            "one_out": int((df["S1"] == 1).sum()),
            "another_runner_on": int((df["S2"] == 1).sum()),
            "late_and_close": int((df["S4"] == 1).sum())}


# ----------------------------------------------------------------------------
# the stages
# ----------------------------------------------------------------------------

def freeze(fit_df, tune_df) -> dict:
    """Fit and tune the candidate and the twin; the frozen record. Reads no 2025 row."""
    yf = fit_df["success"].astype(float).to_numpy()
    yt = tune_df["success"].astype(float).to_numpy()
    of = logit(fit_df["league_p"].to_numpy())
    ot = logit(tune_df["league_p"].to_numpy())
    cand = choose_lambda(matrix(fit_df, FEATURES), yf, of, matrix(tune_df, FEATURES), yt, ot)
    twin = choose_lambda(matrix(fit_df, TWIN_FEATURES), yf, of,
                         matrix(tune_df, TWIN_FEATURES), yt, ot)
    inc_tune = float(log_loss(sigmoid(ot), yt).mean()) if len(yt) else None
    league_p_clipped = int(((fit_df["league_p"] <= CLIP) | (fit_df["league_p"] >= 1 - CLIP)).sum()
                           + ((tune_df["league_p"] <= CLIP)
                              | (tune_df["league_p"] >= 1 - CLIP)).sum())
    return {
        "frozen_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "features": list(FEATURES), "twin_features": list(TWIN_FEATURES),
        "lambda_grid": list(LAMBDA_GRID),
        "candidate": {"lambda": cand["lambda"],
                      "beta": dict(zip(FEATURES, cand["fit"]["beta"])),
                      "converged": cand["fit"]["converged"], "nit": cand["fit"]["nit"],
                      "tune_log_loss_by_lambda": cand["grid"]},
        "twin": {"lambda": twin["lambda"],
                 "beta": dict(zip(TWIN_FEATURES, twin["fit"]["beta"])),
                 "converged": twin["fit"]["converged"], "nit": twin["fit"]["nit"],
                 "tune_log_loss_by_lambda": twin["grid"]},
        "incumbent_tune_log_loss": inc_tune,
        "frames": {
            "fit": {"seasons": list(FIT_SEASONS), "rows": int(len(fit_df)),
                    "rows_by_season": {str(k): int(v) for k, v in
                                       fit_df["season"].astype(str).value_counts().sort_index().items()},
                    "sha256": frame_hash(fit_df), "coverage": coverage(fit_df)},
            "tune": {"seasons": [TUNE_SEASON], "rows": int(len(tune_df)),
                     "sha256": frame_hash(tune_df), "coverage": coverage(tune_df)},
        },
        "offset_probabilities_clipped": league_p_clipped,
    }


def score(frozen: dict, sc_df) -> dict:
    """The one read on the score frame with the frozen coefficients."""
    import numpy as np
    y = sc_df["success"].astype(float).to_numpy()
    off = logit(sc_df["league_p"].to_numpy())
    q = sigmoid(off)
    bc = [frozen["candidate"]["beta"][f] for f in FEATURES]
    bt = [frozen["twin"]["beta"][f] for f in TWIN_FEATURES]
    p = predict(bc, matrix(sc_df, FEATURES), off)
    tw = predict(bt, matrix(sc_df, TWIN_FEATURES), off)
    br = [frozen["candidate"]["beta"][f] for f in RUNNER_TERMS]
    p_run = predict(br, matrix(sc_df, RUNNER_TERMS), off)
    ll_q, ll_p, ll_t = log_loss(q, y), log_loss(p, y), log_loss(tw, y)
    stats = {"dLL": ll_q - ll_p, "dBrier": brier(q, y) - brier(p, y), "dLL_runner": ll_t - ll_p}
    n = int(len(y))
    boot = game_bootstrap(sc_df["game_pk"].to_numpy(), stats) if n else {}
    v = verdict(n, boot)
    swing = (sc_df["we_success"] - sc_df["we_fail"]).to_numpy(dtype=float)
    er = sc_df["er"].to_numpy(dtype=float)
    er_r, er_o = split_er(swing, p_run, sc_df["league_p"].to_numpy(dtype=float), er)
    ident = float(np.abs(sc_df["dv"].to_numpy(dtype=float) + er_r + er_o
                         - sc_df["realized_delta"].to_numpy(dtype=float)).max()) if n else None
    by_t = {}
    for tgt in ("2B", "3B", "HOME"):
        m = (sc_df["target"] == tgt).to_numpy()
        if not m.any():
            continue
        by_t[tgt] = {"n": int(m.sum()), "sum_er_wins": round(float(er[m].sum()), 4),
                     "sum_er_runner_wins": round(float(er_r[m].sum()), 4),
                     "sum_er_other_wins": round(float(er_o[m].sum()), 4)}
    return {
        "n_scored": n,
        "means": {"log_loss_incumbent": float(ll_q.mean()) if n else None,
                  "log_loss_candidate": float(ll_p.mean()) if n else None,
                  "log_loss_twin": float(ll_t.mean()) if n else None,
                  "brier_incumbent": float(brier(q, y).mean()) if n else None,
                  "brier_candidate": float(brier(p, y).mean()) if n else None},
        "bootstrap": {k: v2 for k, v2 in boot.items() if not k.startswith("_")},
        "bootstrap_games": boot.get("_games"),
        "bootstrap_method": boot.get("_draw_method"),
        "verdict": v,
        "calibration_by_decile_of_p": calibration_deciles(p, q, y),
        "er_split_by_target": by_t,
        "er_split_identity_max_abs_error": ident,
        "coverage": coverage(sc_df),
    }


def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _sha256(p: Path) -> str | None:
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None


def eval_payload(frozen: dict, scored: dict, meta: dict) -> dict:
    v = scored["verdict"]
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "tools/mgmt_steal_runner_split.py",
        "model_id": "steal_runner_split",
        "gate": "docs/management-2026-10/STEAL_RUNNER_SPLIT_GATE.md",
        "read": meta,
        "verdict": v["result"],
        "conditions": v["conditions"],
        "failed_conditions": v["failed"],
        "served": False,
        "dv_unchanged": True,
        "frozen_fit": {k: frozen[k] for k in ("features", "twin_features", "lambda_grid",
                                              "candidate", "twin", "incumbent_tune_log_loss",
                                              "frames", "offset_probabilities_clipped",
                                              "frozen_at")},
        "score": {k: scored[k] for k in scored if k != "verdict"},
        "statistic": ("paired per-attempt gains on identical 2025 attempts, positive when the "
                      "candidate is better: dLL = mean(LL(incumbent) - LL(candidate)), dBrier = "
                      "mean(B(incumbent) - B(candidate)), dLL_runner = mean(LL(twin) - "
                      "LL(candidate)); probabilities clipped to [1e-6, 1 - 1e-6]; game bootstrap "
                      "B 2000, seed 20261020; a gain resolves when its one-sided 95% lower bound "
                      "is above zero"),
        "what_it_is_not": ("not served, not a decision value, not a runner or manager rating; "
                           "it prices nothing in the Diamond"),
    }


# ----------------------------------------------------------------------------
# runs
# ----------------------------------------------------------------------------

def run_read(*, ctx: dict, fit_df, tune_df, load_score, out_dir: Path, eval_out: Path,
             meta: dict, say=print) -> dict:
    """The whole read: freeze (written) BEFORE load_score() is called, then score and
    write the eval and the record, then print. Shared by the look and the dry run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    say(f"fit frame: {len(fit_df):,} rows, tune frame: {len(tune_df):,} rows")
    frozen = freeze(fit_df, tune_df)
    (out_dir / FROZEN).write_text(json.dumps(frozen, indent=1) + "\n", encoding="utf-8")
    say(f"frozen: candidate lambda {frozen['candidate']['lambda']}, twin lambda "
        f"{frozen['twin']['lambda']}; written {out_dir / FROZEN}")
    for k, b in frozen["candidate"]["beta"].items():
        say(f"  candidate {k} {b:+.6f}")
    for k, b in frozen["twin"]["beta"].items():
        say(f"  twin      {k} {b:+.6f}")
    for row in frozen["candidate"]["tune_log_loss_by_lambda"]:
        say(f"  tune LL candidate lambda {row['lambda']}: {row['tune_log_loss']:.8f}")
    for row in frozen["twin"]["tune_log_loss_by_lambda"]:
        say(f"  tune LL twin      lambda {row['lambda']}: {row['tune_log_loss']:.8f}")
    say(f"  tune LL incumbent: {frozen['incumbent_tune_log_loss']}")
    say("reading the score frame now")
    sc_df = load_score()
    meta = dict(meta)
    meta["score_rows"] = int(len(sc_df))
    meta["score_frame_sha256"] = frame_hash(sc_df)
    say(f"score frame: {len(sc_df):,} rows, sha256 {meta['score_frame_sha256']}")
    scored = score(frozen, sc_df)
    payload = eval_payload(frozen, scored, meta)
    eval_out.parent.mkdir(parents=True, exist_ok=True)
    eval_out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    (out_dir / RECORD).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    say(f"wrote {eval_out} and {out_dir / RECORD}")
    say(f"n scored {scored['n_scored']:,}; games {scored['bootstrap_games']}")
    for k, s in scored["bootstrap"].items():
        say(f"  {k:10s} point {s['point']:+.8f}  lower95 {s['lower_95_one_sided']:+.8f}  "
            f"90% [{s['interval_90'][0]:+.8f}, {s['interval_90'][1]:+.8f}]  "
            f"resolves {s['resolves']}")
    for k, s in scored["means"].items():
        say(f"  {k}: {s}")
    for k, s in scored["er_split_by_target"].items():
        say(f"  ER split {k}: {s}")
    say(f"  ER split identity max abs error: {scored['er_split_identity_max_abs_error']}")
    say(f"VERDICT {payload['verdict']}; conditions {payload['conditions']}")
    return payload


def fixtures(seed: int = 7):
    """Synthetic attempts with every null the real frame can carry: a runner with no id,
    a runner off the leaderboard, a season with no context block, a catcher not named, a
    catcher with no pop time, a missing pitch hand. Not baseball; a path check."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows = []
    ctx = {"seasons": {}}
    for season in (*FIT_SEASONS, TUNE_SEASON, SCORE_SEASON):
        blk = {"runners": {}, "catchers": {}, "att": {}, "sprint": {"n_runners": 50}}
        if season != "2019":
            ctx["seasons"][season] = blk
        for i in range(260):
            g = int(season) * 1000 + i // 3
            ab = i % 3
            tgt = "2B" if i % 9 else ("3B" if i % 2 else "HOME")
            rid = None if i % 47 == 0 else 1000 + (i % 40)
            if rid is not None and i % 13:
                blk["runners"][str(rid)] = [int(rng.integers(0, 101)), 27.0, 50]
            cid = None if i % 31 == 0 else 2000 + (i % 7)
            if cid is not None:
                blk["att"][f"{g}:{ab}"] = cid
                blk["catchers"][str(cid)] = [None if cid == 2003 else
                                             round(float(rng.normal(2.0, 0.05)), 2), 10, "X"]
            base = {"2B": 1, "3B": 2, "HOME": 4}[tgt] | (2 if i % 5 == 0 and tgt == "2B" else 0)
            sd = float(rng.integers(-6, 7))
            rows.append({
                "season": season, "game_pk": g, "at_bat_index": ab,
                "event_type": f"stolen_base_{tgt.lower()}", "target": tgt,
                "on_first": float(rid) if tgt == "2B" and rid else np.nan,
                "on_second": float(rid) if tgt == "3B" and rid else np.nan,
                "on_third": float(rid) if tgt == "HOME" and rid else np.nan,
                "base_before": base, "outs_before": int(i % 2), "inning": 1 + i % 10,
                "half": "top" if i % 2 else "bottom",
                "score_diff": np.nan if i % 53 == 0 else sd,
                "pitch_hand": None if i % 17 == 0 else ("L" if i % 4 == 0 else "R"),
                "we_success": 0.55, "we_fail": 0.45,
            })
    df = pd.DataFrame(rows)
    p = 0.72 + 0.1 * np.tanh(rng.normal(size=len(df)))
    df["success"] = rng.random(len(df)) < p
    lg = df.groupby(["season", "target"])["success"].mean().rename("league_p").reset_index()
    df = df.merge(lg, on=["season", "target"], how="left")
    df["dv"] = df["league_p"] * df["we_success"] + (1 - df["league_p"]) * df["we_fail"] - 0.5
    real = np.where(df["success"], df["we_success"], df["we_fail"])
    exp = df["league_p"] * df["we_success"] + (1 - df["league_p"]) * df["we_fail"]
    df["er"] = real - exp
    df["realized_delta"] = real - 0.5
    return df, ctx


def dry_run(out_dir: Path | None = None, say=print) -> dict:
    """The whole reporting path on fixtures with nulls, into a scratch directory."""
    df, ctx = fixtures()
    tmp = Path(out_dir or tempfile.mkdtemp(prefix="srs_dry_"))
    fit_df = frame(FIT_SEASONS, ctx, attempts_df=df)
    tune_df = frame([TUNE_SEASON], ctx, attempts_df=df)
    meta = {"kind": "dry run on fixtures", "context_sha256": None}
    return run_read(ctx=ctx, fit_df=fit_df, tune_df=tune_df,
                    load_score=lambda: frame([SCORE_SEASON], ctx, attempts_df=df),
                    out_dir=tmp, eval_out=tmp / "steal_runner_split_eval.json",
                    meta=meta, say=say)


def _context() -> dict:
    return json.loads(CONTEXT.read_text(encoding="utf-8"))


def fit_only(say=print) -> dict:
    """Fit and tune on 2018-2024 and print; writes nothing and reads no 2025 row."""
    ctx = _context()
    fit_df = frame(FIT_SEASONS, ctx)
    tune_df = frame([TUNE_SEASON], ctx)
    fr = freeze(fit_df, tune_df)
    say(json.dumps({k: fr[k] for k in ("candidate", "twin", "incumbent_tune_log_loss",
                                       "frames", "offset_probabilities_clipped")}, indent=1))
    return fr


def look(*, owner_waived: bool, say=print) -> dict:
    """THE ONE READ. Refuses a second run, and a run before LOOK_DATE without the waiver."""
    today = _dt.date.today()
    if EVAL_OUT.exists() or (LOOK_DIR / RECORD).exists() or (LOOK_DIR / FROZEN).exists():
        raise SystemExit("the one read has already run (eval artifact or look record on disk); "
                         "the gate forbids a second read")
    if today < LOOK_DATE and not owner_waived:
        raise SystemExit(f"the gate's look date is {LOOK_DATE}; before it the read needs "
                         "--owner-waived-early-read (EW3-5)")
    if not GATE_DOC.exists():
        raise SystemExit(f"{GATE_DOC} is missing")
    import numpy as np
    import pandas as pd
    import scipy
    import win_expectancy as wx
    meta = {
        "kind": ("OWNER-WAIVED EARLY READ (EW3-5, owner 2026-10-14)" if today < LOOK_DATE
                 else "the registered read"),
        "run_date": today.isoformat(),
        "registered_date": LOOK_DATE.isoformat(),
        "code_commit": _git("rev-parse", "HEAD"),
        "lab_blob": _git("hash-object", str(Path(__file__).resolve())),
        "context_payload": "data/management_steal_context.json",
        "context_sha256": _sha256(CONTEXT),
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "pandas": pd.__version__},
    }
    ctx = _context()
    meta["context_generated_at"] = ctx.get("generated_at")
    meta["context_rows_by_season"] = {s: (b.get("coverage") or {}).get("attempts")
                                      for s, b in sorted((ctx.get("seasons") or {}).items())
                                      if s in (*FIT_SEASONS, TUNE_SEASON, SCORE_SEASON)}
    for k, v in meta.items():
        say(f"{k}: {v}")
    W = wx.WinExpectancy.load()
    fit_df = frame(FIT_SEASONS, ctx, we=W)
    tune_df = frame([TUNE_SEASON], ctx, we=W)
    meta["fit_rows_by_season"] = {str(k): int(v) for k, v in
                                  fit_df["season"].astype(str).value_counts().sort_index().items()}
    meta["tune_rows"] = int(len(tune_df))
    say(f"fit rows by season: {meta['fit_rows_by_season']}; tune rows {meta['tune_rows']}")
    return run_read(ctx=ctx, fit_df=fit_df, tune_df=tune_df,
                    load_score=lambda: frame([SCORE_SEASON], ctx, we=W),
                    out_dir=LOOK_DIR, eval_out=EVAL_OUT, meta=meta, say=say)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run-fixtures", action="store_true")
    g.add_argument("--fit-only", action="store_true")
    g.add_argument("--look", action="store_true")
    ap.add_argument("--owner-waived-early-read", action="store_true")
    ap.add_argument("--out-dir")
    a = ap.parse_args(argv)
    if a.dry_run_fixtures:
        dry_run(Path(a.out_dir) if a.out_dir else None)
    elif a.fit_only:
        fit_only()
    else:
        look(owner_waived=a.owner_waived_early_read)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
