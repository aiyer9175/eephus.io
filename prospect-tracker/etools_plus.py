# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eTools+ (ETOOLS_PLUS, owner decision EW3-28), registered in
docs/tools-2026-10/ETOOLS_PLUS.md (28b97126) before any value existed.

One tools summary per prospect: the shown eTools weighted by the tool-slot weights of the
EFV_ETOOLS_REWEIGHT production fit, candidate E (default D-1), normalized within side;
100 = the side's average live prospect, 10 points per standard deviation, to the nearest
whole number. Descriptive: it claims nothing about outcomes.

    python etools_plus.py            # write data/etools_plus.json from data/etools.json
    python etools_plus.py --check C  # the registered descriptive check, run once (section 6),
                                     # C = the EFV_ETOOLS_REWEIGHT read's cache directory

Run it after every `python etools.py --preview`; the sidecar carries the sha256 of the
eTools payload it read and a test fails when they differ.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ETOOLS_PATH = DATA / "etools.json"
WEIGHTS_PATH = DATA / "_labs" / "efv5" / "efv_etools_reweight_fit.json"
SERVED_PATH = DATA / "etools_plus.json"
CHECK_PATH = DATA / "_labs" / "etools" / "etools_plus_check.json"
DOC = "docs/tools-2026-10/ETOOLS_PLUS.md"
ITEM = "ETOOLS_PLUS"
CANDIDATE = "E"

#: the re-weight's tool-slot driver -> the eTool's tool key (data/etools.json)
SLOT_TOOL = {"e5_pow_hit": "game_pwr", "e5_hit_hit": "hit", "e5_fb_pit": "fb", "e5_cmd_pit": "cmd"}
#: every tool in the definition per side (section 1); a tool absent from the fit weighs 0
DEFINITION = {
    "hit": ("hit", "game_pwr", "pitch_sel", "bat_ctrl", "raw_pwr", "speed", "field", "throw"),
    "pit": ("fb", "cmd", "sl", "cb", "ch"),
}
#: why a defined tool carries no weight (section 1), printed in the tooltip and the sidecar
ZERO_WHY = {
    "hit": "eHIT was refused in the hit slot (one-sign rule)",
    "pitch_sel": "eSEL is in no slot of the eFV head",
    "bat_ctrl": "eBAT is in no slot of the eFV head",
    "raw_pwr": "no passing eTool and no slot",
    "speed": "no passing eTool and no slot",
    "field": "no slot in the eFV head",
    "throw": "no slot in the eFV head",
    "sl": "no slot in the eFV head",
    "cb": "no slot in the eFV head",
    "ch": "no slot in the eFV head",
}
NAMES = {"hit": "Hit", "game_pwr": "Game Power", "pitch_sel": "Pitch Selection", "bat_ctrl": "Bat Control",
         "raw_pwr": "Raw Power", "speed": "Speed", "field": "Field", "throw": "Arm", "fb": "Fastball",
         "cmd": "Command", "sl": "Slider", "cb": "Curveball", "ch": "Changeup"}
KEYS = {"hit": "eHIT", "game_pwr": "ePOW", "pitch_sel": "eSEL", "bat_ctrl": "eBAT", "fb": "eFB", "cmd": "eCMD"}
MIN_GROUP_ROWS = 20


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _r(v, dp=4):
    return None if v is None else round(float(v), dp)


def round_nearest(x: float) -> int:
    """Nearest whole number, halves up (a plus stat rounds to nearest)."""
    return int(math.floor(x + 0.5))


def weights(fit: dict, candidate: str = CANDIDATE) -> dict:
    """{side: {tool: normalized weight}} from production.<candidate>.tool_weights; every
    defined tool is present, the ones without a slot weight at 0."""
    rows = ((fit.get("production") or {}).get(candidate) or {}).get("tool_weights") or {}
    out = {}
    for side, tools in DEFINITION.items():
        raw = {t: 0.0 for t in tools}
        for r in rows.get(side) or []:
            t = SLOT_TOOL.get(r.get("driver"))
            w = float(r.get("weight_pct_equiv") or 0.0)
            if t in raw and w > 0:
                raw[t] += w
        tot = sum(raw.values())
        if tot <= 0:
            raise ValueError(f"no positive tool weight on the {side} side of candidate {candidate}")
        out[side] = {t: raw[t] / tot for t in tools}
    return out


def _mean_sd(xs: list) -> tuple:
    n = len(xs)
    if n < 2:
        return None, None
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / n)
    return m, (sd if sd > 0 else None)


def compose(values: dict, w: dict) -> dict:
    """Section 4 on one pool. values: {player: {tool: value}} of one side; w: {tool: weight}.
    Returns {"players": {player: rec}, "tools": {tool: (mean, sd, n)}, "mean_s", "sd_s"}."""
    live = [t for t, x in w.items() if x > 0]
    stats = {}
    for t in live:
        xs = [v[t] for v in values.values() if v.get(t) is not None]
        stats[t] = _mean_sd(xs) + (len(xs),)
    S, parts = {}, {}
    for pk, v in values.items():
        z = {t: (v[t] - stats[t][0]) / stats[t][1] for t in live
             if v.get(t) is not None and stats[t][1] is not None}
        cov = sum(w[t] for t in z)
        if cov <= 0:
            continue
        S[pk] = sum(w[t] * z[t] for t in z) / cov
        parts[pk] = (z, cov)
    mean_s, sd_s = _mean_sd(list(S.values()))
    players = {}
    if sd_s is not None:
        for pk, s in S.items():
            z, cov = parts[pk]
            plus = 100.0 + 10.0 * (s - mean_s) / sd_s
            contrib = {t: 10.0 * w[t] * z[t] / cov / sd_s for t in z}
            players[pk] = {"plus_raw": plus, "plus": round_nearest(plus), "coverage": cov, "z": z,
                           "points": contrib, "centring": -10.0 * mean_s / sd_s}
    return {"players": players, "tools": stats, "mean_s": mean_s, "sd_s": sd_s}


def build(etools_doc: dict, fit: dict) -> dict:
    """data/etools_plus.json from the eTools payload and the re-weight fit."""
    W = weights(fit)
    out_players, sides = {}, {}
    for side in ("hit", "pit"):
        vals, shown = {}, {}
        for pk, p in (etools_doc.get("players") or {}).items():
            if p.get("side") != side:
                continue
            tools = p.get("tools") or {}
            vals[pk] = {t: float(r["etool"]) for t, r in tools.items()
                        if t in W[side] and r.get("etool") is not None}
            shown[pk] = {t: r.get("shown") for t, r in tools.items()}
        res = compose(vals, W[side])
        sides[side] = {
            "weights": {t: _r(x, 4) for t, x in W[side].items()},
            "carry_weight": [t for t, x in W[side].items() if x > 0],
            "zero_weight": {t: ZERO_WHY.get(t, "no slot weight") for t, x in W[side].items() if x <= 0},
            "pool_n": len(res["players"]),
            "tool_pool": {t: {"mean": _r(m, 3), "sd": _r(s, 3), "n": n} for t, (m, s, n) in res["tools"].items()},
            "mean_s": _r(res["mean_s"], 6), "sd_s": _r(res["sd_s"], 6),
        }
        for pk, rec in sorted(res["players"].items()):
            p = etools_doc["players"][pk]
            parts = []
            for t, x in W[side].items():
                if x <= 0:
                    continue
                parts.append([t, _r(x, 4), shown[pk].get(t), _r(rec["points"].get(t), 2) if t in rec["points"] else None])
            out_players[pk] = {"mlbam": p.get("mlbam"), "side": side, "plus": rec["plus"],
                               "coverage": _r(rec["coverage"], 4), "parts": parts,
                               "centring": _r(rec["centring"], 2)}
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "item": ITEM, "decision": "EW3-28", "doc": DOC, "role": "descriptive",
        "scale": "100 + 10 x z of the weighted mean of the tool z scores, within side, nearest",
        "weights_source": {"path": "data/_labs/efv5/efv_etools_reweight_fit.json",
                           "field": f"production.{CANDIDATE}.tool_weights", "candidate": CANDIDATE,
                           "default": "D-1"},
        "etools_sha256": None, "weights_sha256": None,
        "names": NAMES, "keys": KEYS,
        "sides": sides, "players": out_players,
    }


def check_summary() -> dict | None:
    """The descriptive check's pooled numbers (section 6), copied from its lab artifact so
    the glossary and the registry derive from a served file; None before the check ran."""
    if not CHECK_PATH.exists():
        return None
    d = json.loads(CHECK_PATH.read_text(encoding="utf-8"))
    out = {"role": "descriptive", "adjudicates": "nothing", "artifact": "data/_labs/etools/etools_plus_check.json",
           "generated_at": d.get("generated_at"), "frames": {}}
    for fid, blk in (d.get("frames") or {}).items():
        out["frames"][fid] = {
            side: {k: {"vs_outcome": b[k]["vs_outcome"]["rho"], "vs_consensus_fv": b[k]["vs_consensus_fv"]["rho"],
                       "n": b[k]["vs_outcome"]["n"]}
                   for k in ("etools_plus", "cons_plus")}
            for side, b in blk.items()}
    return out


def export(*, log=print) -> Path:
    et = json.loads(ETOOLS_PATH.read_text(encoding="utf-8"))
    fit = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    doc = build(et, fit)
    doc["etools_sha256"] = _sha(ETOOLS_PATH)
    doc["weights_sha256"] = _sha(WEIGHTS_PATH)
    doc["check"] = check_summary()
    SERVED_PATH.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8", newline="\n")
    log(f"eTools+: {doc['sides']['hit']['pool_n']} hitters, {doc['sides']['pit']['pool_n']} pitchers "
        f"-> {SERVED_PATH}")
    return SERVED_PATH


# ---------------------------------------------------------------------------
# the registered descriptive check (section 6), run once
# ---------------------------------------------------------------------------

def _spearman(a: list, b: list):
    from scipy.stats import spearmanr
    if len(a) < 3:
        return None
    r = spearmanr(a, b).statistic
    return None if r is None or not math.isfinite(r) else float(r)


def within(rows: list, key: str, target: str) -> dict:
    """Row-weighted mean over (side, year) groups of MIN_GROUP_ROWS or more of the Spearman
    of rows[key] with rows[target]."""
    by = {}
    for r in rows:
        if r.get(key) is None or r.get(target) is None:
            continue
        by.setdefault(r["group"], []).append(r)
    num = den = 0.0
    groups = {}
    for g, rs in sorted(by.items()):
        if len(rs) < MIN_GROUP_ROWS:
            continue
        rho = _spearman([r[key] for r in rs], [r[target] for r in rs])
        if rho is None:
            continue
        groups[g] = {"n": len(rs), "rho": round(rho, 4)}
        num += rho * len(rs)
        den += len(rs)
    return {"rho": round(num / den, 4) if den else None, "n": int(den), "groups": groups}


def check_rows(scored: list, pairs: dict, fid: str, W: dict) -> list:
    """Each scored row with its as-of eTools+, the consensus-grade composite and the weighted
    eTools alone; eTools+ composed inside each (side, year) group."""
    out = []
    by = {}
    for c in scored:
        p = pairs.get((fid, c["side"], int(c["year"]), c["key"]))
        if not p:
            continue
        by.setdefault(c["group"], []).append((c, p))
    for g, items in by.items():
        side = items[0][0]["side"]
        w = W[side]
        et = {c["key"]: {t: float(p["tools"][t][1]) for t in w if w[t] > 0 and t in p["tools"]
                         and math.isfinite(p["tools"][t][1])} for c, p in items}
        cg = {c["key"]: {t: float(p["tools"][t][0]) for t in w if w[t] > 0 and t in p["tools"]
                         and math.isfinite(p["tools"][t][0])} for c, p in items}
        e_res = compose(et, w)["players"]
        c_res = compose(cg, w)["players"]
        for c, _p in items:
            k = c["key"]
            row = {"group": g, "side": side, "war": (c.get("outcome") or {}).get("war"),
                   "cfv": (c.get("grades") or {}).get("prospx_consensus"),
                   "etools_plus": (e_res.get(k) or {}).get("plus_raw"),
                   "cons_plus": (c_res.get(k) or {}).get("plus_raw")}
            for t in w:
                if w[t] > 0:
                    row["e_" + t] = et[k].get(t)
            out.append(row)
    return out


def run_check(cache_dir: Path, *, log=print) -> dict:
    import pickle
    if CHECK_PATH.exists():
        raise SystemExit(f"refused: {CHECK_PATH} exists; the registered check runs once")
    import efv_etools_reweight as RW
    BT, _ = RW._tools()
    with (cache_dir / "build.pkl").open("rb") as fh:
        b1 = pickle.load(fh)
    with (cache_dir / "part1_pairs.pkl").open("rb") as fh:
        pairs = pickle.load(fh)
    fit = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    W = weights(fit)
    inp = b1["inp"]
    frames = {}
    for fid in BT.FRAMES_DEV:
        rows = check_rows(inp.scored(fid), pairs, fid, W)
        blk = {}
        for side in ("hit", "pit"):
            rs = [r for r in rows if r["side"] == side]
            keys = ["etools_plus", "cons_plus"] + ["e_" + t for t in W[side] if W[side][t] > 0]
            blk[side] = {k: {"vs_outcome": within(rs, k, "war"), "vs_consensus_fv": within(rs, k, "cfv")}
                         for k in keys}
            blk[side]["rows_with_etools_plus"] = sum(1 for r in rs if r["etools_plus"] is not None)
        frames[fid] = blk
        log(f"{fid}: " + json.dumps({s: {k: (v["vs_outcome"]["rho"], v["vs_consensus_fv"]["rho"])
                                          for k, v in b.items() if isinstance(v, dict)}
                                      for s, b in blk.items()}))
    doc = {"item": ITEM, "doc": DOC, "role": "descriptive", "adjudicates": "nothing",
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "frames_read": list(BT.FRAMES_DEV),
           "statistic": ("row-weighted mean over (side, year) groups of 20 or more rows of the within-group "
                         "Spearman; vs_outcome = outcome.war (the eWAR v2 eFV label), vs_consensus_fv = "
                         "prospx_consensus; no FV-level cut"),
           "series": {"etools_plus": "eTools+ from the as-of eTools (part1_pairs, forward-chained)",
                      "cons_plus": "the same weights on the consensus tool grades (reference)",
                      "e_<tool>": "the weighted eTool alone (reference)"},
           "weights": {s: {t: round(x, 4) for t, x in w.items() if x > 0} for s, w in W.items()},
           "sources": {"cache": str(cache_dir).replace("\\", "/").split("/scratchpad/")[-1],
                       "weights_sha256": _sha(WEIGHTS_PATH)},
           "frames": frames}
    CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECK_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    log(f"check -> {CHECK_PATH}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", metavar="CACHE", help="the registered descriptive check (run once)")
    a = ap.parse_args(argv)
    if a.check:
        run_check(Path(a.check))
        return 0
    export()
    return 0


if __name__ == "__main__":
    sys.exit(main())
