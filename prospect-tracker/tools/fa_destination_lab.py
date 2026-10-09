# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The FA destination lab: the one producer of data/fa_destination_eval.json.

Registered in docs/fa-2026-10/FA_DESTINATION_GATE.md before any code existed.
This file was built by task Q9_04a and has NOT been run on the real chain: the
one look is task Q9_04b. Any computation on the real 2018-2026 chain of a
ranking, probability, coefficient, floor or metric of P, N, L_perm,
payroll_level or incumbency_only, of any arm on the primary frame, or of any
join of an MLBTR pick to a signing, before that look, is an EARLY LOOK and
voids the registration (gate section 15). The build task's tests run on
fixtures only.

TWO MODES.
  --dry-run   the whole reporting path on a synthetic fixture that carries
              nulls (a member with no price, a club with no payroll row, an
              empty winter, a duplicate and an integrity drop in the Gate 2
              collection, unresolved and tied MLBTR rows). Writes only to
              .cache/fa_destination/dry_run/ (or --out). The look repeats it
              first, as gate section 15 step (1) asks.
  --look      the registered read. Refuses when the artifact already exists.
              Reads cached pages only (scrapers.cache_only), so it fetches
              nothing.

ORDER (gate section 15): step 0 on the realized-price frame; the Gate 2
collection, the join and its counts; every arm's per-winter fit with its
coefficients written; the floors block written; the metrics, clauses and ship
verdict; the reported blocks, the industry comparators last. The artifact is
rewritten after each step, and its `order` list records the steps as written.

WHAT IT NEVER TOUCHES. It imports fa_fit_backtest.build_rows, _rank_metrics
and _fit_logit and never calls run_fit_gate (whose persist default rewrites
data/fa_gate3_eval.json). It reads Gate 2's predicted prices only through the
GATE2_COLLECT hook with persist=False, persist_dpw=False, so the auto
re-export a gate save triggers (owner answer M14-1) never fires. It never
calls fa_export and never multiplies P(enter) into P(signs).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fa_destination as fd  # noqa: E402
import fa_fit_backtest as fb  # noqa: E402

OUT_PATH = ROOT / "data" / "fa_destination_eval.json"
DRY_RUN_DIR = ROOT / ".cache" / "fa_destination" / "dry_run"
GATE3_PATH = ROOT / "data" / "fa_gate3_eval.json"
MLBTR_RETRO_PATH = ROOT / "data" / "_labs" / "fa_predictions" / "mlbtr_retro_2015_2025.json"

MRR_MDE95 = 0.0139           # teamfit_conditional_gate.mde95, fixed (section 9)
BOOT_B = 2000
BOOT_SEED = 7
MIN_TRAIN_POSITIVES = 30     # the _fit_logit rule (section 4.3)
LN30 = math.log(30.0)
HOLM_FIRST, HOLM_SECOND = 0.025, 0.05
LPERM_SHARE_CAP = 0.60
STABILITY_MIN_WINTERS = 7
SLOPE_BAND = (0.8, 1.2)
STEP0_ARMS = ("random", "payroll_only", "behavior_only", "live_analog", "fitted_full",
              "banded_twin")
BASELINES = ("random", "payroll_space", "payroll_level", "behavior_only",
             "live_analog", "incumbency_only")
FITTED_ARMS = ("P", "N", "L_perm")
NULL_LINE = ("the Club Ledger's spending history did not make destinations more "
             "predictable than the Fit's will-spend term already does")


# ==========================================================================
# inputs
# ==========================================================================

class LabInputs:
    """Everything the lab reads, injectable so the dry run and the tests use
    fixtures. realized_rows: build_rows() output. primary_rows_fn(override):
    build_rows(price_override=override). signings: {(winter, player_key):
    {player_key, player_name, class_year, mlbam_id, from_team, to_team, qo,
    years, npv_usd}} for the Gate 3 chain. all_signings: the same records for
    every stored winter, for the industry comparator. club_states: {Y:
    fa_destination.club_state(Y)}. gate2_fn(): the GATE2_COLLECT rows, called
    once, after step 0 (gate section 15 step 4)."""

    def __init__(self, *, realized_rows, primary_rows_fn, signings, all_signings,
                 club_states, gate2_fn, mlbtr, qo_acceptances, gate_doc_text,
                 weights, registered_step0, fixture, input_counts=None):
        self.realized_rows = realized_rows
        self.primary_rows_fn = primary_rows_fn
        self.signings = signings
        self.all_signings = all_signings
        self.club_states = club_states
        self.gate2_fn = gate2_fn
        self.mlbtr = mlbtr
        self.qo_acceptances = qo_acceptances
        self.gate_doc_text = gate_doc_text
        self.weights = weights
        self.registered_step0 = registered_step0
        self.fixture = fixture
        self.input_counts = input_counts or {}


def collect_gate2() -> list:
    """Gate 2's forward-chained predictions, one tuple per scored signing:
    (winter, player key, predicted guarantee $M, actual guarantee $M,
    predicted AAV $M, actual AAV $M, predicted years, actual years). The Gate D
    precedent: persist=False and persist_dpw=False, the hook reset in a
    finally, so nothing under data/ is written and no re-export runs."""
    import fa_backtest as fbt
    fbt.GATE2_COLLECT = []
    try:
        fbt.run_market_gate(persist=False, persist_dpw=False)
        return list(fbt.GATE2_COLLECT)
    finally:
        fbt.GATE2_COLLECT = None


def registered_step0(path: Path = GATE3_PATH) -> dict:
    """The registered Gate 3 numbers, read from the committed artifact."""
    g3 = json.loads(Path(path).read_text(encoding="utf-8"))
    res = g3["results"]
    out = {k: dict(res[k]) for k in ("random", "payroll_only", "behavior_only",
                                     "live_analog", "fitted_full")}
    out["banded_twin"] = dict(g3["teamfit_conditional_gate"]["chain_candidate"])
    out["_source"] = {"artifact": "data/fa_gate3_eval.json",
                      "generated_at": g3.get("generated_at")}
    return out


def _signing_record(s: dict, fm) -> dict:
    return {"player_key": s.get("player_key"), "player_name": s.get("player_name"),
            "class_year": s.get("class_year"), "mlbam_id": s.get("mlbam_id"),
            "from_team": s.get("from_team"), "to_team": s.get("to_team"),
            "qo": bool(s.get("qo")), "years": s.get("years"),
            "npv_usd": float(fm._npv_of(s))}


def real_inputs() -> LabInputs:
    """The registered inputs (the look only). Cached pages only."""
    import fa_cba
    import fa_market as fm
    import scrapers
    doc = (ROOT / fd.GATE_DOC).read_text(encoding="utf-8")
    with scrapers.cache_only():
        realized = fb.build_rows()
        enriched = fm.enriched_signings(2015, 2026)
        frame_keys = {(r["winter"], r["signing"]) for r in realized}
        signings, dup = {}, 0
        all_signings = {}
        for s in enriched:
            rec = _signing_record(s, fm)
            all_signings.setdefault((s["class_year"], s.get("mlbam_id")), rec)
            k = (s["class_year"], s["player_key"])
            if s.get("to_team") not in fb.ORGS or k not in frame_keys:
                continue
            if k in signings:
                dup += 1
            signings[k] = rec
        winters = sorted({r["winter"] for r in realized})
        states = {Y: fd.club_state(Y) for Y in winters}

    def gate2():
        with scrapers.cache_only():
            return collect_gate2()

    def primary(override):
        with scrapers.cache_only():
            return fb.build_rows(price_override=override)

    mlbtr = None
    if MLBTR_RETRO_PATH.exists():
        mlbtr = json.loads(MLBTR_RETRO_PATH.read_text(encoding="utf-8"))
        mlbtr["_sha256"] = hashlib.sha256(MLBTR_RETRO_PATH.read_bytes()).hexdigest()
    return LabInputs(
        realized_rows=realized, primary_rows_fn=primary, signings=signings,
        all_signings=all_signings, club_states=states, gate2_fn=gate2,
        mlbtr=mlbtr, qo_acceptances=fa_cba.qo_acceptances(), gate_doc_text=doc,
        weights=fb._live_weights(), registered_step0=registered_step0(),
        fixture=False, input_counts={"duplicate_gate3_keys": dup,
                                     "enriched_signings": len(enriched)})


# ==========================================================================
# the fixture (dry run): synthetic, with nulls
# ==========================================================================

FIXTURE_SIZES = {2018: 40, 2019: 36, 2020: 0, 2021: 34, 2022: 33}
FIXTURE_HISTORY = (2015, 2016, 2017)
FIXTURE_NO_PAYROLL = {2020: "MIA"}         # season Y-1 = 2020 has no MIA row
FIXTURE_SEED = 20261009


def fixture_inputs() -> LabInputs:
    """A synthetic chain over winters 2018-2022 whose 2020 winter is empty.
    It carries: a member with no Gate 2 price, a club with no payroll row,
    an OAK club code, a duplicate and an integrity drop in the collection, a
    collected tuple with no Gate 3 signing, an accepted QO, and MLBTR rows that
    are unresolved, tied, missing a pick or not a scored signing."""
    rng = np.random.default_rng(FIXTURE_SEED)
    orgs = fb.ORGS
    spend = rng.normal(0.0, 1.0, len(orgs))
    signings_by_year: dict[int, list[dict]] = defaultdict(list)
    mid = 900000
    for Y in FIXTURE_HISTORY + tuple(FIXTURE_SIZES):
        n = FIXTURE_SIZES.get(Y, 25)
        for i in range(n):
            mid += 1
            frm = None if rng.random() < 0.12 else orgs[int(rng.integers(0, 30))]
            if frm is not None and rng.random() < 0.3:
                to = frm
            else:
                p = np.exp(spend - spend.max())
                to = orgs[int(rng.choice(30, p=p / p.sum()))]
            years = int(rng.integers(1, 6))
            guar = float(round(float(np.exp(rng.normal(16.0, 1.1))), -3))
            signings_by_year[Y].append({
                "player_key": f"fx{Y}_{i:02d}", "player_name": f"Fixture Player {Y} {i}",
                "class_year": Y, "mlbam_id": mid, "from_team": frm,
                "to_team": ("OAK" if to == "ATH" and Y in FIXTURE_HISTORY else to),
                "qo": bool(rng.random() < 0.1), "years": years,
                "guarantee_usd": guar, "mlb_deal": True,
                "npv_guarantee_usd": guar})

    def load(y):
        return {s["player_key"]: s for s in signings_by_year.get(y, [])}

    payroll_by_season = {}
    for season in range(2016, 2023):
        pay = {}
        for j, o in enumerate(orgs):
            if FIXTURE_NO_PAYROLL.get(season) == o:
                continue
            code = "OAK" if o == "ATH" else o
            pay[code] = {"tax_payroll_usd": float(150e6 + 40e6 * spend[j]
                                                  + rng.normal(0, 10e6)),
                         "payor": ("1st-Time" if spend[j] > 1.0 else "Non-Tax")}
        payroll_by_season[season] = pay

    winters = sorted(FIXTURE_SIZES)
    states = {Y: fd.club_state(Y, load_signings=load, npv_fn=lambda k, y, g: float(g),
                               payroll=payroll_by_season[Y - 1]) for Y in winters}

    def rows_for(override):
        rows = []
        for Y in winters:
            st = states[Y]
            for s in signings_by_year.get(Y, []):
                npv = s["guarantee_usd"]
                aav = npv / max(s["years"], 1)
                if override is not None:
                    price = override.get((Y, s["player_key"]))
                    if price is None:
                        continue
                    npv, aav = float(price[0]), float(price[1])
                srng = np.random.default_rng(int(s["mlbam_id"]))
                for j, o in enumerate(orgs):
                    tax = st["clubs"][o]["tax_payroll_prev_usd"]
                    afford = (max(0.0, min(1.0, (st["threshold_prev_usd"] - tax) / (2 * aav)))
                              if tax else 0.5)
                    beh = float(min(1.0, max(0.0, 0.5 + 0.2 * spend[j] + srng.normal(0, 0.1))))
                    rows.append({
                        "winter": Y, "signing": s["player_key"], "org": o,
                        "signed": 1 if s["to_team"] == o else 0,
                        "need": float(srng.random() < 0.2),
                        "window": float(srng.random()),
                        "afford": afford, "park": float(srng.random()),
                        "behavior": beh, "behavior_clipped": beh,
                        "behavior_cond": float(min(1.0, beh * (0.8 + 0.4 * srng.random()))),
                        "incumbent": 1.0 if s["from_team"] == o else 0.0})
        return rows

    signings, all_signings = {}, {}
    for Y, lst in signings_by_year.items():
        for s in lst:
            rec = {"player_key": s["player_key"], "player_name": s["player_name"],
                   "class_year": Y, "mlbam_id": s["mlbam_id"],
                   "from_team": s["from_team"], "to_team": s["to_team"], "qo": s["qo"],
                   "years": s["years"], "npv_usd": float(s["guarantee_usd"])}
            all_signings[(Y, s["mlbam_id"])] = rec
            if Y in FIXTURE_SIZES:
                signings[(Y, s["player_key"])] = rec

    tuples = []
    for (Y, key), rec in sorted(signings.items()):
        if key == "fx2019_03":                       # the member with no price
            continue
        g = rec["npv_usd"]
        pg = g * float(np.exp(rng.normal(0, 0.3)))
        act = g + (5.0 if key == "fx2021_05" else 0.0)  # an integrity drop
        t = (Y, key, pg / 1e6, act / 1e6, pg / max(rec["years"], 1) / 1e6,
             g / max(rec["years"], 1) / 1e6, float(rec["years"]), float(rec["years"]))
        tuples.append(t)
        if key == "fx2022_07":                       # a duplicate key
            tuples.append(t)
    tuples.append((2021, "not_a_gate3_signing", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))

    def pick(Y, i):
        return signings_by_year[Y][i]

    mlbtr_rows = {
        2017: [{"mlbam_id": pick(2017, 0)["mlbam_id"], "pred_team": pick(2017, 0)["to_team"],
                "pred_team_by_writer": None},
               {"mlbam_id": None, "pred_team": "NYY", "pred_team_by_writer": None}],
        2019: [{"mlbam_id": pick(2019, 0)["mlbam_id"], "pred_team": "LAD",
                "pred_team_by_writer": None},
               {"mlbam_id": pick(2019, 1)["mlbam_id"], "pred_team": pick(2019, 1)["to_team"],
                "pred_team_by_writer": None},
               {"mlbam_id": None, "pred_team": "BOS", "pred_team_by_writer": None},
               {"mlbam_id": 123, "pred_team": "SEA", "pred_team_by_writer": None}],
        2021: [{"mlbam_id": pick(2021, 0)["mlbam_id"], "pred_team": None,
                "pred_team_by_writer": [
                    {"team": pick(2021, 0)["to_team"]}, {"team": "NYM"},
                    {"team": None}]},
               {"mlbam_id": pick(2021, 1)["mlbam_id"], "pred_team": None,
                "pred_team_by_writer": None}],
        2022: [{"mlbam_id": pick(2022, i)["mlbam_id"],
                "pred_team": pick(2022, i)["to_team"] if i % 2 else "TOR",
                "pred_team_by_writer": None} for i in range(6)],
    }
    mlbtr = {"_sha256": "fixture", "seasons": {
        f"{cy - 1}-{str(cy)[2:]}": {"class_year": cy, "n_unresolved": sum(
            1 for r in rows if r["mlbam_id"] is None), "rows": rows}
        for cy, rows in mlbtr_rows.items()}}
    qo_acc = [{"class_year": 2021, "player_name": pick(2021, 2)["player_name"],
               "team": pick(2021, 2)["from_team"]}]
    doc = (ROOT / fd.GATE_DOC).read_text(encoding="utf-8")
    return LabInputs(
        realized_rows=rows_for(None), primary_rows_fn=rows_for, signings=signings,
        all_signings=all_signings, club_states=states, gate2_fn=lambda: list(tuples),
        mlbtr=mlbtr, qo_acceptances=qo_acc, gate_doc_text=doc,
        weights=fb._live_weights(), registered_step0=registered_step0(), fixture=True,
        input_counts={"duplicate_gate3_keys": 0})


# ==========================================================================
# the join (section 4.2)
# ==========================================================================

def join_gate2(tuples: list, signings: dict, winters=()) -> tuple[dict, dict]:
    """{(winter, key): (guarantee_usd, aav_usd)} and the counts by winter
    (every winter in ``winters`` is listed, an empty one with zeros)."""
    by_key: dict[tuple, list] = defaultdict(list)
    for t in tuples:
        by_key[(int(t[0]), t[1])].append(t)
    winters = sorted({int(Y) for Y in winters} | {k[0] for k in signings}
                     | {k[0] for k in by_key})
    counts = {Y: {"gate3_signings": 0, "matched": 0, "unmatched": 0, "duplicate": 0,
                  "integrity_drop": 0, "tuples_without_gate3_signing": 0}
              for Y in winters}
    override = {}
    for (Y, key), rec in sorted(signings.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        c = counts[Y]
        c["gate3_signings"] += 1
        got = by_key.get((Y, key)) or []
        if not got:
            c["unmatched"] += 1
            continue
        if len(got) > 1:
            c["duplicate"] += 1
            continue
        t = got[0]
        if abs(float(t[3]) * 1e6 - float(rec["npv_usd"])) > 1.0:
            c["integrity_drop"] += 1
            continue
        c["matched"] += 1
        override[(Y, key)] = (float(t[2]) * 1e6, float(t[4]) * 1e6)
    for (Y, key) in by_key:
        if (Y, key) not in signings:
            counts[Y]["tuples_without_gate3_signing"] += 1
    total = {k: sum(c[k] for c in counts.values()) for k in
             next(iter(counts.values()), {})}
    return override, {"by_winter": {str(Y): c for Y, c in counts.items()}, "total": total}


# ==========================================================================
# frames
# ==========================================================================

def build_frame(rows: list, signings: dict, club_states: dict, price: str,
                exclude: set | None = None) -> dict:
    """Members sorted by (winter, player_key), each with its six features over
    the 30 clubs, the signed club's index and the frame's own AAV."""
    grouped = fd.comps_from_rows(rows)
    members, dropped = [], {"no_single_signed_club": 0, "no_signing_record": 0,
                            "excluded": 0}
    flags = defaultdict(int)
    third = defaultdict(int)
    for (Y, key) in sorted(grouped, key=lambda k: (k[0], str(k[1]))):
        comps = grouped[(Y, key)]
        if exclude and (Y, key) in exclude:
            dropped["excluded"] += 1
            continue
        rec = signings.get((Y, key))
        if rec is None:
            dropped["no_signing_record"] += 1
            continue
        if set(comps) != set(fd.ORGS) or sum(int(comps[o]["signed"]) for o in fd.ORGS) != 1:
            dropped["no_single_signed_club"] += 1
            continue
        y = next(j for j, o in enumerate(fd.ORGS) if comps[o]["signed"])
        if price == "realized":
            aav = rec["npv_usd"] / max(int(rec["years"] or 1), 1)
        else:
            aav = rec["_price_aav_usd"]
        feat = fd.member_features(club_states[Y], comps, aav_usd=aav, qo=rec["qo"],
                                  from_team=rec["from_team"])
        for k, v in feat["flags"].items():
            flags[k] += v
        if club_states[Y].get("threshold_regime") == "cba_2017":
            third[str(Y)] += feat["third_tier_rows"]
        inc = [j for j, o in enumerate(fd.ORGS) if comps[o]["incumbent"]]
        members.append({
            "winter": Y, "key": key, "y": y, "feat": feat, "aav_usd": aav,
            "mlbam_id": rec.get("mlbam_id"), "player_name": rec.get("player_name"),
            "incumbent_idx": inc[0] if len(inc) == 1 else None,
            "afford": [float(comps[o]["afford"]) for o in fd.ORGS],
            "behavior_cond": [float(comps[o]["behavior_cond"]) for o in fd.ORGS],
            "behavior": [float(comps[o]["behavior"]) for o in fd.ORGS],
            "unbanded_analog": [sum(fb.LIVE_WEIGHTS[f] * float(comps[o][f]) for f in fb.FEATS)
                                for o in fd.ORGS],
        })
    winters = sorted({m["winter"] for m in members})
    scored = []
    for Y in winters:
        n_prior = sum(1 for m in members if m["winter"] < Y)
        if n_prior >= MIN_TRAIN_POSITIVES:
            scored.append(Y)
    return {"price": price, "members": members, "winters": winters,
            "scored_winters": scored, "dropped": dropped, "flags": dict(flags),
            "third_tier_rows_2017_agreement": dict(third)}


def _scored(frame) -> list:
    s = set(frame["scored_winters"])
    return [m for m in frame["members"] if m["winter"] in s]


# ==========================================================================
# fits (section 6, 7)
# ==========================================================================

def _member_for_arm(m: dict, arm: str) -> dict:
    if arm == "L_perm":
        return fd.permute_l(m["feat"], fd.permutation_for_winter(m["winter"]))
    return m["feat"]


def fit_arms(frame: dict) -> dict:
    """Every fitted arm's forward chain: per scored winter, the fold's
    coefficients, standardization, convergence and coef_hash, and the
    out-of-fold probabilities in the scored order. Also incumbency_only's
    per-fold re-sign share."""
    out = {}
    scored = _scored(frame)
    for arm in FITTED_ARMS:
        names = fd.ARM_FEATURES[arm]
        folds, probs = {}, []
        for Y in frame["scored_winters"]:
            train = [m for m in frame["members"] if m["winter"] < Y]
            test = [m for m in frame["members"] if m["winter"] == Y]
            Xtr = fd.stack([_member_for_arm(m, arm) for m in train], names)
            Xte = fd.stack([_member_for_arm(m, arm) for m in test], names)
            Xtr, Xte, stats = fd.fold_standardize(Xtr, Xte, names)
            coefs, info = fd.fit_clogit(Xtr, np.asarray([m["y"] for m in train]), names)
            rec = {"coefs": coefs, "standardization": stats, **info,
                   "zero_sd_features": sorted(f for f, s in stats.items() if s["zero_sd"])}
            rec["coef_hash"] = fd.coef_hash({"arm": arm, "winter": Y, "names": list(names),
                                             "coefs": coefs, "standardization": stats})
            folds[str(Y)] = rec
            probs.append(fd.predict_proba(Xte, coefs, names))
        out[arm] = {"features": list(names), "folds": folds,
                    "probs": (np.vstack(probs) if probs else np.zeros((0, fd.N_CLUBS)))}
    shares = {}
    for Y in frame["scored_winters"]:
        train = [m for m in frame["members"] if m["winter"] < Y and m["incumbent_idx"] is not None]
        n_own = sum(1 for m in train if m["y"] == m["incumbent_idx"])
        shares[str(Y)] = {"n": len(train), "resign": n_own,
                          "share": (n_own / len(train)) if train else None}
    out["incumbency_only"] = {"fold_resign_share": shares,
                              "probs": _incumbency_probs(scored, shares)}
    return out


def _incumbency_probs(scored: list, shares: dict) -> np.ndarray:
    P = np.full((len(scored), fd.N_CLUBS), 1.0 / fd.N_CLUBS)
    for i, m in enumerate(scored):
        s = shares[str(m["winter"])]["share"]
        if m["incumbent_idx"] is None or s is None:
            continue
        P[i, :] = (1.0 - s) / (fd.N_CLUBS - 1)
        P[i, m["incumbent_idx"]] = s
    return P


def serving_fit(frame: dict) -> dict:
    """P and N fitted on every matched winter of the frame: the coefficients a
    flip would serve for the next class, with their coef_hash."""
    out = {}
    for arm in ("P", "N"):
        names = fd.ARM_FEATURES[arm]
        ms = frame["members"]
        X = fd.stack([m["feat"] for m in ms], names)
        X, _, stats = fd.fold_standardize(X, X[:0], names)
        coefs, info = fd.fit_clogit(X, np.asarray([m["y"] for m in ms]), names)
        rec = {"features": list(names), "coefs": coefs, "standardization": stats,
               "winters": frame["winters"], **info}
        rec["coef_hash"] = fd.coef_hash({"arm": arm, "winter": "serving",
                                         "names": list(names), "coefs": coefs,
                                         "standardization": stats})
        out[arm] = rec
    return out


# ==========================================================================
# metrics (section 8)
# ==========================================================================

def _ranks(scores: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Rank of the signed club under a descending sort that keeps ORGS order
    on ties (Gate 3's sort, ties alphabetical by club code)."""
    n = len(y)
    if n == 0:
        return np.zeros(0, dtype=int)
    s = scores[np.arange(n), y][:, None]
    j = np.arange(scores.shape[1])[None, :]
    return 1 + (scores > s).sum(axis=1) + ((scores == s) & (j < y[:, None])).sum(axis=1)


def rank_metrics(scores: np.ndarray, members: list) -> dict:
    """Top-1/3/5 and MRR exactly as fa_fit_backtest._rank_metrics computes
    them (four decimals), on the frame's scored rows."""
    pooled = {f"{m['winter']}:{m['key']}": [
        {"signed": 1 if j == m["y"] else 0, "_s": float(scores[i, j])}
        for j in range(fd.N_CLUBS)] for i, m in enumerate(members)}
    if not pooled:
        return {"n": 0, "top1": None, "top3": None, "top5": None, "mrr": None}
    return fb._rank_metrics(pooled, lambda r: r["_s"])


def _rr(scores: np.ndarray, members: list) -> np.ndarray:
    return 1.0 / _ranks(scores, np.asarray([m["y"] for m in members], dtype=int))


H30 = sum(1.0 / k for k in range(1, 31))


def _expected_random():
    return {1: 1 / 30, 3: 3 / 30, 5: 5 / 30, "rr": H30 / 30}


def _expected_incumbency(m: dict) -> dict:
    if m["incumbent_idx"] is None:
        return _expected_random()
    if m["y"] == m["incumbent_idx"]:
        return {1: 1.0, 3: 1.0, 5: 1.0, "rr": 1.0}
    return {1: 0.0, 3: 2 / 29, 5: 4 / 29, "rr": sum(1.0 / r for r in range(2, 31)) / 29}


def analytic_metrics(members: list, kind: str) -> tuple[dict, np.ndarray]:
    ex = [(_expected_random() if kind == "random" else _expected_incumbency(m))
          for m in members]
    n = len(ex)
    if not n:
        return {"n": 0, "top1": None, "top3": None, "top5": None, "mrr": None}, np.zeros(0)
    rr = np.asarray([e["rr"] for e in ex])
    return {"n": n, "top1": round(sum(e[1] for e in ex) / n, 4),
            "top3": round(sum(e[3] for e in ex) / n, 4),
            "top5": round(sum(e[5] for e in ex) / n, 4),
            "mrr": round(float(rr.mean()), 4)}, rr


def log_losses(P: np.ndarray, members: list) -> np.ndarray:
    if not members:
        return np.zeros(0)
    y = np.asarray([m["y"] for m in members], dtype=int)
    return -np.log(P[np.arange(len(y)), y])


def reliability(P: np.ndarray, members: list) -> dict:
    """OLS slope of the realized indicator on P (with an intercept) over all
    30 x n rows, and ECE in ten equal-count bins sorted by P, ties by club
    code, then winter and player key."""
    if not members:
        return {"slope": None, "ece": None, "rows": 0}
    rows = []
    for i, m in enumerate(members):
        for j, o in enumerate(fd.ORGS):
            rows.append((float(P[i, j]), o, m["winter"], str(m["key"]),
                         1.0 if j == m["y"] else 0.0))
    p = np.asarray([r[0] for r in rows])
    r = np.asarray([r[4] for r in rows])
    vp = float(np.var(p))
    slope = float(np.mean((p - p.mean()) * (r - r.mean())) / vp) if vp > 0 else None
    rows.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    order_p = np.asarray([t[0] for t in rows])
    order_r = np.asarray([t[4] for t in rows])
    ece = 0.0
    for bp, br in zip(np.array_split(order_p, 10), np.array_split(order_r, 10)):
        if len(bp):
            ece += len(bp) / len(rows) * abs(float(br.mean()) - float(bp.mean()))
    return {"slope": slope, "ece": ece, "rows": len(rows)}


def baseline_scores(members: list) -> dict:
    """Ranking scores of the four ranked baselines on a frame's members."""
    return {
        "payroll_space": np.asarray([m["afford"] for m in members]).reshape(-1, fd.N_CLUBS),
        "payroll_level": np.asarray([m["feat"]["payroll_level"] for m in members]).reshape(-1, fd.N_CLUBS),
        "behavior_only": np.asarray([m["behavior_cond"] for m in members]).reshape(-1, fd.N_CLUBS),
        "live_analog": np.asarray([m["feat"]["fit_analog"] for m in members]).reshape(-1, fd.N_CLUBS),
        "registered_unbanded_live_analog": np.asarray(
            [m["unbanded_analog"] for m in members]).reshape(-1, fd.N_CLUBS),
        "registered_unbanded_behavior_only": np.asarray(
            [m["behavior"] for m in members]).reshape(-1, fd.N_CLUBS),
    }


def frame_metrics(frame: dict, fits: dict) -> dict:
    """Every arm and baseline on the frame's scored rows: rank metrics, and
    for P, N, L_perm, random and incumbency_only the log loss; reliability for
    the three fitted arms. Also the per-signing vectors the bootstrap reads."""
    members = _scored(frame)
    out, rr, ll = {}, {}, {}
    for arm in FITTED_ARMS:
        P = fits[arm]["probs"]
        out[arm] = rank_metrics(P, members)
        rr[arm] = _rr(P, members)
        ll[arm] = log_losses(P, members)
        out[arm]["log_loss"] = float(ll[arm].mean()) if len(ll[arm]) else None
        out[arm]["reliability"] = reliability(P, members)
    out["random"], rr["random"] = analytic_metrics(members, "random")
    ll["random"] = np.full(len(members), LN30)
    out["random"]["log_loss"] = LN30 if members else None
    out["incumbency_only"], rr["incumbency_only"] = analytic_metrics(members, "incumbency")
    ll["incumbency_only"] = log_losses(fits["incumbency_only"]["probs"], members)
    out["incumbency_only"]["log_loss"] = (float(ll["incumbency_only"].mean())
                                          if members else None)
    for name, sc in baseline_scores(members).items():
        out[name] = rank_metrics(sc, members)
        rr[name] = _rr(sc, members) if members else np.zeros(0)
    return {"metrics": out, "rr": rr, "ll": ll}


def per_winter(frame: dict, fits: dict) -> dict:
    members = _scored(frame)
    out = {}
    for Y in frame["scored_winters"]:
        idx = [i for i, m in enumerate(members) if m["winter"] == Y]
        ms = [members[i] for i in idx]
        row = {"n": len(ms)}
        for arm in FITTED_ARMS:
            P = fits[arm]["probs"][idx]
            row[arm] = {**rank_metrics(P, ms), "log_loss": float(log_losses(P, ms).mean())}
        sc = baseline_scores(ms)
        for name in ("payroll_space", "payroll_level", "behavior_only", "live_analog"):
            row[name] = rank_metrics(sc[name], ms)
        row["random"] = analytic_metrics(ms, "random")[0]
        row["incumbency_only"] = analytic_metrics(ms, "incumbency")[0]
        out[str(Y)] = row
    return out


# ==========================================================================
# floors, clauses, ship rule (sections 9-11)
# ==========================================================================

def bootstrap_draws(n: int) -> np.ndarray:
    """The one set of resamples: rng = default_rng(7), 2,000 draws of
    rng.integers(0, n, n), over the scored signings in (winter, key) order."""
    rng = np.random.default_rng(BOOT_SEED)
    if n == 0:
        return np.zeros((BOOT_B, 0), dtype=int)
    return np.stack([rng.integers(0, n, n) for _ in range(BOOT_B)])


def floors_block(ll_p: np.ndarray, draws: np.ndarray) -> dict:
    """Written BEFORE any arm's mean metric (section 9)."""
    if ll_p.size == 0:
        sd = None
    else:
        sd = float(np.std(ll_p[draws].mean(axis=1), ddof=1))
    return {"mrr_mde95": MRR_MDE95,
            "log_loss_boot_sd": sd,
            "log_loss_floor": (1.96 * sd) if sd is not None else None,
            "resample_seed": BOOT_SEED, "resample_count": BOOT_B,
            "resample_unit": "one signing with its 30 rows",
            "n_scored": int(ll_p.size)}


def _p_le_zero(diffs: np.ndarray) -> float:
    return (1.0 + float(np.sum(diffs <= 0))) / (BOOT_B + 1.0)


def paired_mde95(a: np.ndarray, b: np.ndarray, draws: np.ndarray) -> float | None:
    if a.size == 0:
        return None
    d = a[draws].mean(axis=1) - b[draws].mean(axis=1)
    return 1.96 * float(np.std(d, ddof=1))


def clauses(m: dict, rr: dict, ll: dict, draws: dict, floors: dict, per_w: dict,
            arm: str = "P") -> dict:
    """C1 to C5 for one arm in P's place (sections 10, 11)."""
    a = m[arm]

    def gt(x, y, by):
        return x is not None and y is not None and (x - y) > by

    c1 = (gt(a["mrr"], m["payroll_space"]["mrr"], MRR_MDE95)
          and gt(a["mrr"], m["payroll_level"]["mrr"], MRR_MDE95)
          and a["top5"] is not None
          and a["top5"] > m["payroll_space"]["top5"] and a["top5"] > m["payroll_level"]["top5"])
    c2 = gt(a["mrr"], m["live_analog"]["mrr"], MRR_MDE95)
    rel = a.get("reliability") or {}
    c4 = (a.get("log_loss") is not None and floors["log_loss_floor"] is not None
          and (LN30 - a["log_loss"]) > floors["log_loss_floor"]
          and rel.get("slope") is not None
          and SLOPE_BAND[0] <= rel["slope"] <= SLOPE_BAND[1])
    wins = sum(1 for row in per_w.values()
               if row[arm]["mrr"] is not None and row["payroll_space"]["mrr"] is not None
               and row[arm]["mrr"] >= row["payroll_space"]["mrr"])
    c5 = len(per_w) >= STABILITY_MIN_WINTERS and wins >= STABILITY_MIN_WINTERS
    out = {"C1": bool(c1), "C2": bool(c2), "C4": bool(c4), "C5": bool(c5),
           "C5_winters_at_or_above": wins, "C5_scored_winters": len(per_w)}
    if arm != "P":
        return out
    # C3: P against N, Holm over MRR and log loss, then the L_perm share.
    if rr["P"].size:
        d_mrr = rr["P"][draws].mean(axis=1) - rr["N"][draws].mean(axis=1)
        d_ll = ll["N"][draws].mean(axis=1) - ll["P"][draws].mean(axis=1)
        p = {"mrr": _p_le_zero(d_mrr), "log_loss": _p_le_zero(d_ll)}
    else:
        p = {"mrr": 1.0, "log_loss": 1.0}
    order = sorted(p, key=lambda k: (p[k], k))
    rejected = []
    if p[order[0]] <= HOLM_FIRST:
        rejected.append(order[0])
        if p[order[1]] <= HOLM_SECOND:
            rejected.append(order[1])
    M = {"mrr": {x: m[x]["mrr"] for x in FITTED_ARMS},
         "log_loss": {x: (-m[x]["log_loss"] if m[x]["log_loss"] is not None else None)
                      for x in FITTED_ARMS}}
    favours, shares = {}, {}
    for k in ("mrr", "log_loss"):
        mp, mn, ml = M[k]["P"], M[k]["N"], M[k]["L_perm"]
        favours[k] = (mp is not None and mn is not None and mp > mn)
        shares[k] = ((ml - mn) / (mp - mn)) if (favours[k] and ml is not None) else None
    c3 = (any(favours[k] for k in rejected)
          and all(favours[k] and shares[k] is not None and shares[k] < LPERM_SHARE_CAP
                  for k in rejected)
          and bool(rejected))
    out.update({"C3": bool(c3), "C3_p": p, "C3_holm_rejected": rejected,
                "C3_point_favours_P": favours, "C3_lperm_share": shares})
    return out


def ship_verdict(cl_p: dict, cl_n: dict) -> dict:
    core = ("C1", "C2", "C4", "C5")
    if all(cl_p[c] for c in core) and cl_p["C3"]:
        return {"serve": "P", "loss": None}
    if all(cl_p[c] for c in core) and not cl_p["C3"]:
        if all(cl_n[c] for c in core):
            return {"serve": "N", "loss": NULL_LINE}
        return {"serve": None, "loss": NULL_LINE + "; N fails a clause in P's place"}
    failed = [c for c in core if not cl_p[c]]
    return {"serve": None, "loss": "clauses failed: " + ", ".join(failed)}


# ==========================================================================
# reported blocks (sections 12, 13)
# ==========================================================================

def expected_deals(frame: dict, fits: dict) -> dict:
    members = _scored(frame)
    P = fits["P"]["probs"]
    out = {}
    for Y in frame["scored_winters"]:
        idx = [i for i, m in enumerate(members) if m["winter"] == Y]
        out[str(Y)] = {o: {"expected": round(float(P[idx, j].sum()), 4) if idx else 0.0,
                           "realized": sum(1 for i in idx if members[i]["y"] == j)}
                       for j, o in enumerate(fd.ORGS)}
    return out


def _mlbtr_pick_credit(row: dict) -> dict | None:
    """{club: credit} for one MLBTR row: the named club, or the club most
    writers name, a k-way tie crediting 1/k each. None when no club parses."""
    team = fd.canonical_club(row.get("pred_team"))
    if team:
        return {team: 1.0}
    picks = [fd.canonical_club(p.get("team")) for p in (row.get("pred_team_by_writer") or [])]
    picks = [p for p in picks if p]
    if not picks:
        return None
    tally = defaultdict(int)
    for p in picks:
        tally[p] += 1
    top = max(tally.values())
    tied = sorted(c for c, v in tally.items() if v == top)
    return {c: 1.0 / len(tied) for c in tied}


def industry_retro(mlbtr: dict | None, frame: dict, fits: dict, all_signings: dict) -> dict:
    if not mlbtr:
        return {"available": False, "reason": "no MLBTR retro file"}
    members = _scored(frame)
    by_id = {(m["winter"], m["mlbam_id"]): i for i, m in enumerate(members)}
    counts, out = {}, {"source_sha256": mlbtr.get("_sha256")}
    matched = []
    alone = defaultdict(list)
    for label, season in sorted((mlbtr.get("seasons") or {}).items()):
        cy = int(season["class_year"])
        c = {"rows": 0, "unresolved": 0, "not_a_scored_signing": 0, "no_parsed_pick": 0,
             "matched": 0}
        for r in season.get("rows") or []:
            c["rows"] += 1
            if r.get("mlbam_id") is None:
                c["unresolved"] += 1
                continue
            credit = _mlbtr_pick_credit(r)
            i = by_id.get((cy, r["mlbam_id"]))
            if i is None:
                c["not_a_scored_signing"] += 1
                rec = all_signings.get((cy, r["mlbam_id"]))
                club = fd.canonical_club(rec.get("to_team")) if rec else None
                if (cy not in frame["scored_winters"] and club and credit is not None):
                    alone[str(cy)].append(credit.get(club, 0.0))
                continue
            if credit is None:
                c["no_parsed_pick"] += 1
                continue
            c["matched"] += 1
            matched.append((i, credit.get(fd.ORGS[members[i]["y"]], 0.0)))
        counts[label] = c
    out["counts_by_offseason"] = counts
    out["mlbtr_alone_unscored_class_years"] = {
        cy: {"n": len(v), "hit_rate": (sum(v) / len(v)) if v else None}
        for cy, v in sorted(alone.items())}
    arms = {}
    idx = np.asarray([i for i, _ in matched], dtype=int)
    mlbtr_hit = np.asarray([h for _, h in matched], dtype=float)
    ms = [members[i] for i in idx]
    rng = np.random.default_rng(BOOT_SEED)
    draws = (np.stack([rng.integers(0, len(idx), len(idx)) for _ in range(BOOT_B)])
             if len(idx) else None)
    for arm in ("P", "N"):
        if not len(idx):
            arms[arm] = {"n": 0}
            continue
        P = fits[arm]["probs"][idx]
        ranks = _ranks(P, np.asarray([m["y"] for m in ms], dtype=int))
        model_hit = (ranks == 1).astype(float)
        d = (model_hit[draws].mean(axis=1) - mlbtr_hit[draws].mean(axis=1))
        arms[arm] = {"n": len(idx), "model_hit_rate": float(model_hit.mean()),
                     "mlbtr_hit_rate": float(mlbtr_hit.mean()),
                     "paired_diff": float(model_hit.mean() - mlbtr_hit.mean()),
                     "paired_diff_ci95": [float(np.quantile(d, 0.025)),
                                          float(np.quantile(d, 0.975))],
                     "model_top3_hit_rate": float((ranks <= 3).mean()),
                     "model_mrr": float((1.0 / ranks).mean())}
    out["head_to_head"] = arms
    out["pick_rule"] = ("the club the post names; where it prints each writer's pick, "
                        "the club most writers name, a k-way tie crediting 1/k each; a row "
                        "with no parsed club is counted, not scored")
    return out


def _qo_excluded_keys(frame: dict, acceptances: list) -> tuple[set, dict]:
    from scrapers import canonical_player_key, normalize_key

    def norm(name):
        return canonical_player_key(normalize_key(name)) if name else None

    want = {(int(a["class_year"]), norm(a.get("player_name"))) for a in acceptances}
    keys = set()
    for m in frame["members"]:
        if (m["winter"], norm(m.get("player_name"))) in want or (m["winter"], m["key"]) in want:
            keys.add((m["winter"], m["key"]))
    return keys, {"acceptances": len(acceptances), "matched_signings": len(keys)}


# ==========================================================================
# the run
# ==========================================================================

def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_jsonable(v) for v in o.tolist()]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def persist(doc: dict, out_path: Path, step: str) -> None:
    """Rewrite the artifact with the step appended to its order list."""
    doc.setdefault("order", []).append(step)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(_jsonable(doc), indent=1) + "\n", encoding="utf-8")


def step0(inputs: LabInputs) -> dict:
    """The realized-price frame reproduced the way run_fit_gate scores it,
    without calling run_fit_gate; a drift is disclosed beside the registered
    value and the run proceeds (the TEAMFIT drift rule)."""
    rows = inputs.realized_rows
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[f"{r['winter']}:{r['signing']}"].append(r)
    W = fb.LIVE_WEIGHTS
    today = {
        "random": {"n": len(groups), "top1": round(1 / 30, 4), "top3": round(3 / 30, 4),
                   "top5": round(5 / 30, 4), "mrr": round(H30 / 30, 4)},
        "payroll_only": fb._rank_metrics(groups, lambda r: r["afford"]),
        "behavior_only": fb._rank_metrics(groups, lambda r: r["behavior"]),
        "live_analog": fb._rank_metrics(groups, lambda r: sum(W[f] * r[f] for f in fb.FEATS)),
        "banded_twin": fb._rank_metrics(groups, lambda r: (
            sum(W[f] * r[f] for f in ("need", "window", "afford", "park"))
            + W["behavior"] * r["behavior_cond"])),
    }
    feats = fb.FEATS + ("incumbent",)
    ff = {}
    for Y in sorted({r["winter"] for r in rows}):
        cf = fb._fit_logit([r for r in rows if r["winter"] < Y], feats)
        if cf is None:
            continue
        for k, g in groups.items():
            if k.startswith(f"{Y}:"):
                ff[k] = [{**r, "_s": sum(c * r[f] for c, f in zip(cf, feats))} for r in g]
    today["fitted_full"] = (fb._rank_metrics(ff, lambda r: r["_s"]) if ff
                            else {"n": 0, "top1": None, "top3": None, "top5": None, "mrr": None})
    reg = inputs.registered_step0
    arms, drift = {}, []
    for arm in STEP0_ARMS:
        r = {k: reg[arm].get(k) for k in ("n", "top1", "top3", "top5", "mrr")}
        t = {k: today[arm].get(k) for k in ("n", "top1", "top3", "top5", "mrr")}
        exact = r == t
        arms[arm] = {"registered": r, "today": t, "bit_exact": exact}
        if not exact:
            drift.append(arm)
    rows_hash = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"))
                               .encode("utf-8")).hexdigest()
    return {"registered_source": reg.get("_source"), "arms": arms, "drift": drift,
            "drift_rule": ("disclosed, registered value beside today's; the run proceeds "
                           "on the current frame; no floor, clause or definition moves"),
            "rows": len(rows), "signings": len(groups), "rows_sha256": rows_hash}


def _fold_record(fits: dict) -> dict:
    out = {a: {"features": fits[a]["features"], "folds": fits[a]["folds"]} for a in FITTED_ARMS}
    out["incumbency_only"] = {"fold_resign_share": fits["incumbency_only"]["fold_resign_share"]}
    return out


def _club_state_counts(states: dict) -> dict:
    return {str(Y): {"counts": st["counts"], "threshold_usd": st["threshold_usd"],
                     "threshold_prev_usd": st["threshold_prev_usd"],
                     "threshold_regime": st["threshold_regime"]}
            for Y, st in sorted(states.items())}


def run(inputs: LabInputs, out_path: Path, generated_at: str) -> dict:
    """The whole lab in the registered order. Returns the artifact."""
    proto = fd.check_protocol(inputs.gate_doc_text)
    weights = fd.check_weights(inputs.weights)
    doc = {"model_id": fd.MODEL_ID, "gate_doc": fd.GATE_DOC, "protocol_sha256": proto,
           "generated_at": generated_at, "dry_run": bool(inputs.fixture),
           "fit_weights": weights, "serve_flag": "FA_DESTINATION_SERVE",
           "inputs": {**inputs.input_counts,
                      "club_states": _club_state_counts(inputs.club_states)}}
    if inputs.fixture:
        doc["fixture_note"] = ("synthetic dry run: no number here is a measurement of any "
                               "free agent, club or winter")
    # (3) step 0
    doc["step0"] = step0(inputs)
    persist(doc, out_path, "step0")
    # (4) the Gate 2 collection, the join and its counts
    tuples = inputs.gate2_fn()
    override, join_counts = join_gate2(tuples, inputs.signings, inputs.club_states)
    doc["gate2_join"] = {"collected_tuples": len(tuples), **join_counts}
    persist(doc, out_path, "gate2_join")
    # (5) every arm's per-winter fit
    signings = {k: dict(v) for k, v in inputs.signings.items()}
    for k, (g, a) in override.items():
        signings[k]["_price_guarantee_usd"] = g
        signings[k]["_price_aav_usd"] = a
    primary = build_frame(inputs.primary_rows_fn(override), signings,
                          inputs.club_states, "gate2_predicted")
    fits = fit_arms(primary)
    doc["primary_frame"] = {"signings": len(primary["members"]),
                            "winters": primary["winters"],
                            "scored_winters": primary["scored_winters"],
                            "n_scored": len(_scored(primary)),
                            "dropped": primary["dropped"], "feature_flags": primary["flags"]}
    doc["folds"] = _fold_record(fits)
    persist(doc, out_path, "folds")
    # (6) the floors block, before any arm's mean metric
    members = _scored(primary)
    draws = bootstrap_draws(len(members))
    ll_p = log_losses(fits["P"]["probs"], members)
    doc["floors"] = floors_block(ll_p, draws)
    persist(doc, out_path, "floors")
    # (7) metrics, clauses, ship verdict
    fm_ = frame_metrics(primary, fits)
    pw = per_winter(primary, fits)
    cl_p = clauses(fm_["metrics"], fm_["rr"], fm_["ll"], draws, doc["floors"], pw, "P")
    cl_n = clauses(fm_["metrics"], fm_["rr"], fm_["ll"], draws, doc["floors"], pw, "N")
    verdict = ship_verdict(cl_p, cl_n)
    doc["metrics"] = fm_["metrics"]
    doc["clauses"] = {"P": cl_p, "N_in_P_place": cl_n}
    doc["verdict"] = verdict
    doc["loss_ledger"] = [verdict["loss"]] if verdict["loss"] else []
    persist(doc, out_path, "metrics_clauses_verdict")
    # (8) reported, never gated
    rep = {}
    rep["per_winter"] = pw
    m = fm_["metrics"]
    rep["N_vs_live_analog"] = {"N": m["N"], "live_analog": m["live_analog"],
                               "mrr_diff": (m["N"]["mrr"] - m["live_analog"]["mrr"])
                               if m["N"]["mrr"] is not None else None}
    rep["registered_unbanded_on_primary"] = {
        "live_analog": m["registered_unbanded_live_analog"],
        "behavior_only": m["registered_unbanded_behavior_only"]}
    rep["same_frame_paired_mde95"] = {
        c: paired_mde95(fm_["rr"]["P"], fm_["rr"][c], draws)
        for c in ("N", "L_perm", "payroll_space", "payroll_level", "behavior_only",
                  "live_analog", "incumbency_only", "random")}
    realized = build_frame(inputs.realized_rows, inputs.signings, inputs.club_states,
                           "realized")
    rfits = fit_arms(realized)
    rep["realized_price_frame"] = {
        "signings": len(realized["members"]), "scored_winters": realized["scored_winters"],
        "metrics": frame_metrics(realized, rfits)["metrics"],
        "folds": _fold_record(rfits),
        "third_tier_rows_2017_agreement": realized["third_tier_rows_2017_agreement"]}
    excl, excl_counts = _qo_excluded_keys(primary, inputs.qo_acceptances)
    qframe = build_frame(inputs.primary_rows_fn(override), signings, inputs.club_states,
                         "gate2_predicted", exclude=excl)
    qfits = fit_arms(qframe)
    rep["accepted_qo_excluded"] = {**excl_counts, "rule": "removed from the frame, refit",
                                   "metrics": frame_metrics(qframe, qfits)["metrics"]}
    rep["third_tier_rows_2017_agreement"] = primary["third_tier_rows_2017_agreement"]
    rep["expected_mlb_deals_by_club"] = expected_deals(primary, fits)
    rep["first_club_concentration_served_class"] = {
        "available": False,
        "reason": "the serving builder (plan item FAA-6) does not exist yet"}
    sf = serving_fit(primary)
    rep["serving_fit"] = sf
    doc["coef_hash"] = sf[verdict["serve"]]["coef_hash"] if verdict["serve"] else None
    doc["reported"] = rep
    persist(doc, out_path, "reported")
    # industry comparators last
    doc["industry"] = {"retro": industry_retro(inputs.mlbtr, primary, fits,
                                               inputs.all_signings),
                       "forward": {"status": "pending",
                                   "reason": ("scored against the frozen vector after the "
                                              "2026-27 class closes (gate section 13)")}}
    persist(doc, out_path, "industry")
    return doc


def _owner_question(task_out: Path, exc: BaseException) -> None:
    task_out.mkdir(parents=True, exist_ok=True)
    (task_out / "OWNER_QUESTION.md").write_text(
        "# FA destination look: exception after step 0 began\n\n"
        "Gate section 15 crash protocol: STOP, no rerun.\n\n```\n"
        + "".join(traceback.format_exception(exc)) + "```\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--look", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--task-out", type=Path, default=None)
    ap.add_argument("--generated-at", default=date.today().isoformat())
    a = ap.parse_args(argv)
    if a.dry_run:
        out = (a.out or DRY_RUN_DIR) / "fa_destination_eval.dryrun.json"
        doc = run(fixture_inputs(), out, a.generated_at)
        print(f"dry run written: {out}")
        print(f"order: {doc['order']}")
        print(f"verdict (fixture, meaningless): {doc['verdict']}")
        return 0
    if OUT_PATH.exists():
        print(f"refusing: {OUT_PATH} exists; the look runs once")
        return 2
    inputs = real_inputs()
    try:
        doc = run(inputs, OUT_PATH, a.generated_at)
    except Exception as e:
        if a.task_out:
            _owner_question(a.task_out, e)
        raise
    print(f"written: {OUT_PATH}  verdict {doc['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
