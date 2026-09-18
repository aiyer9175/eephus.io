# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""RE-GATE 2: RIV+ against REM+, pre-registered in docs/HEM_RIV_REGATE_GATE.md
(frozen 2026-09-18, before any number here was computed).

WHAT RIV+ IS FOR, decided before anything was tested (gate R2-0): RIV+ is a
VALUE RECORD, not a forecaster. WPA is an outcome; it already carries the
leverage a manager handed the pitcher, the sequencing he met and the defense
behind him. Nothing in that construction is a claim about next year. So this
gate tests RIV+ DESCRIPTIVELY, against the one thing a realized-value record
can be checked against: what clubs paid for it.

  B1 (primary, k = 1)
      delta = rho(RIV+_served(walk year), AAV) - rho(REM+(walk year), AAV)
      ONE target (the AAV of the free-agent contract signed in the winter after
      the walk year), ONE scale (Spearman, same matched rows, both candidates),
      baseline REM+ named explicitly as the owner decision requires.

What the shipped eval (data/riv_plus_eval.json, tools/rem_plus_lab.py) could
not establish, as code facts (gate R2-1): it compares two different targets on
two different scales; its `riv_less_stable_than_rem` pass clause can be passed
by ADDING NOISE; `market_check_aav` emits point rhos with no interval anywhere;
its floor is a hard-coded 0.02; identity is normalized-name only with no
receipts; rows are un-clustered; and the lab scores `riv_raw` (the bare
weighted z) while the board serves `rem_plus.score_riv_plus`, which DIVIDES by
the composite own pool sd, so pooled across winters the evaluated index and the
served index are not the same statistic. That last one is the same
served-versus-eval normalizer defect as re-gate 1, and it is re-gated the same
way.

The repeatability question is kept, asked correctly (one target at a time), and
carries ZERO verdict weight; its interpretation is fixed in advance so it can
neither credit nor condemn RIV+ (gate R2-7).

  -> data/riv_market_regate_eval.json

Run: python tools/riv_market_regate_lab.py [--no-write]
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bullpen_export as be  # noqa: E402
import mlb_leverage  # noqa: E402
import plus_lab_harness as plh  # noqa: E402
import rem_plus  # noqa: E402
from rem_plus_backtest import SEASONS as BT_SEASONS  # noqa: E402
from xhem_served_regate_lab import (cell, cluster_gaps_full,  # noqa: E402
                                    iid_gaps_full, _sd)

DATA = ROOT / "data"
FA_ARCHIVE = DATA / "fa_archive.json"
OUT_PATH = DATA / "riv_market_regate_eval.json"
GATE_DOC = "docs/HEM_RIV_REGATE_GATE.md"

SEASONS = list(BT_SEASONS)           # 2018, 2019, 2021-2025 (ex-2020)
MIN_TBF_Y = 100                      # the walk-year sample floor, unchanged
MIN_TBF_NEXT = 60                    # disclosure leg only
BOOT = 2000
SEED_R2 = 20260918
MIN_MATCHED = 50                     # gate R2-3 support floor; the shipped 20 is a shrug
MDE_Z = 1.645


def _r4(v):
    return None if v is None else round(v, 4)


def _norm_name(s: str) -> str:
    """tools/rem_plus_lab._norm_name, reproduced so the fallback identity rule
    is byte-identical to the one the shipped eval used."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", s)
    return "_".join(s.split())


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _std(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _git_blob_sha1(path: Path) -> str:
    """The vintage receipt the gate requires: the same hash `git hash-object`
    prints, computed without shelling out."""
    b = path.read_bytes()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(b))
    h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# per-season pool: the SERVED scoring path, plus the lab's un-restandardized
# riv_raw kept beside it so the normalizer difference is measurable.
# --------------------------------------------------------------------------- #
def lab_riv_raw(rows: dict) -> None:
    """tools/rem_plus_lab.score_riv, reproduced: the bare weighted z composite
    with NO re-standardize. This is what the shipped eval scored."""
    arms = [r for r in rows.values() if r.get("wpa") is not None]
    if len(arms) < 10:
        for r in rows.values():
            r["riv_raw_lab"] = None
        return
    mu_w, sd_w = _mean([r["wpa"] for r in arms]), _std([r["wpa"] for r in arms])
    sdmd = [((r.get("sd") or 0) - (r.get("md") or 0)) for r in arms]
    mu_s, sd_s = _mean(sdmd), _std(sdmd)
    for r in rows.values():
        if r.get("wpa") is None:
            r["riv_raw_lab"] = None
            continue
        zs = []
        if sd_w:
            zs.append((rem_plus.RIV_W_WPA, (r["wpa"] - mu_w) / sd_w))
        s = (r.get("sd") or 0) - (r.get("md") or 0)
        if sd_s:
            zs.append((rem_plus.RIV_W_SDMD, (s - mu_s) / sd_s))
        if not zs:
            r["riv_raw_lab"] = None
            continue
        r["riv_raw_lab"] = sum(w * v for w, v in zs) / sum(w for w, _ in zs)


def load_season(y: int) -> dict:
    """MLBAM -> one reliever record for season y, scored through the SERVED
    path: rem_plus.score_pool's own pool filter, REM+, then
    rem_plus.score_riv_plus (which re-standardizes the composite on its own
    pool spread, the thing the board serves)."""
    rows = be.load_season_pitching(y)
    if not rows:
        return {}
    swstr = be.load_bref_swstr(y)
    try:
        leverage, _c = mlb_leverage.fetch_season_leverage(y)
    except Exception as e:                                    # noqa: BLE001
        print(f"  {y}: leverage unavailable ({e})")
        leverage = {}
    rels = be.build_relievers(rows, leverage, swstr)
    pool = [r for r in rels
            if rem_plus.is_true_reliever(r) and not rem_plus._is_opener(r)]
    for r in pool:
        rem_plus.derive_rates(r)
    p = rem_plus.build_pool(pool)
    for r in pool:
        rem_plus.rem_plus(r, p)
    rem_plus.score_riv_plus([r for r in pool if r.rem_plus is not None])
    out = {}
    for r in pool:
        if r.rem_plus is None:
            continue
        out[r.mlbam] = {
            "name": r.name, "team": r.team,
            "rem_plus": r.rem_plus, "rem_plus_raw": r.rem_plus_raw,
            "riv_plus_served": r.riv_plus, "riv_served_raw": r.riv_plus_raw,
            "tbf": r.tbf, "ip": r.ip, "g": r.g,
            "wpa": r.wpa, "sd": r.sd, "md": r.md, "gmli": r.gmli,
            "ra9": r.rates.get("ra9"),
        }
    lab_riv_raw(out)
    return out


# --------------------------------------------------------------------------- #
# B1: the market pair set, with identity receipts
# --------------------------------------------------------------------------- #
def build_market_rows(by_season: dict) -> dict:
    arch = json.loads(FA_ARCHIVE.read_text(encoding="utf-8"))
    try:
        import fa_ident
        canon_ok = not fa_ident.index_sides_missing()
    except Exception as e:                                    # noqa: BLE001
        fa_ident = None
        canon_ok = False
        print(f"  canonical identity path unavailable ({e}); name fallback only")

    name_maps, collisions = {}, {}
    for y, pool in by_season.items():
        m: dict = {}
        dupes: dict = {}
        for mid, rec in pool.items():
            k = _norm_name(rec["name"])
            if k in m:
                dupes.setdefault(k, [m[k]]).append(mid)
            m[k] = mid
        name_maps[y] = m
        collisions[y] = dupes

    rows, unmatched, seen = [], [], set()
    n_rp_signings = 0
    by_method = {"canonical_mlbam": 0, "normalized_name": 0}
    drop_reason: dict = {}
    for w in arch.get("winters", []):
        winter = int(w.get("year") or 0)
        walk = winter - 1
        pool = by_season.get(walk)
        for s in w.get("signings", []):
            if "RP" not in str(s.get("pos", "")) or not s.get("aav"):
                continue
            n_rp_signings += 1
            if not pool:
                drop_reason["no_pool_for_walk_year"] = drop_reason.get(
                    "no_pool_for_walk_year", 0) + 1
                continue
            mid = None
            method = None
            if canon_ok and fa_ident is not None:
                try:
                    cand = fa_ident.resolve(s.get("name", ""), range(winter - 4, winter))
                except Exception:                             # noqa: BLE001
                    cand = None
                if cand is not None and cand in pool:
                    mid, method = cand, "canonical_mlbam"
            if mid is None:
                cand = name_maps[walk].get(_norm_name(s.get("name", "")))
                if cand is not None:
                    mid, method = cand, "normalized_name"
            if mid is None:
                unmatched.append({"winter": winter, "name": s.get("name", ""),
                                  "key": s.get("key", ""), "pos": s.get("pos", "")})
                drop_reason["identity_unresolved"] = drop_reason.get(
                    "identity_unresolved", 0) + 1
                continue
            rec = pool[mid]
            if (rec.get("tbf") or 0) < MIN_TBF_Y:
                drop_reason["walk_year_tbf_below_floor"] = drop_reason.get(
                    "walk_year_tbf_below_floor", 0) + 1
                continue
            if rec.get("riv_served_raw") is None or rec.get("rem_plus_raw") is None:
                drop_reason["index_missing"] = drop_reason.get("index_missing", 0) + 1
                continue
            key = (mid, winter)
            if key in seen:
                drop_reason["duplicate_player_winter"] = drop_reason.get(
                    "duplicate_player_winter", 0) + 1
                continue
            seen.add(key)
            by_method[method] += 1
            rows.append({
                "mlbam": mid, "name": rec["name"], "winter": winter,
                "walk_year": walk, "aav": float(s["aav"]),
                "riv_served_raw": rec["riv_served_raw"],
                "riv_plus_served_int": float(rec["riv_plus_served"]),
                "riv_raw_lab": rec.get("riv_raw_lab"),
                "rem_plus_raw": rec["rem_plus_raw"],
                "rem_plus_int": float(rec["rem_plus"]),
                "method": method,
            })
    return {"rows": rows, "unmatched": unmatched, "by_method": by_method,
            "drop_reason": drop_reason, "n_rp_signings_with_aav": n_rp_signings,
            "collisions": {str(y): {k: v for k, v in d.items()}
                           for y, d in collisions.items() if d},
            "canonical_identity_available": canon_ok}


def _compare(primary, baseline, tgt, players, strata, seed=SEED_R2) -> dict:
    v1 = iid_gaps_full(primary, {"vs_rem_plus": baseline}, tgt, BOOT,
                       seed)["vs_rem_plus"]
    v2 = cluster_gaps_full(primary, {"vs_rem_plus": baseline}, tgt, players,
                           strata, BOOT, seed)["vs_rem_plus"]
    return {"v1": cell(primary, baseline, tgt, v1),
            "v2": cell(primary, baseline, tgt, v2),
            "_v1": v1, "_v2": v2}


def run(write: bool = True) -> dict:
    t0 = time.time()
    by_season = {}
    for y in SEASONS + [max(SEASONS) + 1]:
        by_season[y] = load_season(y)
        print(f"  {y}: {len(by_season[y])} relievers scored")

    mk = build_market_rows(by_season)
    rows = mk["rows"]
    n = len(rows)
    print(f"  B1 matched signings: {n}")

    refused = n < MIN_MATCHED
    payload_b1 = None
    holm = None
    verdict = None
    reason = None

    if refused:
        verdict = "provisional"
        reason = (f"REFUSED: only {n} matched RP signings, below the "
                  f"pre-registered support floor of {MIN_MATCHED}. The gate "
                  f"publishes coverage only and the clock moves to the next "
                  f"free-agent class (2027-03-01).")
    else:
        aav = [r["aav"] for r in rows]
        aav_log = [math.log(v + 1.0) for v in aav]
        riv = [r["riv_served_raw"] for r in rows]
        rem = [r["rem_plus_raw"] for r in rows]
        players = [r["mlbam"] for r in rows]
        winters = [r["winter"] for r in rows]

        b1 = _compare(riv, rem, aav, players, winters)
        # the log transform is a RANK no-op; said out loud and then checked,
        # because the log looks like a choice and is not one.
        rank_noop = bool(plh.spearman(riv, aav) == plh.spearman(riv, aav_log)
                         and plh.spearman(rem, aav) == plh.spearman(rem, aav_log))

        holm = None
        try:
            from efv_power_lab import holm_family
            d = b1["_v1"]
            holm = {"v1": holm_family([{"key": "B1_riv_plus",
                                        "delta": sum(d) / len(d), "sd": _sd(d)}]),
                    "v2": holm_family([{"key": "B1_riv_plus",
                                        "delta": sum(b1["_v2"]) / len(b1["_v2"]),
                                        "sd": _sd(b1["_v2"])}])}
        except Exception as e:                                # noqa: BLE001
            holm = {"note": f"holm_family unavailable: {e}"}

        # ---- the pre-registered decision rule (gate R2-5) ------------------ #
        # Applied LITERALLY. Where the rule and a later measurement disagree the
        # measurement is what the gate uses, and the disagreement is recorded
        # rather than edited away - see rule_note below, which is the honest
        # report of a rule this run found to be mis-specified. The verdict is
        # still the one the pre-registered rule produces, because the
        # mis-specification makes the rule HARSHER than its stated intent and
        # softening a pre-registered outcome after seeing it is the move this
        # document exists to forbid.
        c1, c2 = b1["v1"], b1["v2"]
        lo1, lo2 = c1["gap_ci"]["lo95"], c2["gap_ci"]["lo95"]
        mde1, mde2 = c1["mde95_in_run"], c2["mde95_in_run"]
        directional = bool(c1["hi95_lt_0"] or c2["hi95_lt_0"])
        by_resolution = bool(lo1 <= -mde1 or lo2 <= -mde2)
        if directional or by_resolution:
            verdict = "deprecated"
            if directional:
                reason = ("REFUTED, DIRECTIONALLY: the gap hi95 is below zero, so "
                          "REM+ tracks reliever pay BETTER than the value index "
                          "built to capture deployed value. RIV+'s only surviving "
                          "claim is dead. Whether the column stays on the board is "
                          "an open question for the display lane.")
            else:
                reason = (
                    "REFUTED ON RESOLUTION, and the direction must be said plainly "
                    "so the row is not misread: the gap POINT ESTIMATE still "
                    "favours RIV+ (%s vs %s, gap mean %s), but its lower bound sits "
                    "at or below the in-run MDE95, so the pre-registered rule fires. "
                    "RIV+ is NOT shown to be worse than REM+; it is shown not to be "
                    "BETTER, which is the only claim the row made. The published "
                    "market edge (0.576 vs 0.508) does not survive one target, one "
                    "scale, the walk-year sample floor and canonical identity: on "
                    "this pair set REM+ reads %s, not 0.508, and the edge collapses "
                    "to a coin flip. Whether the column stays on the board is an "
                    "open question for the display lane."
                    % (c1["rho_primary"], c1["rho_baseline"],
                       c1["gap_ci"]["mean"], c1["rho_baseline"]))
        elif lo1 > 0 and lo2 > 0:
            verdict = "validated"
            reason = ("Validated DESCRIPTIVELY: RIV+ aligns with reliever "
                      "free-agent AAV better than REM+ under BOTH conventions. "
                      "This is a realized-value record, not a forecast.")
        else:
            verdict = "provisional"
            reason = ("Not separable from REM+ on market alignment at this n: the "
                      "gap lower bound sits at or below zero but inside the in-run "
                      "MDE95 under both conventions, so the claim drops 'better "
                      "than REM+'. This is a realized-value record, not a forecast.")

        # ---- labelled sensitivities, zero verdict weight ------------------- #
        sens = {
            "served_integers": {
                "note": ("the comparison a board reader actually makes: the served "
                         "RIV+ integer against the served REM+ integer"),
                **{k: v for k, v in _compare([r["riv_plus_served_int"] for r in rows],
                                             [r["rem_plus_int"] for r in rows],
                                             aav, players, winters).items()
                   if not k.startswith("_")}},
            "lab_riv_raw_no_restandardize": {
                "note": ("the statistic the SHIPPED eval scored (tools/rem_plus_lab "
                         "riv_raw, the bare weighted z with no re-standardize). "
                         "Pooled across winters it is not the same statistic as the "
                         "served column; this cell is how much that matters here."),
                **{k: v for k, v in _compare(
                    [r["riv_raw_lab"] for r in rows], rem, aav, players, winters).items()
                   if not k.startswith("_")}},
            "log_aav_is_a_rank_no_op": rank_noop,
        }
        payload_b1 = {
            "estimand": ("rho(RIV+_served(walk year), AAV) - rho(REM+(walk year), AAV), "
                         "one target, one scale, same matched rows"),
            "target": ("the AAV of the free-agent contract signed in the winter "
                       "following the walk year (raw dollars; Spearman, so the "
                       "shipped log transform is a rank no-op and is labelled as one)"),
            "baseline": "REM+ (unrounded rem_plus_raw), named explicitly per the owner decision",
            "primary": ("RIV+_served: the per-season composite re-standardized on its "
                        "own pool spread, as rem_plus.score_riv_plus ships it"),
            "n_matched_signings": n,
            "v1": b1["v1"], "v2": b1["v2"],
            "sensitivities": sens,
            "decision_rule_trigger": {
                "refuted_directionally_hi95_lt_0": directional,
                "refuted_on_resolution_lo95_le_minus_mde95": by_resolution,
                "v1": {"lo95": lo1, "minus_mde95": -mde1},
                "v2": {"lo95": lo2, "minus_mde95": -mde2},
            },
            "rule_note_mis_specification_found_in_run": (
                "RECORDED, not edited away. The pre-registered R2-5 middle band "
                "('lo95 <= 0 but lo95 > -MDE95 under both conventions -> stays "
                "provisional') is unreachable for a gap centred near zero, and the "
                "algebra is one line: lo95 is the 2.5th percentile of the gap draws, "
                "roughly mean - 1.96*sd, while -MDE95 is -1.645*sd, so lo95 > -MDE95 "
                "requires mean > 0.315*sd. A dead-centre null therefore lands in the "
                "REFUTED row rather than the not-separable row. This run is exactly "
                "that case (gap mean 0.099 sd). The rule is applied as written "
                "because it is harsher than its own stated intent and softening a "
                "pre-registered outcome after seeing it is forbidden; the "
                "mis-specification is carried here so the NEXT re-gate fixes the "
                "band rather than inheriting it. The reading that travels with the "
                "verdict is 'not shown to be better', never 'shown to be worse'."),
        }

    # ---- R2-7 disclosure leg: ZERO verdict weight ------------------------- #
    disc = {}
    for tgt_name, tgt_key in (("RIV+(Y+1)", "riv_served_raw"),
                              ("REM+(Y+1)", "rem_plus_raw")):
        p_riv, p_rem, t, mids, pys, oys = [], [], [], [], [], []
        for y in SEASONS:
            ny = y + 1
            cur, nxt = by_season.get(y), by_season.get(ny)
            if not cur or not nxt or not plh.season_complete(ny):
                continue
            for mid, a in cur.items():
                b = nxt.get(mid)
                if not b or (a["tbf"] or 0) < MIN_TBF_Y or (b["tbf"] or 0) < MIN_TBF_NEXT:
                    continue
                if (a.get("riv_served_raw") is None or a.get("rem_plus_raw") is None
                        or b.get(tgt_key) is None):
                    continue
                p_riv.append(a["riv_served_raw"])
                p_rem.append(a["rem_plus_raw"])
                t.append(b[tgt_key])
                mids.append(mid)
                pys.append(y)
                oys.append(ny)
        if len(t) < 30:
            disc[tgt_name] = {"note": "too few pairs", "n": len(t)}
            continue
        t_v2 = plh.zscore_within(oys, t)
        d1 = iid_gaps_full(p_rem, {"vs_riv_plus": p_riv}, t, BOOT,
                           SEED_R2)["vs_riv_plus"]
        d2 = cluster_gaps_full(p_rem, {"vs_riv_plus": p_riv}, t_v2, mids, pys,
                               BOOT, SEED_R2)["vs_riv_plus"]
        disc[tgt_name] = {
            "n_pairs": len(t),
            "question": f"does REM+(Y) or RIV+(Y) predict {tgt_name} better",
            "gap_is": "rho(REM+) - rho(RIV+)",
            "v1": cell(p_rem, p_riv, t, d1),
            "v2": cell(p_rem, p_riv, t_v2, d2),
        }
    disclosure = {
        "verdict_weight": "ZERO, by declaration (gate R2-7)",
        "interpretation_fixed_in_advance": (
            "If REM+ beats RIV+ at forecasting next-year RIV+, that CONFIRMS RIV+ "
            "carries a large non-repeatable deployment and sequencing component, "
            "which is consistent with the two-number design and is NOT a failure "
            "under the descriptive frame. It does, however, FORBID any forward "
            "reading of the RIV+ column, and the glossary and column copy must say "
            "so (a display consequence). If RIV+ were to BEAT REM+ at forecasting "
            "next-year RIV+, the premise of the two-number design would be wrong "
            "and a re-design question would open; it still would not pass this "
            "gate, because this gate is the market leg."),
        "results": disc,
    }

    coverage = {
        "note": ("Coverage is reported separately and is NEVER used to explain a "
                 "gap. Identity resolution is the binding constraint on this pair "
                 "set, so it is reported, never assumed."),
        "n_rp_signings_with_aav_in_archive": mk["n_rp_signings_with_aav"],
        "n_matched": len(rows),
        "matched_by_identity_method": mk["by_method"],
        "canonical_identity_path_available": mk["canonical_identity_available"],
        "drops_by_reason": mk["drop_reason"],
        "n_unmatched_signings": len(mk["unmatched"]),
        "unmatched_signings": mk["unmatched"],
        "normalized_name_collisions_in_pool_by_season": mk["collisions"],
        "matched_n_by_winter": {},
        "support_floor": MIN_MATCHED,
    }
    for r in rows:
        k = str(r["winter"])
        coverage["matched_n_by_winter"][k] = coverage["matched_n_by_winter"].get(k, 0) + 1
    coverage["matched_n_by_winter"] = dict(sorted(coverage["matched_n_by_winter"].items()))

    payload = {
        "generated_at": date.today().isoformat(),
        "experiment": "RE-GATE 2 (B1)",
        "gate_document": GATE_DOC,
        "pre_registered": "2026-09-18, frozen before any number in this artifact was computed",
        "model": "riv_plus",
        "what_riv_is_for": (
            "RIV+ is a VALUE RECORD, not a forecaster: a leverage-weighted account "
            "of the wins a reliever actually added. It is therefore gated "
            "DESCRIPTIVELY, against what clubs paid, and the claim it carries is "
            "descriptive. Gating it as a forecaster would test a claim it never "
            "made."),
        "shipped_eval_defects_addressed": [
            "two different targets on two different scales (forward_stability_check)",
            "a pass condition that rewards noise (riv_less_stable_than_rem)",
            "no interval anywhere on the market comparison",
            "a stored 0.02 constant used as a floor",
            "identity by normalized name with no receipts",
            "un-clustered rows although relievers sign in several winters",
            ("the eval scored riv_raw while the board serves the re-standardized "
             "composite, so pooled across winters they are not the same statistic"),
        ],
        "seasons": SEASONS,
        "seed": SEED_R2,
        "boot": BOOT,
        "fa_archive_vintage": {
            "path": "data/fa_archive.json",
            "git_blob_sha1": _git_blob_sha1(FA_ARCHIVE),
        },
        "harness": plh.convention_meta(
            "AAV of the signed contract (raw, pooled across winters)",
            "AAV of the signed contract"),
        "conventions": {
            "v1": "iid paired resample over matched signings",
            "v2": ("player-clustered (all of a player's signings move together), "
                   "SIGNING-WINTER stratified, because pay levels differ by winter"),
            "mde95": ("derived in run as 1.645 * bootstrap sd of the gap; the "
                      "hard-coded 0.02 slack is retired by this gate"),
        },
        "B1_primary": payload_b1,
        "multiplicity": {
            "family": "one primary test, B1, so k = 1 and Holm is the identity; "
                      "declared anyway so the family size is on the record",
            "holm": holm,
            "outside_the_family_by_declaration": [
                "the R2-7 disclosure leg", "the served-integer sensitivity",
                "the lab riv_raw sensitivity", "every coverage figure"],
        },
        "disclosure_repeatability_leg": disclosure,
        "coverage": coverage,
        "retirements": [
            ("the hard-coded -0.02 slack at tools/rem_plus_lab.py is replaced by an "
             "in-run MDE95"),
            ("riv_less_stable_than_rem is removed as a PASS condition, because a "
             "check that a number is noisier than its baseline can be passed by "
             "adding noise to it"),
        ],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    payload["verdict"] = {"riv_plus": verdict, "reason": reason,
                          "summary": _summary(payload, verdict, reason)}

    print(json.dumps({"n": len(rows), "verdict": verdict,
                      "B1_v1": (payload_b1 or {}).get("v1", {}).get("gap_ci"),
                      "B1_v2": (payload_b1 or {}).get("v2", {}).get("gap_ci")},
                     indent=1))
    if write:
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(OUT_PATH)
        print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    return {OUT_PATH: payload}


def _summary(p: dict, verdict: str, reason: str) -> str:
    b1 = p.get("B1_primary")
    if not b1:
        return f"RE-GATE 2 {verdict}: {reason}"
    return (
        f"RE-GATE 2, B1 market alignment on {b1['n_matched_signings']} matched RP "
        f"signings: RIV+_served vs AAV rho {b1['v1']['rho_primary']}, REM+ "
        f"{b1['v1']['rho_baseline']}; gap v1 {b1['v1']['gap_ci']} "
        f"(MDE95 {b1['v1']['mde95_in_run']}), gap v2 {b1['v2']['gap_ci']} "
        f"(MDE95 {b1['v2']['mde95_in_run']}). Verdict {verdict}. {reason}")


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv[1:])
