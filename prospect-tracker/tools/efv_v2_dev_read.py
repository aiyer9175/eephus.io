# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The ONE development read of eFV v2 champion H0 (EV-09, docs/efv-v2/PROGRAM.md s3.4).

H0 (efv_v2_model) against eFV v1 and PROSPX consensus, with MLB Pipeline and FanGraphs
beside them, on the two DEVELOPMENT frames and nothing else:

    vm_dev   the vintage-matched frame F-VM at frame version vm2 (every input pinned to
             the raters' preseason read of the debut year), window from
             source_backtest._resolved_years (2017 to 2023 today). Rows are rebuilt
             exactly as source_backtest.run_source_backtest builds them, in the same
             order, and both eFV legs are carried onto the consensus grade grid by the
             same rank remap, so the v1 leg reproduces the served vm2 numbers (receipt
             under frames.vm_dev.parity). Outcome: career WAR to date; contributor at
             source_backtest.CONTRIBUTOR_WAR.
    lv_dev   the list-vintage frame F-LV on development vintages 2011 to 2019
             (efv_vintage_frame.DEV_VINTAGES) with the W3 label (efv_labels). H0 and v1
             are both fitted per vintage on matrix rows with decision year before V,
             every frame player excluded from training. Contributor on W3 is the
             development convention w_star_dev: the W3 value whose exceedance share
             equals the six-season contributor share on vintages 2011 to 2016 (label
             distributions only, no grader read; EV-05 re-derives it on the frozen label).

Every delta is E_cond: the forward-chained scores are fixed and only players are
resampled, player-clustered, through source_backtest._paired_delta_ci (same resampler,
B and seed as the claim instruments). Development rows adjudicate NOTHING: both frames
are spent (PROGRAM.md s3.1), the label is eWAR v2, not the frozen fWAR label, and no row
here is a claim. The rows land in data/efv_progress.json as role "development".

NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025 and later debut cohorts
(R-VM). The guards run before any score is computed; a violation raises.

Run once:  python tools/efv_v2_dev_read.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_labels as L  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

H0_KEY = "efv_v2_h0"
V1_KEY = "xfv"
CONS = SB.CONSENSUS_KEY
RATERS_OUT = ((H0_KEY, "efv_v2_h0"), (V1_KEY, "efv_v1"), (CONS, "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
#: (name, a, b): every delta the read reports, a minus b.
COMPARISONS = (("h0_vs_prospx_consensus", H0_KEY, CONS),
               ("h0_vs_efv_v1", H0_KEY, V1_KEY),
               ("efv_v1_vs_prospx_consensus", V1_KEY, CONS),
               ("h0_vs_mlb_pipeline", H0_KEY, "mlb_pipeline"),
               ("h0_vs_fangraphs", H0_KEY, "fangraphs"))
W_STAR_VINTAGES = tuple(range(2011, 2017))


def _guards() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    bad = sorted(set(F.DEV_VINTAGES) & set(F.RESERVED_LV))
    if bad:
        raise F.ReservedFrameError(f"DEV_VINTAGES overlaps RESERVED_LV: {bad}")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins}


def _remap(raw: list[float], cons: list[float]) -> list[float]:
    """source_backtest's rank remap onto the consensus grade grid (vm1 and vm2)."""
    m = len(raw)
    order = sorted(range(m), key=lambda i: raw[i])
    cons_sorted = sorted(cons)
    out = [0.0] * m
    for rank_pos, i in enumerate(order):
        pp = rank_pos / (m - 1) if m > 1 else 0.0
        out[i] = round(cons_sorted[min(m - 1, int(round(pp * (m - 1))))], 1)
    return out


def _rater_stats(rows: list[dict]) -> dict:
    out = {}
    for key, name in RATERS_OUT:
        rr = [c for c in rows if c["grades"].get(key) is not None]
        if not rr:
            continue
        g = [c["grades"][key] for c in rr]
        sp = SB._spearman(g, [c["outcome"]["war"] for c in rr])
        au = SB._auc(g, [bool(c["outcome"]["contributor"]) for c in rr])
        out[name] = {"n": len(rr), "spearman": None if sp is None else round(sp, 4),
                     "auc": None if au is None else round(au, 4)}
    return out


def _reading(ci) -> str:
    if not (isinstance(ci, list) and len(ci) == 2):
        return "development only; no interval"
    if ci[0] > 0:
        return "development only; CI95 above zero"
    if ci[1] < 0:
        return "development only; CI95 below zero"
    return "development only; CI95 spans zero"


def _deltas(rows: list[dict], seed: int, B: int) -> dict:
    out = {}
    for name, a, b in COMPARISONS:
        legs = {}
        for metric in ("spearman", "auc"):
            f = SB._paired_delta_ci(rows, a, b, metric, label=f"{name}.{metric}",
                                    B=B, seed=seed)
            legs[metric] = {"delta": f.get("point_delta"), "ci95": f.get("ci95"),
                            "mde95": f.get("mde95"), "estimator": "E_cond",
                            "ci95_estimator": "E_cond, player-clustered",
                            "n": f.get("n"), "n_clusters": f.get("n_clusters"),
                            "B": f.get("B"), "B_used": f.get("B_used"),
                            "seed": f.get("seed"), "p_gt_0": f.get("p_gt_0"),
                            "status": f.get("status", "derived"),
                            "reading": _reading(f.get("ci95"))}
        out[name] = legs
    return out


def _n_by_side(rows: list[dict], side_of: dict) -> dict:
    out = {}
    for c in rows:
        s = side_of.get(c["key"])
        if s in ("hit", "pit"):
            out[s] = out.get(s, 0) + 1
    return out


def _fold_receipts(models: dict[str, dict[int, dict]], data: dict[str, list[dict]]
                   ) -> list[dict]:
    out = []
    for side, ms in models.items():
        for yr, m in sorted(ms.items()):
            sel = m["selection"]
            fvs = [r["fv"] for r in data[side] if r["decision_year"] == yr]
            out.append({"side": side, "year": yr, "n_train": m["n_train"],
                        "n_reached": m["n_reached"],
                        "alpha_r": H._akey(sel["alpha_r"]),
                        "alpha_w": H._akey(sel["alpha_w"]),
                        "inner_years_r": sel["inner_years_r"],
                        "inner_years_w": sel["inner_years_w"],
                        "offset": m["offset"],
                        "offset_monotone_on_scored_range": H.offset_curve_is_monotone(
                            m, min(fvs), max(fvs))})
    return out


# ---------------------------------------------------------------------------
# vm_dev: the vintage-matched frame, frame version vm2
# ---------------------------------------------------------------------------

def vm_dev(data_dir: Path) -> tuple[list[dict], dict]:
    universe = SB._load_universe(data_dir)
    years = SB._resolved_years(universe, date.today().year)
    if any(y >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm window reaches R-VM: {years}")
    raters = list(SB.SCORED_SOURCES) + [CONS]
    common_by_year = {y: [] for y in years}
    for p in universe:
        out = SB._outcome(p)
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if g and all(r in g for r in raters):
                common_by_year[y].append({"key": p.get("player_key"), "year": y,
                                          "grades": {r: g[r] for r in raters},
                                          "outcome": out})
    data = {s: H.training_rows(s) for s in ("hit", "pit")}
    models = {s: H.fold_models(s, data=data[s]) for s in ("hit", "pit")}
    v1 = {**V1.oos_grades("hit"), **V1.oos_grades("pit")}
    v1_rec: dict = {}
    v1_pin = {}
    for s in ("hit", "pit"):
        v1_pin.update(V1.oos_grades(s, timing_pin=True, receipts=v1_rec))
    h0, h0_pin, h0_rec, off_pin = {}, {}, {}, {}
    for s in ("hit", "pit"):
        h0.update(H.oos_scores(s, data=data[s], models=models[s]))
        h0_pin.update(H.oos_scores(s, timing_pin=True, receipts=h0_rec, data=data[s],
                                   models=models[s]))
        off_pin.update(H.oos_scores(s, timing_pin=True, heads=False, data=data[s],
                                    models=models[s]))
    side_of: dict = {}
    for s in ("hit", "pit"):
        for r in data[s]:
            side_of.setdefault(r["player_key"], s)
    rows_x = [c for y in years for c in common_by_year[y] if c["key"] in v1]
    missing_h0 = sum(1 for c in rows_x if c["key"] not in h0)
    cons_x = [c["grades"][CONS] for c in rows_x]
    g_v1 = _remap([v1_pin.get(c["key"], v1[c["key"]]) for c in rows_x], cons_x)
    g_h0 = _remap([h0_pin.get(c["key"], h0.get(c["key"], float("-inf"))) for c in rows_x],
                  cons_x)
    frame, raw_h0, raw_off, pin_fv = [], [], [], []
    for i, c in enumerate(rows_x):
        dy = (c["outcome"] or {}).get("debut_year")
        if dy is None or c["year"] != dy:
            continue
        rec = v1_rec.get(c["key"]) if c["key"] in v1_pin else None
        if not rec or rec.get("window_year") != c["year"]:
            continue
        lo, hi = f"{c['year']}{SB._WINDOW_START_MMDD}", f"{c['year']}{SB._WINDOW_END_MMDD}"
        if not (lo <= (rec.get("asof_date") or "") < hi):
            continue
        if c["key"] not in h0_pin:
            continue
        if dy >= F.R_VM_FIRST_DEBUT_YEAR:
            raise F.ReservedFrameError(f"vm row in R-VM: {c['key']} {dy}")
        row = dict(c)
        row["grades"] = dict(c["grades"], **{V1_KEY: g_v1[i], H0_KEY: g_h0[i]})
        frame.append(row)
        raw_h0.append(h0_pin[c["key"]])
        raw_off.append(off_pin[c["key"]])
        pin_fv.append(h0_rec[c["key"]]["consensus_fv_raw"])
    # liveness: within one fitted model (one side, one fold year) the offset-only
    # score orders the rows exactly as its consensus input does. Across models the
    # maps differ by construction, so the pooled order is not the consensus order.
    groups: dict = {}
    for i, c in enumerate(frame):
        groups.setdefault((side_of.get(c["key"]), c["year"]), []).append(i)
    inversions = split_ties = 0
    for idx in groups.values():
        order = sorted(idx, key=lambda i: (raw_off[i], pin_fv[i]))
        inversions += sum(1 for a, b in zip(order, order[1:]) if pin_fv[b] < pin_fv[a])
        split_ties += sum(1 for a, b in zip(order, order[1:])
                          if pin_fv[b] == pin_fv[a] and raw_off[b] != raw_off[a])
    live = {"n": len(frame), "n_models": len(groups),
            "unit": "one fitted model: one side, one fold year",
            "order_inversions": inversions, "equal_input_split": split_ties,
            "offset_only_reproduces_consensus_order": inversions == 0 and split_ties == 0,
            "pooled_spearman_offset_only_vs_input": round(SB._spearman(raw_off, pin_fv), 6),
            "raw_h0_spearman": round(SB._spearman(raw_h0, [c["outcome"]["war"]
                                                           for c in frame]), 4)}
    meta = {"window": [min(years), max(years)], "years": years, "side_of": side_of,
            "models": models, "data": data, "liveness": live,
            "coverage": {"population_rows": len(rows_x), "population_without_h0": missing_h0,
                         "v1_pinned_scores": len(v1_pin), "h0_pinned_scores": len(h0_pin),
                         "fold_years": {s: {"efv_v1": sorted({r["decision_year"]
                                                              for r in data[s]
                                                              if r["player_key"] in v1}),
                                            "efv_v2_h0": sorted(models[s])}
                                        for s in ("hit", "pit")},
                         "fold_note": ("H0 skips a fold whose training rows hold fewer "
                                       "than two reached or two never-reached rows (no "
                                       "REACHED map can be fitted); v1 scores it")}}
    return frame, meta


# ---------------------------------------------------------------------------
# lv_dev: the list-vintage frame on development vintages
# ---------------------------------------------------------------------------

def w_star_dev(label_rows: list[tuple[int, dict]]) -> dict:
    """The W3 contributor threshold on labels alone (no grade read)."""
    use = [lab for v, lab in label_rows if v in W_STAR_VINTAGES
           and lab.get("w3") is not None and lab.get("l6") is not None]
    n = len(use)
    k = sum(1 for lab in use if lab["l6"] >= V1._CONTRIB_WAR)
    if not n or not k:
        return {"w_star": None, "n": n, "six_season_contributor_share": None}
    share = k / n
    w_desc = sorted((lab["w3"] for lab in use), reverse=True)
    w = w_desc[k - 1]
    return {"w_star": w, "n": n, "n_six_season_contributors": k,
            "six_season_contributor_share": round(share, 4),
            "w3_exceedance_share_at_w_star": round(
                sum(1 for x in w_desc if x >= w) / n, 4),
            "vintages": list(W_STAR_VINTAGES),
            "six_season_threshold": V1._CONTRIB_WAR,
            "convention": ("the k-th largest W3 on the rows, k = the number of "
                           "six-season contributors; development convention on the "
                           "eWAR v2 label, re-derived by EV-05 on the frozen label")}


def lv_dev() -> tuple[list[dict], dict]:
    for v in F.DEV_VINTAGES:
        F.guard_score_request(v, purpose="development read")
    universe = F.load_universe()
    war = L.war_seasons_table()
    data = {s: H.training_rows(s) for s in ("hit", "pit")}
    frames, labels_all, per = [], [], []
    for side in ("hit", "pit"):
        for V in F.DEV_VINTAGES:
            if V in F.RESERVED_LV:
                raise F.ReservedFrameError(f"lv vintage {V} is reserved")
            rows = F.build_frame(side, V, universe=universe)
            labs = L.labels_for_frame(rows, universe=universe, war=war)
            labels_all += [(V, lab) for lab in labs]
            sc = H.lv_scores(side, V, rows, data=data[side])
            rec = {"side": side, "vintage": V, "status": sc["status"],
                   "frame_rows": len(rows), "n_train": sc["n_train"],
                   "n_train_excluded_in_frame": sc["n_train_excluded_in_frame"]}
            if sc["status"] == "ok":
                m = sc["model"]
                rec.update(alpha_r=H._akey(m["selection"]["alpha_r"]),
                           alpha_w=H._akey(m["selection"]["alpha_w"]),
                           offset=m["offset"],
                           offset_monotone_on_frame=sc["offset_monotone_on_frame"])
                n_scored = 0
                for r, lab in zip(rows, labs):
                    k = r["player_key"]
                    g = r["grades"]
                    if (g.get(CONS) is None or lab.get("w3") is None
                            or k not in sc["h0"]):
                        continue
                    grades = {CONS: g[CONS], H0_KEY: sc["h0"][k], V1_KEY: sc["v1"][k]}
                    for src in SB.SCORED_SOURCES:
                        if g.get(src) is not None:
                            grades[src] = g[src]
                    frames.append({"key": k, "vintage": V, "side": side,
                                   "grades": grades, "w3": lab["w3"]})
                    n_scored += 1
                rec["n_scored"] = n_scored
            per.append(rec)
    ws = w_star_dev(labels_all)
    for c in frames:
        c["outcome"] = {"war": c["w3"], "contributor": (ws["w_star"] is not None
                                                         and c["w3"] >= ws["w_star"])}
    return frames, {"per_vintage": per, "w_star_dev": ws,
                    "vintages_scored": sorted({c["vintage"] for c in frames})}


# ---------------------------------------------------------------------------
# the artifact
# ---------------------------------------------------------------------------

def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _label_id() -> str | None:
    """The eWAR label identity the board fingerprint carries (label=...)."""
    try:
        import storage
        fp = storage.board_basis_fingerprint()
    except Exception:                                         # noqa: BLE001
        return None
    for part in (fp or "").split("|"):
        if part.startswith("label="):
            return part[len("label="):]
    return None


def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _parity(sb_path: Path, stats: dict, n: int, deltas: dict) -> dict:
    try:
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "source_backtest.json unreadable"}
    acc = sb.get("accuracy") or {}
    served = acc.get(SB.VM2_BASIS) or {}
    hv2 = acc.get("head_to_head_verdict_vm2") or {}
    x = (served.get("xfv") or {})
    c = (served.get(CONS) or {})
    mine = deltas["efv_v1_vs_prospx_consensus"]["spearman"]
    return {"artifact": "data/source_backtest.json", "generated_at": sb.get("generated_at"),
            "key": f"accuracy.{SB.VM2_BASIS}",
            "served_n": x.get("n"), "read_n": n,
            "served_efv_v1_spearman": x.get("spearman"),
            "read_efv_v1_spearman": stats.get("efv_v1", {}).get("spearman"),
            "served_consensus_spearman": c.get("spearman"),
            "read_consensus_spearman": stats.get("prospx_consensus", {}).get("spearman"),
            "served_efv_v1_auc": x.get("auc"),
            "read_efv_v1_auc": stats.get("efv_v1", {}).get("auc"),
            "served_ci95_v1_vs_consensus": hv2.get("ci95"),
            "read_ci95_v1_vs_consensus": mine.get("ci95"),
            "reproduces": (x.get("n") == n
                           and x.get("spearman") == stats.get("efv_v1", {}).get("spearman")
                           and c.get("spearman") == stats.get("prospx_consensus", {}).get("spearman")
                           and hv2.get("ci95") == mine.get("ci95"))}


def run(data_dir: Path | None = None, *, seed: int = H.SEED, B: int | None = None,
        write: bool = True) -> dict:
    t0 = time.time()
    data_dir = Path(data_dir) if data_dir is not None else H.DATA_DIR
    B = SB._CLAIM_BOOT_B if B is None else int(B)
    guards = _guards()
    vm_rows, vm_meta = vm_dev(data_dir)
    vm_stats = _rater_stats(vm_rows)
    vm_d = _deltas(vm_rows, seed, B)
    lv_rows, lv_meta = lv_dev()
    lv_stats = _rater_stats(lv_rows)
    lv_d = _deltas(lv_rows, seed, B)
    guards["lv_vintages_read"] = lv_meta["vintages_scored"]
    guards["vm_years_read"] = vm_meta["years"]
    lv_by_side: dict = {}
    for c in lv_rows:
        lv_by_side[c["side"]] = lv_by_side.get(c["side"], 0) + 1
    doc = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_id": H.MODEL_ID,
        "role": "development",
        "adjudicates": False,
        "note": ("development frames, spent, not a claim: H0 is adjudicated only on the "
                 "reserved frames after docs/efv-v2/EFV_V2_GATE.md commits"),
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                  "id": _label_id()},
        "code": {"commit": _commit(), "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py"),
                 "tool": "tools/efv_v2_dev_read.py"},
        "spec": {"heads": {s: H.head_keys(s) for s in ("hit", "pit")},
                 "alphas": [H._akey(a) for a in H.ALPHAS],
                 "fold_gates": {"min_test_rows": H.MIN_TEST_ROWS,
                                "min_train_rows": H.MIN_TRAIN_ROWS},
                 "training_target": "target_censored (six-season, v1 censoring rule)",
                 "reached": "matrix kind: debuted 1, never-MLB bust 0; recent busts excluded",
                 "clip": "none",
                 "bootstrap": {"B": B, "seed": seed, "estimator": "E_cond",
                               "unit": "player cluster"}},
        "reserved_guard": guards,
        "frames": {
            "vm_dev": {"frame_version": "vm2", "window": vm_meta["window"],
                       "n": len(vm_rows), "n_by_side": _n_by_side(vm_rows, vm_meta["side_of"]),
                       "outcome": "career WAR to date",
                       "contributor": f"career WAR >= {SB.CONTRIBUTOR_WAR}",
                       "raters": vm_stats, "deltas": vm_d,
                       "verdict": vm_d["h0_vs_prospx_consensus"]["spearman"]["reading"],
                       "liveness": vm_meta["liveness"], "coverage": vm_meta["coverage"],
                       "parity": _parity(data_dir / "source_backtest.json", vm_stats,
                                         len(vm_rows), vm_d),
                       "folds": _fold_receipts(vm_meta["models"], vm_meta["data"])},
            "lv_dev": {"frame_version": "lv1", "window": [min(lv_meta["vintages_scored"]),
                                                          max(lv_meta["vintages_scored"])],
                       "vintages_requested": list(F.DEV_VINTAGES),
                       "vintages_scored": lv_meta["vintages_scored"],
                       "n": len(lv_rows), "n_by_side": lv_by_side,
                       "n_players": len({c["key"] for c in lv_rows}),
                       "outcome": "W3 (WAR over the first three MLB seasons, 0 if no debut "
                                  "within three seasons of V)",
                       "contributor": "W3 >= w_star_dev",
                       "w_star_dev": lv_meta["w_star_dev"],
                       "raters": lv_stats, "deltas": lv_d,
                       "verdict": lv_d["h0_vs_prospx_consensus"]["spearman"]["reading"],
                       "per_vintage": lv_meta["per_vintage"]},
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    if write:
        out = H.DEV_EVAL_PATH
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(out)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-ledger", action="store_true",
                    help="write the artifact but do not update data/efv_progress.json")
    a = ap.parse_args(argv)
    doc = run()
    for fid in ("vm_dev", "lv_dev"):
        f = doc["frames"][fid]
        d = f["deltas"]["h0_vs_prospx_consensus"]["spearman"]
        print(f"{fid}: n {f['n']}, H0 {f['raters']['efv_v2_h0']['spearman']}, "
              f"v1 {f['raters']['efv_v1']['spearman']}, "
              f"consensus {f['raters']['prospx_consensus']['spearman']}, "
              f"H0 - consensus {d['delta']} CI {d['ci95']} ({d['reading']})")
    if not a.no_ledger:
        import efv_progress
        print(efv_progress.summary_line(efv_progress.update(trigger="efv_change")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
