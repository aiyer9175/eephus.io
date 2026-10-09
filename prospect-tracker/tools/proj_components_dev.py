# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The DEV half of PJ-C (task PJ_4_COMPONENT_HEADS_DEV): choose the component
heads' constants on the DEV frame and freeze them, once.

docs/PROJ_COMPONENTS_GATE.md sections 1, 3 and 4; LANE_A 2.1, 2.2 and 3.1.

WHAT RUNS. Bases 2014 to 2021, every cell with label season <= 2021 (2020
excluded), through proj_eval.run_components with look=False, which refuses any
later label season. For each base the engine is fitted point in time
(fa_projection.fitted_models(corpus, B - 1)), the aging_v3 service is fitted
point in time for the H3 and H4 age curves (unifier U5), and the held constants
are the last completed season's (proj_components.season_constants(B - 1)).

WHAT IS CHOSEN, in this order, each from the record the gate fixed:
  1. each shrink constant from its four-point grid by the DEV h1 rate MAE
     (ties to the first grid point);
  2. each Savant term (sprint speed in H3; OAA and arm in H4) IN only when
     its DEV paired delta, with minus without, is below zero; the slope the
     'with' head carries at base B is fitted on DEV rows of earlier bases only
     (label season <= B - 1), so the admission read is forward-chained inside
     DEV; the frozen slope is the fit on every DEV h1 row;
  3. the gmLI constant R (the DEV mean of relievers' runs above replacement per
     100 IP before the multiplier, IP-weighted over the DEV label seasons);
  4. each component's 80% range: the q10 and q90 of the pooled DEV season-runs
     residual (an absent season counts as 0) by horizon and exposure tier.

WHAT IS PUBLISHED. model/proj_components/params.json (every chosen constant,
admitted term, slope, range quantile, R, the vintage id and the frame schema
hash) and model/proj_components/dev_receipt.json (the DEV tables, MDE95 per
head and comparator, the Statcast decisions, the replica receipts). Nothing is
written under data/; the look (PJ_5) carries the dev block into the eval
artifact.

THE RECEIPTS. fwar_frame on REALIZED inputs against the frozen vintage on
2011 to 2021 (tools/fwar_replica_eval's hitters and pitchers with the feed
values replaced by the vintage's), the DEV MAE of H2 (batting runs, through
the scorer) and of P3's FIP-runs leg (runs above the league from FIP per 100
IP, the pitcher component the replica gates), beside Gate 1's wRC+ and FIP
figures.

Usage:
    python tools/proj_components_dev.py --write          # freeze (once)
    python tools/proj_components_dev.py --out DIR        # preview to DIR only
    python tools/proj_components_dev.py --quick --out DIR
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import logging
import pickle
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aging_v3                      # noqa: E402
import aging_v3_sidecar              # noqa: E402
import fa_projection as fp           # noqa: E402
import fwar_frame as F               # noqa: E402
import fwar_vintage                  # noqa: E402
import proj_components as PC         # noqa: E402
import proj_eval as pe               # noqa: E402

log = logging.getLogger("proj_components_dev")

SEED = 20261124
VIF = 1.8
DEV_FIRST_BASE, DEV_LAST_BASE = 2014, 2021
DEV_LAST_LABEL = 2021
RECEIPT_SEASONS = list(range(2011, 2022))
MIN_RANGE_N = 50
MIN_BETA_ROWS = 200
GRID_B = 20                           # the MAE does not depend on the draws

VERDICT_HEADS = ("bsr", "fld_pos", "gmli_relief", "ra9_gap")
RECEIPT_HEADS = ("batting", "league", "replacement")
EXPOSURE_HEADS = ("pa", "ip")
ALL_HEADS = VERDICT_HEADS + RECEIPT_HEADS + EXPOSURE_HEADS


def dev_cells() -> list[tuple[int, int]]:
    out = []
    for B in range(DEV_FIRST_BASE, DEV_LAST_BASE + 1):
        for h in range(1, PC.HORIZONS + 1):
            L = B + h - 1
            if L > DEV_LAST_LABEL or L in PC.PJC_EXCLUDED_LABEL_SEASONS:
                continue
            out.append((B, h))
    return out


# --------------------------------------------------------------------------
# Assembly: one engine pass per (side, row)
# --------------------------------------------------------------------------

class Dev:
    def __init__(self, corpus, frame, blob, bases, quick=False):
        self.corpus, self.frame, self.blob = corpus, frame, blob
        self.bases = list(bases)
        self.quick = quick
        self.cells = [c for c in dev_cells() if c[0] in set(self.bases)]
        self.league = corpus["league"]
        self.by_player = {"hit": {}, "pit": {}}
        for side in ("hit", "pit"):
            for r in corpus[side]:
                if r.get("mlbam"):
                    self.by_player[side].setdefault(int(r["mlbam"]), {})[int(r["season"])] = r
        self.sidecar = aging_v3_sidecar.load(corpus, build_if_missing=False)
        self.consts: dict[int, dict] = {}
        self.fits: dict[int, tuple] = {}
        self.age_curves: dict[int, dict] = {}
        self.rows: list[dict] = []          # {side, row, eng, consts, age_curves}

    def constants(self, season: int) -> dict:
        if season not in self.consts:
            self.consts[season] = PC.season_constants(season, self.corpus, self.blob)
        return self.consts[season]

    def prepare(self):
        t0 = time.time()
        label_seasons = sorted({B + h - 1 for B, h in self.cells})
        for s in sorted(set(label_seasons) | {B - 1 for B in self.bases}):
            self.constants(s)
        log.info("constants for %s (%.1fs)", sorted(self.consts), time.time() - t0)
        for B in self.bases:
            curves, war_map = fp.fitted_models(self.corpus, B - 1)
            model = aging_v3.fitted(self.corpus, B - 1, None, sidecar=self.sidecar)
            self.fits[B] = (curves, war_map)
            self.age_curves[B] = PC.component_age_curves(model)
        log.info("engine and aging fits for bases %s (%.1fs)", self.bases, time.time() - t0)
        n = 0
        for side in ("hit", "pit"):
            rows = [r for r in self.frame[side] if r["base"] in set(self.bases)]
            if self.quick:
                rows = rows[::12]
            for r in rows:
                B = r["base"]
                seasons = self.by_player[side].get(r["mlbam"]) or {}
                hist = [seasons[s] for s in (B - 1, B - 2, B - 3) if s in seasons]
                curves, _wm = self.fits[B]
                eng = PC.engine_projection(hist, side, B, r["age"], curves, self.league)
                if eng is None:
                    continue
                self.rows.append({"side": side, "row": r, "eng": eng,
                                  "consts": self.consts[B - 1],
                                  "age_curves": self.age_curves[B]})
                n += 1
        log.info("engine pass: %d rows (%.1fs)", n, time.time() - t0)

    # ---- heads under one params dict ---------------------------------------
    def heads(self, params: dict) -> dict:
        """{(side, mlbam, base): block}"""
        out = {}
        for x in self.rows:
            r = x["row"]
            if x["side"] == "hit":
                blk = PC.hitter_heads(x["eng"], r["feat"], params, x["consts"], x["age_curves"])
            else:
                blk = PC.pitcher_heads(x["eng"], r["feat"], params, x["consts"])
            out[(x["side"], r["mlbam"], r["base"])] = blk
        return out

    def scorer_rows(self, r_relief: float) -> list[dict]:
        rows = []
        for x in self.rows:
            rows.extend(PC.scorer_rows(x["row"], x["side"], self.cells, self.consts, r_relief))
        return rows

    def feat_of(self, side, mlbam, base):
        return next(x["row"]["feat"] for x in self.rows
                    if x["side"] == side and x["row"]["mlbam"] == mlbam and x["row"]["base"] == base)


# --------------------------------------------------------------------------
# Predictors and comparators (closures over the heads)
# --------------------------------------------------------------------------

def _rate600(runs, pa):
    return None if runs is None or not pa else runs / pa * 600.0


def make_predictors(heads: dict, dev: Dev, r_relief: float, with_ranges=True) -> dict:
    feats = {(x["side"], x["row"]["mlbam"], x["row"]["base"]): x["row"]["feat"] for x in dev.rows}
    consts = {x["row"]["base"]: x["consts"] for x in dev.rows}

    def line(r):
        blk = heads.get((r["side"], r["mlbam"], r["base"]))
        return None if blk is None else blk["lines"].get(int(r["h"]))

    def hit_rate(comp, key):
        def fn(r):
            ln = line(r)
            if ln is None or ln.get(key) is None or not ln.get("pa"):
                return None
            out = {"rate": _rate600(ln[key], ln["pa"]), "exposure": ln["pa"]}
            q = (ln.get("ranges") or {}).get(comp) if with_ranges else None
            if q:
                out["p10"], out["p90"] = q
            return out
        return fn

    def ra9_gap(r):
        ln = line(r)
        if ln is None or ln.get("ra9gap_100ip") is None or not ln.get("ip"):
            return None
        c = consts[r["base"]]
        out = {"rate": ln["ra9gap_100ip"] * c["rpw"], "exposure": ln["ip"]}
        q = (ln.get("ranges") or {}).get("ra9_gap") if with_ranges else None
        if q:
            out["p10"], out["p90"] = q
        return out

    def gmli_relief(r):
        blk = heads.get((r["side"], r["mlbam"], r["base"]))
        ln = line(r)
        if blk is None or ln is None or blk["role"] != "RP" or ln.get("gmli") is None:
            return None
        if ln.get("relief_ip") is None or not ln.get("ip"):
            return None
        out = {"rate": F.leverage_multiplier(ln["gmli"]) * r_relief, "exposure": ln["relief_ip"]}
        q = (ln.get("ranges") or {}).get("gmli_relief") if with_ranges else None
        if q:
            out["p10"], out["p90"] = q
        return out

    def expo(key, comp):
        def fn(r):
            ln = line(r)
            if ln is None or ln.get(key) is None:
                return None
            out = {"exposure": ln[key]}
            q = (ln.get("ranges") or {}).get(comp) if with_ranges else None
            if q:
                out["p10"], out["p90"] = q
            return out
        return fn

    return {"bsr": hit_rate("bsr", "bsr"), "fld_pos": hit_rate("fld_pos", "fld_pos"),
            "batting": hit_rate("batting", "bat"), "league": hit_rate("league", "lg"),
            "replacement": hit_rate("replacement", "rep"),
            "gmli_relief": gmli_relief, "ra9_gap": ra9_gap,
            "pa": expo("pa", "pa"), "ip": expo("ip", "ip")}


def make_comparators(dev: Dev, r_relief: float) -> dict:
    feats = {(x["side"], x["row"]["mlbam"], x["row"]["base"]): x["row"]["feat"] for x in dev.rows}
    consts = {x["row"]["base"]: x["consts"] for x in dev.rows}
    cache: dict = {}

    def naive(r):
        key = (r["side"], r["mlbam"], r["base"])
        if key not in cache:
            cache[key] = PC.naive_components(r["side"], feats[key])
        return cache[key]

    def n_hit(comp):
        return lambda r: naive(r).get(comp)

    def n_gap(r):
        v = naive(r).get("ra9gap_100ip")
        return None if v is None else v * consts[r["base"]]["rpw"]

    def n_gm(r):
        v = naive(r).get("gmli")
        return None if v is None else F.leverage_multiplier(v) * r_relief

    def implicit_def(r):
        return PC.implicit_def_rate(r["mlbam"], r["base"])

    return {"bsr": {"naive": n_hit("bsr"), "implicit": lambda r: 0.0},
            "fld_pos": {"naive": n_hit("fld_pos"), "implicit": implicit_def},
            "batting": {"naive": n_hit("batting")},
            "league": {"naive": n_hit("league")},
            "replacement": {"naive": n_hit("replacement")},
            "gmli_relief": {"naive": n_gm, "implicit": lambda r: 1.0 * r_relief},
            "ra9_gap": {"naive": n_gap, "implicit": lambda r: 0.0}}


# --------------------------------------------------------------------------
# The DEV choices
# --------------------------------------------------------------------------

def r_relief_constant(dev: Dev) -> dict:
    """IP-weighted mean of relievers' runs above replacement per 100 IP before
    the multiplier, over the DEV label seasons on realized inputs."""
    runs = ip = 0.0
    n = 0
    seasons = sorted({B + h - 1 for B, h in dev.cells})
    for s in seasons:
        for x in PC.realized_pitching(s, dev.consts[s], dev.blob):
            if not x["reliever"] or x["drpw"] is None:
                continue
            runs += (x["raap9"] + F.RP_REPLACEMENT * x["drpw"]) * x["ip"] / 9.0
            ip += x["ip"]
            n += 1
    return {"R": (runs / ip * 100.0) if ip > 0 else 0.0, "n_reliever_rows": n,
            "relief_ip": round(ip, 1), "seasons": seasons,
            "rule": "IP-weighted mean over DEV label seasons of (RAAP9 + 0.03 x dRPW) x IP / 9 per 100 IP"}


def grid_search(dev: Dev, scored_rows, comps, base_params: dict, r_relief: float) -> dict:
    """Each shrink constant by the DEV h1 rate MAE on its head."""
    plan = {"bsr_pa": "bsr", "fld_inn": "fld_pos", "gmli_g": "gmli_relief", "ra9gap_ip": "ra9_gap"}
    chosen = dict(base_params.get("shrink") or {})
    tables = {}
    for key, comp in plan.items():
        table = {}
        best = None
        for K in PC.K_GRIDS[key]:
            params = dict(base_params, shrink=dict(chosen, **{key: K}))
            heads = dev.heads(params)
            preds = make_predictors(heads, dev, r_relief, with_ranges=False)
            rep = pe.run_components(scored_rows, {comp: preds[comp]}, {comp: comps[comp]},
                                    dev.cells, SEED, B=GRID_B, vif=VIF)
            hz = rep["components"][comp]["horizons"]
            table[str(K)] = {str(h): {"mae": c.get("mae"), "n_survived": c.get("n_survived"),
                                      "mae_star": c.get("mae_star"),
                                      "naive_mae": (c.get("comparators") or {}).get("naive", {}).get("mae")}
                             for h, c in hz.items()}
            m1 = hz[1]["mae"] if 1 in hz else None
            log.info("grid %s K=%s: h1 MAE %s", key, K, m1)
            if m1 is not None and (best is None or m1 < best[1]):
                best = (K, m1)
        if best is None:
            raise RuntimeError(f"grid {key}: no h1 MAE on DEV")
        chosen[key] = best[0]
        tables[key] = {"head": comp, "grid": list(PC.K_GRIDS[key]), "chosen": best[0],
                       "h1_mae_by_K": {k: v["1"]["mae"] for k, v in table.items()},
                       "table": table, "rule": "argmin h1 DEV rate MAE, ties to the first grid point"}
    return {"shrink": chosen, "tables": tables}


def _fit_beta(pairs):
    """Exposure-weighted OLS slope of residual on centered value: (beta, center, n)."""
    n = len(pairs)
    if n < MIN_BETA_ROWS:
        return None, None, n
    w = sum(e for _v, _r, e in pairs)
    cx = sum(v * e for v, _r, e in pairs) / w
    cr = sum(r * e for _v, r, e in pairs) / w
    sxx = sum(e * (v - cx) ** 2 for v, _r, e in pairs)
    sxy = sum(e * (v - cx) * (r - cr) for v, r, e in pairs)
    if sxx <= 0:
        return None, cx, n
    return sxy / sxx, cx, n


def savant_admission(dev: Dev, scored_rows, comps, params: dict, r_relief: float, B: int) -> dict:
    """The DEV Statcast decisions: with minus without, forward-chained slopes."""
    heads0 = dev.heads(params)                      # without any term
    rows_by_key = {(r["side"], r["mlbam"], r["base"], r["h"]): r for r in scored_rows}
    feats = {(x["side"], x["row"]["mlbam"], x["row"]["base"]): x["row"]["feat"] for x in dev.rows}
    decisions = {}
    for term, (head, _key) in PC.SAVANT_TERMS.items():
        comp = "bsr" if head == "bsr" else "fld_pos"
        line_key = "bsr" if head == "bsr" else "fld_pos"
        # the (value, residual, exposure) pairs of every DEV h1 row with the term
        pairs_by_base: dict[int, list] = defaultdict(list)
        for (side, mlbam, base), blk in heads0.items():
            if side != "hit":
                continue
            r = rows_by_key.get((side, mlbam, base, 1))
            if r is None or not r["exposure"] or r["labels"].get(comp) is None:
                continue
            v = PC.savant_value(feats[(side, mlbam, base)], term)
            ln = blk["lines"][1]
            if v is None or ln.get(line_key) is None:
                continue
            pred = _rate600(ln[line_key], ln["pa"])
            act = r["labels"][comp] / r["exposure"] * 600.0
            pairs_by_base[base].append((v, act - pred, r["exposure"]))
        betas = {}
        for Bb in dev.bases:
            prior = [p for b, ps in pairs_by_base.items() if b <= Bb - 1 for p in ps]
            beta, center, n = _fit_beta(prior)
            betas[Bb] = {"beta": beta, "center": center, "n": n}
        all_pairs = [p for ps in pairs_by_base.values() for p in ps]
        beta_all, center_all, n_all = _fit_beta(all_pairs)

        def with_term(r, term=term, betas=betas, comp=comp, line_key=line_key):
            blk = heads0.get((r["side"], r["mlbam"], r["base"]))
            if blk is None:
                return None
            ln = blk["lines"].get(int(r["h"]))
            if ln is None or ln.get(line_key) is None:
                return None
            rate = _rate600(ln[line_key], ln["pa"])
            if rate is None:
                return None
            b = betas.get(r["base"]) or {}
            v = PC.savant_value(feats[(r["side"], r["mlbam"], r["base"])], term)
            if b.get("beta") is not None and v is not None:
                rate += b["beta"] * (v - b["center"])
            return {"rate": rate, "exposure": ln["pa"]}

        def without(r, comp=comp, line_key=line_key):
            blk = heads0.get((r["side"], r["mlbam"], r["base"]))
            if blk is None:
                return None
            ln = blk["lines"].get(int(r["h"]))
            if ln is None or ln.get(line_key) is None:
                return None
            return _rate600(ln[line_key], ln["pa"])

        # rows without the term never enter: the paired read is on rows the term exists on
        rows_term = [r for r in scored_rows if r["side"] == "hit"
                     and PC.savant_value(feats[(r["side"], r["mlbam"], r["base"])], term) is not None]
        rep = pe.run_components(rows_term, {comp: with_term},
                                {comp: dict(comps[comp], without=without)},
                                dev.cells, SEED, B=B, vif=VIF)
        hz = rep["components"][comp]["horizons"]
        c1 = hz.get(1) or {}
        blk = ((c1.get("comparators") or {}).get("without") or {}).get("pooled") or {}
        delta = blk.get("delta")
        admitted = delta is not None and delta < 0 and beta_all is not None
        decisions[term] = {
            "head": head, "scored_as": comp, "admitted": bool(admitted),
            "delta_with_minus_without_h1": delta, "ub95": blk.get("ub95"), "mde95": blk.get("mde95"),
            "n_players": blk.get("n_players"), "n_rows_h1": c1.get("n"),
            "mae_with": c1.get("mae"), "mae_without": ((c1.get("comparators") or {}).get("without") or {}).get("mae"),
            "beta_frozen": beta_all, "center_frozen": center_all, "n_fit_rows": n_all,
            "betas_by_base": {str(b): v for b, v in betas.items()},
            "by_horizon": {str(h): {"mae_with": c.get("mae"),
                                    "mae_without": ((c.get("comparators") or {}).get("without") or {}).get("mae"),
                                    "delta": (((c.get("comparators") or {}).get("without") or {}).get("pooled") or {}).get("delta")}
                           for h, c in hz.items()},
            "rule": "IN only if the h1 DEV paired delta (with minus without) is below 0; "
                    "the slope at base B is fitted on DEV rows with label season <= B - 1",
        }
        log.info("savant %s: delta %s ub95 %s -> %s", term, delta, blk.get("ub95"),
                 "IN" if admitted else "OUT")
    return decisions


def residual_ranges(dev: Dev, heads: dict, scored_rows, r_relief: float) -> dict:
    """{comp: {h: {tier: {q10, q90, n}}}} of pooled season-runs residuals."""
    import numpy as np
    preds = make_predictors(heads, dev, r_relief, with_ranges=False)
    acc: dict = defaultdict(list)
    for r in scored_rows:
        blk = heads.get((r["side"], r["mlbam"], r["base"]))
        if blk is None:
            continue
        tier = blk["tier"]
        for comp in ALL_HEADS:
            side, kind = pe.COMPONENT_SPECS[comp]
            if side != r["side"]:
                continue
            out = preds[comp](r)
            if out is None:
                continue
            if kind == "exposure":
                pred_runs = out["exposure"]
                actual = float(r["exposure"] or 0.0)
            else:
                act_exp = (r.get("exposures") or {}).get(comp, r.get("exposure")) or 0.0
                label = (r.get("labels") or {}).get(comp)
                if act_exp > 0 and label is None:
                    continue
                pred_runs = out["rate"] * out["exposure"] / pe.COMPONENT_RATE_SCALE[side]
                actual = float(label) if act_exp > 0 else 0.0
            acc[(comp, int(r["h"]), tier)].append(actual - pred_runs)
    out: dict = {}
    for (comp, h, tier), xs in acc.items():
        if len(xs) < MIN_RANGE_N:
            continue
        q10, q90 = np.percentile(np.asarray(xs, dtype=float), [10, 90])
        out.setdefault(comp, {}).setdefault(str(h), {})[tier] = {
            "q10": round(float(q10), 4), "q90": round(float(q90), 4), "n": len(xs)}
    return out


def fip_runs_receipt(dev: Dev, heads: dict) -> dict:
    """P3's receipt: the FIP-runs leg (runs above the league from FIP per 100
    IP) against the realized leg from the vintage's FIP at the label season's
    constants, IP-weighted on survived rows, beside the naive 5/4/3 FIP."""
    acc: dict = defaultdict(lambda: {"w": 0.0, "e": 0.0, "en": 0.0, "n": 0})
    for x in dev.rows:
        if x["side"] != "pit":
            continue
        r, blk = x["row"], heads.get(("pit", x["row"]["mlbam"], x["row"]["base"]))
        if blk is None:
            continue
        naive = PC.naive_components("pit", r["feat"]).get("fip")
        for h, lab in r["labels"].items():
            if (r["base"], h) not in set(dev.cells):
                continue
            ip, fip_l = lab.get("ip"), lab.get("fip")
            if not ip or fip_l is None:
                continue
            cL = dev.consts[lab["season"]]
            actual = (cL["lg_era"] - float(fip_l)) * 100.0 / 9.0
            pred = blk["lines"][h]["fip_runs_100ip"]
            a = acc[h]
            a["w"] += ip
            a["e"] += ip * abs(pred - actual)
            a["n"] += 1
            if naive is not None:
                a["en"] += ip * abs((x["consts"]["lg_era"] - naive) * 100.0 / 9.0 - actual)
    return {str(h): {"n_survived": a["n"], "mae": round(a["e"] / a["w"], 4) if a["w"] else None,
                     "naive_mae": round(a["en"] / a["w"], 4) if a["w"] else None}
            for h, a in sorted(acc.items())}


# --------------------------------------------------------------------------
# The replica receipt: fwar_frame on realized inputs against the vintage
# --------------------------------------------------------------------------

def _load_replica_tool():
    spec = importlib.util.spec_from_file_location("fwar_replica_eval",
                                                  ROOT / "tools" / "fwar_replica_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replica_receipt(blob: dict, seasons=RECEIPT_SEASONS) -> dict:
    FR = _load_replica_tool()
    saber_live = FR.saber
    hit_fields = [f for f in fwar_vintage.HITTING_FIELDS if f not in ("numTeams", "plateAppearances")]
    pit_fields = [f for f in fwar_vintage.PITCHING_FIELDS if f != "numTeams"]
    diffs = {"n_rows": 0, "n_rows_differing": 0, "max_abs_diff": 0.0, "n_live_only": 0}

    def saber_vintage(kind, season):
        rows, amb = saber_live(kind, season)
        vg = PC.vintage_group(blob, season, kind) or {}
        fields = hit_fields if kind == "hitting" else pit_fields
        out = {}
        for pid, r in rows.items():
            v = vg.get(pid)
            if v is None:
                diffs["n_live_only"] += 1
                continue
            st = dict(r.get("stat") or {})
            differ = False
            for f in fields:
                nv = PC._num(v.get(f))
                if nv is None:
                    continue
                ov = PC._num(st.get(f))
                if ov is not None and abs(ov - nv) > 1e-6:
                    differ = True
                    diffs["max_abs_diff"] = max(diffs["max_abs_diff"], abs(ov - nv))
                st[f] = nv
            diffs["n_rows"] += 1
            diffs["n_rows_differing"] += int(differ)
            out[pid] = dict(r, stat=st)
        return out, amb

    FR.saber = saber_vintage
    out = {}
    for y in seasons:
        h = FR.hitters(y)
        p = FR.pitchers(y)
        hc = h.get("components") or {}
        pc = p.get("components") or {}
        out[str(y)] = {
            "hitters": {k: hc[k] for k in ("batting", "wsb", "bsr", "positional", "league", "replacement") if k in hc},
            "pitchers": {k: pc[k] for k in ("fip_runs",) if k in pc},
            "rows": {"hitters": (h.get("rows") or {}).get("scored_pa_gt_0"),
                     "pitchers": (p.get("rows") or {}).get("scored")},
        }
        log.info("replica %s: %s | fip_runs %s", y,
                 {k: v["verdict"] for k, v in out[str(y)]["hitters"].items()},
                 (out[str(y)]["pitchers"].get("fip_runs") or {}).get("verdict"))
    FR.saber = saber_live
    summary = {}
    for side, comps in (("hitters", ("batting", "wsb", "bsr", "positional", "league", "replacement")),
                        ("pitchers", ("fip_runs",))):
        for c in comps:
            v = {s: b[side][c]["verdict"] for s, b in out.items() if c in b[side]}
            summary[f"{side}.{c}"] = {"pass": sorted(s for s, x in v.items() if x == "PASS"),
                                      "fail": sorted(s for s, x in v.items() if x != "PASS")}
    return {"what": "fwar_frame on realized inputs (tools/fwar_replica_eval hitters and pitchers, "
                    "PF back-solved as that tool does) scored against the FROZEN vintage's values "
                    "in place of the live feed; gate as data/fwar_replica_eval.json",
            "gate": {"tolerance_runs": F.TOLERANCE_RUNS, "share": F.GATE_SHARE},
            "vintage_vs_live_feed": diffs, "seasons": out, "summary": summary}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def _gate1_figures() -> dict:
    try:
        d = json.loads((ROOT / "data" / "fa_gate1_eval.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    p = d.get("pooled") or {}
    return {k: {kk: p[k].get(kk) for kk in ("mae_model", "mae_base", "n")}
            for k in ("wrc_plus", "fip") if k in p}


def _mde_table(report: dict) -> dict:
    out = {}
    for comp, blk in report["components"].items():
        c1 = (blk.get("horizons") or {}).get(1) or {}
        row = {"mae_h1": c1.get("mae"), "n_survived_h1": c1.get("n_survived"), "comparators": {}}
        for name, k in (c1.get("comparators") or {}).items():
            pooled, star = k.get("pooled") or {}, k.get("star") or {}
            row["comparators"][name] = {
                "mae": k.get("mae"), "mde95": pooled.get("mde95"), "delta": pooled.get("delta"),
                "ub95": pooled.get("ub95"), "n_players": pooled.get("n_players"),
                "star_mde95": star.get("mde95"), "star_delta": star.get("delta"),
                "underpowered_at_10pct": (None if pooled.get("mde95") is None or not k.get("mae")
                                          else pooled["mde95"] > 0.10 * k["mae"]),
            }
        out[comp] = row
    return out


def run(bases, B: int, quick: bool, out_dir: Path | None, write: bool) -> int:
    t0 = time.time()
    if PC.PARAMS_PATH.exists() and write:
        print(f"{PC.PARAMS_PATH} exists: DEV is frozen once; refusing to rewrite")
        return 2
    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    blob = fwar_vintage.load()
    frame = PC.build_component_frame(corpus, DEV_FIRST_BASE, PC.PJC_LABEL_SEASON_MAX)
    dev = Dev(corpus, frame, blob, bases, quick=quick)
    bad = [c for c in dev.cells if c[0] + c[1] - 1 > DEV_LAST_LABEL]
    if bad:
        q = (out_dir or Path(".")) / "OWNER_QUESTION.md"
        q.write_text(f"A DEV cell would read a label season above {DEV_LAST_LABEL}: {bad}\n",
                     encoding="utf-8")
        print(f"STOP: {q}")
        return 3
    dev.prepare()

    rr = r_relief_constant(dev)
    r_relief = rr["R"]
    scored_rows = dev.scorer_rows(r_relief)
    comps = make_comparators(dev, r_relief)
    for r in scored_rows:
        assert not any(str(k).lower() == "war" for k in r["labels"])
    log.info("scorer rows %d, R_relief %.4f (%.1fs)", len(scored_rows), r_relief, time.time() - t0)

    base_params = {"shrink": {}, "savant": {}, "R_relief": r_relief}
    g = grid_search(dev, scored_rows, comps, base_params, r_relief)
    params = {"shrink": g["shrink"], "savant": {}, "R_relief": r_relief}
    log.info("shrink chosen %s (%.1fs)", g["shrink"], time.time() - t0)

    decisions = savant_admission(dev, scored_rows, comps, params, r_relief, B)
    params["savant"] = {t: {"admitted": d["admitted"],
                            "beta": (d["beta_frozen"] if d["admitted"] else None),
                            "center": (d["center_frozen"] if d["admitted"] else None),
                            "head": d["head"]}
                        for t, d in decisions.items()}
    log.info("savant decisions %s (%.1fs)", {t: d["admitted"] for t, d in decisions.items()},
             time.time() - t0)

    heads = dev.heads(params)
    ranges = residual_ranges(dev, heads, scored_rows, r_relief)
    params["ranges"] = ranges
    heads = dev.heads(params)
    preds = make_predictors(heads, dev, r_relief, with_ranges=True)
    comps_all = dict(comps)
    report = pe.run_components(scored_rows, {c: preds[c] for c in ALL_HEADS},
                               {c: comps_all[c] for c in ALL_HEADS if c in comps_all},
                               dev.cells, SEED, B=B, vif=VIF)
    log.info("final DEV scoring done (%.1fs)", time.time() - t0)
    print(pe.format_components_report(report))

    fip_receipt = fip_runs_receipt(dev, heads)
    replica = replica_receipt(blob) if not quick else {"skipped": "quick"}

    n_np = defaultdict(int)
    for blk in heads.values():
        for c in blk["not_projected"]:
            n_np[c] += 1
    stamp = _dt.date.today().isoformat()
    params_out = {
        "task": "PJ_4_COMPONENT_HEADS_DEV", "frozen_on": stamp, "heads_version": PC.HEADS_VERSION,
        "vintage_id": blob["vintage_id"], "frame_schema_tag": frame["meta"]["schema_tag"],
        "frame_schema": PC.frame_schema(corpus),
        "dev": {"bases": list(dev.bases), "cells": [list(c) for c in dev.cells],
                "label_seasons": sorted({b + h - 1 for b, h in dev.cells}), "quick": quick,
                "n_rows": {"hit": sum(1 for x in dev.rows if x["side"] == "hit"),
                           "pit": sum(1 for x in dev.rows if x["side"] == "pit")},
                "n_scorer_rows": len(scored_rows)},
        "shrink": params["shrink"], "savant": params["savant"], "R_relief": r_relief,
        "ranges": ranges,
        "age_terms": {"bsr": "aging_v3 component_curve('hit','bsr') fitted at B - 1 (U5)",
                      "fld": "aging_v3 component_curve('hit','fld') fitted at B - 1 (U5)",
                      "framing": "none", "aging_v3_version": aging_v3.AGING_V3_VERSION},
        "constants_rule": "every league constant held at the last completed season B - 1 "
                          "(data/league_constants.json plus season_constants' derived terms); "
                          "PF 1.0; no framing charge; replacement at 2430 games; WARIP from the "
                          "realized chain of B - 1",
        "bootstrap": {"seed": SEED, "B": B, "vif": VIF},
    }
    receipt = {
        "task": "PJ_4_COMPONENT_HEADS_DEV", "written_on": stamp, "params_sha256": PC.params_hash(params_out),
        "dev_frame": params_out["dev"],
        "constants_by_season": {str(s): {k: v for k, v in c.items() if k != "receipt"} | {"receipt": c["receipt"]}
                                for s, c in sorted(dev.consts.items())},
        "R_relief": rr,
        "grid_search": g["tables"],
        "statcast_decisions": decisions,
        "mde95": _mde_table(report),
        "dev_tables": report,
        "not_projected_counts": dict(n_np),
        "receipts": {"fwar_replica_vs_vintage_2011_2021": replica,
                     "h2_batting_dev": {str(h): {"mae": c.get("mae"), "naive_mae": (c.get("comparators") or {}).get("naive", {}).get("mae"),
                                                 "n_survived": c.get("n_survived"), "bias": c.get("bias")}
                                        for h, c in report["components"]["batting"]["horizons"].items()},
                     "p3_fip_runs_leg_dev": fip_receipt,
                     "gate1_figures_beside": _gate1_figures(),
                     "note": "no WAR residual is computed on any frame row (gate section 3); P3's receipt is its FIP-runs leg"},
        "elapsed_s": round(time.time() - t0, 1),
    }
    target = PC.PARAMS_DIR if write else (out_dir or Path("."))
    target.mkdir(parents=True, exist_ok=True)
    (target / "params.json").write_text(json.dumps(params_out, indent=1, sort_keys=True) + "\n",
                                         encoding="utf-8")
    (target / "dev_receipt.json").write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n",
                                              encoding="utf-8")
    print(f"params sha256 {receipt['params_sha256']}")
    print(f"wrote {target / 'params.json'} and dev_receipt.json ({receipt['elapsed_s']}s)")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="freeze model/proj_components (once)")
    ap.add_argument("--out", type=Path, default=None, help="preview directory (no freeze)")
    ap.add_argument("--quick", action="store_true", help="every 12th row, no replica receipt")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--bases", default=f"{DEV_FIRST_BASE}-{DEV_LAST_BASE}")
    a = ap.parse_args(argv)
    lo, hi = (int(x) for x in a.bases.split("-"))
    bases = [b for b in range(lo, hi + 1) if DEV_FIRST_BASE <= b <= DEV_LAST_BASE]
    if not a.write and a.out is None:
        ap.error("--write or --out DIR")
    return run(bases, a.bootstrap, a.quick, a.out, a.write)


if __name__ == "__main__":
    raise SystemExit(main())
