# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV wave 2: the anchor arms (EFV3_W2_1c; owner EW2-3, EW2-4, EW2-6, 2026-10-08).

eFV's order is u_c (the within-(side, V) consensus percentile, the anchor) plus the
driver terms. Every arm here REPLACES u_c ONLY: the heads, the DS-06 admission, the
DS-08 weights (data/efv_v2_assembly.json) and the output map are V2's, refit per fold on
the new anchor exactly as efv_v2_candidates.fit_mc2_anchor refits them. The comparator
stays served PROSPX consensus; the displayed consensus FV is not changed by anything
here (an anchor is an eFV input, never a board column).

THE ARMS (model_id "efv_w2_anchor:<arm>"; every rule below is fixed in this docstring
BEFORE any development read and is not tuned on one):

    an1_rel  AN-1, the reliability-weighted consensus. u_c* is the weighted mean of the
             present sources' within-(side, V) percentiles; each source's weight is its
             out-of-sample within-(side, V') Spearman against the frame's label on
             vintages V' at most V - 3, relative to the mean over the sources with
             history, shrunk toward equal with 150 pseudo rows and clamped to
             (0.6, 1.5): efv_v2_candidates.build_source_reliability, unchanged. This IS
             the rule of MC-2 (EFV3_C03); the read reproduces MC-2 and is reported as
             that reproduction, not as a new result.
    an1_pl   AN-1 simple variant, Pipeline-heavier FIXED weights: mlb_pipeline 2.0,
             fangraphs 1.0 on every (side, V), no estimation at all. Chosen before any
             read from the lane I4 finding (Pipeline leads served consensus +0.018
             within on list vintages 2011 to 2019, FanGraphs orders worse within); that
             finding was measured on vintages that include lv_dev, so the lv_dev read of
             this arm is TILTED and is labelled so in the artifact.
    an2_pos  AN-2 (the owner's idea): weights per source x position group, estimated on
             vintages at most V - 3 and shrunk toward the global AN-1 weights.
             Groups, read at or before the row's read (the EFV3_C05 covariates,
             tools/efv_v2_pricing_calibration: the latest real-grader listing inside the
             row's window; pitchers by the MiLB games-started share of the last season
             ended by the read, else a relief token in the listing):
               hitters, fine scheme: C, SS, CF, IF (2B, 3B, IF, MI), COF (LF, RF, OF),
               1B_DH (1B, DH); used for a (side, V) only when EVERY fine group holds at
               least AN2_MIN_GROUP_HISTORY (300) history rows (rows at V' <= V - 3
               carrying a scored source and a label; counts only, no outcome is read to
               decide); else the EFV3_C02 families (efv_v2_candidates.position_family:
               middle, corner, other).
               pitchers: sp and rp (the EFV3_C05 role rule).
             Per (side, V, group): each source's Spearman over the history rows of that
             group, size-weighted over the (side, V') slices of at least 20 rows
             (efv_v2_stat.MIN_GROUP_ROWS), floored at source_backtest.SPEARMAN_FLOOR,
             relative to the mean over the sources with history IN THE GROUP; when fewer
             than two sources have history in the group the group takes the global
             AN-1 weights unchanged. SHRINKAGE (fixed, stated here before any read):
             w = (n * raw + K * w_global) / (n + K), K = 150 pseudo rows
             (source_backtest.WEIGHT_SHRINK_K), then clamped to (0.6, 1.5); n is the
             source's history rows in the group. A row with no group (no in-window
             listing, no MiLB role) takes the global AN-1 weights.

MISSING SOURCES (every arm): the mean renormalizes over the sources the row carries (a
missing source contributes no weight and no column; no indicator); a one-source row's
grade is first shrunk toward the prior exactly as consensus.compute_consensus_point
shrinks it (efv_v2_candidates.anchor_values, unchanged); a row with no scored source
takes the consensus percentile (counted in the coverage).

AS OF. Every column is dated on or before the row's read: grades are the frame's own
in-window grades (lv) or the timing-pinned preseason read (vm, efv_v2_model.
pinned_inputs); positions and roles are read inside the row's window; weights for
vintage V read only vintages at most V - 3 (C.RELIABILITY_LAG). On vm_dev the years are
debut years and the history label is career WAR to date (the MC-2 design rule).

FRAMES. Development frames only: lv_dev (list vintages 2017 to 2019, W3 on the frozen
fWAR label) and vm_dev at vm2 (debut years 2017 to 2023), built by
tools/efv_v2_model_class_screen.build_inputs, whose guards run first (no list vintage
2020 or 2021, no 2025+ debut cohort, reserved_vm_pins() empty). Nothing is grouped,
counted or averaged by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); position group
and side are the only strata.

STATISTICS. efv_v2_stat: within (side, vintage) Spearman primary, pooled after the
identical output map secondary, contributor AUC; paired_delta, E_cond, player clusters,
B 2000, seed 20260906. Per arm and frame: arm vs V2, arm vs consensus, arm vs Pipeline
and FanGraphs (descriptive), per side and both sides, the per-fold deltas, and the
anchor alone (u_c* with no driver term) against consensus. A DEVELOPMENT read: it
adjudicates nothing and is not a claim.

Run:  python efv_w2_anchor.py --check      (frames, coverage, weight tables; no statistic)
      python efv_w2_anchor.py              (writes data/_labs/efv_w2/efv_w2_anchor.json and
                                            the progress-ledger development rows)
      python tools/efv_screen_lab.py --wave2-dev efv_w2_anchor    (the same, via the lab)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import efv_v2_candidates as C  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

MODULE = "efv_w2_anchor"
ITEM = "EFV3_W2_1c_ANCHORS"
TOOL = "efv_w2_anchor.py"
OUT_PATH = H.DATA_DIR / "_labs" / "efv_w2" / f"{MODULE}.json"
NOTE = "wave 2 anchor arm; development frame, spent, not a claim"
FROZEN_PROVIDER = "fwar"
MODEL_PREFIX = "efv_w2_anchor:"
ARMS: tuple[str, ...] = ("an1_rel", "an1_pl", "an2_pos")
ARM_IDS: dict[str, str] = {a: MODEL_PREFIX + a for a in ARMS}
ARM_WHAT: dict[str, str] = {
    "an1_rel": ("AN-1: reliability-weighted consensus anchor (source within Spearman on "
                "vintages at most V - 3, k 150 shrink, clamp 0.6 to 1.5); the MC-2 rule"),
    "an1_pl": "AN-1 simple variant: fixed weights mlb_pipeline 2.0, fangraphs 1.0",
    "an2_pos": ("AN-2: weights per source x position group on vintages at most V - 3, "
                "shrunk toward the AN-1 weights with 150 pseudo rows"),
}
SOURCES: tuple[str, ...] = tuple(SB.SCORED_SOURCES)
CONS = SB.CONSENSUS_KEY
FIXED_WEIGHTS: dict[str, float] = {"mlb_pipeline": 2.0, "fangraphs": 1.0}
AN2_SHRINK_K = SB.WEIGHT_SHRINK_K
AN2_MIN_GROUP_HISTORY = 300
AN2_MIN_SLICE_ROWS = S.MIN_GROUP_ROWS
HIT_FINE: dict[str, str] = {"C": "C", "SS": "SS", "CF": "CF", "2B": "IF", "3B": "IF",
                            "IF": "IF", "MI": "IF", "LF": "COF", "RF": "COF", "OF": "COF",
                            "1B": "1B_DH", "DH": "1B_DH"}
HIT_FINE_GROUPS: tuple[str, ...] = ("C", "SS", "CF", "IF", "COF", "1B_DH")
HIT_C02_GROUPS: tuple[str, ...] = C.MC5_FAMILIES["hit"]
PIT_GROUPS: tuple[str, ...] = C.MC5_FAMILIES["pit"]
UNKNOWN = "unknown"
FRAMES: tuple[str, ...] = ("lv_dev", "vm_dev")
FRAME_KIND = {"lv_dev": "lv", "vm_dev": "vm"}
TILTED = {("an1_pl", "lv_dev"): ("the fixed Pipeline weight was chosen from lane I4, "
                                 "measured on list vintages 2011 to 2019, which include "
                                 "lv_dev")}
B_DEFAULT = S.B_DEFAULT
SEED = S.SEED_DEFAULT
ARM_KEY = "efv_w2_anchor"
V2_KEY = "efv_v2"
ANCHOR_ONLY_KEY = "anchor_only"
RATERS_OUT = ((ARM_KEY, "efv_w2_anchor"), (V2_KEY, "efv_v2"), (CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"),
              (ANCHOR_ONLY_KEY, "anchor_only"))
COMPARISONS = (("arm_vs_efv_v2", ARM_KEY, V2_KEY),
               ("arm_vs_prospx_consensus", ARM_KEY, CONS),
               ("arm_vs_mlb_pipeline", ARM_KEY, "mlb_pipeline"),
               ("arm_vs_fangraphs", ARM_KEY, "fangraphs"))
SIDE_COMPARISONS = (("arm_vs_efv_v2", ARM_KEY, V2_KEY),
                    ("arm_vs_prospx_consensus", ARM_KEY, CONS),
                    ("anchor_only_vs_prospx_consensus", ANCHOR_ONLY_KEY, CONS))
#: progress-ledger maps (efv_progress.build_dev_rows): (row name, artifact key)
PROGRESS_RATERS = (("efv", "efv_w2_anchor"), ("efv_v2_base", "efv_v2"),
                   ("prospx_consensus", "prospx_consensus"),
                   ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
PROGRESS_DELTAS = (("vs_efv_v2_base", "arm_vs_efv_v2"),
                   ("vs_prospx_consensus", "arm_vs_prospx_consensus"),
                   ("vs_mlb_pipeline", "arm_vs_mlb_pipeline"),
                   ("vs_fangraphs", "arm_vs_fangraphs"))


def _single_source() -> dict:
    import consensus as CS
    return {"k": CS.SINGLE_SOURCE_K, "prior": CS.SINGLE_SOURCE_PRIOR}


# ---------------------------------------------------------------------------
# position groups (as of the read)
# ---------------------------------------------------------------------------

def hitter_token(position) -> str:
    """The first token of a listed position ("SS/2B" reads SS)."""
    return str(position or "").upper().split("/")[0].strip()


def row_groups(side: str, cov: dict | None) -> dict:
    """{"fine", "c02", "how"} for one row from its EFV3_C05 covariates (the listing and
    the role inside the row's window). Pitchers carry sp or rp in both schemes."""
    cov = cov or {}
    how = cov.get("family_how") or "none"
    if side == "pit":
        fam = cov.get("family")
        g = fam if fam in PIT_GROUPS else UNKNOWN
        return {"fine": g, "c02": g, "how": how}
    lst = cov.get("listing")
    if not lst:
        return {"fine": UNKNOWN, "c02": UNKNOWN, "how": how}
    tok = hitter_token(lst.get("position"))
    return {"fine": HIT_FINE.get(tok, UNKNOWN), "c02": C.position_family(tok, "hit"),
            "how": how}


# ---------------------------------------------------------------------------
# the weight tables
# ---------------------------------------------------------------------------

def fixed_reliability(rel: dict) -> dict:
    """AN-1 simple variant: the reliability document with every (side, V) weight set to
    FIXED_WEIGHTS (a source not named keeps 1.0). Nothing is estimated."""
    out = {k: v for k, v in rel.items() if k not in ("table", "stats", "rule")}
    out["table"] = {side: {V: {s: float(FIXED_WEIGHTS.get(s, 1.0))
                               for s in rel["sources"][side]}
                           for V in rel["table"][side]}
                    for side in rel["table"]}
    out["rule"] = ("fixed weights " + ", ".join(f"{s} {w}" for s, w in FIXED_WEIGHTS.items())
                   + " on every (side, V); the single-source rule unchanged")
    out["stats"] = None
    return out


def _rho_of(rows: list[dict], source: str) -> float | None:
    return SB._spearman([float(r["grades"][source]) for r in rows],
                        [float(r["target"]) for r in rows])


def group_reliability(rows_by_side_vintage: dict, global_rel: dict, *,
                      target_vintages=None, frame: str = "lv",
                      gate_sha: str | None = None) -> dict:
    """The AN-2 table keyed (side, V): the scheme, the per-group weights and the history
    statistics. Rows are {side: {V: rows}}, each row carrying `grades`, `target` (the
    frame's label, read as ranks only) and `group` ({"fine", "c02"}). For a target V
    only vintages at most V - RELIABILITY_LAG are read (the global table's own rule)."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    lag = C.RELIABILITY_LAG
    lo, hi = SB.WEIGHT_CLAMP
    table: dict = {}
    stats_doc: dict = {}
    for side, by_v in rows_by_side_vintage.items():
        vintages = sorted(int(v) for v in by_v)
        H._check_years(vintages)
        if frame == "lv":
            for v in vintages:
                F.guard_score_request(v, gate_sha=gate_sha, purpose="anchor group table")
        srcs = list(global_rel["sources"][side])
        targets = (vintages if target_vintages is None
                   else sorted(int(v) for v in target_vintages))
        H._check_years(targets)
        table[side], stats_doc[side] = {}, {}
        for V in targets:
            if frame == "lv":
                F.guard_score_request(V, gate_sha=gate_sha, purpose="anchor group table")
            hist = [v for v in vintages if v <= V - lag]
            glob = {s: float(global_rel["table"][side][str(V)].get(s, 1.0)) for s in srcs}
            usable = [r for v in hist for r in by_v[v] if r.get("target") is not None
                      and any((r.get("grades") or {}).get(s) is not None for s in srcs)]
            if side == "pit":
                scheme, key, groups = "role", "fine", PIT_GROUPS
                counts = {g: sum(1 for r in usable if r["group"]["fine"] == g) for g in groups}
            else:
                counts = {g: sum(1 for r in usable if r["group"]["fine"] == g)
                          for g in HIT_FINE_GROUPS}
                if counts and min(counts.values()) >= AN2_MIN_GROUP_HISTORY:
                    scheme, key, groups = "fine", "fine", HIT_FINE_GROUPS
                else:
                    scheme, key, groups = "c02", "c02", HIT_C02_GROUPS
                    counts = {g: sum(1 for r in usable if r["group"]["c02"] == g)
                              for g in groups}
            gw, gstats = {}, {}
            for g in groups:
                st = {}
                for s in srcs:
                    tot, n, slices = 0.0, 0, 0
                    for v in hist:
                        rr = [r for r in by_v[v] if r["group"][key] == g
                              and r.get("target") is not None
                              and (r.get("grades") or {}).get(s) is not None]
                        if len(rr) < AN2_MIN_SLICE_ROWS:
                            continue
                        rho = _rho_of(rr, s)
                        if rho is None:
                            continue
                        tot += rho * len(rr)
                        n += len(rr)
                        slices += 1
                    st[s] = {"rho": (round(tot / n, 5) if n else None), "n": n, "slices": slices}
                with_hist = [s for s in srcs if st[s]["rho"] is not None]
                w = dict(glob)
                how = "global (fewer than two sources with history in the group)"
                if len(with_hist) >= 2:
                    floored = {s: max(SB.SPEARMAN_FLOOR, st[s]["rho"]) for s in with_hist}
                    mean_rho = sum(floored.values()) / len(floored)
                    for s in with_hist:
                        raw = floored[s] / mean_rho
                        n = st[s]["n"]
                        shr = (n * raw + AN2_SHRINK_K * glob[s]) / (n + AN2_SHRINK_K)
                        w[s] = round(min(hi, max(lo, shr)), 4)
                    how = "group reliability shrunk toward the global weight"
                gw[g] = w
                gstats[g] = {"sources": st, "how": how}
            table[side][str(V)] = {"scheme": scheme, "key": key, "groups": gw,
                                   "global": glob, "history_rows": counts, "reads": hist}
            stats_doc[side][str(V)] = gstats
    return {"rule": ("per (side, V, position group): each source's within Spearman over "
                     f"the group's history rows at vintages at most V - {lag}, relative "
                     "to the mean over the sources with history in the group, shrunk "
                     f"toward the global AN-1 weight with K {AN2_SHRINK_K} pseudo rows "
                     f"and clamped to {list(SB.WEIGHT_CLAMP)}; fewer than two sources "
                     "with history in the group, or a row with no group, takes the "
                     "global weights"),
            "frame": frame, "lag": lag, "shrink_k": AN2_SHRINK_K,
            "clamp": list(SB.WEIGHT_CLAMP), "rho_floor": SB.SPEARMAN_FLOOR,
            "min_slice_rows": AN2_MIN_SLICE_ROWS,
            "min_group_history": AN2_MIN_GROUP_HISTORY,
            "sources": {s: list(global_rel["sources"][s]) for s in table},
            "single_source": dict(global_rel["single_source"]),
            "table": table, "stats": stats_doc}


def row_weights(rows: list[dict], side: str, rel: dict, *, groups: dict | None = None,
                group_table: dict | None = None) -> list[dict]:
    """{source: weight} per row. Without a group table: the reliability table at the
    row's own decision year (AN-1). With one: the row's group weights under the scheme
    of its year, the global weights for a row with no group (AN-2). `groups` maps
    (player_key, decision_year) to the row's {"fine", "c02"}."""
    out = []
    for r in rows:
        V = str(int(r["decision_year"]))
        glob = rel["table"][side].get(V)
        if glob is None:
            raise ValueError(f"no reliability weights for year {V}")
        if group_table is None:
            out.append(dict(glob))
            continue
        ent = group_table["table"][side].get(V)
        if ent is None:
            raise ValueError(f"no group weights for year {V}")
        g = ((groups or {}).get((r["player_key"], int(r["decision_year"])))
             or {}).get(ent["key"], UNKNOWN)
        out.append(dict(ent["groups"].get(g) or glob))
    return out


# ---------------------------------------------------------------------------
# the anchor column (as of the read) and its coverage
# ---------------------------------------------------------------------------

def anchor_column(rows: list[dict], weights: list[dict], sources, single_source: dict
                  ) -> tuple[np.ndarray, int]:
    """(u_c* per row, rows with no listed source): efv_v2_candidates.anchor_values with a
    weight per (row, source). Inside each decision year every source's grades over the
    rows carrying it go to their within percentile (a one-source row's grade first
    shrunk toward the prior); u_c* is the weighted mean over the row's PRESENT sources
    (renormalized); a row with no source takes the consensus percentile."""
    if len(weights) != len(rows):
        raise ValueError("one weight dict per row")
    srcs = [s for s in sources if s != CONS]
    w_src = 1.0 / (1.0 + float(single_source["k"]))
    prior = float(single_source["prior"])
    years = [int(r["decision_year"]) for r in rows]
    num = np.zeros(len(rows))
    den = np.zeros(len(rows))
    by: dict = {}
    for i, y in enumerate(years):
        by.setdefault(y, []).append(i)
    for _V, idx in by.items():
        n_src = {i: sum(1 for s in srcs if (rows[i].get("grades") or {}).get(s) is not None)
                 for i in idx}
        for s in srcs:
            have = [i for i in idx if (rows[i].get("grades") or {}).get(s) is not None]
            if not have:
                continue
            vals = []
            for i in have:
                g = float(rows[i]["grades"][s])
                vals.append(w_src * g + (1.0 - w_src) * prior if n_src[i] == 1 else g)
            pct = H.within_pct(vals, [0] * len(have))
            for j, i in enumerate(have):
                w = float(weights[i].get(s, 1.0))
                num[i] += w * pct[j]
                den[i] += w
    u_cons = H.within_pct([r["fv"] for r in rows], years)
    safe = np.where(den > 0, den, 1.0)
    return np.where(den > 0, num / safe, u_cons), int((den == 0).sum())


def coverage(rows: list[dict], side: str, sources=SOURCES, groups: dict | None = None) -> dict:
    """Per decision year: rows, rows carrying each source, both, one, none (the consensus
    fallback), and the group counts when `groups` is given."""
    out: dict = {}
    for r in rows:
        V = str(int(r["decision_year"]))
        c = out.setdefault(V, {"n": 0, "by_source": {s: 0 for s in sources}, "both": 0,
                               "single": 0, "none": 0})
        c["n"] += 1
        have = [s for s in sources if (r.get("grades") or {}).get(s) is not None]
        for s in have:
            c["by_source"][s] += 1
        c["both" if len(have) >= 2 else ("single" if have else "none")] += 1
        if groups is not None:
            g = groups.get((r["player_key"], int(r["decision_year"]))) or {}
            gc = c.setdefault("groups", {})
            k = f"{g.get('fine', UNKNOWN)}"
            gc[k] = gc.get(k, 0) + 1
    return {"side": side, "by_year": dict(sorted(out.items()))}


# ---------------------------------------------------------------------------
# the arm's fit and prediction (V2's heads refit on the anchor)
# ---------------------------------------------------------------------------

def fit_anchor(train: list[dict], u_train, side: str, frame: str, weights: dict, *,
               arm: str, anchor_doc: dict, absent_ok: bool | None = None,
               alphas=H.V2_ALPHAS) -> dict:
    """efv_v2_candidates.fit_mc2_anchor with the anchor handed in: V2's heads, admission
    rule and weights, fitted with u_c* (u_train, one value per training row) in place of
    u_c; fit_v2 is the base (pricing line and fold receipt kept)."""
    C.guard_training_rows(train, frame)
    u_train = np.asarray(u_train, dtype=np.float64)
    if u_train.size != len(train):
        raise ValueError("one anchor value per training row")
    rows = [dict(r, **{C.ANCHOR_KEY: float(u_train[i])}) for i, r in enumerate(train)]
    base = H.fit_v2(train, side, frame=frame, weights=weights, absent_ok=absent_ok)
    ob = frame == "lv"
    ab = ob and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    cands = C._skill_cands(side)
    skill = None
    keys, checks = C._admitted_keys_a(rows, cands, target="u_y", has_block_only=True)
    if keys:
        def fit_s(tr, a):
            return C._skill_fit_g(tr, keys, a, C._v2_design(keys))
        a_s = C._select_alpha_g(rows, fit_s, C._skill_loss, alphas=alphas)
        skill = fit_s(rows, a_s)
        if skill is not None:
            skill.update({"side": side, "admission": checks, "candidates": list(cands),
                          "anchor": True})
            skill["score_sd"] = C._score_sd(skill, H.skill_training_rows(rows))
    timing = None
    if not (side == "pit" and not H.head_usable(skill)):
        tcands = H.timing_candidates(side, ids_outcome_blind=ob, absence_admitted=ab)
        tkeys, tchecks = C._admitted_keys_a(rows, tcands, target="reached",
                                            has_block_only=False)

        def fit_t(tr, a):
            return C._timing_fit_g(tr, tkeys, a, C._v2_design(tkeys))
        a_t = C._select_alpha_g(rows, fit_t, C._timing_loss, alphas=alphas)
        timing = fit_t(rows, a_t)
        if timing is not None:
            timing.update({"side": side, "admission": tchecks, "candidates": list(tcands),
                           "ids_outcome_blind": bool(ob), "anchor": True})
            timing["score_sd"] = C._score_sd(timing, rows)
    m = C._assemble(base, "mc2", skill=skill, timing=timing, weights=weights, side=side,
                    anchor=anchor_doc)
    m.update({"model_id": ARM_IDS[arm], "arm": arm})
    return m


def predict_anchor(model: dict, rows: list[dict], u_rows) -> list[dict]:
    """predict_v2's output with u_c* as the anchor; the grade still comes from the rows'
    consensus values (efv_v2_candidates._predict)."""
    return C._predict(model, rows, u_c=np.asarray(u_rows, dtype=np.float64))


def _receipt(m: dict) -> dict:
    return {"consensus_only": m["consensus_only"], "w_skill": m["w_skill"],
            "w_time": m["w_time"], "skill_keys": (m["skill"] or {}).get("keys"),
            "timing_keys": (m["timing"] or {}).get("keys"),
            "n_train_rows_without_source": (m.get("anchor") or {}).get(
                "n_train_rows_without_source")}


# ---------------------------------------------------------------------------
# the real inputs: frames (the C03 builder), groups, weight tables
# ---------------------------------------------------------------------------

def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def build(*, log=print) -> dict:
    """The C03 frames and V2 base (tools/efv_v2_model_class_screen.build_inputs, guards
    first), the position group of every row at its read, the history rows with groups,
    and the three weight tables per frame. No arm is fitted here."""
    import efv_v2_assemble as ASM
    import efv_v2_model_class_screen as MCS
    import efv_v2_pricing_calibration as PC
    t0 = time.time()
    frames_lv = ASM.build_frames()
    log(f"lv frames built ({round(time.time() - t0, 1)} s)")
    captured: dict = {}
    orig_bf, orig_pin = ASM.build_frames, H.pinned_inputs

    def pin_capture(side, data, receipts=None):
        rec = {} if receipts is None else receipts
        out = orig_pin(side, data, rec)
        captured.setdefault(side, {}).update(rec)
        return out
    ASM.build_frames = lambda *a, **k: frames_lv
    H.pinned_inputs = pin_capture
    try:
        inputs = MCS.build_inputs(log=log)
    finally:
        ASM.build_frames, H.pinned_inputs = orig_bf, orig_pin
    log(f"C03 inputs built ({round(time.time() - t0, 1)} s)")
    listings = PC.load_listings()
    roles = PC.MilbRoles()
    groups: dict = {"lv_dev": {}, "vm_dev": {}}
    hows: dict = {"lv_dev": {}, "vm_dev": {}}

    def put(fid, side, key, cov):
        g = row_groups(side, cov)
        groups[fid].setdefault(side, {})[key] = g
        hk = f"{side}:{g['how']}"
        hows[fid][hk] = hows[fid].get(hk, 0) + 1
    # lv: every frame row (training rows, scored rows and history rows are frame rows)
    lv_hist: dict = {}
    for side in F.SIDES:
        lv_hist[side] = {}
        for V, (rows, labs) in frames_lv[side].items():
            for r, lab in zip(rows, labs):
                put("lv_dev", side, (r["player_key"], int(V)),
                    PC.lv_covariates(dict(r, side=side), listings, roles))
                g = (r.get("grades") or {})
                if lab.get("w3") is None or g.get(CONS) is None:
                    continue
                lv_hist[side].setdefault(int(V), []).append(
                    {"grades": {s: float(g[s]) for s in SOURCES if g.get(s) is not None},
                     "target": float(lab["w3"]),
                     "group": groups["lv_dev"][side][(r["player_key"], int(V))]})
    log(f"lv groups read ({round(time.time() - t0, 1)} s)")
    # vm: training rows at the matrix row's own read, scored rows at the pinned read,
    # history rows (debut cohorts) at the debut-year preseason
    fr_vm = inputs["frames"]["vm_dev"]
    side_of: dict = {}
    for side in F.SIDES:
        raw = {r["player_key"]: r for r in json.loads(
            H._matrix_path(side).read_text(encoding="utf-8"))}
        for k in raw:
            side_of.setdefault(k, side)
        rec = captured.get(side) or {}
        for yr, blk in fr_vm["by_side"][side].items():
            for r in blk["train"]:
                key = (r["player_key"], int(r["decision_year"]))
                if key in groups["vm_dev"].get(side, {}):
                    continue
                rw = raw.get(r["player_key"])
                cov = (PC.vm_covariates(side, rw, rw.get("asof_date"), listings, roles)
                       if rw else None)
                put("vm_dev", side, key, cov)
            for r in blk["test"]:
                key = (r["player_key"], int(r["decision_year"]))
                rw = raw.get(r["player_key"]) or {"player_key": r["player_key"]}
                asof = (rec.get(r["player_key"]) or {}).get("asof_date")
                put("vm_dev", side, key,
                    PC.vm_covariates(side, rw, asof, listings, roles) if asof else None)
    universe = SB._load_universe(H.DATA_DIR)
    by_key = {p.get("player_key"): p for p in universe}
    vm_hist: dict = {s: {} for s in F.SIDES}
    for p in universe:
        k = p.get("player_key")
        side = side_of.get(k)
        out = SB._outcome(p)
        dy = out.get("debut_year")
        if side is None or dy is None or dy < min(F.DEV_VINTAGES) or dy >= F.R_VM_FIRST_DEBUT_YEAR:
            continue
        g = MCS._grades_for(by_key, k, dy)
        if not g:
            continue
        read = f"{int(dy)}-03-01"
        cov = PC.covariates(side, player_key=k, mlbam=p.get("mlbam_id"),
                            birth_date=p.get("birth_date"), read_date=read,
                            lo=f"{int(dy) - 1}-03-01", hi=PC._next_day(read),
                            listings=listings, roles=roles)
        vm_hist[side].setdefault(int(dy), []).append(
            {"grades": g, "target": float(out["war"]), "group": row_groups(side, cov)})
    log(f"vm groups read ({round(time.time() - t0, 1)} s)")
    hist = {"lv_dev": lv_hist, "vm_dev": vm_hist}
    single = _single_source()
    tables: dict = {}
    for fid in FRAMES:
        fr = inputs["frames"][fid]
        kind = FRAME_KIND[fid]
        years = sorted({int(r["decision_year"]) for side in F.SIDES
                        for blk in fr["by_side"][side].values()
                        for r in blk["train"] + blk["test"]})
        rel = C.build_source_reliability(hist[fid], single_source=single,
                                         target_vintages=years, frame=kind)
        # the history rows rebuilt here must give the C03 table bit for bit
        if rel["table"] != fr["reliability"]["table"]:
            raise RuntimeError(f"{fid}: the rebuilt history rows do not reproduce the "
                               "C03 reliability table")
        tables[fid] = {"an1_rel": fr["reliability"], "an1_pl": fixed_reliability(fr["reliability"]),
                       "an2_pos": group_reliability(hist[fid], fr["reliability"],
                                                    target_vintages=years, frame=kind)}
    return {"inputs": inputs, "groups": groups, "group_how": hows, "tables": tables,
            "single_source": single, "elapsed_build_s": round(time.time() - t0, 1)}


def _fold_weights(built: dict, fid: str, arm: str, side: str, rows: list[dict]) -> list[dict]:
    t = built["tables"][fid]
    if arm == "an2_pos":
        return row_weights(rows, side, t["an1_rel"], groups=built["groups"][fid].get(side),
                           group_table=t["an2_pos"])
    return row_weights(rows, side, t[arm])


def arm_orders(built: dict, fid: str, arm: str, *, log=print) -> tuple[dict, dict, dict]:
    """({(side, fold, key): order_idx}, {(side, fold, key): u_c*}, fold receipts)."""
    inputs = built["inputs"]
    fr = inputs["frames"][fid]
    kind = FRAME_KIND[fid]
    single = built["single_source"]
    orders, anchors, receipts = {}, {}, {}
    for side in F.SIDES:
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            t0 = time.time()
            train, test = blk["train"], blk["test"]
            C.guard_training_rows(train, kind)
            w_tr = _fold_weights(built, fid, arm, side, train)
            w_te = _fold_weights(built, fid, arm, side, test)
            u_tr, miss_tr = anchor_column(train, w_tr, SOURCES, single)
            u_te, miss_te = anchor_column(test, w_te, SOURCES, single)
            doc = {"side": side, "lag": C.RELIABILITY_LAG, "sources": list(SOURCES),
                   "single_source": dict(single), "n_train_rows_without_source": miss_tr,
                   "n_test_rows_without_source": miss_te, "indicator_columns": [],
                   "comparator": "served consensus (u_c), unchanged"}
            m = fit_anchor(train, u_tr, side, kind, inputs["weights"], arm=arm,
                           anchor_doc=doc, absent_ok=inputs.get("absent_ok"))
            pred = predict_anchor(m, test, u_te)
            o = {p["player_key"]: float(p["order_idx"]) for p in pred}
            u = {r["player_key"]: float(u_te[i]) for i, r in enumerate(test)}
            for c in blk["scored"]:
                if c["key"] not in o:
                    raise RuntimeError(f"{arm} {fid} {side} {fold}: no score for {c['key']}")
                orders[(side, fold, c["key"])] = o[c["key"]]
                anchors[(side, fold, c["key"])] = u[c["key"]]
            receipts[f"{side}|{fold}"] = dict(_receipt(m), n_train=len(train),
                                              n_scored=len(blk["scored"]),
                                              elapsed_s=round(time.time() - t0, 1))
            log(f"  {arm} {fid} {side} {fold}: {len(train)} train, {len(blk['scored'])} "
                f"scored, {round(time.time() - t0, 1)} s")
    return orders, anchors, receipts


def mc2_parity(built: dict, fid: str, orders: dict) -> dict:
    """an1_rel against efv_v2_candidates.fit_mc2_anchor / predict_mc2 on every fold:
    the generic anchor fit must give MC-2's order bit for bit."""
    fr = built["inputs"]["frames"][fid]
    kind = FRAME_KIND[fid]
    rel = fr["reliability"]
    n, bad = 0, 0
    for side in F.SIDES:
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            m = C.fit_mc2_anchor(blk["train"], side, kind, built["inputs"]["weights"], rel,
                                 absent_ok=built["inputs"].get("absent_ok"))
            o = {p["player_key"]: float(p["order_idx"]) for p in C.predict_mc2(m, blk["test"])}
            for c in blk["scored"]:
                n += 1
                if o[c["key"]] != orders[(side, fold, c["key"])]:
                    bad += 1
    return {"rows": n, "differ": bad, "reproduces": bad == 0}


def rows_with_arm(built: dict, fid: str, orders: dict, anchors: dict) -> list[dict]:
    fr = built["inputs"]["frames"][fid]
    out = []
    for side in F.SIDES:
        for fold in fr["folds"]:
            blk = fr["by_side"][side].get(fold)
            if blk is None:
                continue
            for c in blk["scored"]:
                row = dict(c)
                row["grades"] = dict(c["grades"], **{
                    ARM_KEY: orders[(side, fold, c["key"])],
                    ANCHOR_ONLY_KEY: anchors[(side, fold, c["key"])]})
                out.append(row)
    return out


def _leg(d: dict) -> dict:
    return {k: d.get(k) for k in ("delta", "ci95", "mde95", "sd", "n", "n_rows", "reading",
                                  "p_gt_0", "estimator", "ci95_estimator") if k in d}


def frame_read(rows: list[dict], *, B: int, seed: int) -> dict:
    import efv_v2_model_class_screen as MCS
    blk = MCS.frame_block(rows, B=B, seed=seed, comparisons=COMPARISONS,
                          raters_out=RATERS_OUT)
    per_side = {}
    for side in F.SIDES:
        sel = [c for c in rows if c["side"] == side]
        per_side[side] = {"n": len(sel)}
        for name, a, b in SIDE_COMPARISONS:
            per_side[side][name] = _leg(MCS.within_delta_only(sel, a, b, B=B, seed=seed))
    both_anchor = _leg(MCS.within_delta_only(rows, ANCHOR_ONLY_KEY, CONS, B=B, seed=seed))
    n_side: dict = {}
    for c in rows:
        n_side[c["side"]] = n_side.get(c["side"], 0) + 1
    return {"n": len(rows), "n_by_side": n_side,
            "n_players": len({c["key"] for c in rows}),
            "groups": sorted({c["group"] for c in rows}),
            "raters": blk["raters"], "deltas": blk["deltas"],
            "anchor_only_vs_prospx_consensus": both_anchor,
            "per_side": per_side,
            "fold_deltas_vs_v2": MCS.fold_deltas(rows, ARM_KEY, V2_KEY),
            "fold_deltas_vs_consensus": MCS.fold_deltas(rows, ARM_KEY, CONS)}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _tables_doc(built: dict) -> dict:
    out = {}
    for fid in FRAMES:
        t = built["tables"][fid]
        out[fid] = {"an1_rel": {k: v for k, v in t["an1_rel"].items() if k != "stats"},
                    "an1_rel_stats": t["an1_rel"].get("stats"),
                    "an1_pl": t["an1_pl"],
                    "an2_pos": t["an2_pos"]}
    return out


def coverage_doc(built: dict) -> dict:
    out = {}
    for fid in FRAMES:
        fr = built["inputs"]["frames"][fid]
        g = built["groups"][fid]
        out[fid] = {"group_source": dict(sorted(built["group_how"][fid].items()))}
        for side in F.SIDES:
            scored = [dict(c, player_key=c["key"], decision_year=c["year"])
                      for blk in fr["by_side"][side].values() for c in blk["scored"]]
            tests = [r for blk in fr["by_side"][side].values() for r in blk["test"]]
            out[fid][side] = {
                "scored": coverage(scored, side, groups=g.get(side)),
                "test_rows": coverage(tests, side, groups=g.get(side))}
    return out


def inert_receipt(built: dict) -> dict:
    """Which (frame, side, year) weight entries differ from equal weights, per arm: an
    arm whose every scored-year entry is equal reads the equal-weight anchor there."""
    out = {}
    for fid in FRAMES:
        fr = built["inputs"]["frames"][fid]
        t = built["tables"][fid]
        out[fid] = {}
        for side in F.SIDES:
            rows = {}
            for fold in fr["folds"]:
                V = str(fold)
                a1 = t["an1_rel"]["table"][side][V]
                a2 = t["an2_pos"]["table"][side][V]
                rows[V] = {"an1_rel_equal": all(abs(w - 1.0) < 1e-12 for w in a1.values()),
                           "an2_pos_equal": all(abs(w - 1.0) < 1e-12 for gw in a2["groups"].values()
                                                for w in gw.values()),
                           "an2_scheme": a2["scheme"],
                           "sources_with_history": sorted(
                               s for s, st in (t["an1_rel"]["stats"][side][V]).items()
                               if st.get("rho") is not None)}
            out[fid][side] = rows
    return out


def run(built: dict, *, B: int = B_DEFAULT, log=print) -> dict:
    import efv_v2_model_class_screen as MCS
    t0 = time.time()
    inputs = built["inputs"]
    ds16 = MCS._ds16_block()
    parity = MCS.base_parity(inputs, ds16)
    if not parity["reproduces"]:
        raise RuntimeError("the V2 base does not reproduce the DS-16 block; nothing scored")
    doc: dict = {
        "schema": 1, "item": ITEM, "module": MODULE,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": TOOL, "role": "development", "adjudicates": False, "selects": False,
        "exploratory": False, "note": NOTE,
        "owner_decision": ("EW2-6 (2026-10-08): select on the development frames only, then "
                           "confirm one committed configuration once on the reserved frames; "
                           "this artifact is the development read and reads no reserved row"),
        "label": MCS._label(),
        "code": {"commit": _commit(), "tool": TOOL, "module_sha256": _sha(ROOT / TOOL),
                 "efv_v2_candidates_sha256": _sha(ROOT / "efv_v2_candidates.py"),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")},
        "assembly_sha256": _sha(H.ASSEMBLY_PATH),
        "weights": inputs["weights"],
        "statistic": {"primary": S.STAT_LABEL[S.PRIMARY], "secondary": S.STAT_LABEL[S.SECONDARY],
                      "veto": S.STAT_LABEL["auc"], "min_group_rows": S.MIN_GROUP_ROWS,
                      "group": "(side, list vintage) on lv_dev; (side, debut year) on vm_dev",
                      "code": "efv_v2_stat.py"},
        "bootstrap": {"B": int(B), "seed": SEED, "estimator": "E_cond", "unit": "player cluster"},
        "reserved_guard": inputs["guards"],
        "base_parity": parity,
        "arms_registered": {a: {"model_id": ARM_IDS[a], "what": ARM_WHAT[a]} for a in ARMS},
        "fixed_weights": dict(FIXED_WEIGHTS),
        "weight_tables": _tables_doc(built),
        "inert": inert_receipt(built),
        "coverage": coverage_doc(built),
        "arms": {},
    }
    for arm in ARMS:
        a_doc = {"arm": arm, "model_id": ARM_IDS[arm], "what": ARM_WHAT[arm], "frames": {}}
        for fid in FRAMES:
            orders, anchors, receipts = arm_orders(built, fid, arm, log=log)
            rows = rows_with_arm(built, fid, orders, anchors)
            t1 = time.time()
            f = frame_read(rows, B=B, seed=SEED)
            f["receipts"] = receipts
            f["role"] = "development"
            if (arm, fid) in TILTED:
                f["tilted"] = True
                f["tilt"] = TILTED[(arm, fid)]
            if arm == "an1_rel":
                f["mc2_parity"] = mc2_parity(built, fid, orders)
                if not f["mc2_parity"]["reproduces"]:
                    raise RuntimeError(f"an1_rel does not reproduce MC-2 on {fid}")
            w = f["deltas"]["arm_vs_efv_v2"]["spearman"]
            c = f["deltas"]["arm_vs_prospx_consensus"]["spearman"]
            f["verdict"] = (f"DEVELOPMENT ONLY: within vs V2 {_rnd(w.get('delta'), 4)} "
                            f"(CI95 {w.get('ci95')}), vs consensus {_rnd(c.get('delta'), 4)} "
                            f"(CI95 {c.get('ci95')}); adjudicates nothing")
            f["note"] = (f"wave 2 anchor arm {arm} ({ARM_WHAT[arm]}); development read on a "
                         "spent frame, not a claim"
                         + (f"; TILTED: {TILTED[(arm, fid)]}" if (arm, fid) in TILTED else ""))
            a_doc["frames"][fid] = f
            log(f"  {arm} {fid}: vs V2 {w.get('delta')} {w.get('ci95')}; vs consensus "
                f"{c.get('delta')} {c.get('ci95')} ({round(time.time() - t1, 1)} s stats)")
        doc["arms"][arm] = a_doc
    doc["elapsed_s"] = round(time.time() - t0 + built.get("elapsed_build_s", 0.0), 1)
    return doc


def write_doc(doc: dict, out: Path = OUT_PATH) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n"
    for ch in (chr(0x2014), chr(0x2013)):
        if ch in text:
            raise RuntimeError("an em-dash or en-dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)
    return out


def progress_docs(doc: dict) -> list[dict]:
    """One development document per arm in the shape efv_progress.build_dev_rows reads. A
    TILTED frame read (TILTED) lands no progress row: the ledger's development rows are
    drawn on the Source Comparison chart, and a tilted read never is."""
    out = []
    for arm, a in (doc.get("arms") or {}).items():
        out.append({"role": "development", "model_id": a["model_id"],
                    "generated_at": doc.get("generated_at"), "label": doc.get("label") or {},
                    "code": doc.get("code") or {},
                    "frames": {fid: {k: f.get(k) for k in ("n", "n_by_side", "raters",
                                                           "deltas", "verdict", "note")}
                               for fid, f in a["frames"].items()
                               if not f.get("tilted")}})
    return out


def append_progress(doc: dict, out: Path = OUT_PATH, *, data_dir=None) -> dict:
    """The arms' development rows into data/efv_progress.json (its durable ledger too);
    no other row is built or moved."""
    import efv_progress as P
    now = datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    src = [{"path": P._rel(Path(out)), "generated_at": doc.get("generated_at"),
            "sha256": P._sha256(Path(out))}]
    cands = []
    for d in progress_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now.date().isoformat(),
                                  trigger="efv_change", now_iso=now_iso, frames=FRAMES,
                                  raters=PROGRESS_RATERS, deltas=PROGRESS_DELTAS)
    data_dir_p = Path(data_dir) if data_dir is not None else P.DATA_DIR
    return P.commit_rows(cands, data_dir=data_dir_p,
                         sb=P._load_json(data_dir_p / P.SB_NAME), now_iso=now_iso)


def summary_lines(doc: dict) -> list[str]:
    out = []
    for arm, a in doc["arms"].items():
        for fid, f in a["frames"].items():
            w = f["deltas"]["arm_vs_efv_v2"]["spearman"]
            c = f["deltas"]["arm_vs_prospx_consensus"]["spearman"]
            ps = f["per_side"]
            out.append(
                f"{arm:8s} {fid}: n {f['n']}; vs V2 {w.get('delta')} CI {w.get('ci95')}; "
                f"vs consensus {c.get('delta')} CI {c.get('ci95')}; hit vs V2 "
                f"{ps['hit']['arm_vs_efv_v2'].get('delta')} {ps['hit']['arm_vs_efv_v2'].get('ci95')} "
                f"vs cons {ps['hit']['arm_vs_prospx_consensus'].get('delta')} "
                f"{ps['hit']['arm_vs_prospx_consensus'].get('ci95')}; pit vs V2 "
                f"{ps['pit']['arm_vs_efv_v2'].get('delta')} {ps['pit']['arm_vs_efv_v2'].get('ci95')} "
                f"vs cons {ps['pit']['arm_vs_prospx_consensus'].get('delta')} "
                f"{ps['pit']['arm_vs_prospx_consensus'].get('ci95')}")
    return out


def check_doc(built: dict) -> dict:
    import efv_v2_model_class_screen as MCS
    return {"check": True, "guards": built["inputs"]["guards"],
            "counts": MCS.counts(built["inputs"]), "label": MCS._label(),
            "inert": inert_receipt(built), "coverage": coverage_doc(built),
            "an2_schemes": {fid: {s: {V: e["scheme"] for V, e in
                                      built["tables"][fid]["an2_pos"]["table"][s].items()}
                                  for s in F.SIDES} for fid in FRAMES}}


def main(argv=None) -> int:
    import efv_labels as L
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="build the frames, groups and weight tables; no statistic")
    ap.add_argument("--no-ledger", action="store_true",
                    help="write the artifact but no progress-ledger row")
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    if L.provider() != FROZEN_PROVIDER:
        log(f"refused: label provider is {L.provider()!r}, not the frozen {FROZEN_PROVIDER!r}")
        return 2
    built = build(log=log)
    if a.check:
        log(json.dumps(check_doc(built), indent=1, default=str))
        return 0
    doc = run(built, log=log)
    out = write_doc(doc)
    log(f"wrote {out} ({doc['elapsed_s']} s)")
    for line in summary_lines(doc):
        log(line)
    if not a.no_ledger:
        res = append_progress(doc, out)
        log(f"progress ledger: appended {len(res['appended'])} rows, {res['n_rows']} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
