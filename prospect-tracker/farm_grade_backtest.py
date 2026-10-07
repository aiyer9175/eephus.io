# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Farm grade validation (model-audit Phase 4b, WS-8) — does ranking
systems the way the farm tree does PREDICT future system output?

Historical farm grades were never snapshotted (the tree is recomputed
per export), so the literal farm_tree_v40 letter cannot be backtested.
What CAN be validated — the Gate-3 "reduced analog" pattern — is the
tree's dominant signal: the FINANCIAL CORE. farm_score's tiebreaker
blends surplus_z / dvm_z / grad-WAR_z, and surplus is the load-bearing
branch; everything else nudges ranks within a tier. So the gate asks:

  Rank all 30 orgs at vintage Y by Σ surplus(FV) over their listed
  prospects (today's value framework applied to vintage FVs — the same
  reconstruction the real surplus backtest validated). Does that
  ranking predict the org's REALIZED graduate production in Y..Y+3
  better than a dumb prospect-count baseline?

  ANALOGS    a) sum_surplus_mm  — Σ calibrated surplus per org (the
                financial core, convex: stars dominate)
             b) sum_expected_war — Σ FV-anchor 6y WAR (linear FV mass)
             c) count            — # listed prospects (the baseline)
             d) count_fv50plus   — # listed at FV ≥ 50 (top-end depth)
  REALIZED   per org-vintage: every prospect on the org's vintage-Y
             list who debuted in [Y, Y+3], summing career_war bWAR over
             seasons Y..Y+3 (negative WAR counts as produced — the
             grade claims production, not roster decisions).
  METRIC     Spearman rank correlation across orgs, per vintage
             (2018-2022 — the last vintage whose Y+3 window closed in
             2025) + pooled mean. The analog must beat (c) to claim
             the tree ranks better than "who has the most names".

Caveats stated: (1) realized output through Y+3 misses late bloomers —
it's a promotion-window metric, matching the grade's product claim
("how strong is this system NOW"); (2) prediction uses TODAY'S surplus
config on vintage FVs (the documented convention from
surplus_backtest_real); (3) org assignment = modal org across the
vintage's earliest per-source snapshots (trades mid-window not
re-attributed).

Artifact: data/farm_grade_eval.json.
Run: python farm_grade_backtest.py
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import storage
import value_framework as vf

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "farm_grade_eval.json"

VINTAGE_YEARS = (2018, 2019, 2020, 2021, 2022)
WINDOW = 3            # realized window = Y .. Y+WINDOW
MIN_ORG_N = 3         # orgs with fewer vintage listings don't rank
# franchise code drift + non-team rows in old snapshots
_ORG_ALIAS = {"OAK": "ATH"}
_ORG_JUNK = {"Office of the Commissioner"}


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None

    def _ranks(v: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx * vy) ** 0.5, 4)


def _load() -> tuple[dict, dict, dict]:
    """listings {(pk, Y): {fv, org}}, war_seasons {pk: {year: war}},
    bio {pk: {position, is_pitcher}}."""
    with storage.connect() as con:
        rows = con.execute("""
            SELECT player_key, source, substr(snapshot_date,1,4) AS y,
                   MIN(snapshot_date) AS d
            FROM snapshots WHERE fv IS NOT NULL
              AND substr(snapshot_date,1,4) IN ({})
            GROUP BY player_key, source, y""".format(
            ",".join(f"'{y}'" for y in VINTAGE_YEARS))).fetchall()
        per: dict[tuple, list] = {}
        for r in rows:
            s = con.execute(
                "SELECT fv, org FROM snapshots WHERE player_key=? AND source=? AND snapshot_date=?",
                (r["player_key"], r["source"], r["d"])).fetchone()
            if s and s["fv"] is not None:
                per.setdefault((r["player_key"], int(r["y"])), []).append(
                    (float(s["fv"]), s["org"]))
        listings = {}
        for key, vals in per.items():
            orgs = [_ORG_ALIAS.get(o, o) for _, o in vals
                    if o and o not in _ORG_JUNK]
            listings[key] = {
                "fv": statistics.median(v for v, _ in vals),
                "org": Counter(orgs).most_common(1)[0][0] if orgs else None}
        cw = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
        bio = {r["player_key"]: dict(r) for r in con.execute(
            "SELECT player_key, position, is_pitcher FROM players")}
    return listings, cw, bio


def _gap_ci_vs_count(org_rows: list[tuple]) -> dict:
    """LIBRARY_14: the paired interval on the gap between the surplus-mass
    ranking and the prospect-count baseline, each the mean over vintages of
    its per-vintage Spearman with realized output (surplus minus count, so
    positive means the financial core ranks better). Team-clustered: an org
    is drawn with all its vintages, which are the same club's farm."""
    import numpy as np
    import gap_intervals as gi
    vy = np.array([r[1] for r in org_rows])
    sur = np.array([r[2] for r in org_rows], float)
    cnt = np.array([r[3] for r in org_rows], float)
    real = np.array([r[4] for r in org_rows], float)

    def gaps(idx):
        rs, rc = [], []
        for y in VINTAGE_YEARS:
            sel = idx[vy[idx] == y]
            a, b = gi.spearman(sur[sel], real[sel]), gi.spearman(cnt[sel], real[sel])
            if a is not None:
                rs.append(a)
            if b is not None:
                rc.append(b)
        return {"spearman": float(np.mean(rs) - np.mean(rc)) if rs and rc else None}

    return gi.paired_cluster_interval([r[0] for r in org_rows], gaps, seed=gi.SEED,
                                      cluster="team (org): a club is drawn with every vintage")


def run(persist: bool = True) -> dict:
    listings, cw, bio = _load()
    by_org_vintage: dict[tuple, list] = defaultdict(list)
    for (pk, vy), li in listings.items():
        if li["org"]:
            by_org_vintage[(li["org"], vy)].append((pk, li["fv"]))

    per_vintage: dict[int, dict] = {}
    pooled: dict[str, list[float]] = defaultdict(list)
    org_rows: list[tuple] = []      # (org, vintage, surplus, count, realized)
    for vy in VINTAGE_YEARS:
        orgs = sorted({org for (org, y) in by_org_vintage if y == vy})
        preds: dict[str, dict[str, float]] = {}
        realized: dict[str, float] = {}
        for org in orgs:
            members = by_org_vintage[(org, vy)]
            if len(members) < MIN_ORG_N:
                continue
            sur = war6 = cnt50 = 0.0
            real = 0.0
            for pk, fv in members:
                b = bio.get(pk) or {}
                is_pit = vf.is_pitcher_position(b.get("position"))
                s = vf.point_estimate_surplus_usd(fv, is_pit, b.get("position"))
                if s:
                    sur += s / 1e6
                war6 += vf.fv_to_6yr_avg_war(fv) or 0.0
                if fv >= 50:
                    cnt50 += 1
                seasons = cw.get(pk) or {}
                debut = min(seasons) if seasons else None
                if debut is not None and vy <= debut <= vy + WINDOW:
                    real += sum(w_ for y_, w_ in seasons.items()
                                if vy <= y_ <= vy + WINDOW)
            preds[org] = {"sum_surplus_mm": round(sur, 1),
                          "sum_expected_war": round(war6, 1),
                          "count": len(members),
                          "count_fv50plus": cnt50}
            realized[org] = round(real, 1)
        common = [o for o in preds if o in realized]
        ys = [realized[o] for o in common]
        org_rows += [(o, vy, preds[o]["sum_surplus_mm"], preds[o]["count"],
                      realized[o]) for o in common]
        row = {"n_orgs": len(common),
               "spearman": {k: _spearman([preds[o][k] for o in common], ys)
                            for k in ("sum_surplus_mm", "sum_expected_war",
                                      "count", "count_fv50plus")},
               "realized_total_war": round(sum(ys), 1)}
        per_vintage[vy] = row
        for k, v in row["spearman"].items():
            if v is not None:
                pooled[k].append(v)

    mean_rho = {k: round(statistics.mean(v), 4) for k, v in pooled.items()}
    beats = (mean_rho.get("sum_surplus_mm", 0) > mean_rho.get("count", 0))
    out = {
        "generated_at": date.today().isoformat(),
        "vintage_years": list(VINTAGE_YEARS),
        "window_years": WINDOW,
        "conventions": {
            "scope": "REDUCED ANALOG — the farm tree's financial core "
                     "(sum of surplus over vintage FVs), not the literal "
                     "v40 letter (grades were never snapshotted)",
            "org": "modal org across earliest per-source vintage snapshots",
            "realized": "sum of graduates' bWAR over seasons Y..Y+3, debut in [Y, Y+3]",
            "prediction_pricing": "today's calibrated value framework on vintage FVs",
        },
        "per_vintage": {str(k): v for k, v in per_vintage.items()},
        "mean_spearman": mean_rho,
        "mean_spearman_gap_ci_vs_count": _gap_ci_vs_count(org_rows) if org_rows else None,
        "verdict": {
            "financial_core_beats_count": beats,
            "summary": ("the surplus-mass ranking out-predicts the "
                        "prospect-count baseline" if beats else
                        "the surplus-mass ranking does NOT beat the "
                        "prospect-count baseline — the tree's financial "
                        "dominance is not validated"),
        },
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print("mean spearman:", rep["mean_spearman"])
    for vy, row in rep["per_vintage"].items():
        print(vy, row["n_orgs"], row["spearman"], "realized", row["realized_total_war"])
    print("verdict:", rep["verdict"]["summary"])
