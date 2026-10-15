# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV against consensus, pooled for power (EFV_BEAT_POOLED_POWER; owner EW3-11 path 2,
2026-10-15; method docs/efv-v2/EFV_BEAT_POOLED_POWER.md, committed alone before this module).

ONE estimand over every development frame: the within (frame, side, year) Spearman of eFV v5
COMBINED minus that of PROSPX consensus, size-weighted over the groups of lv_dev (list
vintages 2017 to 2019) and vm_dev (debut cohorts 2017 to 2023), a player in both frames
keeping his lv_dev rows (section 2.3), with a paired player-clustered bootstrap (B 4000, seed
20261016) and a club-clustered sensitivity. The power (mde95) is reported before the point.
PASS when the one-sided 95 percent lower bound is above 0 under both clusterings.

Two stages, each run once:
    --dev    the development read (the estimand, V2 and v1 beside it, the sensitivities, the
             2026 holdout record quoted for corroboration); writes the artifact.
    --spent  the spent frames R-LV and R-VM read once more, labelled SPENT, corroboration only;
             adds its block to the artifact.

Nothing served moves: no fit, weight, flag or served file is written. The v5 COMBINED folds are
refit in memory as the development fit fitted them, and a parity guard against the fit and
spent artifacts stops the read when they differ.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only groups are frame, side and year.
Consensus enters as a rater. Nothing here groups, counts or averages rows by consensus-FV
level; test_efv_beat_pooled_power.py scans this source.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import efv_v2_stat as S  # noqa: E402
import source_backtest as SB  # noqa: E402

ITEM = "EFV_BEAT_POOLED_POWER"
TOOL = "tools/efv_beat_pooled_power.py"
DOC = "docs/efv-v2/EFV_BEAT_POOLED_POWER.md"
RESULTS_DOC = "docs/efv-v2/EFV_BEAT_POOLED_POWER_RESULTS.md"
OUT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv_beat_pooled_power.json"
FIT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv5_combined_fit.json"
SPENT_FIT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv5_combined_spent.json"
HOLDOUT_PATH = ROOT / "data" / "efv_2026_holdout.json"
#: The registration commit (the document alone, before this module).
REGISTRATION_COMMIT = "4eee1808"
#: The gate sha every spent read opened the reserved frames on.
GATE_SHA = "e7931ce4e13110eebb53555bff455ff13ca7c502"
B = 4000
SEED = 20261016
PARITY_TOL = 1e-4
CLUB_UNKNOWN = "UNK"
CLUSTERINGS = ("player", "club")
SCOPES = ("both", "hit", "pit")
SIDES = ("hit", "pit")
#: rater name -> row score key
V5 = "efv_v5_combined"
V2 = "efv_v2"
V1 = "efv_v1"
CONS = "prospx_consensus"
#: (comparison name, rater a, rater b); the first is the estimand.
COMPARISONS = (("v5c_vs_consensus", V5, CONS),
               ("v2_vs_consensus", V2, CONS),
               ("v1_vs_consensus", V1, CONS),
               ("v5c_vs_v2", V5, V2))
PRIMARY = "v5c_vs_consensus"
#: The de-duplication rules (section 2.3): the registered one first.
DEDUP_RULES = ("keep_lv", "keep_vm", "none")
DEDUP_PRIMARY = "keep_lv"
HOLDOUT_LEG = "war2026|spearman|pooled|efv_v5_combined-consensus"
SPENT_LABEL = "SPENT (read before by v3, v4, v5 and v5 COMBINED; corroboration only)"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------
# the pooled rows
# ---------------------------------------------------------------------------

def frame_kind(fid: str) -> str:
    """lv for a list-vintage frame, vm for a vintage-matched one."""
    return "lv" if fid.startswith("lv") else "vm"


def club_of(rec: dict | None, year: int) -> str:
    """The org on the latest board point dated in [year-01-01, year-05-01), else on the
    latest point dated before that window's end, else UNK (section 5)."""
    lo, hi = f"{int(year)}{SB._WINDOW_START_MMDD}", f"{int(year)}{SB._WINDOW_END_MMDD}"
    inside, before = None, None
    for p in (rec or {}).get("points") or []:
        d = str(p.get("snapshot_date") or "")
        org = str(p.get("org") or "").strip().upper()
        if not d or not org or d >= hi:
            continue
        if d >= lo and (inside is None or d >= inside[0]):
            inside = (d, org)
        if before is None or d >= before[0]:
            before = (d, org)
    got = inside or before
    return got[1] if got else CLUB_UNKNOWN


def pooled_row(fid: str, c: dict, scores: dict, club: str) -> dict:
    side = c["side"]
    year = int(c["year"])
    return {"key": c["key"], "frame": fid, "kind": frame_kind(fid), "side": side, "year": year,
            "pgroup": f"{fid}:{side}|{year}", "club": club, "scores": dict(scores),
            "y": float(c["outcome"]["war"])}


def dedupe(rows: list[dict], rule: str) -> list[dict]:
    """Section 2.3. keep_lv: a player with any lv-frame row loses his vm-frame rows;
    keep_vm: a player with a vm-frame row loses his lv-frame rows; none: every row."""
    if rule not in DEDUP_RULES:
        raise ValueError(f"unknown de-duplication rule {rule!r}")
    if rule == "none":
        return list(rows)
    lv = {r["key"] for r in rows if r["kind"] == "lv"}
    vm = {r["key"] for r in rows if r["kind"] == "vm"}
    both = lv & vm
    drop = "vm" if rule == "keep_lv" else "lv"
    return [r for r in rows if not (r["key"] in both and r["kind"] == drop)]


# ---------------------------------------------------------------------------
# the statistic (efv_v2_stat._within_pair over frame-prefixed groups, every rater at once)
# ---------------------------------------------------------------------------

class Pool:
    """The rows as arrays: scores per rater, outcome, group codes, kept groups."""

    def __init__(self, rows: list[dict], raters):
        self.rows = rows
        self.raters = tuple(raters)
        for r in rows:
            for k in self.raters:
                if r["scores"].get(k) is None:
                    raise ValueError(f"row {r['key']} {r['pgroup']} has no {k} score")
        self.n = len(rows)
        self.y = np.asarray([r["y"] for r in rows], dtype=np.float64)
        self.codes = np.asarray([r["pgroup"] for r in rows])
        self.score = {k: np.asarray([r["scores"][k] for r in rows], dtype=np.float64)
                      for k in self.raters}
        self.keep = S.kept_groups(self.codes)
        self.side_of = {str(u): str(u).split(":", 1)[1].split("|", 1)[0] for u in self.keep}

    def group_rhos(self, idx: np.ndarray) -> list[tuple[str, int, dict]]:
        """[(group, rows, {rater: rho or None})] over the kept groups, on rows idx (with
        repeats), groups with fewer than 3 drawn rows skipped (the DS-15 rule)."""
        gc = self.codes[idx]
        out = []
        for u in self.keep:
            m = idx[gc == u]
            if m.size < 3:
                continue
            yr = SB._ranks_np(np, self.y[m])
            rh = {k: SB._corr_np(np, SB._ranks_np(np, self.score[k][m]), yr)
                  for k in self.raters}
            out.append((str(u), int(m.size), rh))
        return out

    def pair(self, grhos, a: str, b: str, scope: str) -> tuple[float | None, float | None]:
        """W(a), W(b) on the scope's groups: a group counts only when both have a rho."""
        ta = tb = 0.0
        n = 0
        for u, size, rh in grhos:
            if scope != "both" and self.side_of[u] != scope:
                continue
            ra, rb = rh.get(a), rh.get(b)
            if ra is None or rb is None:
                continue
            ta += ra * size
            tb += rb * size
            n += size
        if not n:
            return None, None
        return ta / n, tb / n


def summarize(draws: list[float]) -> dict:
    if len(draws) <= S._MAX_TOO_FEW_DRAWS:
        return {"status": "not derived: too few usable draws", "B_used": len(draws)}
    d = np.asarray(draws, dtype=np.float64)
    sd = float(d.std(ddof=1))
    q = np.quantile(d, [0.025, 0.05, 0.95, 0.975])
    return {"mde95": round(S.Z95 * sd, 4), "sd": round(sd, 5),
            "lb95": round(float(q[1]), 4), "ub95": round(float(q[2]), 4),
            "ci95": [round(float(q[0]), 4), round(float(q[3]), 4)],
            "p_gt_0": round(float((d > 0).mean()), 4), "B_used": int(d.size),
            "status": "derived"}


def read_pool(rows: list[dict], comparisons, *, B_: int = B, seed: int = SEED,
              clusterings=CLUSTERINGS, log=print) -> dict:
    """Every comparison by scope: the point (a, b, delta, n, groups) and, per clustering,
    the paired E_cond interval with the power first."""
    raters = sorted({k for _n, a, b in comparisons for k in (a, b)})
    pool = Pool(rows, raters)
    full = pool.group_rhos(np.arange(pool.n))
    out: dict = {"n": pool.n, "n_players": len({r["key"] for r in rows}),
                 "n_by_side": {s: sum(1 for r in rows if r["side"] == s) for s in SIDES},
                 "n_by_frame": {}, "groups_kept": [str(u) for u in pool.keep],
                 "rows_by_group": {u: size for u, size, _rh in full},
                 "rho_by_group": {u: {k: _rnd(v, 4) for k, v in rh.items()} for u, _s, rh in full},
                 "legs": {}}
    for r in rows:
        out["n_by_frame"][r["frame"]] = out["n_by_frame"].get(r["frame"], 0) + 1
    for name, a, b in comparisons:
        for scope in SCOPES:
            wa, wb = pool.pair(full, a, b, scope)
            n_s = sum(size for u, size, _rh in full if scope == "both" or pool.side_of[u] == scope)
            out["legs"][f"{name}|{scope}"] = {
                "comparison": name, "a": a, "b": b, "scope": scope, "n": n_s,
                "w_a": _rnd(wa), "w_b": _rnd(wb),
                "delta": None if (wa is None or wb is None) else _rnd(wa - wb)}
    for cl in clusterings:
        keys = [r["key"] if cl == "player" else r["club"] for r in rows]
        ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
        order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
        rng = np.random.default_rng(int(seed))
        diffs: dict = {leg: [] for leg in out["legs"]}
        t0 = time.time()
        for _ in range(int(B_)):
            idx = SB._cluster_draw(np, rng, order, starts, lens)
            if idx.size < 8:
                continue
            g = pool.group_rhos(idx)
            for leg, spec in out["legs"].items():
                if spec["delta"] is None:
                    continue
                xa, xb = pool.pair(g, spec["a"], spec["b"], spec["scope"])
                if xa is not None and xb is not None:
                    diffs[leg].append(xa - xb)
        for leg, d in diffs.items():
            blk = summarize(d)
            blk.update(B=int(B_), seed=int(seed), n_clusters=len(ids))
            out["legs"][leg][cl] = blk
        log(f"    {cl}-clustered: {B_} draws over {pool.n} rows, {len(ids)} clusters "
            f"({round(time.time() - t0, 1)} s)")
    return out


def verdict(leg: dict) -> dict:
    """Section 6: PASS when lb95 > 0 under both clusterings; else trails (player ub95 < 0)
    or ties."""
    p = leg.get("player") or {}
    c = leg.get("club") or {}
    lp, lc = p.get("lb95"), c.get("lb95")
    passed = bool(lp is not None and lc is not None and lp > 0 and lc > 0)
    if passed:
        word = "beats"
    elif p.get("ub95") is not None and p["ub95"] < 0:
        word = "trails"
    else:
        word = "ties"
    return {"pass": passed, "verdict": "PASS" if passed else "FAIL", "word": word,
            "delta": leg.get("delta"), "lb95_player": lp, "lb95_club": lc,
            "mde95_player": p.get("mde95"), "mde95_club": c.get("mde95"),
            "ci95_player": p.get("ci95"), "ci95_club": c.get("ci95")}


# ---------------------------------------------------------------------------
# building the frames (the v5 COMBINED folds in memory; v1 from DS-16)
# ---------------------------------------------------------------------------

def _universe() -> dict:
    import efv_v2_model as H
    return {p.get("player_key"): p for p in SB._load_universe(H.DATA_DIR)}


def _check_parity(fid: str, rows5: list[dict], art: dict, BT) -> dict:
    blk = (art.get("frames") or {}).get(fid) or {}
    got = {"v5c_vs_prospx_consensus": BT.within_delta_point(rows5, BT.V3_KEY, BT.CONS),
           "v5c_vs_efv_v2": BT.within_delta_point(rows5, BT.V3_KEY, BT.V2_KEY)}
    rec = {}
    for name, v in got.items():
        want = (((blk.get("deltas") or {}).get(name) or {}).get("spearman") or {}).get("delta")
        ok = want is not None and v is not None and abs(float(v) - float(want)) <= PARITY_TOL
        rec[name] = {"artifact": want, "recomputed": _rnd(v), "ok": ok}
        if not ok:
            raise RuntimeError(f"parity guard: {fid} {name} recomputed {v} against the "
                               f"artifact's {want}; nothing read")
    rec["n"] = {"artifact": blk.get("n"), "recomputed": len(rows5)}
    if blk.get("n") != len(rows5):
        raise RuntimeError(f"parity guard: {fid} rows {len(rows5)} against {blk.get('n')}")
    return rec


def v5c_rows(stage: str, *, log=print) -> tuple[dict, dict]:
    """{fid: v5 COMBINED frame rows} (efv5_combined's rows_with, the order under BT.V3_KEY)
    and the parity receipts."""
    import efv5_combined as E5
    import efv5_group_drivers as G
    BT, _B4 = E5._tools()
    with G.registered(), E5.v5c_names():
        if stage == "dev":
            inp, _f, _r = E5.build_dev(log=log)
            fids, art_path = BT.FRAMES_DEV, FIT_PATH
        else:
            inp, _g, _r = E5.build_spent(gate_sha=GATE_SHA, log=log)
            fids, art_path = BT.FRAMES_RES, SPENT_FIT_PATH
        art = json.loads(Path(art_path).read_text(encoding="utf-8"))
        fits = E5.Fits(inp)
        out, parity = {}, {}
        for fid in fids:
            orders, _rec = fits.orders(fid)
            rows = inp.rows_with(fid, orders)
            parity[fid] = _check_parity(fid, rows, art, BT)
            log(f"  {fid}: {len(rows)} rows; parity with {Path(art_path).name} holds")
            out[fid] = rows
    return out, parity


def v1_rows(*, log=print) -> dict:
    """{(group, player_key): DS-16 row} on lv_dev and vm_dev."""
    import efv_v2_dev_read as DR
    import efv_v2_model as H
    weights = H.load_weights()
    vm, _m = DR.v2_vm_dev(H.DATA_DIR, weights)
    lv, _m2 = DR.v2_lv_dev(weights)
    log(f"  DS-16 rows: lv_dev {len(lv)}, vm_dev {len(vm)}")
    return {"lv_dev": {(c["group"], c["key"]): c for c in lv},
            "vm_dev": {(c["group"], c["key"]): c for c in vm}}


def assemble(frames5: dict, v1: dict | None, universe: dict) -> tuple[list[dict], dict]:
    """The pooled rows of every frame with every rater's score, the v1 join checked."""
    import efv_v3_backtest as BT
    rows, rec = [], {}
    for fid, rows5 in frames5.items():
        j = {"rows": len(rows5), "joined": 0, "v2_differs": 0, "cons_differs": 0,
             "outcome_differs": 0, "missing": 0}
        for c in rows5:
            sc = {V5: float(c["grades"][BT.V3_KEY]), V2: float(c["grades"][BT.V2_KEY]),
                  CONS: float(c["grades"][BT.CONS])}
            if v1 is not None:
                d = (v1.get(fid) or {}).get((c["group"], c["key"]))
                if d is None:
                    j["missing"] += 1
                    continue
                if abs(float(d["grades"]["efv_v2"]) - sc[V2]) > 1e-9:
                    j["v2_differs"] += 1
                if abs(float(d["grades"][BT.CONS]) - sc[CONS]) > 1e-9:
                    j["cons_differs"] += 1
                if abs(float(d["outcome"]["war"]) - float(c["outcome"]["war"])) > 1e-9:
                    j["outcome_differs"] += 1
                sc[V1] = float(d["grades"]["xfv"])
                j["joined"] += 1
            rows.append(pooled_row(fid, c, sc, club_of(universe.get(c["key"]), c["year"])))
        if v1 is not None and (j["missing"] or j["v2_differs"] or j["cons_differs"]
                               or j["outcome_differs"]):
            raise RuntimeError(f"v1 join guard: {fid} {j}; nothing read")
        rec[fid] = j
    return rows, rec


def holdout_record() -> dict:
    d = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    leg = (((d.get("frames") or {}).get("list") or {}).get("legs") or {}).get(HOLDOUT_LEG) or {}
    return {"artifact": "data/efv_2026_holdout.json", "leg": HOLDOUT_LEG,
            "role": "corroboration only (EW3-13; the 2026 frame is spent)",
            "verdict": d.get("verdict"), "pass": d.get("pass"),
            "delta": leg.get("delta"), "n": leg.get("n"),
            "lb95_player": (leg.get("player") or {}).get("lb95"),
            "lb95_club": (leg.get("club") or {}).get("lb95"),
            "ci95_player": (leg.get("player") or {}).get("ci95"),
            "generated_at": d.get("generated_at")}


def club_receipt(rows: list[dict]) -> dict:
    clubs: dict = {}
    for r in rows:
        clubs[r["club"]] = clubs.get(r["club"], 0) + 1
    return {"n_clubs": len(clubs), "rows_unknown": clubs.get(CLUB_UNKNOWN, 0)}


# ---------------------------------------------------------------------------
# the stages
# ---------------------------------------------------------------------------

def _code() -> dict:
    return {"commit": _git("rev-parse", "--short=8", "HEAD"),
            "registration_commit": REGISTRATION_COMMIT, "tool": TOOL}


def run_dev(*, log=print) -> dict:
    t0 = time.time()
    log("development frames: v5 COMBINED folds in memory")
    frames5, parity = v5c_rows("dev", log=log)
    log("development frames: v1 from DS-16")
    v1 = v1_rows(log=log)
    universe = _universe()
    rows_all, join = assemble(frames5, v1, universe)
    variants = {}
    for rule in DEDUP_RULES:
        rows = dedupe(rows_all, rule)
        log(f"  pooled ({rule}): {len(rows)} rows")
        comps = COMPARISONS if rule == DEDUP_PRIMARY else COMPARISONS[:1]
        variants[rule] = read_pool(rows, comps, log=log)
        variants[rule]["clubs"] = club_receipt(rows)
    per_frame = {}
    prim_rows = dedupe(rows_all, DEDUP_PRIMARY)
    for fid in frames5:
        sel = [r for r in prim_rows if r["frame"] == fid]
        per_frame[fid] = read_pool(sel, COMPARISONS[:1], clusterings=("player",), log=log)
    prim = variants[DEDUP_PRIMARY]["legs"][f"{PRIMARY}|both"]
    v = verdict(prim)
    lv_keys = {r["key"] for r in rows_all if r["kind"] == "lv"}
    vm_keys = {r["key"] for r in rows_all if r["kind"] == "vm"}
    doc = {
        "schema": 1, "item": ITEM, "produced_by": TOOL, "registration": DOC,
        "generated_at": _now(), "code": _code(),
        "owner_decision": "EW3-11 (2026-10-15), path 2: pooled power",
        "role": "development (the v5 COMBINED penalty was chosen on these frames out of fold)",
        "label": _label(),
        "statistic": ("within (frame, side, year) Spearman, size-weighted over groups of at "
                      f"least {S.MIN_GROUP_ROWS} rows; rater minus PROSPX consensus"),
        "estimand": f"{PRIMARY}|both on the {DEDUP_PRIMARY} pool of lv_dev and vm_dev",
        "bootstrap": {"B": B, "seed": SEED, "estimator": "E_cond, paired",
                      "clusterings": list(CLUSTERINGS),
                      "intervals": "percentile; lb95/ub95 one-sided 95 percent, ci95 two-sided; "
                                   "mde95 = 1.645 x sd"},
        "pass_rule": ("v5 COMBINED minus PROSPX consensus pooled over sides: one-sided 95 "
                      "percent lower bound above 0 under both clusterings"),
        "power_first": {"mde95_player": v["mde95_player"], "mde95_club": v["mde95_club"]},
        "verdict": v,
        "dedup": {"rule": DEDUP_PRIMARY, "players_in_both": len(lv_keys & vm_keys),
                  "rows_before": len(rows_all), "rows_after": len(prim_rows),
                  "vm_rows_dropped": sum(1 for r in rows_all if r["kind"] == "vm"
                                         and r["key"] in lv_keys)},
        "parity": parity, "v1_join": join,
        "pooled": variants[DEDUP_PRIMARY],
        "sensitivities": {k: variants[k] for k in DEDUP_RULES if k != DEDUP_PRIMARY},
        "per_frame": per_frame,
        "timing_edge": ("not pooled: no EFV_BEAT_TIMING_EDGE registration exists at HEAD "
                        "(registration section 2.2)"),
        "holdout_2026": holdout_record(),
        "spent": None,
        "elapsed_s": round(time.time() - t0, 1)}
    return doc


def run_spent(doc: dict, *, log=print) -> dict:
    t0 = time.time()
    log("spent frames (read once, SPENT): v5 COMBINED folds in memory")
    frames5, parity = v5c_rows("spent", log=log)
    universe = _universe()
    rows_all, _join = assemble(frames5, None, universe)
    rows = dedupe(rows_all, DEDUP_PRIMARY)
    comps = (COMPARISONS[0], COMPARISONS[1], COMPARISONS[3])
    blk = read_pool(rows, comps, log=log)
    blk["clubs"] = club_receipt(rows)
    lv_keys = {r["key"] for r in rows_all if r["kind"] == "lv"}
    vm_keys = {r["key"] for r in rows_all if r["kind"] == "vm"}
    per_frame = {fid: read_pool([r for r in rows if r["frame"] == fid], comps[:1],
                                clusterings=("player",), log=log) for fid in frames5}
    leg = blk["legs"][f"{PRIMARY}|both"]
    return {"label": SPENT_LABEL, "frames": sorted(frames5), "gate_sha": GATE_SHA,
            "generated_at": _now(), "code": _code(), "parity": parity,
            "dedup": {"rule": DEDUP_PRIMARY, "players_in_both": len(lv_keys & vm_keys),
                      "rows_before": len(rows_all), "rows_after": len(rows)},
            "pooled": blk, "per_frame": per_frame, "reading": verdict(leg),
            "v1": "not built on the spent frames by this pipeline (registration section 7)",
            "elapsed_s": round(time.time() - t0, 1)}


def _label() -> dict:
    import efv_labels as L
    return {"provider": L.provider()}


def write(doc: dict) -> Path:
    import efv_v3_backtest as BT
    return BT.write_doc(doc, OUT_PATH)


def summary_lines(doc: dict) -> list[str]:
    out = []
    v = doc["verdict"]
    out.append(f"POWER FIRST: mde95 player {v['mde95_player']}, club {v['mde95_club']}")
    for leg, spec in doc["pooled"]["legs"].items():
        p = spec.get("player") or {}
        c = spec.get("club") or {}
        out.append(f"{leg}: n {spec['n']} delta {spec['delta']} lb95 {p.get('lb95')} / "
                   f"{c.get('lb95')} ci95 {p.get('ci95')} mde95 {p.get('mde95')}")
    out.append(f"VERDICT: {v['verdict']} ({v['word']})")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--spent", action="store_true")
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    import efv_labels as L
    if L.provider() != "fwar":
        log(f"refused: label provider is {L.provider()!r}, not the frozen 'fwar'")
        return 2
    if _git("cat-file", "-e", REGISTRATION_COMMIT) is None:
        log("refused: the registration commit is not in this repository")
        return 2
    if a.dev:
        if OUT_PATH.exists():
            log(f"refused: {OUT_PATH} exists; the development read ran once")
            return 2
        doc = run_dev(log=log)
        write(doc)
        for line in summary_lines(doc):
            log(line)
        return 0
    if a.spent:
        if not OUT_PATH.exists():
            log("refused: the development read comes first")
            return 2
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if doc.get("spent") is not None:
            log("refused: the spent frames were read once by this tool")
            return 2
        doc["spent"] = run_spent(doc, log=log)
        write(doc)
        sp = doc["spent"]["pooled"]["legs"]
        for leg, spec in sp.items():
            p = spec.get("player") or {}
            log(f"SPENT {leg}: n {spec['n']} delta {spec['delta']} lb95 {p.get('lb95')} "
                f"ci95 {p.get('ci95')} mde95 {p.get('mde95')}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
