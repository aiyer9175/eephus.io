# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETA FanGraphs-blend gate lab (registered 2026-09-25).

Registered gate: docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md (clauses frozen and
committed before any read of the frame). Two fixed-form arms against the served
champion CH40 (estimate_eta with LEVEL_BIAS_ADJ and FORTYMAN_ADJ), computed by
eta.fg_blend_eta_year, the function the served path calls:

  arm A  max(V, rnd(0.5 CH40 + 0.5 FG))            where FanGraphs published a year
  arm B  max(V, rnd(0.5 CH40 + 0.5 FG) - on40(V))  same rows; CH40 elsewhere

plus the keep-or-remove gate for the org promotion multipliers (section 7), and
the frozen live shadow on the 2026 list (section 5).

Frame: the 2024 list only. The 2020 and 2021 lists (eFV's reserved list-vintage
frame) are refused by an assertion; the research lanes' development vintages are
spent and are only ever re-read by --dev, which prints a reproduction check and writes
nothing.

Modes (run from prospect-tracker/):
  python tools/eta_fg_blend_gate.py            the ONE registered look; refuses
                                               before 2026-09-28 and refuses a
                                               second look once the block holds one
  python tools/eta_fg_blend_gate.py --reprint  re-print the stored look
  python tools/eta_fg_blend_gate.py --dev      reproduction check on the lanes' spent
                                               development vintages (no write)

The look writes the blocks fg_blend_gate_2026_09_25 and org_timing_gate_2026_09_25
into data/eta_eval.json (read-modify-write; eta_backtest.run() carries both
forward). It never flips eta.ETA_FG_BLEND_ARM and never writes the registry.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from bisect import bisect_right
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import eta as E  # noqa: E402
import eta_backtest as eb  # noqa: E402

GATE_DOC = "docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md"
ARTIFACT = ROOT / "data" / "eta_eval.json"
BLOCK = "fg_blend_gate_2026_09_25"
ORG_BLOCK = "org_timing_gate_2026_09_25"

LOOK_NOT_BEFORE = date(2026, 9, 28)
FRAME_V = 2024
SHADOW_V = 2026
RESERVED_LV = frozenset({2020, 2021})
DEV_V = (2017, 2018, 2019, 2022, 2023)
DEV_TEST_V = (2018, 2019, 2022, 2023)
# Outcomes: debuts dated on or before the 2026 regular season's final scheduled game.
OUTCOME_CUTOFF = "2026-09-27"
LAST_SEASON = 2026          # overdue = predicted year <= this, for the 2024 frame
ACTIVE_FROM = 2025          # censored_active = pro activity in this season or later
DEV_LAST_SEASON = 2025      # the lanes' convention, --dev only
OVERDUE_LIMIT = 110
PRORATA_BASE = 2311
SEED = 20260928
B = 2000
# Org gate point-in-time window: seasons V-3..V-1 minus the reserved lists' years.
ORG_EXCLUDED_SEASONS = frozenset({2020, 2021})

CACHE = ROOT / ".cache" / "eta_fg_blend"
STATSAPI = "https://statsapi.mlb.com/api/v1"


# ── guards ──────────────────────────────────────────────────────────────────

def assert_frame_vintages(vintages, *, allow_dev: bool = False,
                          allow_shadow: bool = False) -> None:
    """The frame guard. The reserved 2020/2021 lists never pass, whatever the mode."""
    vs = tuple(vintages)
    if not vs:
        raise AssertionError("empty vintage tuple")
    for v in vs:
        if v in RESERVED_LV:
            raise AssertionError(f"list vintage {v} is eFV's reserved frame; never built here")
        ok = (v == FRAME_V or (allow_dev and v in DEV_V)
              or (allow_shadow and v == SHADOW_V))
        if not ok:
            raise AssertionError(f"list vintage {v} is not registered for this mode")


def look_allowed(today: date, artifact: dict) -> tuple[bool, str]:
    """(allowed, reason) for the one registered look."""
    if today < LOOK_NOT_BEFORE:
        return False, f"the look is owed on or after {LOOK_NOT_BEFORE.isoformat()}; today is {today.isoformat()}"
    if (artifact.get(BLOCK) or {}).get("look"):
        return False, "the registered look already ran; use --reprint"
    return True, "ok"


# ── statsapi (cached for the roster pulls, which are historical facts) ─────

def _get_json(url: str):
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:                                   # noqa: BLE001
            last = e
            time.sleep(1 + i)
    raise RuntimeError(f"statsapi fetch failed: {url}: {last}")


def _cached_json(name: str, url: str):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    j = _get_json(url)
    p.write_text(json.dumps(j), encoding="utf-8")
    return j


def team_ids(season: int) -> dict[str, int]:
    from trades import canonical_org
    j = _cached_json(f"teams_{season}.json", f"{STATSAPI}/teams?sportId=1&season={season}")
    return {(canonical_org(t["abbreviation"]) or t["abbreviation"]): t["id"] for t in j["teams"]}


def roster40(team_id: int, d: str) -> set[int]:
    j = _cached_json(f"roster40_{team_id}_{d}.json",
                     f"{STATSAPI}/teams/{team_id}/roster?rosterType=40Man&date={d}")
    return {p["person"]["id"] for p in j.get("roster", [])}


def debut_dates(mlbam_ids) -> dict[int, str | None]:
    """mlbDebutDate per MLBAM id, fetched fresh at the look (never cached)."""
    ids = sorted({int(i) for i in mlbam_ids if i})
    out: dict[int, str | None] = {}
    for k in range(0, len(ids), 100):
        chunk = ids[k:k + 100]
        j = _get_json(f"{STATSAPI}/people?personIds={','.join(map(str, chunk))}")
        for p in j.get("people", []):
            out[int(p["id"])] = p.get("mlbDebutDate")
    return out


# ── frame construction ─────────────────────────────────────────────────────

def _rnd_year(res_year: int | None, vintage: int, today_year: int) -> int | None:
    return vintage + (res_year - today_year) if res_year is not None else None


def champion_year(r: dict, *, on40: bool, org_tendency: dict | None = None,
                  today_year: int | None = None) -> int | None:
    """CH40 for one cohort row: estimate_eta with the served shaves."""
    ty = today_year if today_year is not None else date.today().year
    fm = E.FORTYMAN_ADJ.get(r["level"]) if (on40 and r["level"] in E.FORTYMAN_ADJ) else None
    res = E.estimate_eta(current_level=r["level"], age=r["age"], is_pitcher=r["is_pitcher"],
                         fv=r["fv"], stats=r.get("srow"), snapshot_date=r.get("date"),
                         level_bias_adj=E.LEVEL_BIAS_ADJ, fortyman_adj=fm,
                         org_promotion_tendency=org_tendency)
    return _rnd_year(res.eta_year, r["vintage"], ty)


def _fg_eta(tools_json: str | None, *, require_present: bool) -> int | None | bool:
    """eta_year from one FanGraphs snapshot. False = snapshot does not qualify."""
    try:
        t = json.loads(tools_json) if tools_json else None
    except ValueError:
        return False
    ex = (t or {}).get("_extras") if isinstance(t, dict) else None
    if not isinstance(ex, dict):
        return False
    if require_present:
        pres = ex.get("present")
        if not (isinstance(pres, dict) and any(isinstance(v, (int, float)) for v in pres.values())):
            return False
        return E.fg_eta_year_from_per_source({"fangraphs": {"tools": t}})
    y = E.fg_eta_year_from_per_source({"fangraphs": {"tools": t}})
    return y if y is not None else False


def build_rows(vintages, *, require_present: bool = False, washed_before: int | None = None,
               last_full_season: int | None = None) -> tuple[list[dict], dict]:
    """Cohort rows for the given list vintages with CH40, FG, on40 and org at V."""
    from trades import canonical_org
    vintages = tuple(vintages)
    assert not (set(vintages) & RESERVED_LV), "reserved list vintage requested"
    saved = (eb.VINTAGE_YEARS, eb.WASHED_BEFORE, eb.LAST_FULL_SEASON)
    eb.VINTAGE_YEARS = vintages
    if washed_before is not None:
        eb.WASHED_BEFORE = washed_before
    if last_full_season is not None:
        eb.LAST_FULL_SEASON = last_full_season
    try:
        rows, acct = eb.build_cohort()
    finally:
        eb.VINTAGE_YEARS, eb.WASHED_BEFORE, eb.LAST_FULL_SEASON = saved
    built = {r["vintage"] for r in rows}
    assert not (built & RESERVED_LV), "reserved list vintage built"
    assert built <= set(vintages), f"unexpected vintages {built - set(vintages)}"

    mlbam = json.loads((ROOT / ".cache" / "mlbam_ids.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    snap_org: dict[tuple, str] = {}
    for k, d, org in con.execute("SELECT player_key, snapshot_date, org FROM snapshots"):
        if org and org != "Office of the Commissioner" and (k, d) not in snap_org:
            co = canonical_org(org)
            if co:
                snap_org[(k, d)] = co
    fg: dict[tuple, dict] = {}
    for k, d, tj in con.execute(
            "SELECT player_key, snapshot_date, tools_json FROM snapshots "
            "WHERE source='fangraphs' AND substr(snapshot_date,1,4) IN ({}) "
            "ORDER BY snapshot_date".format(",".join(f"'{v}'" for v in vintages))):
        key = (k, int(d[:4]))
        if key in fg:
            continue
        y = _fg_eta(tj, require_present=require_present)
        if y is False:
            continue
        fg[key] = {"fg": y, "fg_date": d[:10]}
    con.close()

    tids: dict[int, dict[str, int]] = {}
    acct.update({"org_unknown_at_V": 0, "mlbam_unknown": 0, "on40": 0, "fg_present": 0})
    for r in rows:
        v = r["vintage"]
        if v not in tids:
            tids[v] = team_ids(v)
        org = snap_org.get((r["player_key"], r["date"]))
        r["org_v"] = org if org in tids[v] else None
        m = mlbam.get(r["player_key"])
        r["mlbam"] = int(m) if m else None
        on40 = 0
        if r["org_v"] is None:
            acct["org_unknown_at_V"] += 1
        elif r["mlbam"] is None:
            acct["mlbam_unknown"] += 1
        else:
            r["roster_date"] = r["date"][:10]
            on40 = 1 if r["mlbam"] in roster40(tids[v][r["org_v"]], r["roster_date"]) else 0
        r["on40"] = on40
        acct["on40"] += on40
        f = fg.get((r["player_key"], v))
        r["fg"] = f["fg"] if f else None
        r["fg_date"] = f["fg_date"] if f else None
        acct["fg_present"] += 1 if r["fg"] is not None else 0
        r["ch40"] = champion_year(r, on40=bool(on40))
    return rows, acct


def attach_outcomes_2024(rows: list[dict], acct: dict) -> list[dict]:
    """Outcomes through OUTCOME_CUTOFF: StatsAPI mlbDebutDate fills debuts the repo has
    not ingested; a debut before the listing date drops the row (pre-debut rule)."""
    dd = debut_dates(r["mlbam"] for r in rows if r.get("mlbam"))
    try:
        local = {d["player_key"]: d.get("debut_date")
                 for d in json.loads((ROOT / "data" / "debuts.json").read_text(encoding="utf-8"))
                 if d.get("player_key")}
    except (OSError, ValueError):
        local = {}
    kept = []
    acct.update({"debut_from_statsapi": 0, "dropped_debut_before_listing": 0,
                 "debut_after_cutoff_ignored": 0})
    for r in rows:
        api = dd.get(r["mlbam"]) if r.get("mlbam") else None
        ddate = api or local.get(r["player_key"])
        if ddate and ddate[:10] < r["date"][:10]:
            acct["dropped_debut_before_listing"] += 1
            continue
        if ddate and ddate[:10] > OUTCOME_CUTOFF:
            acct["debut_after_cutoff_ignored"] += 1
            ddate = None
        r["debut_date"] = ddate[:10] if ddate else None
        if r["debut_date"]:
            if r.get("outcome") != "debuted":
                acct["debut_from_statsapi"] += 1
            r["actual"] = int(r["debut_date"][:4])
            r["outcome"] = "debuted"
        elif r.get("actual") is not None and r["actual"] <= LAST_SEASON:
            r["outcome"] = "debuted"       # career_war / career_stats year, no date on file
        else:
            if r.get("outcome") == "debuted":
                r["outcome"] = "censored_active"
            r["actual"] = None
        kept.append(r)
    return kept


def c5_clean(r: dict) -> bool:
    """FanGraphs' year is usable only from a snapshot that precedes the debut."""
    if r.get("fg") is None:
        return False
    if r.get("outcome") != "debuted":
        return True
    if r.get("debut_date"):
        return r["fg_date"] < r["debut_date"]
    return int(r["fg_date"][:4]) < int(r["actual"])


def arm_year(r: dict, arm: str) -> int | None:
    fg = r["fg"] if r.get("c5_ok") else None
    return E.fg_blend_eta_year(r["ch40"], fg, r["vintage"], on40=bool(r["on40"]), arm=arm)


# ── scoring ────────────────────────────────────────────────────────────────

def score(pairs) -> dict:
    if not pairs:
        return {"n": 0}
    err = [p - a for p, a in pairs]
    return {"n": len(pairs), "mae": round(sum(abs(e) for e in err) / len(err), 4),
            "within_1y": round(sum(1 for e in err if abs(e) <= 1) / len(err), 4),
            "bias": round(sum(err) / len(err), 4)}


def paired_boot(rows: list[dict], f_cmp, f_arm, *, seed: int = SEED, b: int = B) -> dict:
    """Player-clustered paired bootstrap. dMAE = MAE(cmp) - MAE(arm) (positive = arm
    better); dW1 = W1(arm) - W1(cmp). A fresh generator per comparison, so every
    comparison's draws are reproducible on their own."""
    by: dict[str, list] = {}
    for r in rows:
        a, c, y = f_arm(r), f_cmp(r), r["actual"]
        by.setdefault(r["player_key"], []).append(
            (abs(c - y), abs(a - y), abs(c - y) <= 1, abs(a - y) <= 1))
    keys = list(by)
    sums = np.array([np.array(by[k], float).sum(0) for k in keys])
    cnt = np.array([len(by[k]) for k in keys])
    rng = np.random.default_rng(seed)
    dm = np.empty(b)
    dw = np.empty(b)
    for i in range(b):
        idx = rng.integers(0, len(keys), len(keys))
        s = sums[idx].sum(0)
        n = cnt[idx].sum()
        dm[i] = (s[0] - s[1]) / n
        dw[i] = (s[3] - s[2]) / n
    s = sums.sum(0)
    n = cnt.sum()
    p = 2 * min(float((dm <= 0).mean()), float((dm >= 0).mean()))
    return {"n": int(n), "players": len(keys),
            "dMAE": round(float((s[0] - s[1]) / n), 4),
            "MDE95": round(1.96 * float(dm.std()), 4),
            "ci_dMAE": [round(float(np.percentile(dm, 2.5)), 4), round(float(np.percentile(dm, 97.5)), 4)],
            "p_dMAE": round(max(p, 1.0 / b), 6),
            "dW1": round(float((s[3] - s[2]) / n), 4),
            "ci_dW1": [round(float(np.percentile(dw, 2.5)), 4), round(float(np.percentile(dw, 97.5)), 4)]}


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm step-down: the smallest p tested at alpha/m, the next at alpha/(m-1), ..."""
    order = sorted(pvals, key=lambda k: pvals[k])
    out = {k: False for k in pvals}
    m = len(order)
    for i, k in enumerate(order):
        if pvals[k] <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out


def overdue(rows: list[dict], f, last: int) -> int:
    return sum(1 for r in rows if f(r) is not None and f(r) <= last)


def decide(c: dict[str, dict], c6: dict) -> dict:
    """Section 4's decision rule over per-arm clause results."""
    cand = {a: all(c[a][k] for k in ("C1", "C2", "C3", "C4", "C5")) for a in c}
    if cand.get("A") and cand.get("B"):
        rec = "B" if c6.get("pass") else "A"
    elif cand.get("B"):
        rec = "B"
    elif cand.get("A"):
        rec = "A"
    else:
        rec = None
    return {"ship_candidate": cand, "recommended_arm": rec,
            "verdict": "SHIP CANDIDATE (owner's call)" if rec else "NO SHIP"}


def run_blend_gate(rows: list[dict], log) -> dict:
    for r in rows:
        r["c5_ok"] = c5_clean(r)
    frame = [r for r in rows if r["ch40"] is not None]
    deb = [r for r in frame if r["outcome"] == "debuted"]
    cens = [r for r in frame if r["outcome"] == "censored_active"]
    fgdeb = [r for r in deb if r["c5_ok"]]
    ch = lambda r: r["ch40"]                                        # noqa: E731
    arms = {a: (lambda r, a=a: arm_year(r, a)) for a in E.FG_BLEND_ARMS}
    out: dict = {"n": {"rows": len(frame), "debuted": len(deb), "censored_active": len(cens),
                       "washed_out": sum(1 for r in frame if r["outcome"] == "washed_out"),
                       "fg_debuted_c5_clean": len(fgdeb),
                       "fg_rows_failing_c5": sum(1 for r in frame if r.get("fg") is not None and not r["c5_ok"])}}
    log(f"frame: rows={len(frame)} debuted={len(deb)} censored_active={len(cens)} "
        f"fg_debuted_c5_clean={len(fgdeb)} fg_rows_failing_c5={out['n']['fg_rows_failing_c5']}")
    boots = {a: paired_boot(fgdeb, ch, f) for a, f in arms.items()}
    hp = holm({a: boots[a]["p_dMAE"] for a in arms})
    pro_rata = round(OVERDUE_LIMIT * len(cens) / PRORATA_BASE, 1)
    od_ch = overdue(cens, ch, LAST_SEASON)
    clauses: dict = {}
    for a, f in arms.items():
        bt = boots[a]
        c1 = bt["dMAE"] > 0 and bt["dMAE"] > bt["MDE95"] and hp[a]
        c2 = bt["dW1"] > 0 and bt["ci_dW1"][0] > 0
        pooled = score([(f(r), r["actual"]) for r in deb])
        champ = score([(ch(r), r["actual"]) for r in deb])
        c3 = pooled["mae"] < champ["mae"]
        od = overdue(cens, f, LAST_SEASON)
        c4 = od - od_ch <= OVERDUE_LIMIT
        clauses[a] = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": True,
                      "row_matched": {"CH40": score([(ch(r), r["actual"]) for r in fgdeb]),
                                      a: score([(f(r), r["actual"]) for r in fgdeb])},
                      "boot_vs_CH40": bt, "holm_pass": hp[a],
                      "pooled": {"CH40": champ, a: pooled},
                      "overdue": {"CH40": od_ch, a: od, "delta": od - od_ch, "limit": OVERDUE_LIMIT,
                                  "pro_rata_flag": pro_rata},
                      "moved": {"rows": sum(1 for r in frame if f(r) != ch(r)),
                                "earlier": sum(1 for r in frame if f(r) < ch(r)),
                                "later": sum(1 for r in frame if f(r) > ch(r))}}
        log(f"arm {a} C1 ROW-MATCHED MAE: n={bt['n']} CH40 {clauses[a]['row_matched']['CH40']['mae']} vs "
            f"{clauses[a]['row_matched'][a]['mae']}; dMAE {bt['dMAE']:+.4f} MDE95 {bt['MDE95']} "
            f"CI95 [{bt['ci_dMAE'][0]:+.4f}, {bt['ci_dMAE'][1]:+.4f}] p {bt['p_dMAE']} Holm {'pass' if hp[a] else 'fail'} "
            f"-> {'PASS' if c1 else 'FAIL'}")
        log(f"arm {a} C2 ROW-MATCHED WITHIN-1Y: CH40 {clauses[a]['row_matched']['CH40']['within_1y']} vs "
            f"{clauses[a]['row_matched'][a]['within_1y']}; d {bt['dW1']:+.4f} CI95 [{bt['ci_dW1'][0]:+.4f}, "
            f"{bt['ci_dW1'][1]:+.4f}] -> {'PASS' if c2 else 'FAIL'}")
        log(f"arm {a} C3 POOLED MAE (n={pooled['n']}): {pooled['mae']} vs CH40 {champ['mae']} -> "
            f"{'PASS' if c3 else 'FAIL'}")
        log(f"arm {a} C4 OVERDUE: censored_active n={len(cens)}; CH40 {od_ch} vs {od}; delta "
            f"{od - od_ch:+d} vs limit +{OVERDUE_LIMIT} (pro-rata flag {pro_rata}) -> {'PASS' if c4 else 'FAIL'}")
    bab = paired_boot(fgdeb, arms["A"], arms["B"])
    od_a, od_b = overdue(cens, arms["A"], LAST_SEASON), overdue(cens, arms["B"], LAST_SEASON)
    c6 = {"boot_B_over_A": bab, "overdue_A": od_a, "overdue_B": od_b,
          "pass": bab["ci_dMAE"][0] > 0 and od_b - od_a <= OVERDUE_LIMIT}
    log(f"C6 B OVER A: dMAE {bab['dMAE']:+.4f} CI95 [{bab['ci_dMAE'][0]:+.4f}, {bab['ci_dMAE'][1]:+.4f}]; "
        f"overdue B-A {od_b - od_a:+d} -> {'PASS' if c6['pass'] else 'FAIL'}")
    out["clauses"] = clauses
    out["C6"] = c6
    out["by_level"] = {lv: {"CH40": score([(ch(r), r["actual"]) for r in fgdeb if r["level"] == lv]),
                            **{a: score([(f(r), r["actual"]) for r in fgdeb if r["level"] == lv])
                               for a, f in arms.items()}}
                       for lv in sorted({r["level"] for r in fgdeb}, key=lambda x: (x is None, x or ""))}
    out["coverage_fg_share_of_debuted"] = round(len(fgdeb) / len(deb), 4) if deb else None
    out["decision"] = decide(clauses, c6)
    log(f"VERDICT: {out['decision']['verdict']}; recommended arm {out['decision']['recommended_arm']}")
    return out


def point_in_time_org_tendencies(rows: list[dict], level_changes: dict) -> dict[str, dict]:
    """{listing date: {org: tendency}} per section 7: seasons V-3..V-1 minus 2020/2021,
    events before the listing date, each event's player at his org on his latest
    snapshot dated on or before the listing date."""
    from trades import canonical_org
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    hist: dict[str, list] = {}
    for k, d, org in con.execute(
            "SELECT player_key, snapshot_date, org FROM snapshots WHERE org IS NOT NULL "
            "ORDER BY snapshot_date"):
        co = canonical_org(org) if org != "Office of the Commissioner" else None
        if co:
            hist.setdefault(k, []).append((d[:10], co))
    con.close()
    out: dict[str, dict] = {}
    for d in sorted({r["date"][:10] for r in rows}):
        v = int(d[:4])
        seasons = {y for y in range(v - 3, v)} - ORG_EXCLUDED_SEASONS
        org_by_key = {}
        for k, h in hist.items():
            i = bisect_right([x[0] for x in h], d)
            if i:
                org_by_key[k] = h[i - 1][1]
        out[d] = E.org_promotion_tendencies(level_changes, org_by_key, before=d, seasons=seasons)
    return out


def run_org_gate(rows: list[dict], log) -> dict:
    import run_monthly
    lc = run_monthly._derive_all_level_changes()
    tend = point_in_time_org_tendencies(rows, lc)
    for r in rows:
        t = (tend.get(r["date"][:10]) or {}).get(r["org_v"]) if r.get("org_v") else None
        r["keep"] = champion_year(r, on40=bool(r["on40"]), org_tendency=t)
    frame = [r for r in rows if r["ch40"] is not None and r["keep"] is not None]
    deb = [r for r in frame if r["outcome"] == "debuted"]
    cens = [r for r in frame if r["outcome"] == "censored_active"]
    rem = lambda r: r["ch40"]                                       # noqa: E731
    keep = lambda r: r["keep"]                                      # noqa: E731
    bt = paired_boot(deb, rem, keep)
    od_r, od_k = overdue(cens, rem, LAST_SEASON), overdue(cens, keep, LAST_SEASON)
    moved = sum(1 for r in frame if r["keep"] != r["ch40"])
    survives = moved > 0 and bt["dMAE"] > 0 and bt["ci_dMAE"][0] > 0 and od_k - od_r <= OVERDUE_LIMIT
    out = {"n_debuted": len(deb), "n_censored_active": len(cens), "rows_moved": moved,
           "REMOVE": score([(rem(r), r["actual"]) for r in deb]),
           "KEEP": score([(keep(r), r["actual"]) for r in deb]),
           "boot_KEEP_vs_REMOVE": bt, "overdue": {"REMOVE": od_r, "KEEP": od_k, "delta": od_k - od_r},
           "orgs_with_tendency_by_date": {d: len(t) for d, t in tend.items()},
           "verdict": "KEEP" if survives else "REMOVE"}
    log(f"ORG GATE: debuted n={len(deb)} rows moved {moved}; REMOVE {out['REMOVE'].get('mae')} vs KEEP "
        f"{out['KEEP'].get('mae')}; dMAE {bt['dMAE']:+.4f} CI95 [{bt['ci_dMAE'][0]:+.4f}, {bt['ci_dMAE'][1]:+.4f}]; "
        f"overdue KEEP-REMOVE {od_k - od_r:+d} -> {out['verdict']}")
    return out


def shadow_rows() -> list[dict]:
    """Frozen predictions on the 2026 list. No outcome field is kept."""
    assert_frame_vintages((SHADOW_V,), allow_shadow=True)
    rows, _ = build_rows((SHADOW_V,))
    out = []
    for r in rows:
        r["c5_ok"] = r.get("fg") is not None      # no debut is read for a shadow row
        out.append({"player_key": r["player_key"], "listing_date": r["date"][:10],
                    "level": r["level"], "on40": r["on40"], "fg_eta_year": r["fg"],
                    "CH40": r["ch40"], "A": arm_year(r, "A"), "B": arm_year(r, "B")})
    return out


# ── modes ──────────────────────────────────────────────────────────────────

def _read_artifact() -> dict:
    try:
        return json.loads(ARTIFACT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def run_look() -> int:
    art = _read_artifact()
    ok, why = look_allowed(date.today(), art)
    if not ok:
        print(f"REFUSED: {why}")
        return 2
    lines: list[str] = []

    def log(s: str) -> None:
        lines.append(s)
        print(s)

    assert_frame_vintages((FRAME_V,))
    rows, acct = build_rows((FRAME_V,), washed_before=ACTIVE_FROM, last_full_season=LAST_SEASON)
    rows = attach_outcomes_2024(rows, acct)
    log(f"cohort 2024: {json.dumps(acct, sort_keys=True)}")
    blend = run_blend_gate(rows, log)
    org = run_org_gate(rows, log)
    shadow = shadow_rows()
    log(f"live shadow frozen: 2026 list rows={len(shadow)}; scored after the 2028 regular season")
    stamp = date.today().isoformat()
    art = _read_artifact()
    art[BLOCK] = {"gate_doc": GATE_DOC, "look": stamp, "frame": "list vintage 2024",
                  "outcome_cutoff": OUTCOME_CUTOFF, "seed": SEED, "B": B,
                  "accounting": acct, **blend, "verbatim": lines,
                  "live_shadow_2026": {"frozen": stamp, "score_not_before":
                                       "the day after the 2028 regular season's final scheduled game",
                                       "rows": shadow}}
    art[ORG_BLOCK] = {"gate_doc": GATE_DOC, "look": stamp, "frame": "list vintage 2024", **org}
    ARTIFACT.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print(f"wrote {BLOCK} and {ORG_BLOCK} into {ARTIFACT.name}")
    return 0


def run_reprint() -> int:
    blk = _read_artifact().get(BLOCK) or {}
    if not blk.get("look"):
        print("no registered look on record")
        return 1
    print("\n".join(blk.get("verbatim") or []))
    return 0


def run_dev() -> int:
    """Reproduction check on the lanes' spent development vintages; prints, writes nothing.
    Reproduces the lanes' blend frame (FanGraphs snapshots carrying present grades)."""
    assert_frame_vintages(DEV_V, allow_dev=True)
    rows, acct = build_rows(DEV_V, require_present=True)
    for r in rows:
        r["c5_ok"] = r.get("fg") is not None
    fr = [r for r in rows if r["ch40"] is not None and r["vintage"] in DEV_TEST_V
          and r["outcome"] == "debuted" and r["fg"] is not None]
    cens = [r for r in rows if r["ch40"] is not None and r["outcome"] == "censored_active"
            and r["fg"] is not None]
    print(f"DEV (spent vintages {DEV_V}; adjudicates nothing): on40={acct['on40']} "
          f"org_unknown={acct['org_unknown_at_V']}")
    for name, f in (("CH40", lambda r: r["ch40"]), ("A", lambda r: arm_year(r, "A")),
                    ("B", lambda r: arm_year(r, "B"))):
        s = score([(f(r), r["actual"]) for r in fr])
        print(f"  {name}: {s}; overdue(<= {DEV_LAST_SEASON}) {overdue(cens, f, DEV_LAST_SEASON)} of {len(cens)}")
    print("  lane reference (etaroster blend frame, n 2391): CH40 1.130, BL50 0.971, BR1 0.953; "
          "overdue 495 / 546 / 546 of 1262")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--reprint", action="store_true")
    g.add_argument("--dev", action="store_true")
    a = ap.parse_args(argv)
    if a.reprint:
        return run_reprint()
    if a.dev:
        return run_dev()
    return run_look()


if __name__ == "__main__":
    sys.exit(main())
