# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""dynasty_basis_probe.py - measure the dynasty ranking under BOTH score drivers.

READ-ONLY. Loads the live artifacts (data/xfv.json + data/timeseries.json, the
exact inputs fantasy_export._dynasty_prospects consumes, joined the same way),
builds the dynasty pool twice - once with the retired xfv_grade_quantile as the
score driver (the pre-2026-08-16 basis) and once with THE board grade
(_board_grade) - and prints the rank-coherence numbers side by side. Writes
nothing anywhere.

The question it answers: does the ranking contradict its own visible eFV
column, and how badly, under each driver? The blend weights are UNCHANGED in
both arms (dynasty_blend's shipped constants), so the delta is the driver and
nothing else.

Pre-commit bar for the driver swap (from the approved plan): the new driver
must reach Spearman(rank, shown eFV) >= 0.95 with a worst inversion anywhere
on the served board <= 4.0 FV. The probe prints PASS/FAIL and exits nonzero
on FAIL. Scope note: the served board IS the top 300 (_dynasty_prospects cuts
there), so every metric is measured on what a reader can actually see.

Run: python tools/dynasty_basis_probe.py
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dynasty_blend                       # noqa: E402
from fantasy_export import _board_grade    # noqa: E402

DATA = ROOT / "data"
TOP_N = 300      # the served dynasty section depth (_dynasty_prospects n=300)

# The bar (approved plan, 2026-08-16). Fail it and the swap does not ship.
BAR_SPEARMAN = 0.95
BAR_WORST_INVERSION = 4.0


def _load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _season() -> int:
    """The season _dynasty_prospects actually receives: build_sections passes
    payload['season'], which sits in the head of data/fantasy.json. Read just
    that key from the file head rather than parsing the whole payload."""
    try:
        head = (DATA / "fantasy.json").read_text(encoding="utf-8")[:512]
        m = re.search(r'"season"\s*:\s*(\d{4})', head)
        if m:
            return int(m.group(1))
    except OSError:
        pass
    return datetime.now(timezone.utc).year


def build_pool(ts: dict, xfv: dict, season: int) -> list[dict]:
    """Mirror _dynasty_prospects' join exactly: timeseries roster row joined to
    the xfv.json by_player record on player_key, mlbam required. Each pooled row
    carries both candidate drivers plus the shared blend legs."""
    by_player = (xfv or {}).get("by_player") or {}
    rows = []
    for pl in (ts.get("players") or []):
        key = pl.get("player_key")
        xr = by_player.get(key) if key else None
        mid = pl.get("mlbam_id")
        if not xr or not mid:
            continue
        q = xr.get("xfv_grade_quantile")        # OLD driver (retired scale)
        if q is None:
            q = xr.get("xfv_grade")
        board = _board_grade(xr)                # NEW driver (the shown grade)
        pb = xr.get("p_bucket") or {}
        star = pb.get("star") or 0.0
        bust = xr.get("p_bust")
        if bust is None:
            bust = pb.get("bust") or 0.0
        eta = pl.get("eta")
        eta_year = eta.get("year") if isinstance(eta, dict) else (
            eta if isinstance(eta, int) else None)
        prox = dynasty_blend.eta_proximity(eta_year, season)
        sn = dynasty_blend.surplus_norm(xr.get("surplus_mm"))
        # The DISPLAYED eFV column is the board grade under both drivers (the
        # old code fell back to the quantile only when the board chain was
        # empty, which _board_grade's own fallback already covers).
        rows.append({
            "key": key, "name": pl.get("player_name"),
            "shown": board if board is not None else q,
            "score_old": (dynasty_blend.blend_score(q, star, bust, prox, sn)
                          if q is not None else None),
            "score_new": (dynasty_blend.blend_score(board, star, bust, prox, sn)
                          if board is not None else None),
        })
    return rows


def rank_under(rows: list[dict], score_field: str) -> list[dict]:
    """Sort the way production does: descending score, stable in roster order."""
    pool = [r for r in rows if r.get(score_field) is not None
            and r.get("shown") is not None]
    return sorted(pool, key=lambda r: -r[score_field])


def spearman(xs, ys) -> float | None:
    """Spearman rho, average ranks on ties, stdlib only."""
    n = len(xs)
    if n < 2:
        return None

    def _ranks(vs):
        order = sorted(range(n), key=lambda i: vs[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            mid = (i + j) / 2.0 + 1.0
            for t in range(i, j + 1):
                ranks[order[t]] = mid
            i = j + 1
        return ranks
    rx, ry = _ranks(list(xs)), _ranks(list(ys))
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def metrics(ranked: list[dict]) -> dict:
    """Rank-coherence metrics on the SERVED board: the top-300 section is the
    entire published surface (_dynasty_prospects cuts at n=300), so an
    inversion below rank 300 exists in no reader's world and is out of scope
    on purpose."""
    top = ranked[:TOP_N]
    shown = [r["shown"] for r in top]
    # a reader sees integer-rounded grades, so "visible" inversions are counted
    # on the rounded column: adjacent rows where the lower rank shows more eFV
    vis = sum(1 for a, b in zip(shown, shown[1:]) if round(b) > round(a))
    ge2 = sum(1 for a, b in zip(shown, shown[1:]) if round(b) - round(a) >= 2)
    # worst inversion anywhere on the served board (any pair, not just
    # adjacent): the biggest amount by which a lower-ranked row's shown eFV
    # exceeds a row ranked above it, in raw (unrounded) FV
    worst, running_min = 0.0, float("inf")
    for s in shown:
        if s - running_min > worst:
            worst = s - running_min
        running_min = min(running_min, s)
    # oriented so a perfectly coherent board scores +1: shown eFV against
    # negated rank (rank 1 = best)
    rho = spearman(shown, [-(i + 1) for i in range(len(top))])
    return {"n": len(ranked), "top_n": len(top),
            "adjacent_visible_inversions": vis,
            "adjacent_ge2_inversions": ge2,
            "worst_board_inversion": round(worst, 2),
            "spearman_rank_vs_shown_top300": round(rho, 4) if rho is not None else None}


def main() -> int:
    season = _season()
    print(f"dynasty basis probe  (season {season}, top {TOP_N}; weights: "
          f"star {dynasty_blend.W_STAR:g}, bust {dynasty_blend.W_BUST:g}, "
          f"eta {dynasty_blend.W_ETA:g} @ decay {dynasty_blend.ETA_DECAY:g}, "
          f"surplus {dynasty_blend.W_SURPLUS:g})")
    ts = _load("timeseries.json")
    xfv = _load("xfv.json")
    pool = build_pool(ts, xfv, season)
    print(f"joined pool: {len(pool)} prospects "
          f"(old driver scoreable {sum(1 for r in pool if r['score_old'] is not None)}, "
          f"new {sum(1 for r in pool if r['score_new'] is not None)})")

    old = rank_under(pool, "score_old")
    new = rank_under(pool, "score_new")
    m_old, m_new = metrics(old), metrics(new)

    print("\n%-38s %12s %12s" % ("metric", "old driver", "new driver"))
    for k in ("adjacent_visible_inversions", "adjacent_ge2_inversions",
              "worst_board_inversion", "spearman_rank_vs_shown_top300"):
        print("%-38s %12s %12s" % (k, m_old[k], m_new[k]))

    ro = {r["key"]: i + 1 for i, r in enumerate(old)}
    rn = {r["key"]: i + 1 for i, r in enumerate(new)}
    old300 = {r["key"] for r in old[:TOP_N]}
    new300 = {r["key"] for r in new[:TOP_N]}
    moves = [abs(rn[k] - ro[k]) for k in rn if k in ro]
    moves300 = [abs(rn[k] - ro[k]) for k in (old300 | new300)
                if k in ro and k in rn]
    print(f"\ntop {TOP_N} membership: {len(new300 - old300)} enter, "
          f"{len(old300 - new300)} leave")
    print(f"median |rank move| (both-ranked pool, n={len(moves)}): "
          f"{statistics.median(moves) if moves else None}")
    print(f"median |rank move| (served-board union, n={len(moves300)}): "
          f"{statistics.median(moves300) if moves300 else None}")

    print("\ntop 25 under the NEW driver (old rank alongside):")
    print("%4s %5s %6s %7s  %s" % ("new", "old", "move", "eFV", "name"))
    for i, r in enumerate(new[:25]):
        o = ro.get(r["key"])
        mv = ("%+d" % (o - (i + 1))) if o is not None else "n/a"
        print("%4d %5s %6s %7.1f  %s" % (i + 1, o, mv, r["shown"], r["name"]))

    rho_new = m_new["spearman_rank_vs_shown_top300"] or 0.0
    worst_new = m_new["worst_board_inversion"]
    ok = rho_new >= BAR_SPEARMAN and worst_new <= BAR_WORST_INVERSION
    print(f"\npre-commit bar: Spearman >= {BAR_SPEARMAN} and worst inversion "
          f"<= {BAR_WORST_INVERSION}  ->  "
          f"{'PASS' if ok else 'FAIL (do not ship the driver swap)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
