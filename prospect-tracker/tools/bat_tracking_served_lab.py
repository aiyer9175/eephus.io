# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The ONE served-construction re-read of the bat-tracking blend (arm B of
tools/bat_tracking_lab.py), pre-registered in docs/BAT_TRACKING_SERVED_GATE.md
(committed alone on 2026-10-14 before any number here existed).

    delta = rho(BT_served(Y), wOBA(Y+1)) - rho(fwdHEM+_served(Y), wOBA(Y+1))

on arm B's 528-pair set, unchanged. The candidate is bat_tracking_blend (the
production module the board would call), the baseline is the served xHEM+ Blend
reconstructed by tools/xhem_served_regate_lab. Ladder D0..D4, candidate and
baseline moving together; ONLY D4 (the integers as served) carries a verdict:
gap lo95 > 0 under BOTH v1 and v2 (seed 20261014, 2000 reps, k = 1). D0 must
reproduce data/bat_tracking_eval.json arm B under seed 20260723 or the run
stops before any served-construction number is scored.

Reads caches only (the Savant expected CSVs under .cache/savant_mlb, the lab's
frozen bat-tracking captures under .cache/bat_tracking); fetches nothing.

  -> data/bat_tracking_served_eval.json

Run:  python tools/bat_tracking_served_lab.py --season-complete-asof 2026:2026-10-01
      python tools/bat_tracking_served_lab.py --dry-run   (reporting path on null fixtures)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import plus_lab_harness as plh  # noqa: E402

DATA = ROOT / "data"
OUT_PATH = DATA / "bat_tracking_served_eval.json"
GATE_DOC = "docs/BAT_TRACKING_SERVED_GATE.md"
SEED = 20261014
BOOT = 2000
REGISTERED_DATE = "2026-10-14"
PUBLISHED_D0 = {"n": 528, "rho_candidate": 0.4598, "rho_incumbent": 0.4465,
                "v1_lo95": 0.0015, "v2_lo95": 0.0025}
TARGET_V1 = "Savant wOBA in Y+1 (raw, pooled across folds)"
TARGET_V2 = "Savant wOBA in Y+1"


def _r4(v):
    return None if v is None else round(v, 4)


# --------------------------------------------------------------------------- #
# the decision rule (gate section 6), pure so the dry run can exercise it
# --------------------------------------------------------------------------- #
def decide(d4: dict | None) -> dict:
    """{verdict, flip, reason} from the D4 cells {'v1': cell, 'v2': cell}."""
    c1 = (d4 or {}).get("v1") or {}
    c2 = (d4 or {}).get("v2") or {}
    g1, g2 = c1.get("gap_ci"), c2.get("gap_ci")
    if not g1 or not g2:
        return {"verdict": "INCOMPLETE", "flip": False,
                "reason": "a D4 cell is missing; no verdict is read (stop rule)."}
    if g1["hi95"] < 0 or g2["hi95"] < 0:
        return {"verdict": "REFUTED", "flip": False,
                "reason": ("the D4 gap hi95 is below zero under at least one convention: "
                           "the eval-construction edge does not survive the served "
                           "normalizer. Stays dark.")}
    p1, p2 = g1["lo95"] > 0, g2["lo95"] > 0
    if p1 and p2:
        return {"verdict": "PASS", "flip": True,
                "reason": "the served construction clears the served xHEM+ Blend at D4 "
                          "under BOTH conventions. The flag flips."}
    if p1 or p2:
        return {"verdict": "FAIL", "flip": False,
                "reason": ("the D4 gap lo95 clears zero under %s only; the gate requires "
                           "both conventions. Stays dark." % ("v1" if p1 else "v2"))}
    return {"verdict": "FAIL", "flip": False,
            "reason": ("not separable from the served xHEM+ Blend on the served "
                       "construction at this n (the gap CI straddles zero under both "
                       "conventions). Stays dark.")}


def summary(payload: dict) -> str:
    lad = (payload.get("ladder") or {})
    d4 = lad.get("D4") or {}
    d0 = lad.get("D0_original_seed") or {}
    v1, v2 = d4.get("v1") or {}, d4.get("v2") or {}
    dec = payload.get("decision") or {}
    return (
        "BT Blend served-construction re-read (D4, integers as served) on "
        f"{payload.get('n_pairs')} pairs: rho {v1.get('rho_primary')} vs served xHEM+ "
        f"Blend {v1.get('rho_baseline')}, v1 gap {v1.get('gap_ci')} (MDE95 "
        f"{v1.get('mde95_in_run')}), v2 gap {v2.get('gap_ci')} (MDE95 "
        f"{v2.get('mde95_in_run')}); eval-construction D0 reproduction v1 gap "
        f"{(d0.get('v1') or {}).get('gap_ci')}. Verdict {dec.get('verdict')}: "
        f"{dec.get('reason')}")


# --------------------------------------------------------------------------- #
# inputs (caches only)
# --------------------------------------------------------------------------- #
def load_inputs() -> dict:
    import bat_tracking_lab as btl
    import xhem_plus_lab as xhl
    from phem_marcel_lite_lab import load_hit_season
    from xwoba_projection_blend_lab import load_xwoba

    preds = list(btl.PRED_SEASONS)
    sav = {y: load_xwoba(y) for y in preds + [max(preds) + 1]}
    hit = {y: load_hit_season(y)[0] for y in preds}
    hem_core = {y: xhl.load_hem_core(y) for y in preds}
    bt_rows, bt_pop = {}, {}
    for y in preds:
        path = btl.BT_CACHE / f"bat_tracking_batter_{y}.json"
        if not path.exists():
            raise RuntimeError(f"frozen bat-tracking capture missing: {path}")
        bt_rows[y] = json.loads(path.read_text(encoding="utf-8"))
        bt_pop[y] = btl.load_bt(y)[0]
    return {"preds": preds, "sav": sav, "hit": hit, "hem_core": hem_core,
            "bt_rows": bt_rows, "bt_pop": bt_pop}


def build_pairs(inp: dict) -> tuple[list[dict], dict]:
    """Arm B's pair set exactly (bat_tracking_lab.run_arm_b)."""
    import bat_tracking_lab as btl
    bt_z = {y: btl.zmap(inp["bt_pop"][y], btl.ARM_B_COMPOSITE_FEATS) for y in inp["preds"]}
    pairs, drops = [], {"partial_outcome_kept": 0, "hem_missing": 0, "bt_missing": 0}
    for y in inp["preds"]:
        cur, nxt = inp["sav"].get(y), inp["sav"].get(y + 1)
        if not cur or not nxt:
            continue
        for mid, s in cur.items():
            nn = nxt.get(mid)
            if not nn or s["pa"] < btl.SAVANT_MIN_PA or nn["pa"] < btl.SAVANT_MIN_PA:
                continue
            if not plh.season_complete(y + 1):
                drops["partial_outcome_kept"] += 1
            hem = (inp["hit"].get(y) or {}).get(mid, {}).get("hem_plus_raw")
            if hem is None:
                drops["hem_missing"] += 1
                continue
            z = bt_z.get(y, {}).get(mid)
            if not z:
                drops["bt_missing"] += 1
                continue
            comp = sum(z[k] for k in btl.ARM_B_COMPOSITE_FEATS) / len(btl.ARM_B_COMPOSITE_FEATS)
            pairs.append({"mid": mid, "y": y, "oy": y + 1, "tgt": nn["woba"],
                          "xw": s["est_woba"], "hem": hem, "bt_eval": comp,
                          "pa_y": s["pa"]})
    return pairs, drops


# --------------------------------------------------------------------------- #
def run(write: bool = True) -> dict:
    import bat_tracking_blend as bbt
    import bat_tracking_lab as btl
    import xhem_served_regate_lab as xsr

    t0 = time.time()
    inp = load_inputs()
    pairs, drops = build_pairs(inp)
    n = len(pairs)
    preds = inp["preds"]
    print(f"  pair set: {n} pairs, drops {drops}")

    mids = [p["mid"] for p in pairs]
    pys = [p["y"] for p in pairs]
    oys = [p["oy"] for p in pairs]
    tgt = [p["tgt"] for p in pairs]
    tgt_v2 = plh.zscore_within(oys, tgt)

    # ---- D0: the eval construction, reproduced ---------------------------- #
    zx = plh.zscore_within(pys, [p["xw"] for p in pairs])
    zh = plh.zscore_within(pys, [p["hem"] for p in pairs])
    zb = plh.zscore_within(pys, [p["bt_eval"] for p in pairs])
    cw, fw = btl.CAND_W, btl.FWDHEM_W
    cand = {"D0": [cw[0] * a + cw[1] * b + cw[2] * c for a, b, c in zip(zx, zh, zb)]}
    base = {"D0": [fw[0] * a + fw[1] * b for a, b in zip(zx, zh)]}

    h1 = plh.iid_boot_gaps(cand["D0"], {"fwdhem_incumbent": base["D0"]}, tgt, BOOT,
                           btl.SEED)["fwdhem_incumbent"]
    h2 = plh.cluster_boot_gaps(cand["D0"], {"fwdhem_incumbent": base["D0"]}, tgt_v2,
                               mids, pys, BOOT, btl.SEED)["fwdhem_incumbent"]
    rho_c0 = _r4(plh.spearman(cand["D0"], tgt))
    rho_b0 = _r4(plh.spearman(base["D0"], tgt))
    repro = {
        "seed": btl.SEED, "n": n, "rho_candidate": rho_c0, "rho_incumbent": rho_b0,
        "v1_gap": h1, "v2_gap": h2, "published": PUBLISHED_D0,
        "artifact": "data/bat_tracking_eval.json arm_b_descriptive_blend",
    }
    repro["reproduces_published"] = bool(
        n == PUBLISHED_D0["n"] and rho_c0 == PUBLISHED_D0["rho_candidate"]
        and rho_b0 == PUBLISHED_D0["rho_incumbent"]
        and h1 and h1["lo95"] == PUBLISHED_D0["v1_lo95"]
        and h2 and h2["lo95"] == PUBLISHED_D0["v2_lo95"])
    print(f"  D0 reproduction: {json.dumps(repro)}")
    if not repro["reproduces_published"]:
        payload = {"generated_at": date.today().isoformat(), "gate_document": GATE_DOC,
                   "stopped": "D0 does not reproduce data/bat_tracking_eval.json arm B; "
                              "the reproduction failure is the finding (gate section 9)",
                   "d0_reproduction_check": repro,
                   "season_complete_override": plh.season_complete_override_meta()}
        if write:
            OUT_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        raise SystemExit("STOP: D0 does not reproduce")

    # ---- the served normalizers (complete season pools) ------------------- #
    sav_tuple = {y: {m: (s["woba"], s["est_woba"], s["pa"])
                     for m, s in inp["sav"][y].items()} for y in preds}
    xw_srv = {y: {m: s["est_woba"] for m, s in inp["sav"][y].items()
                  if s["pa"] >= bbt.MIN_PA and s["est_woba"] > 0} for y in preds}
    comp_srv = {y: bbt.composite_map(inp["bt_rows"][y]) for y in preds}
    p_bt = {y: bbt.blend_params(xw_srv[y], inp["hem_core"][y], comp_srv[y]) for y in preds}
    p_fh = {y: xsr.served_fwdhem_pool(sav_tuple[y], inp["hem_core"][y]) for y in preds}
    served_int = {y: bbt.served_values(xw_srv[y], inp["hem_core"][y], comp_srv[y])[0]
                  for y in preds}

    # integrity: the component stage carries no served-versus-eval difference,
    # and the pair-set HEM core is the served HEM core
    comp_diff = max(abs(comp_srv[p["y"]][p["mid"]] - p["bt_eval"]) for p in pairs)
    hem_diff = max(abs(inp["hem_core"][p["y"]][p["mid"]] - p["hem"]) for p in pairs)
    if comp_diff > 1e-9 or hem_diff > 1e-9:
        raise SystemExit(f"STOP: served inputs differ from eval inputs "
                         f"(composite {comp_diff}, hem {hem_diff})")

    cand["D1"] = [bbt.blend_z(p["xw"], p["hem"], comp_srv[p["y"]][p["mid"]], p_bt[p["y"]])
                  for p in pairs]
    cand["D2"] = [bbt.blend_unrounded(p["xw"], p["hem"], comp_srv[p["y"]][p["mid"]],
                                      p_bt[p["y"]]) for p in pairs]
    cand["D3"] = list(cand["D2"])
    cand["D4"] = [float(int(round(v))) for v in cand["D3"]]
    mism = sum(1 for p, v in zip(pairs, cand["D4"]) if served_int[p["y"]][p["mid"]] != v)
    if mism:
        raise SystemExit(f"STOP: D4 differs from bat_tracking_blend.served_values on {mism} rows")

    def _fd1(p):
        q = p_fh[p["y"]]
        return (xsr.W_XWOBA * (p["xw"] - q["mu_x"]) / q["sd_x"]
                + xsr.W_HEM * (p["hem"] - q["mu_h"]) / q["sd_h"])
    base["D1"] = [_fd1(p) for p in pairs]
    base["D2"] = [xsr.served_fwdhem_unrounded(p["xw"], p["hem"], p_fh[p["y"]]) for p in pairs]
    base["D3"] = list(base["D2"])
    base["D4"] = [float(int(round(v))) for v in base["D3"]]

    # ---- the ladder -------------------------------------------------------- #
    ladder = {}
    for rung in ("D0", "D1", "D2", "D3", "D4"):
        seeds = [(SEED, rung)] + ([(btl.SEED, "D0_original_seed")] if rung == "D0" else [])
        for seed, key in seeds:
            d1 = xsr.iid_gaps_full(cand[rung], {"b": base[rung]}, tgt, BOOT, seed)["b"]
            d2 = xsr.cluster_gaps_full(cand[rung], {"b": base[rung]}, tgt_v2, mids, pys,
                                       BOOT, seed)["b"]
            ladder[key] = {"seed": seed,
                           "v1": xsr.cell(cand[rung], base[rung], tgt, d1),
                           "v2": xsr.cell(cand[rung], base[rung], tgt_v2, d2),
                           "n_distinct_candidate": len(set(cand[rung])),
                           "n_distinct_baseline": len(set(base[rung]))}
    ladder["D0_original_seed"]["identical_to_harness"] = bool(
        ladder["D0_original_seed"]["v1"]["gap_ci"] == h1
        and ladder["D0_original_seed"]["v2"]["gap_ci"] == h2)
    decision = decide(ladder["D4"])

    # ---- disclosures, zero verdict weight ---------------------------------- #
    def _pair_cells(primary, baseline):
        d1 = xsr.iid_gaps_full(primary, {"b": baseline}, tgt, BOOT, SEED)["b"]
        d2 = xsr.cluster_gaps_full(primary, {"b": baseline}, tgt_v2, mids, pys, BOOT, SEED)["b"]
        return {"v1": xsr.cell(primary, baseline, tgt, d1),
                "v2": xsr.cell(primary, baseline, tgt_v2, d2)}

    xpool = {y: xsr.served_xhem_pool(sav_tuple[y]) for y in preds}
    xhem_int = [float(int(round(xsr.served_xhem_unrounded(p["xw"], xpool[p["y"]][0]))))
                for p in pairs]
    p_s2 = {y: bbt.blend_params({m: x for m, x in xw_srv[y].items()
                                 if inp["sav"][y][m]["pa"] >= btl.SAVANT_MIN_PA},
                                inp["hem_core"][y], comp_srv[y]) for y in preds}
    s2 = [float(int(round(bbt.blend_unrounded(p["xw"], p["hem"], comp_srv[p["y"]][p["mid"]],
                                               p_s2[p["y"]])))) for p in pairs]
    per_fold = {}
    for y in preds:
        idx = [i for i, p in enumerate(pairs) if p["y"] == y]
        ft = [tgt[i] for i in idx]
        per_fold[f"{y}->{y + 1}"] = {
            "n": len(idx),
            "rho_bt_blend_served": _r4(plh.spearman([cand["D4"][i] for i in idx], ft)),
            "rho_xhem_blend_served": _r4(plh.spearman([base["D4"][i] for i in idx], ft))}
    disclosures = {
        "note": "zero verdict weight (gate section 7)",
        "d4_vs_raw_xwoba_alone": _pair_cells(cand["D4"], [p["xw"] for p in pairs]),
        "d4_vs_served_xhem_plus_integer": _pair_cells(cand["D4"], xhem_int),
        "per_fold_d4": per_fold,
        "S2_pa200_normalizer_pool_vs_served_xhem_blend": dict(
            _pair_cells(s2, base["D4"]),
            pool_n={str(y): (p_s2[y] or {}).get("n_pool") for y in preds}),
    }
    coverage = {
        "note": ("Coverage is never used to explain a gap. The gate speaks only about "
                 "the PA >= 200 subset while the board would stamp PA >= 100, and "
                 "that sentence travels with the verdict."),
        "by_season": {str(y): {
            "J_pool_btblend": p_bt[y]["n_pool"],
            "fwdhem_served_pool": p_fh[y]["n_pool"],
            "fwdhem_rows_left_blank_by_bt_floor": p_fh[y]["n_pool"] - p_bt[y]["n_pool"],
            "bt_leaderboard_rows_at_floor": len(comp_srv[y]),
            "pair_set_n": sum(1 for p in pairs if p["y"] == y)} for y in preds},
    }
    normalizers = {str(y): {k: (round(v, 6) if isinstance(v, float) else v)
                            for k, v in p_bt[y].items()} for y in preds}

    payload = {
        "generated_at": date.today().isoformat(),
        "experiment": "BT Blend served-construction re-read (arm B of the bat-tracking lane)",
        "gate_document": GATE_DOC,
        "pre_registered": f"{REGISTERED_DATE}, committed alone before any number here",
        "owner_waived_early_read": (
            f"run on {date.today().isoformat()} under the owner's 2026-10-14 waiver of "
            "look days (EW3-5); the 2026 outcome half rests on the season-complete "
            "override (EW3-6), logged below"),
        "season_complete_override": plh.season_complete_override_meta(),
        "seed": SEED, "boot": BOOT, "primary_tests": 1,
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "candidate": ("bat_tracking_blend.served_values: 0.595 z(est_woba) + 0.255 "
                      "z(hem_plus_raw) + 0.15 z(BT composite), legs z over J(Y) "
                      "(Savant PA >= 100, HEM core, BT row at >= 100 competitive "
                      "swings), re-standardized, mapped onto the HEM+ ruler, rounded"),
        "baseline": ("served xHEM+ Blend (hitter_export._join_fwdhem_plus) over its own "
                     "served pool, reconstructed by tools/xhem_served_regate_lab, rounded"),
        "n_pairs": n, "drops": drops,
        "integrity": {"composite_served_minus_eval_max_abs": comp_diff,
                      "hem_core_served_minus_eval_max_abs": hem_diff,
                      "d4_matches_production_module": True},
        "d0_reproduction_check": repro,
        "ladder": ladder,
        "decision": decision,
        "disclosures": disclosures,
        "coverage": coverage,
        "served_normalizers": normalizers,
        "approximation_disclosed_in_advance": (
            "the served normalizer is built at pipeline time from whatever rows exist "
            "then; this re-read builds it on complete season pools"),
        "runtime_seconds": round(time.time() - t0, 1),
    }
    payload["summary"] = summary(payload)
    print(payload["summary"])
    if write:
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(OUT_PATH)
        print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    return payload


def dry_run() -> dict:
    """The reporting path on null fixtures: nothing is read or written."""
    out = {}
    for name, d4 in (("none", None), ("null_cells", {"v1": None, "v2": None}),
                     ("null_ci", {"v1": {"gap_ci": None}, "v2": {"gap_ci": None}}),
                     ("pass", {"v1": {"gap_ci": {"mean": .01, "lo95": .001, "hi95": .02}},
                               "v2": {"gap_ci": {"mean": .01, "lo95": .002, "hi95": .02}}}),
                     ("v1_only", {"v1": {"gap_ci": {"mean": .01, "lo95": .001, "hi95": .02}},
                                  "v2": {"gap_ci": {"mean": .0, "lo95": -.01, "hi95": .01}}}),
                     ("refuted", {"v1": {"gap_ci": {"mean": -.03, "lo95": -.05, "hi95": -.01}},
                                  "v2": {"gap_ci": {"mean": .0, "lo95": -.01, "hi95": .01}}})):
        dec = decide(d4)
        out[name] = {"decision": dec,
                     "summary": summary({"n_pairs": None, "ladder": {"D4": d4 or {}},
                                         "decision": dec})}
    print(json.dumps(out, indent=1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-complete-asof", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        return dry_run()
    if plh.set_season_complete_asof(a.season_complete_asof):
        print(f"season-complete override in force: {plh.season_complete_override_meta()}")
    return run(write=not a.no_write)


if __name__ == "__main__":
    main()
