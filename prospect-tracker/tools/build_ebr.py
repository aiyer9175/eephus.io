#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_ebr - the eBR substrate and its descriptive eval, PREVIEWS ONLY.

docs/ebr-2026-09-30/EBR_GATE.md parts 2 to 4; integration.md 4.5's substrate schema.
Writes exactly two files, and nothing under data/:

  .cache/ebr/preview/ebr.json       the substrate: one row per (mlbam, season) with
      pa, opportunities, the five parts (sb, pk, xb_adv, xb_oob, dp), ebr and per-club
      stints; league blocks; each season's RE24 cells with n and sha256; cadence and
      frozen digests; ebr_version; generated_at.
  .cache/ebr/preview/ebr_eval.json  the descriptive eval: the identity receipts I1 to
      I9, league sums, coverage against the feed's hitting rows, the part 4 agreement
      table as AGGREGATES with the bug bands marked, the arm P and F reports, and the
      ewar_link block (season sums of each part minus its FanGraphs and its
      Baseball-Reference counterpart). No per-player FanGraphs, Savant or
      Baseball-Reference value enters it. A look block that tools/ebr_gate.py wrote is
      carried over untouched; this builder never writes one.

The frozen ebr_v1 pool (pooled RE24, K, pooled eXB outcome counts) lives at
.cache/ebr/frozen/ebr_v1_pool.json; when absent it is rebuilt from the record and
must match ebr.FROZEN_POOL_SHA256.

Same-season numbers only. No year-to-year, split-half or forward statistic of eBR or
of a part is computed here: tools/ebr_gate.py alone does that, once, on its day.
Nothing here relates eBR to runs scored or to wins.

Run:  python tools/build_ebr.py [--no-comparators] [--seasons 2018,2019,2021-2026]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ebr  # noqa: E402

RECORD = ROOT / ".cache" / "pbp_runners"
OUT_DIR = ROOT / ".cache" / "ebr" / "preview"
FROZEN_DIR = ROOT / ".cache" / "ebr" / "frozen"
GATE_DOC = "docs/ebr-2026-09-30/EBR_GATE.md"
FREEZE_MONTH_DAY = (11, 1)
PA_FLOORS = (300, 502)
I4_TOL = 0.01
I6_TOL = 0.011
I6_MAX_ABS = 30.0

#: EBR_GATE.md part 4's bug bands. A miss means "find the bug", never "invalid".
#: The steal band reads eSB alone against wSB (amendment 11.1, 2026-10-14: wSB's
#: scope has no pickoffs of runners not attempting); SB runs (eSB + ePK) against
#: wSB, ePK against wSB and ePK's sd are reported beside it, never banded.
BUG_BANDS = {
    "r_ebr_vs_bref_br_dp_502": ("ebr_vs_bref_br_dp", 502, "pearson", ">=", 0.60),
    "r_esb_vs_fg_wsb": ("esb_vs_fg_wsb", 300, "pearson", ">=", 0.80),
    "r_xb_vs_savant_xb": ("xb_vs_savant_xb", 300, "pearson", ">=", 0.50),
    "r_dp_vs_bref_dp": ("dp_vs_bref_dp", 300, "pearson", ">=", 0.60),
    "sd_ratio_sb_xb_vs_bsr": ("sb_xb_vs_fg_bsr", 300, "sd_ratio", "in", (0.5, 2.0)),
    "abs_mean_diff_sb_xb_vs_bsr_502": ("sb_xb_vs_fg_bsr", 502, "mean_diff", "abs<=", 1.0),
    "r_sprint_vs_sb_xb_per600": ("sprint_vs_sb_xb_per600", 300, "pearson", ">=", 0.40),
}

ISOLATED_PREFIXES = ("efv_", "proj_", "fa_", "arb_", "betting_")

#: The FanGraphs basis of each season's counterparts (EBR_GATE.md parts 4 and 9.2).
#: From 2016 the served BsR is wSB plus Savant's runner XB runs and carries no
#: double-play part; through 2015 it is wSB + UBR + wGDP, so eBR's extra-base
#: part is read against UBR and its double-play part against wGDP there: a
#: different construct from the tested one, marked per season.
FG_BASIS_FROM_2016 = "fg_bsr_wsb_plus_savant_xb"
FG_BASIS_PRE_2016 = "fg_bsr_wsb_ubr_wgdp"
FG_BASIS_FIRST_SEASON = 2016
#: wGdp is the double-play comparator through 2024 (part 4); 2025 on it is 0.
FG_WGDP_LAST_SEASON = 2024


def fg_basis(season: int) -> str:
    return FG_BASIS_FROM_2016 if int(season) >= FG_BASIS_FIRST_SEASON else FG_BASIS_PRE_2016


def fg_counterparts(season: int, fg: dict | None) -> dict:
    """{sb, xb, dp} of one FanGraphs row on the season's basis, None where the
    feed value is missing: sb wSb; xb baseRunning - wSb (2016 on) or ubr (through
    2015); dp 0 (2016 on) or wGdp (through 2015)."""
    fg = fg or {}
    wsb, bsr = fg.get("wSb"), fg.get("baseRunning")
    if int(season) >= FG_BASIS_FIRST_SEASON:
        xb = (bsr - wsb) if (bsr is not None and wsb is not None) else None
        dp = 0.0 if bsr is not None else None
    else:
        xb, dp = fg.get("ubr"), fg.get("wGdp")
    return {"sb": wsb, "xb": xb, "dp": dp}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def season_complete(season: int, today: _dt.date | None = None) -> bool:
    t = today or _dt.date.today()
    return t >= _dt.date(int(season), *FREEZE_MONTH_DAY)


def _write_json(path: Path, obj, *, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=indent, sort_keys=True, separators=(",", ":") if indent is None
                              else (",", ": ")), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------
# the record
# --------------------------------------------------------------------------
def load_record(record: Path = RECORD, seasons=None) -> tuple[dict, dict]:
    """({season: (pa, rn)}, manifest) for the MLB seasons of the runner record."""
    import pandas as pd
    man = json.loads((Path(record) / "manifest.json").read_text(encoding="utf-8"))
    out = {}
    for s, blk in sorted((man.get("seasons") or {}).items()):
        s = int(s)
        if seasons is not None and s not in seasons:
            continue
        pa = pd.read_parquet(Path(record) / blk["files"]["pa"])
        rn = pd.read_parquet(Path(record) / blk["files"]["runners"])
        out[s] = (pa, rn)
    return out, man


# --------------------------------------------------------------------------
# statistics (aggregates only)
# --------------------------------------------------------------------------
def _rank(v):
    import numpy as np
    from scipy.stats import rankdata
    return rankdata(np.asarray(v, dtype=float))


def agreement(x, y) -> dict:
    """Pearson and Spearman r, SD ratio (ours over theirs), OLS slope (ours on
    theirs) and mean difference (ours minus theirs), with n."""
    import numpy as np
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = int(len(x))
    if n < 5 or x.std() == 0 or y.std() == 0:
        return {"n": n, "pearson": None, "spearman": None, "sd_ratio": None, "slope": None,
                "mean_diff": (round(float((x - y).mean()), 4) if n else None)}
    pr = float(np.corrcoef(x, y)[0, 1])
    sr = float(np.corrcoef(_rank(x), _rank(y))[0, 1])
    return {"n": n, "pearson": round(pr, 4), "spearman": round(sr, 4),
            "sd_ratio": round(float(x.std(ddof=1) / y.std(ddof=1)), 4),
            "slope": round(float(np.cov(x, y, ddof=1)[0, 1] / y.var(ddof=1)), 4),
            "mean_diff": round(float((x - y).mean()), 4)}


def band_check(stat: dict, kind: str, op: str, bound):
    v = (stat or {}).get(kind)
    if v is None:
        return None
    if op == ">=":
        return bool(v >= bound)
    if op == "in":
        return bool(bound[0] <= v <= bound[1])
    if op == "abs<=":
        return bool(abs(v) <= bound)
    return None


# --------------------------------------------------------------------------
# comparators (read through their own modules; never served from here)
# --------------------------------------------------------------------------
def load_comparators(season: int) -> dict:
    """The published series for one season, by mlbam, plus the official PA lines.
    Fail-soft: a missing source is an empty map and the eval says so."""
    out = {"fg": {}, "bref": {}, "savant": {}, "sprint": {}, "lines": {}, "lg": None,
           "sources": {}}
    try:
        import saber_feed
        splits = saber_feed.fetch_splits(season) or []
        rows, ambiguous, _ = saber_feed.resolve_groups(splits)
        for pid, row in rows.items():
            st = row.get("stat") or {}
            out["fg"][pid] = {k: saber_feed.run_value(st.get(k)) for k in ("baseRunning", "wSb", "wGdp", "ubr")}
        out["sources"]["fg"] = {"rows": len(splits), "players": len(rows), "ambiguous": len(ambiguous)}
    except Exception as e:  # noqa: BLE001
        out["sources"]["fg"] = {"error": str(e)[:200]}
    try:
        import war_source
        df = war_source.stint_frame("bat", provider="bwar")
        d = df[df["year_ID"] == int(season)]
        g = d.groupby("mlb_ID")[["runs_br", "runs_dp", "PA"]].sum()
        for mid, r in g.iterrows():
            if mid == mid:
                out["bref"][int(mid)] = {"runs_br": float(r["runs_br"]), "runs_dp": float(r["runs_dp"])}
        out["sources"]["bref"] = {"players": len(out["bref"]), "stale": war_source.served_stale()}
    except Exception as e:  # noqa: BLE001
        out["sources"]["bref"] = {"error": str(e)[:200]}
    try:
        import savant_running
        sv = savant_running.load(season, offline=True)
        for mid, r in sv["brv"].items():
            out["savant"][mid] = {"tot": r.get("runner_runs_tot"), "xb": r.get("runner_runs_XB"),
                                  "n_xb": r.get("N_runner_moved_XB")}
        out["sources"]["savant"] = {"players": len(sv["brv"]), "fetched_at": sv["fetched_at"]}
    except Exception as e:  # noqa: BLE001
        out["sources"]["savant"] = {"error": str(e)[:200]}
    try:
        import savant_sprint
        blob = json.loads((ROOT / "data" / "savant_sprint.json").read_text(encoding="utf-8"))
        for mid, by in (blob.get("by_mlbam") or blob.get("players") or {}).items():
            v = (by or {}).get(str(season)) if isinstance(by, dict) else None
            ft = (v or {}).get("ft_s") if isinstance(v, dict) else None
            if ft is None:
                ft = savant_sprint.speed_for(mid, season)
            if ft is not None:
                out["sprint"][int(mid)] = float(ft)
        out["sources"]["sprint"] = {"players": len(out["sprint"])}
    except Exception as e:  # noqa: BLE001
        out["sources"]["sprint"] = {"error": str(e)[:200]}
    try:
        p = ROOT / ".cache" / f"fa_statsapi_hitting_{int(season)}.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        body = raw.get("body", raw) if isinstance(raw, dict) else raw
        if isinstance(body, str):
            body = json.loads(body)
        for x in ((body.get("stats") or [{}])[0].get("splits") or []):
            pid = (x.get("player") or {}).get("id")
            if pid is None:
                continue
            st = x.get("stat") or {}
            c = out["lines"].setdefault(int(pid), defaultdict(float))
            for k in ("plateAppearances", "stolenBases", "caughtStealing", "hits", "doubles",
                      "triples", "homeRuns", "baseOnBalls", "intentionalWalks", "hitByPitch"):
                c[k] += float(st.get(k) or 0)
        out["sources"]["lines"] = {"players": len(out["lines"]),
                                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    except Exception as e:  # noqa: BLE001
        out["sources"]["lines"] = {"error": str(e)[:200]}
    try:
        import league_constants
        out["lg"] = league_constants.league_totals(int(season))
    except Exception:  # noqa: BLE001
        out["lg"] = None
    return out


def agreement_block(season: int, rows: list, comp: dict) -> dict:
    """Part 4's comparisons, aggregates only, at PA 300+ and 502+ (official PA)."""
    F = ebr.FIELDS
    ix = {f: F.index(f) for f in F}
    blk = {}
    lines = comp.get("lines") or {}
    lg = comp.get("lg") or {}
    for floor in PA_FLOORS:
        pairs = defaultdict(lambda: ([], []))
        for r in rows:
            mid = r[0]
            pa_off = (lines.get(mid) or {}).get("plateAppearances", 0)
            if pa_off < floor:
                continue
            sb = r[ix["sb"]] + r[ix["pk"]]
            xb = r[ix["xb_adv"]] + r[ix["xb_oob"]]
            dp = r[ix["dp"]]
            e = r[ix["ebr"]]
            fg = comp["fg"].get(mid) or {}
            fgc = fg_counterparts(season, fg)
            fg_sb_xb = ((fgc["sb"] + fgc["xb"]) if (fgc["sb"] is not None and fgc["xb"] is not None)
                        else None)
            br = comp["bref"].get(mid) or {}
            sv = comp["savant"].get(mid) or {}

            def add(name, a, b):
                if a is None or b is None or (isinstance(b, float) and math.isnan(b)):
                    return
                pairs[name][0].append(a)
                pairs[name][1].append(b)
            # On the 2016-on basis fg_sb_xb is baseRunning itself; through 2015 it is
            # wSb + ubr (BsR without its wGdp part), the like-for-like counterpart.
            add("sb_xb_vs_fg_bsr", sb + xb, fg_sb_xb)
            if season < FG_BASIS_FIRST_SEASON:
                add("ebr_vs_fg_bsr_full", e, fg.get("baseRunning"))
            if br:
                add("ebr_vs_bref_br_dp", e, br["runs_br"] + br["runs_dp"])
                add("dp_vs_bref_dp", dp, br["runs_dp"])
            add("sb_xb_vs_savant_total", sb + xb, sv.get("tot"))
            add("esb_vs_fg_wsb", r[ix["sb"]], fg.get("wSb"))
            add("sb_runs_vs_fg_wsb", sb, fg.get("wSb"))
            add("epk_vs_fg_wsb", r[ix["pk"]], fg.get("wSb"))
            add("xb_vs_savant_xb", xb, sv.get("xb"))
            if season <= FG_WGDP_LAST_SEASON:
                add("dp_vs_fg_wgdp", dp, fg.get("wGdp"))
            add("xb_opps_vs_savant_n_moved_xb", r[ix["opp_xb"]], sv.get("n_xb"))
            if floor == 300 and r[ix["pa"]] > 0:
                add("sprint_vs_sb_xb_per600", (sb + xb) * 600.0 / r[ix["pa"]], comp["sprint"].get(mid))
            # The wSB-parity check: FanGraphs' linear weights on the counts. The
            # SB and CS counts are the StatsAPI lines', which I2 proves equal to
            # the record's for every player of a completed season.
            ln = lines.get(mid) or {}
            if lg and lg.get("lg_wsb") is not None and fg.get("wSb") is not None:
                one_b = ln.get("hits", 0) - ln.get("doubles", 0) - ln.get("triples", 0) - ln.get("homeRuns", 0)
                den = one_b + ln.get("baseOnBalls", 0) + ln.get("hitByPitch", 0) - ln.get("intentionalWalks", 0)
                wsb = (ln.get("stolenBases", 0) * lg["run_sb"] + ln.get("caughtStealing", 0) * lg["run_cs"]
                       - lg["lg_wsb"] * den)
                add("wsb_parity_record_counts_vs_fg_wsb", wsb, fg.get("wSb"))
        blk[f"pa{floor}"] = {k: agreement(*v) for k, v in sorted(pairs.items())}
        pk_runs = pairs.get("epk_vs_fg_wsb")
        if pk_runs and len(pk_runs[0]) > 1:
            import numpy as np
            blk[f"pa{floor}"]["epk_vs_fg_wsb"]["sd_epk"] = round(float(np.std(pk_runs[0], ddof=1)), 4)
        if floor == 300:
            par = pairs.get("wsb_parity_record_counts_vs_fg_wsb")
            if par and par[0]:
                import numpy as np
                blk["pa300"]["wsb_parity_record_counts_vs_fg_wsb"]["mae"] = round(
                    float(np.mean(np.abs(np.array(par[0]) - np.array(par[1])))), 4)
    bands = {}
    for name, (comp_name, floor, kind, op, bound) in BUG_BANDS.items():
        stat = blk.get(f"pa{floor}", {}).get(comp_name)
        bands[name] = {"value": (stat or {}).get(kind), "bound": [op, bound],
                       "pass": band_check(stat, kind, op, bound)}
    return {"by_floor": blk, "bug_bands": bands, "fg_basis": fg_basis(season)}


def ewar_link_block(season: int, rows: list, comp: dict) -> dict:
    """Season sums of each part minus its FanGraphs and Baseball-Reference
    counterparts (each series summed over its own rows)."""
    F = ebr.FIELDS
    ix = {f: F.index(f) for f in F}
    s_sb = sum(r[ix["sb"]] + r[ix["pk"]] for r in rows)
    s_xb = sum(r[ix["xb_adv"]] + r[ix["xb_oob"]] for r in rows)
    s_dp = sum(r[ix["dp"]] for r in rows)
    fg = comp.get("fg") or {}
    br = comp.get("bref") or {}
    cps = [fg_counterparts(season, v) for v in fg.values()]
    f_wsb = sum((c["sb"] or 0.0) for c in cps)
    f_xb = sum((c["xb"] or 0.0) for c in cps)
    f_dp = sum((c["dp"] or 0.0) for c in cps)
    f_gdp = sum((v.get("wGdp") or 0.0) for v in fg.values())
    pre = season < FG_BASIS_FIRST_SEASON
    b_br = sum(v["runs_br"] for v in br.values())
    b_dp = sum(v["runs_dp"] for v in br.values())
    r4 = lambda v: round(v, 3)  # noqa: E731
    return {"ebr_sums": {"sb": r4(s_sb), "xb": r4(s_xb), "dp": r4(s_dp)},
            "fg_basis": fg_basis(season),
            "fangraphs": {"counterparts": {"sb": "wSb",
                                           "xb": ("ubr" if pre else "baseRunning - wSb"),
                                           "dp": ("wGdp" if pre else
                                                  "0 (no double-play part in the served BsR since 2016)")},
                          "sb_minus": r4(s_sb - f_wsb), "xb_minus": r4(s_xb - f_xb),
                          "dp_minus": r4(s_dp - f_dp),
                          "published_wgdp_sum_reference": r4(f_gdp), "n_rows": len(fg)},
            "baseball_reference": {"counterparts": {"sb_xb": "runs_br", "dp": "runs_dp"},
                                   "sb_xb_minus": r4(s_sb + s_xb - b_br), "dp_minus": r4(s_dp - b_dp),
                                   "n_rows": len(br)}}


def feed_coverage(rows: list, comp: dict) -> dict:
    """I7's last clause: the share of the feed's hitting rows with a nonzero
    baseRunning that carry an eBR row."""
    have = {r[0] for r in rows}
    nz = [mid for mid, v in (comp.get("fg") or {}).items() if (v.get("baseRunning") or 0.0) != 0.0]
    if not nz:
        return {"n_feed_nonzero": 0, "covered": 0, "share": None, "pass": None}
    cov = sum(1 for m in nz if m in have)
    share = cov / len(nz)
    return {"n_feed_nonzero": len(nz), "covered": cov, "share": round(share, 4), "pass": bool(share >= 0.99)}


def isolation_scan(root: Path = ROOT) -> dict:
    """I9: no fitted consumer imports ebr or reads its artifacts; no betting module
    reads a baserunning file or an ebr key."""
    offenders = []
    imp = re.compile(r"^\s*(import\s+ebr\b|from\s+ebr\s+import|import\s+.*\bebr\b)", re.M)
    reads = re.compile(r"(\.cache/ebr|data/ebr|ebr\.json|ebr_eval|pbp_runners)")
    bet = re.compile(r"(baserunning_|savant_running|[\"']ebr[\"'])")
    files = list(Path(root).glob("*.py")) + list((Path(root) / "tools").glob("*.py"))
    for p in sorted(files):
        name = p.name
        fitted = name.startswith(ISOLATED_PREFIXES) or name == "leaderboard_vintages.py"
        if not fitted:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if imp.search(text) or reads.search(text):
            offenders.append(name)
        elif name.startswith("betting_") and bet.search(text):
            offenders.append(name)
    return {"pass": not offenders, "offenders": offenders, "scanned": len(files)}


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------
def load_or_build_pool(raw: dict, opps: dict, frozen_dir: Path = FROZEN_DIR, pool_doc=None) -> dict:
    if pool_doc is not None:
        ebr.check_frozen_pool(pool_doc)
        return pool_doc
    path = Path(frozen_dir) / f"{ebr.EBR_VERSION}_pool.json"
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        ebr.check_frozen_pool(doc)
        return doc
    doc = ebr.frozen_pool_document(raw, opps)
    ebr.check_frozen_pool(doc)
    _write_json(path, doc, indent=1)
    return doc


def arm_tercile_fn(season: int, arm_blob: dict | None):
    """Prior-season Savant arm terciles among outfielders (primary 7, 8 or 9)."""
    if not arm_blob or season < 2021:
        return None
    prior = str(season - 1)
    vals = {}
    for mid, by in (arm_blob.get("by_mlbam") or {}).items():
        b = (by or {}).get(prior) or {}
        if b.get("primary_code") in ("7", "8", "9") and b.get("all") is not None:
            vals[int(mid)] = float(b["all"])
    if len(vals) < 30:
        return None
    import numpy as np
    xs = sorted(vals.values())
    lo, hi = float(np.quantile(xs, 1 / 3)), float(np.quantile(xs, 2 / 3))

    def f(mid):
        v = vals.get(int(mid))
        if v is None:
            return None
        return 0 if v <= lo else (1 if v <= hi else 2)
    return f


def build(*, record: Path = RECORD, out_dir: Path = OUT_DIR, frozen_dir: Path = FROZEN_DIR,
          seasons=None, today: _dt.date | None = None, generated_at: str | None = None,
          comparators=True, comparator_loader=None, pool_doc=None, arm_blob=None,
          record_data=None) -> tuple[dict, dict]:
    t0 = time.time()
    if record_data is None:
        data, man = load_record(record, seasons)
    else:
        data, man = record_data
    if not data:
        raise ebr.EbrRefusal("the runner record holds no season")
    raw = {s: ebr.season_raw(pa) for s, (pa, rn) in data.items()}
    opps = {}
    for s, (pa, rn) in data.items():
        o = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(o)
        opps[s] = o
    pool = load_or_build_pool(raw, opps, frozen_dir, pool_doc)
    K = float(pool["K"])
    if not (ebr.K_CLIP[0] <= K <= ebr.K_CLIP[1]):
        raise ebr.EbrRefusal(f"K {K} is outside [500, 5000]")
    prev_sub = None
    sub_path = Path(out_dir) / "ebr.json"
    eval_path = Path(out_dir) / "ebr_eval.json"
    if sub_path.exists():
        try:
            prev_sub = json.loads(sub_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev_sub = None
    prev_eval = None
    if eval_path.exists():
        try:
            prev_eval = json.loads(eval_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev_eval = None
    if arm_blob is None:
        try:
            arm_blob = json.loads((ROOT / "data" / "savant_arm.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            arm_blob = None
    all_rows, re24, league, identity, frozen_digests = [], {}, {}, {}, {}
    agreement_out, ewar_link, coverage, arms = {}, {}, {}, {}
    mrec = (man or {}).get("seasons") or {}
    for s in sorted(data):
        pa, rn = data[s]
        table = ebr.shrunk_table(raw[s], pool["re_pool"], K, s)
        tsha = ebr.table_sha(table)
        credits, lg, _ = ebr.season_credits(pa, rn, table, pool["xb_pool_counts"], opps=opps[s])
        players = ebr.player_rows(credits, pa, opps[s])
        rows = ebr.substrate_rows(s, players)
        sums = defaultdict(float)
        for _, _, _, part, v in credits:
            sums[part] += v
        i4 = {p: round(sums.get(p, 0.0), 6) for p in ebr.PARTS}
        F = ebr.FIELDS
        ix = {f: F.index(f) for f in F}
        bad_i6 = [r[0] for r in rows
                  if abs(sum(r[ix[p]] for p in ebr.PARTS) - r[ix["ebr"]]) > I6_TOL
                  or any(isinstance(r[ix[p]], float) and math.isnan(r[ix[p]]) for p in ebr.PARTS + ("ebr",))
                  or abs(r[ix["ebr"]]) > I6_MAX_ABS]
        xbl = lg["xb"]
        n_opp = sum(xbl["opportunities"].values())
        n_cl = sum(xbl["clamped"].values())
        digest = _sha_obj({"rows": rows, "re24": tsha, "ebr_version": ebr.EBR_VERSION})
        complete = season_complete(s, today)
        prev_digest = ((prev_sub or {}).get("cadence") or {}).get("frozen_digests", {}).get(str(s))
        if complete and prev_digest is not None and prev_digest != digest:
            raise ebr.EbrRefusal(f"season {s} is frozen and its rebuild differs "
                                 f"({digest[:12]} against {prev_digest[:12]})")
        if complete:
            frozen_digests[str(s)] = digest
        re24[str(s)] = {"sha256": tsha, "lambda": round(ebr.season_lambda(raw[s], pool["re_pool"]), 6),
                        "cells": {c: [round(table[c], 6), int(raw[s][c]["n"])] for c in ebr.CELLS},
                        "raw": {c: round(raw[s][c]["mean"], 6) for c in ebr.CELLS}}
        league[str(s)] = {"sum": i4, "n_runners": len(rows), "steal": lg["steal"], "xb": lg["xb"],
                          "dp": lg["dp"]}
        rec = (mrec.get(str(s)) or {}).get("receipts") or {}
        identity[str(s)] = {
            "complete": complete, "fg_basis": fg_basis(s),
            "record_source": (mrec.get(str(s)) or {}).get("source"),
            "I1": rec.get("I1"), "I2": rec.get("I2"), "I3": rec.get("I3"),
            "I4": {"sums": i4, "pass": all(abs(v) <= I4_TOL for v in i4.values())},
            "I5": {"cells": len(table), "monotone": True, "K": K, "sha256": tsha,
                   "pass": len(table) == 24 and ebr.K_CLIP[0] <= K <= ebr.K_CLIP[1]},
            "I6": {"rows": len(rows), "violations": len(bad_i6), "max_abs_ebr": round(max(
                (abs(r[ix["ebr"]]) for r in rows), default=0.0), 3), "pass": not bad_i6},
            "I7": {"eligible_xb": n_opp, "priced_xb": n_opp - n_cl,
                   "priced_share": round((n_opp - n_cl) / n_opp, 6) if n_opp else None,
                   "share_priced_from_cell_n50": xbl["share_priced_from_cell_n50"]},
            "I8": {"digest": digest, "frozen": complete,
                   "previous_digest": prev_digest,
                   "unchanged": (None if prev_digest is None else prev_digest == digest)},
            "sb_cs_from_record": {"sb": lg["steal"]["sb"], "cs": lg["steal"]["cs"]},
        }
        if comparators:
            comp = (comparator_loader or load_comparators)(s)
            agreement_out[str(s)] = agreement_block(s, rows, comp)
            agreement_out[str(s)]["sources"] = comp.get("sources")
            ewar_link[str(s)] = ewar_link_block(s, rows, comp)
            coverage[str(s)] = feed_coverage(rows, comp)
            i7 = identity[str(s)]["I7"]
            i7["feed_rows_covered"] = coverage[str(s)]
            i7["pass"] = bool((i7["priced_share"] or 0) >= 0.99
                              and coverage[str(s)]["pass"] is not False)
        else:
            identity[str(s)]["I7"]["pass"] = bool((identity[str(s)]["I7"]["priced_share"] or 0) >= 0.99)
        bo = ebr.Backoff(opps[s], pool["xb_pool_counts"])
        prior = [op for y in (s - 3, s - 2, s - 1) for op in opps.get(y, [])]
        arm_blk = {}
        if prior:
            arm_blk["P"] = ebr.arm_report(rows, opps[s], table, bo, ebr.arm_p_override(opps[s], prior, bo))
            arm_blk["P"]["prior_seasons"] = [y for y in (s - 3, s - 2, s - 1) if y in opps]
        else:
            arm_blk["P"] = {"note": "no prior season in the record"}
        tf = arm_tercile_fn(s, arm_blob)
        if tf is not None:
            arm_blk["F"] = ebr.arm_report(rows, opps[s], table, bo, ebr.arm_f_override(opps[s], tf, bo))
        else:
            arm_blk["F"] = {"note": "Savant arm starts in 2020; the arm uses the prior season, 2021 on"}
        arms[str(s)] = arm_blk
        all_rows.extend(rows)
    gen = generated_at or _now()
    live = [s for s in sorted(data) if not season_complete(s, today)]
    substrate = {
        "schema": 1, "model": "ebr", "ebr_version": ebr.EBR_VERSION, "generated_at": gen,
        "live_built_at": (man or {}).get("built_at"), "gate": GATE_DOC,
        "seasons": sorted(data),
        "fg_basis": {str(s): fg_basis(s) for s in sorted(data)},
        "stamps": {"K": K, "kappa": ebr.KAPPA, "pool_seasons": list(ebr.POOL_SEASONS),
                   "pool_sha256": pool["sha256"], "record_built_at": (man or {}).get("built_at"),
                   "re24_sha256": {s: re24[s]["sha256"] for s in re24}},
        "re24": re24, "league": league,
        "cadence": {"live_season": (live[-1] if live else None), "frozen_seasons": sorted(int(k) for k in frozen_digests),
                    "frozen_digests": frozen_digests},
        "fields": list(ebr.FIELDS), "rows": all_rows,
    }
    ev = {
        "schema": 1, "model": "ebr_eval", "ebr_version": ebr.EBR_VERSION, "generated_at": gen,
        "gate": GATE_DOC, "descriptive": True,
        "note": ("Same-season descriptives only. Aggregates: no per-player FanGraphs, Savant or "
                 "Baseball-Reference value is stored. Bug bands mark a value to investigate, "
                 "never a verdict on validity."),
        "stamps": substrate["stamps"],
        "pool": {k: pool[k] for k in ("K", "K_raw", "W", "tau2", "lambda", "fit_set_plays", "sha256")},
        "identity": identity, "isolation_I9": isolation_scan(),
        "league_sums": {s: league[s]["sum"] for s in league},
        "coverage": coverage, "agreement": agreement_out, "arms": arms, "ewar_link": ewar_link,
        "build_seconds": round(time.time() - t0, 1),
    }
    if prev_eval and prev_eval.get("look") is not None:
        ev["look"] = prev_eval["look"]
    for s, blk in identity.items():
        blk["I9"] = {"pass": ev["isolation_I9"]["pass"]}
        keys = ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I9")
        blk["all_pass"] = all(((blk.get(k) or {}).get("pass") is True) for k in keys)
    return substrate, ev


def write(substrate: dict, ev: dict, out_dir: Path = OUT_DIR) -> None:
    out_dir = Path(out_dir)
    if out_dir.resolve() == (ROOT / "data").resolve() or "data" in out_dir.resolve().parts[-1:]:
        raise ebr.EbrRefusal("build_ebr writes previews only, never under data/")
    _write_json(out_dir / "ebr.json", substrate)
    _write_json(out_dir / "ebr_eval.json", ev, indent=1)


def _parse_seasons(s: str):
    """A range skips 2020 (the 60-game season); the explicit token 2020 keeps it."""
    out = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(x for x in range(int(a), int(b) + 1) if x != 2020)
        elif part:
            out.append(int(part))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="eBR substrate and eval, previews only")
    ap.add_argument("--seasons", default=None)
    ap.add_argument("--no-comparators", action="store_true")
    a = ap.parse_args(argv)
    seasons = _parse_seasons(a.seasons) if a.seasons else None
    sub, ev = build(seasons=seasons, comparators=not a.no_comparators)
    write(sub, ev)
    for s, blk in sorted(ev["identity"].items()):
        bands = ((ev.get("agreement") or {}).get(s) or {}).get("bug_bands") or {}
        miss = [k for k, v in bands.items() if v.get("pass") is False]
        print(f"  {s}: rows {blk['I6']['rows']}  I1-I9 {blk['all_pass']}  "
              f"priced {blk['I7']['priced_share']}  bands missed {miss or 'none'}")
    print(f"wrote {OUT_DIR / 'ebr.json'} and {OUT_DIR / 'ebr_eval.json'} in {ev['build_seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
