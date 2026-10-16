# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The stale-vote rule inside PROSPX consensus (BA_KEEP_FORWARD_READ Part C; owner EW3-39,
2026-10-16), read once on the development frames. The rule is fixed in
docs/efv-v2/BA_KEEP_FORWARD_READ.md (committed alone before this file existed).

    --check   build the frames, find and capture every row's as-of point, run the parity
              checks Q1 and Q2, count the touched rows, and stop. No outcome is read.
    --run     the registered read, once: arms S, D, W, D1, the nulls ND and NW, the planted
              check PLD, the board effect, written to
              data/_labs/ba_grade/ba_stale_vote_read.json.

Each arm's value on a row is consensus.compute_consensus_point called on the exact arguments the
served build_timeseries hands it at the row's as-of point (captured from one served build), with
only the arm's change to the votes. A vote is an outlet's effective explicit-FV row on the point
(after consensus._dedupe_source_aliases; constant anchors are not votes); removing a vote
removes every row of that outlet from the point. Nothing served is written. No row is grouped by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md): the groups are frame, side and year. Only
lv_dev and vm_dev are read; a reserved row is refused (ba_grade_consensus_lab.guard_rows).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(1, str(ROOT / "tools"))

TASK = "BA_KEEP_FORWARD_READ"
DOC = "docs/efv-v2/BA_KEEP_FORWARD_READ.md"
ARTIFACT = ROOT / "data" / "_labs" / "ba_grade" / "ba_stale_vote_read.json"
BA = "baseballamerica"
FRAMES = ("lv_dev", "vm_dev")
#: Section C4: a vote this many cycles older than its point is stale (rule D); D1 uses 1.
STALE_AGE = 2
STALE_AGE_D1 = 1
DECAY = 0.5
NULL_K = 200
PERM_SEED = 20261016
P_NULL = 0.05
PLD_QUANTILE = 0.95
CONS_KEY = "prospx_consensus"
ARMS = ("S", "D", "W", "D1")


# ---------------------------------------------------------------------------
# votes on one point
# ---------------------------------------------------------------------------

def _year(date) -> int:
    return int(str(date)[:4])


def outlet_of(source: str) -> str:
    import consensus as C
    return C.SOURCE_ALIASES.get(source, source)


def votes(ds: list) -> dict:
    """{outlet: snapshot year} of the point's effective explicit-FV votes."""
    import consensus as C
    out = {}
    for s in C._dedupe_source_aliases(list(ds)):
        if s.fv is None or s.source in C.CONSTANT_ANCHOR_SOURCES:
            continue
        out[s.source] = _year(s.snapshot_date)
    return out


def ages(ds: list, event_date: str) -> dict:
    """{outlet: age in cycles} of the point's votes."""
    y = _year(event_date)
    return {o: y - yr for o, yr in votes(ds).items()}


def remove_outlets(ds: list, outlets) -> list:
    """The point's rows without any row of the given outlets (canonical or alias)."""
    drop = set(outlets)
    return [s for s in ds if outlet_of(s.source) not in drop]


def stale_outlets(ds: list, event_date: str, min_age: int, only: str | None = None) -> list[str]:
    """The outlets rule D (min_age) removes on this point: votes at least min_age cycles old,
    when at least one younger vote would remain; [] otherwise. `only` restricts the candidates
    to one outlet (BA, for the board effect)."""
    ag = ages(ds, event_date)
    stale = sorted(o for o, a in ag.items() if a >= min_age and (only is None or o == only))
    if not stale:
        return []
    if not any(a < min_age for o, a in ag.items() if o not in stale):
        return []
    return stale


def decay_weights(ds: list, event_date: str, base: dict | None,
                  only: str | None = None) -> dict | None:
    """Rule W: source_weights with each vote STALE_AGE or more cycles old at
    DECAY ** (age - 1); None when no vote is touched (the point is unchanged)."""
    ag = ages(ds, event_date)
    hit = {o: DECAY ** (a - 1) for o, a in ag.items()
           if a >= STALE_AGE and (only is None or o == only)}
    if not hit or len(hit) == len(ag):
        return None
    w = dict(base or {})
    w.update(hit)
    return w


def value(pt) -> float | None:
    if pt is None:
        return None
    v = pt.consensus_fv_raw if pt.consensus_fv_raw is not None else pt.consensus_fv
    return None if v is None else float(v)


def arm_point(arm: str, ds: list, kw: dict, *, only: str | None = None):
    """(value, touched) of one arm on one captured point."""
    import consensus as C
    ev = kw.get("event_date")
    if arm == "S":
        return value(C.compute_consensus_point(ds, **kw)), False
    if arm in ("D", "D1"):
        st = stale_outlets(ds, ev, STALE_AGE if arm == "D" else STALE_AGE_D1, only)
        if not st:
            return value(C.compute_consensus_point(ds, **kw)), False
        return value(C.compute_consensus_point(remove_outlets(ds, st), **kw)), True
    if arm == "W":
        w = decay_weights(ds, ev, kw.get("source_weights"), only)
        if w is None:
            return value(C.compute_consensus_point(ds, **kw)), False
        return value(C.compute_consensus_point(ds, **dict(kw, source_weights=w))), True
    raise ValueError(f"unknown arm {arm!r}")


def null_drop(ds: list, kw: dict, k: int, rng) -> float | None:
    """ND: k votes chosen at random among the point's votes removed (at least one kept)."""
    import consensus as C
    outs = sorted(votes(ds))
    k = min(int(k), len(outs) - 1)
    pick = [outs[i] for i in rng.choice(len(outs), size=k, replace=False)] if k > 0 else []
    return value(C.compute_consensus_point(remove_outlets(ds, pick), **kw))


def null_weights(ds: list, kw: dict, rng) -> float | None:
    """NW: the weights rule W gives on this point, assigned to randomly chosen votes."""
    import consensus as C
    w = decay_weights(ds, kw.get("event_date"), None)
    outs = sorted(votes(ds))
    if not w:
        return value(C.compute_consensus_point(ds, **kw))
    vals = list(w.values())
    pick = [outs[i] for i in rng.choice(len(outs), size=len(vals), replace=False)]
    ww = dict(kw.get("source_weights") or {})
    ww.update(dict(zip(pick, vals)))
    return value(C.compute_consensus_point(ds, **dict(kw, source_weights=ww)))


def plant_values(ds: list, outlet: str, fv: float) -> list:
    """The point's rows with every row of `outlet` carrying the published grade `fv`."""
    return [dataclasses.replace(s, fv=float(fv)) if outlet_of(s.source) == outlet
            and s.fv is not None else s for s in ds]


def planted_assignment(units: list[dict]) -> dict:
    """PLD: {(row id, outlet): grade}. Within each (frame, side), the stale votes' own grades
    re-assigned so the highest grade goes to the lowest-outcome row (ties by player key,
    then outlet)."""
    out = {}
    for fs in sorted({(u["fid"], u["side"]) for u in units}):
        grp = [u for u in units if (u["fid"], u["side"]) == fs]
        vals = sorted((u["fv"] for u in grp), reverse=True)
        order = sorted(grp, key=lambda u: (u["war"], u["key"], u["outlet"]))
        for u, v in zip(order, vals):
            out[(u["rid"], u["outlet"])] = float(v)
    return out


def holm(ps: dict) -> dict:
    """Holm-adjusted p values over the family {name: p}."""
    items = sorted((p, n) for n, p in ps.items() if p is not None)
    out, run = {}, 0.0
    m = len(items)
    for i, (p, n) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[n] = round(run, 4)
    for n, p in ps.items():
        out.setdefault(n, None)
    return out


# ---------------------------------------------------------------------------
# capture: the served arguments at each as-of point
# ---------------------------------------------------------------------------

def _universe() -> dict:
    out = {}
    for f in ("timeseries.json", "debuts.json", "inactive.json"):
        p = ROOT / "data" / f
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in (d if isinstance(d, list) else (d.get("players") or [])):
            out.setdefault(r.get("player_key"), r)
    return out


def asof_point(points: list, fid: str, year: int, rec: dict | None):
    """The row's as-of point: vm_dev [Y-01-01, Y-05-01); lv_dev window_bounds(V, debut day)."""
    import efv_dataset as D
    lo, hi = f"{int(year)}-01-01", f"{int(year)}-05-01"
    if fid == "lv_dev" and rec is not None:
        dd = D.debut_day_for_cutoff(rec)[0]
        if dd and str(dd)[:10] < hi:
            hi = str(dd)[:10]
    win = [q for q in points if q.snapshot_date and lo <= q.snapshot_date < hi]
    return sorted(win, key=lambda q: q.snapshot_date)[-1] if win else None


def _sig(pt) -> tuple:
    return (value(pt), tuple(sorted((s, (x or {}).get("fv_published"))
                                    for s, x in (pt.per_source or {}).items())))


def capture(snaps: list, wanted: dict) -> tuple[dict, list]:
    """{(key, date): (ds, kw)} for every wanted (key, date) -> served point, from one served
    build. A point a same-name fold moved onto `key` is matched by its signature among the
    calls of keys with the same base name (Q2). Returns (captured, unresolved)."""
    import consensus as C
    dates = {d for (_k, d) in wanted}
    calls: dict = {}
    orig = C.compute_consensus_point

    def wrap(ds, **kw):
        if ds and kw.get("event_date") in dates:
            calls[(ds[0].player_key, kw["event_date"])] = (list(ds), dict(kw))
        return orig(ds, **kw)
    C.compute_consensus_point = wrap
    try:
        C.build_timeseries(snaps, normalize=C.ADOPT_NORMALIZED_CONSENSUS)
    finally:
        C.compute_consensus_point = orig
    out, bad = {}, []
    for (key, d), pt in wanted.items():
        if (key, d) in calls:
            out[(key, d)] = calls[(key, d)]
            continue
        base = key.split("__")[0]
        sig = _sig(pt)
        hits = [k for (k, dd) in calls if dd == d and k != key and k.split("__")[0] == base
                and _sig(orig(calls[(k, d)][0], **calls[(k, d)][1])) == sig]
        if len(hits) == 1:
            out[(key, d)] = calls[(hits[0], d)]
        else:
            bad.append({"key": key, "date": d, "matches": hits})
    return out, bad


# ---------------------------------------------------------------------------
# guards, rows and the run
# ---------------------------------------------------------------------------

def registration_sha() -> str | None:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%H", "--", DOC], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return None
    return out or None


def _r(v, n=5):
    return None if v is None else round(float(v), n)


def stat_rows(rows: list[dict], vals: dict) -> list[dict]:
    return [{"fid": r["fid"], "key": r["key"], "side": r["side"], "year": r["year"],
             "group": r["group"], "war": r["war"], "contrib": r["contrib"],
             "v": {a: vals[a][r["rid"]] for a in vals}} for r in rows]


def run(*, check_only: bool = False, null_k: int = NULL_K, B: int | None = None,
        log=print) -> dict:
    import ba_grade_consensus_lab as LAB
    import consensus as C
    import efv_labels as L
    import efv_v2_model_class_screen as MCS
    import efv_v2_stat as S
    import storage
    t0 = time.time()
    sha = registration_sha()
    if not sha:
        raise RuntimeError(f"refused: {DOC} is not committed")
    if not check_only and L.provider() != "fwar":
        raise RuntimeError(f"refused: label provider is {L.provider()!r}, not the frozen 'fwar'")
    B = S.B_DEFAULT if B is None else int(B)
    seed = S.SEED_DEFAULT
    scored, guards = LAB.dev_rows(log=log)
    log(f"frames: lv_dev {len(scored['lv_dev'])}, vm_dev {len(scored['vm_dev'])} scored rows "
        f"({round(time.time() - t0, 1)} s)")
    uni = _universe()
    snaps = storage.load_all_snapshots()
    ts = {p.player_key: p for p in C.build_timeseries(
        snaps, normalize=C.ADOPT_NORMALIZED_CONSENSUS)}
    rows, wanted, missing = [], {}, []
    for fid in FRAMES:
        for c in scored[fid]:
            p = ts.get(c["key"])
            q = asof_point(p.points if p else [], fid, int(c["year"]), uni.get(c["key"]))
            if q is None:
                missing.append((fid, c["key"], c["year"]))
                continue
            rid = len(rows)
            rows.append({"rid": rid, "fid": fid, "key": c["key"], "side": c["side"],
                         "year": int(c["year"]), "group": f"{fid}|{c['group']}",
                         "date": q.snapshot_date, "stored": float(c["grades"][CONS_KEY]),
                         "war": None if check_only else float(c["outcome"]["war"]),
                         "contrib": None if check_only else bool(c["outcome"]["contributor"])})
            wanted[(c["key"], q.snapshot_date)] = q
    if missing:
        raise RuntimeError(f"Q2 failed: {len(missing)} rows have no as-of point: {missing[:5]}")
    cap, bad = capture(snaps, wanted)
    if bad:
        raise RuntimeError(f"Q2 failed: {len(bad)} as-of points not captured: {bad[:5]}")
    log(f"Q2: {len(cap)} as-of points captured for {len(rows)} rows "
        f"({round(time.time() - t0, 1)} s)")
    vals = {a: {} for a in ARMS}
    touched = {a: set() for a in ARMS}
    q1_bad = []
    for r in rows:
        ds, kw = cap[(r["key"], r["date"])]
        for a in ARMS:
            v, t = arm_point(a, ds, kw)
            vals[a][r["rid"]] = v
            if t:
                touched[a].add(r["rid"])
        if vals["S"][r["rid"]] is None or abs(vals["S"][r["rid"]] - r["stored"]) > 1e-9:
            q1_bad.append((r["fid"], r["key"], r["year"], vals["S"][r["rid"]], r["stored"]))
    if q1_bad:
        raise RuntimeError(f"Q1 failed on {len(q1_bad)} rows: {q1_bad[:5]}")
    log("Q1: the unchanged recomputation equals the frames' stored consensus on every row")

    def counts(ids):
        out = {}
        for r in rows:
            if r["rid"] in ids:
                k = f"{r['fid']}|{r['side']}"
                out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))
    doc: dict = {
        "task": TASK, "document": DOC, "registration_sha": sha,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frames_guards": guards, "rows": len(rows),
        "rows_by_frame": {f: sum(1 for r in rows if r["fid"] == f) for f in FRAMES},
        "parity": {"Q1": True, "Q2": True, "captured": len(cap)},
        "touched": {a: {"rows": len(touched[a]), "by_frame_side": counts(touched[a])}
                    for a in ARMS if a != "S"},
        "rule": {"stale_age": STALE_AGE, "stale_age_d1": STALE_AGE_D1, "decay": DECAY},
    }
    doc["board_effect"] = board_effect(snaps, log=log)
    if check_only:
        doc["check_only"] = True
        log(f"check done ({round(time.time() - t0, 1)} s); no outcome was read")
        return doc
    # --- the read ---------------------------------------------------------------
    doc["label"] = MCS._label()
    srows = stat_rows(rows, vals)
    rng = np.random.default_rng(PERM_SEED)
    dT = sorted(touched["D"])
    wT = sorted(touched["W"])
    kD = {}
    for rid in dT:
        r = rows[rid]
        ds, kw = cap[(r["key"], r["date"])]
        kD[rid] = len(stale_outlets(ds, kw["event_date"], STALE_AGE))
    nd, nw = [], []
    for k in range(int(null_k)):
        vN = dict(vals["S"])
        for rid in dT:
            r = rows[rid]
            ds, kw = cap[(r["key"], r["date"])]
            vN[rid] = null_drop(ds, kw, kD[rid], rng)
        vW = dict(vals["S"])
        for rid in wT:
            r = rows[rid]
            ds, kw = cap[(r["key"], r["date"])]
            vW[rid] = null_weights(ds, kw, rng)
        rr = stat_rows(rows, {"S": vals["S"], "N": vN, "M": vW})
        nd.append(LAB.delta(rr, "N", "S", B=0, seed=seed)["delta"])
        nw.append(LAB.delta(rr, "M", "S", B=0, seed=seed)["delta"])
        if k % 50 == 0 or k == null_k - 1:
            log(f"null draw {k + 1}/{null_k} ({round(time.time() - t0, 1)} s)")
    # planted
    units = []
    for rid in dT:
        r = rows[rid]
        ds, kw = cap[(r["key"], r["date"])]
        eff = {s.source: s for s in C._dedupe_source_aliases(list(ds))}
        for o in stale_outlets(ds, kw["event_date"], STALE_AGE):
            units.append({"rid": rid, "fid": r["fid"], "side": r["side"], "key": r["key"],
                          "war": r["war"], "outlet": o, "fv": float(eff[o].fv)})
    plant = planted_assignment(units)
    vP = dict(vals["S"])
    for rid in dT:
        r = rows[rid]
        ds, kw = cap[(r["key"], r["date"])]
        pds = ds
        for (prid, o), v in plant.items():
            if prid == rid:
                pds = plant_values(pds, o, v)
        vP[rid] = value(C.compute_consensus_point(pds, **kw))
    rr = stat_rows(rows, {"S": vP, "D": vals["D"]})
    d_pl = LAB.delta(rr, "D", "S", B=B, seed=seed)
    pld = LAB.plant_passes(d_pl, nd, PLD_QUANTILE, absolute=False)
    log(f"PLD {pld}")
    read: dict = {}
    raw_p = {}
    for name, (a, null) in {"G1": ("D", nd), "G2": ("W", nw), "G3": ("D1", None)}.items():
        d = LAB.delta(srows, a, "S", B=B, seed=seed)
        p = LAB.p_null(d.get("delta"), null, two_sided=False) if null is not None else None
        blk = {"a": a, "b": "S", "within": {k: d.get(k) for k in
                                           ("delta", "ci95", "sd", "mde95", "n", "n_clusters",
                                            "groups_kept", "B_used", "status")},
               "p_null": p, "secondary": {}, "per_frame": {}}
        for st in ("pooled", "auc"):
            ds_ = LAB.delta(srows, a, "S", B=B, seed=seed, statistic=st)
            blk["secondary"][st] = {k: ds_.get(k) for k in ("delta", "ci95", "status")}
        for f in FRAMES:
            ds_ = LAB.delta([r for r in srows if r["fid"] == f], a, "S", B=B, seed=seed)
            blk["per_frame"][f] = {k: ds_.get(k) for k in ("delta", "ci95", "n", "status")}
        read[name] = blk
        if null is not None:
            raw_p[name] = p
    adj = holm(raw_p)
    for name in ("G1", "G2"):
        blk = read[name]
        ok = bool(LAB.ci_excludes_zero(blk["within"]) and adj[name] is not None
                  and adj[name] < P_NULL and pld["passes"])
        sign = None if blk["within"].get("delta") is None else (
            "positive" if blk["within"]["delta"] > 0 else "negative")
        blk.update({"p_holm": adj[name], "planted_passed": pld["passes"],
                    "ci_excludes_zero": LAB.ci_excludes_zero(blk["within"]),
                    "resolves": ok, "reading": ("RESOLVED " + sign) if ok else "UNRESOLVED"})
        log(f"{name} {blk['a']}-S: within {blk['within']['delta']} CI95 "
            f"{blk['within']['ci95']} p {blk['p_null']} holm {adj[name]} -> {blk['reading']}")
    read["G3"]["reading"] = "reported, not adjudicated"
    doc["read"] = read
    doc["nulls"] = {
        "K": int(null_k), "seed": PERM_SEED,
        "ND_minus_S": {"mean": _r(np.mean(nd)), "sd": _r(np.std(nd, ddof=1)),
                       "p95": _r(np.quantile(nd, 0.95)), "p5": _r(np.quantile(nd, 0.05))},
        "NW_minus_S": {"mean": _r(np.mean(nw)), "sd": _r(np.std(nw, ddof=1)),
                       "p95": _r(np.quantile(nw, 0.95)), "p5": _r(np.quantile(nw, 0.05))},
        "ND_draws": [_r(x) for x in nd], "NW_draws": [_r(x) for x in nw]}
    doc["planted"] = {"PLD": pld, "units": len(units)}
    doc["arms_within"] = {a: LAB.within_of(srows, a) for a in ARMS}
    res = [read[n]["resolves"] and read[n]["reading"].endswith("positive") for n in ("G1", "G2")]
    doc["recommendation"] = (
        {"default": "CANDIDATE", "why": "a stale-vote rule resolves positive (C10)"}
        if any(res) else
        {"default": "NO CHANGE", "why": "nothing resolves positive; BA's own question waits "
                                        "for F4 of the forward read (C10)"})
    doc["elapsed_s"] = round(time.time() - t0, 1)
    return doc


def board_effect(snaps: list, log=print) -> dict:
    """Outcome-free: on the latest point of every active eFV board row, the change rules D and W
    would make, for every outlet and for BA's votes only, by side."""
    import consensus as C
    xfv = {k: r for k, r in json.loads((ROOT / "data" / "xfv.json").read_text(
        encoding="utf-8"))["by_player"].items()
           if r.get("kind") == "active" and (r.get("efv_v2") or {}).get("group")}
    side_of = {k: ("pit" if r.get("side") == "P" else "hit") for k, r in xfv.items()}
    ts = C.build_timeseries(snaps, normalize=C.ADOPT_NORMALIZED_CONSENSUS)
    wanted = {(p.player_key, p.points[-1].snapshot_date): p.points[-1]
              for p in ts if p.player_key in xfv and p.points}
    del ts
    cap, bad = capture(snaps, wanted)
    out = {"rows": len(wanted), "not_captured": len(bad)}
    for only, tag in ((None, "all_outlets"), (BA, "ba_only")):
        for arm in ("D", "W", "D1"):
            per = {}
            for side in ("hit", "pit"):
                d = []
                for (k, dt), (ds, kw) in cap.items():
                    if side_of.get(k) != side:
                        continue
                    v1, t = arm_point(arm, ds, kw, only=only)
                    if t:
                        d.append(v1 - value(C.compute_consensus_point(ds, **kw)))
                a = np.asarray(d, dtype=np.float64)
                per[side] = ({"touched": int(a.size), "mean": round(float(a.mean()), 3),
                              "mean_abs": round(float(np.abs(a).mean()), 3),
                              "largest_up": round(float(a.max()), 2),
                              "largest_down": round(float(a.min()), 2),
                              "moved_1fv_or_more": int((np.abs(a) >= 1.0).sum())}
                             if a.size else {"touched": 0})
            out[f"{tag}_{arm}"] = per
    log(f"board effect: {len(wanted)} rows")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="parity checks only; no outcome read")
    g.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--null-k", type=int, default=NULL_K)
    ap.add_argument("--out", default=str(ARTIFACT))
    a = ap.parse_args(argv)
    doc = run(check_only=a.check, null_k=a.null_k)
    if a.run:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(json.dumps({k: doc[k] for k in ("rows", "rows_by_frame", "parity", "touched",
                                              "board_effect")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
