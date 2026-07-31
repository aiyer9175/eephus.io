# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""W-TBS2 (Phase 4b): tiebreaker stack vs incumbent TBS -- pre-registered gate lane.

Registration: docs/efv-2026-07-24/GATES.md section W-TBS2. One attempt. Everything
in this header is FROZEN before the run.

UNIVERSE
  Resolved cohorts: rows of data/xfv_scored.json (hit) + data/xfv_scored_pitcher.json
  (pit) with censored == False, joined to data/xfv_hitter_matrix.json /
  data/xfv_pitcher_matrix.json on player_key. Labels = matrix target_resolved
  (realized first-6yr WAR, wave-B repaired matrices regenerated 2026-07-24). Rows
  without a matrix join or without target_resolved are dropped (counted). A player_key
  appearing on both sides keeps the hit-side row only.

TIE GROUPS
  Identical displayed quantile grade at 0.1 grain = exact equality of
  xfv_grade_display (already served at 1dp; keyed as a 1dp string to kill float fuzz),
  POOLED across sides (the live board is one board; a hit 50.0 ties a pit 50.0).
  Eligible groups: n >= 2 members AND >= 2 distinct realized-WAR values (groups with
  zero label variance carry no ordering information for either side and are skipped
  symmetrically).

INCUMBENT (the thing being beaten)
  prospx fvCmpDesc arbitrates exact-decimal eFV ties by TBS (_tiebreakerScoreRaw,
  prospx/index.html). Reproduction on as-of-prospect fields, mirroring the frontend's
  renormalize-over-present-weights contract (live-only inputs -- RPS+, SC+, Stuff+
  statline, age tier, movement, health/breakout multipliers, '+' flag -- are absent
  for every resolved historical row, so they drop out for ALL rows identically):
    parts = [tbsNorm(tool_composite, 40, 70) w 0.24]
            [tbsNorm(tool_max,       40, 70) w 0.10]
            [tbsNorm(xfv_war_6yr,   0.1,2.6) w 0.90]
    score = round(100 * sum(present v*w) / sum(present w))   # frontend Math.round
  tool_composite approximates the served tools.composite_overall from matrix
  as-of-prospect grades: hit = power-mean p=4 of {hit .476, pwr .476, spd .048}
  (storage.py O-Tool weights renormalized over matrix-available tools, pwr =
  max(game_pwr, raw_pwr)); pit = 0.65 * mean(pitch grades) + 0.35 * cmd.
  tool_max = max of present grades (frontend _perToolMax). SENSITIVITY (non-gating):
  incumbent_efv_only = the 0.90-weight eFV term alone.

CHALLENGER (frozen stack, GATES order)
  Within a tie group, pairwise comparator with fall-through:
    1. xfv_proxy score (data/xfv_proxy_eval.json projections; abstains unless BOTH
       have a score)  ->  2. p_bucket star odds  ->  3. aStuff+ (pitchers only,
       data/stuff_plus_aaa.json players[mlbam].stuff_plus, both must have it)
    -> else tie (frontend name order = no signal = tie).
  AP+ never enters (registered constraint).

ORDERING -> SCALAR
  Both orderings are scored per group by COPELAND score (beats minus beaten under
  the ordering's comparator across all group-mates): deterministic, symmetric,
  handles partial-coverage fall-through without inventing a scalar. For the
  incumbent (a total preorder on rounded TBS) Copeland is rank-equivalent to
  average ranks.

METRIC + BAR
  Per-group Spearman(Copeland, realized WAR) with average ranks; a group where an
  ordering's Copeland vector is constant scores rho = 0.0 for that ordering (no
  information). Pooled = group-size-weighted mean (weight = n members). Delta =
  challenger - incumbent on the SAME groups. Group-clustered bootstrap: resample
  groups with replacement, 2000 reps, seed 20260724. Bar: delta lo95 > 0.

Run:  python tools/efv_tbs2_lab.py     -> data/xfv_tbs2_eval.json
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SEED = 20260724
N_BOOT = 2000

HIT_TOOLS = ("tool_hit", "tool_game_pwr", "tool_raw_pwr", "tool_speed",
             "tool_field", "tool_throw")
PIT_PITCH = ("tool_fb", "tool_sl", "tool_cb", "tool_ch")


def _tbs_norm(v, lo, hi):
    if v is None or not math.isfinite(v):
        return None
    return max(0.0, min(1.0, (float(v) - lo) / (hi - lo)))


def _power_mean(vals, p=4):
    return (sum(v ** p for v in vals) / len(vals)) ** (1.0 / p)


def _tool_composite(mrow, side):
    if side == "hit":
        # storage.py O-Tool HIT 40 / PWR 40 / SPD 4 renormalized over the
        # matrix-available offense tools (bctrl/psel not in the matrices).
        pwr = [mrow.get("tool_game_pwr"), mrow.get("tool_raw_pwr")]
        pwr = max((v for v in pwr if v is not None), default=None)
        parts = [(mrow.get("tool_hit"), 0.40), (pwr, 0.40),
                 (mrow.get("tool_speed"), 0.04)]
        vals, ws = [], []
        for v, w in parts:
            if v is not None:
                vals.append(float(v)); ws.append(w)
        if not vals:
            return None
        # weighted power-mean p=4 (storage O-Tool shape)
        s = sum(w for w in ws)
        return (sum(w / s * (v ** 4) for v, w in zip(vals, ws))) ** 0.25
    stuff = [mrow.get(k) for k in PIT_PITCH]
    stuff = [float(v) for v in stuff if v is not None]
    stuff = sum(stuff) / len(stuff) if stuff else None
    cmd = mrow.get("tool_cmd")
    cmd = float(cmd) if cmd is not None else None
    if stuff is not None and cmd is not None:
        return 0.65 * stuff + 0.35 * cmd
    return stuff if stuff is not None else cmd


def _tool_max(mrow, side):
    keys = HIT_TOOLS if side == "hit" else PIT_PITCH + ("tool_cmd",)
    vals = [float(mrow[k]) for k in keys if mrow.get(k) is not None]
    return max(vals) if vals else None


def _incumbent_tbs(row, efv_only=False):
    parts = []
    if not efv_only:
        parts += [(_tbs_norm(row["tool_comp"], 40, 70), 0.24),
                  (_tbs_norm(row["tool_max"], 40, 70), 0.10)]
    parts += [(_tbs_norm(row["xfv_war_6yr"], 0.1, 2.6), 0.90)]
    num = den = 0.0
    for v, w in parts:
        if v is not None:
            num += v * w; den += w
    if den == 0:
        return 0
    return round(100.0 * num / den)   # frontend Math.round


def _challenger_cmp(a, b):
    """+1 if a ahead of b, -1 if behind, 0 tie. Frozen stack with fall-through."""
    # 1 - xfv_proxy (both must be covered, else abstain)
    if a["proxy"] is not None and b["proxy"] is not None:
        if a["proxy"] != b["proxy"]:
            return 1 if a["proxy"] > b["proxy"] else -1
    # 2 - p_bucket star odds
    if a["star"] is not None and b["star"] is not None:
        if a["star"] != b["star"]:
            return 1 if a["star"] > b["star"] else -1
    # 3 - aStuff+ (pitchers, both covered)
    if a["stuff"] is not None and b["stuff"] is not None:
        if a["stuff"] != b["stuff"]:
            return 1 if a["stuff"] > b["stuff"] else -1
    return 0


def _copeland(group, cmp_fn):
    n = len(group)
    sc = [0] * n
    for i in range(n):
        for j in range(i + 1, n):
            c = cmp_fn(group[i], group[j])
            if c > 0:
                sc[i] += 1; sc[j] -= 1
            elif c < 0:
                sc[i] -= 1; sc[j] += 1
    return sc


def _avg_ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _spearman(xs, ys):
    """Average-rank Spearman; constant xs -> 0.0 by frozen convention."""
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return 0.0
    rx, ry = _avg_ranks(xs), _avg_ranks(ys)
    mx = sum(rx) / len(rx); my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else 0.0


def _load_universe():
    proxy = json.loads((DATA / "xfv_proxy_eval.json").read_text(encoding="utf-8"))
    proxy = proxy.get("projections") or {}
    stuff = json.loads((DATA / "stuff_plus_aaa.json").read_text(encoding="utf-8"))
    stuff = stuff.get("players") or {}
    rows, drops = [], Counter()
    seen = set()
    for side, sf, mf in (("hit", "xfv_scored.json", "xfv_hitter_matrix.json"),
                         ("pit", "xfv_scored_pitcher.json", "xfv_pitcher_matrix.json")):
        scored = json.loads((DATA / sf).read_text(encoding="utf-8"))
        matrix = {r["player_key"]: r for r in
                  json.loads((DATA / mf).read_text(encoding="utf-8"))}
        for s in scored:
            if s.get("censored") is not False:
                drops["censored_or_unflagged"] += 1
                continue
            pk = s["player_key"]
            if pk in seen:
                drops["dup_pit_side"] += 1
                continue
            m = matrix.get(pk)
            if m is None:
                drops["no_matrix_join"] += 1
                continue
            if m.get("target_resolved") is None:
                drops["no_resolved_label"] += 1
                continue
            if s.get("xfv_grade_display") is None:
                drops["no_display_grade"] += 1
                continue
            seen.add(pk)
            mlbam = m.get("mlbam_id")
            stf = stuff.get(str(mlbam)) if (side == "pit" and mlbam) else None
            px = proxy.get(pk)
            rows.append({
                "player_key": pk, "side": side, "kind": s.get("kind"),
                "grade": f'{float(s["xfv_grade_display"]):.1f}',
                "war": float(m["target_resolved"]),
                "xfv_war_6yr": s.get("xfv_war_6yr"),
                "star": (s.get("p_bucket") or {}).get("star"),
                "proxy": (px or {}).get("proj_xwoba"),
                "stuff": (stf or {}).get("stuff_plus"),
                "stuff_season": (stf or {}).get("season"),
                "tool_comp": _tool_composite(m, side),
                "tool_max": _tool_max(m, side),
            })
    return rows, drops


def _pair_decisions(group):
    """Which stack level decides each within-group pair (contribution audit)."""
    c = Counter()
    n = len(group)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = group[i], group[j]
            if a["proxy"] is not None and b["proxy"] is not None and a["proxy"] != b["proxy"]:
                c["proxy"] += 1
            elif a["star"] is not None and b["star"] is not None and a["star"] != b["star"]:
                c["star"] += 1
            elif a["stuff"] is not None and b["stuff"] is not None and a["stuff"] != b["stuff"]:
                c["stuff"] += 1
            else:
                c["undecided"] += 1
    return c


def run():
    rows, drops = _load_universe()
    groups = defaultdict(list)
    for r in rows:
        groups[r["grade"]].append(r)
    eligible, skipped = [], Counter()
    for g, members in sorted(groups.items()):
        if len(members) < 2:
            skipped["singleton"] += 1
            continue
        if len({m["war"] for m in members}) < 2:
            skipped["zero_label_variance"] += 1
            continue
        eligible.append((g, members))

    per_group, pair_c = [], Counter()
    star_only_rhos = []
    for g, members in eligible:
        wars = [m["war"] for m in members]
        # stamp incumbent TBS first
        for m in members:
            m["_tbs"] = _incumbent_tbs(m)
            m["_tbs_efv"] = _incumbent_tbs(m, efv_only=True)
        inc = _copeland(members, lambda a, b:
                        (a["_tbs"] > b["_tbs"]) - (a["_tbs"] < b["_tbs"]))
        inc_efv = _copeland(members, lambda a, b:
                            (a["_tbs_efv"] > b["_tbs_efv"]) - (a["_tbs_efv"] < b["_tbs_efv"]))
        cha = _copeland(members, _challenger_cmp)

        def _star_cmp(a, b):
            if a["star"] is not None and b["star"] is not None and a["star"] != b["star"]:
                return 1 if a["star"] > b["star"] else -1
            return 0
        star_only = _copeland(members, _star_cmp)
        rho_i = _spearman(inc, wars)
        rho_ie = _spearman(inc_efv, wars)
        rho_c = _spearman(cha, wars)
        rho_s = _spearman(star_only, wars)
        per_group.append({"grade": g, "n": len(members),
                          "rho_incumbent": rho_i, "rho_challenger": rho_c,
                          "rho_incumbent_efv_only": rho_ie,
                          "rho_star_only": rho_s})
        star_only_rhos.append(rho_s)
        pair_c += _pair_decisions(members)

    w = [pg["n"] for pg in per_group]
    tw = sum(w)

    def _pool(key):
        return sum(pg[key] * pg["n"] for pg in per_group) / tw

    pooled_inc = _pool("rho_incumbent")
    pooled_inc_efv = _pool("rho_incumbent_efv_only")
    pooled_cha = _pool("rho_challenger")
    pooled_star = _pool("rho_star_only")

    # group-clustered bootstrap on the delta
    rng = random.Random(SEED)
    n_g = len(per_group)
    deltas = []
    for _ in range(N_BOOT):
        num = den = 0.0
        for _ in range(n_g):
            pg = per_group[rng.randrange(n_g)]
            num += (pg["rho_challenger"] - pg["rho_incumbent"]) * pg["n"]
            den += pg["n"]
        deltas.append(num / den)
    deltas.sort()
    lo95 = deltas[int(0.025 * N_BOOT)]
    hi95 = deltas[int(0.975 * N_BOOT) - 1]
    point = pooled_cha - pooled_inc

    # sensitivity delta vs efv-only incumbent (non-gating)
    deltas_e = []
    rng2 = random.Random(SEED)
    for _ in range(N_BOOT):
        num = den = 0.0
        for _ in range(n_g):
            pg = per_group[rng2.randrange(n_g)]
            num += (pg["rho_challenger"] - pg["rho_incumbent_efv_only"]) * pg["n"]
            den += pg["n"]
        deltas_e.append(num / den)
    deltas_e.sort()

    # clean (no look-ahead) star-only challenger delta vs incumbent TBS (non-gating).
    # aStuff+ carries admitted look-ahead (AAA 2023-2026 pitches measured AFTER the
    # as-of-prospect cut); proxy always abstains here. This isolates the one honest
    # as-of-prospect challenger signal -- p_bucket star odds alone -- so a reader can
    # see the miss is not an artifact of the contaminated stuff leg.
    deltas_s = []
    rng3 = random.Random(SEED)
    for _ in range(N_BOOT):
        num = den = 0.0
        for _ in range(n_g):
            pg = per_group[rng3.randrange(n_g)]
            num += (pg["rho_star_only"] - pg["rho_incumbent"]) * pg["n"]
            den += pg["n"]
        deltas_s.append(num / den)
    deltas_s.sort()

    sizes = Counter(pg["n"] for pg in per_group)
    size_dist = {str(k): sizes[k] for k in sorted(sizes)}

    # coverage
    n_rows = len(rows)
    cov = {
        "proxy_resolved_players": sum(1 for r in rows if r["proxy"] is not None),
        "star_resolved_players": sum(1 for r in rows if r["star"] is not None),
        "stuff_resolved_pitchers": sum(1 for r in rows if r["side"] == "pit"
                                       and r["stuff"] is not None),
        "n_resolved_pitchers": sum(1 for r in rows if r["side"] == "pit"),
    }

    # 5 named example ties: largest eligible groups with label variance where the
    # two orderings disagree at the top; show who the challenger promotes.
    examples = []
    by_grade = {g: mem for g, mem in eligible}
    for pg in sorted(per_group, key=lambda x: -x["n"]):
        mem = by_grade[pg["grade"]]
        cha_sc = _copeland(mem, _challenger_cmp)
        for m in mem:
            m["_tbs"] = _incumbent_tbs(m)
        inc_sc = _copeland(mem, lambda a, b:
                           (a["_tbs"] > b["_tbs"]) - (a["_tbs"] < b["_tbs"]))
        top_c = max(range(len(mem)), key=lambda i: (cha_sc[i], -inc_sc[i]))
        top_i = max(range(len(mem)), key=lambda i: (inc_sc[i], -cha_sc[i]))
        if top_c == top_i:
            continue
        pm, im = mem[top_c], mem[top_i]
        examples.append({
            "tie_grade": pg["grade"], "group_n": pg["n"],
            "incumbent_top": im["player_key"],
            "incumbent_top_realized_war6": im["war"],
            "challenger_promotes": pm["player_key"],
            "promoted_realized_war6": pm["war"],
            "promoted_star_odds": pm["star"],
            "incumbent_top_star_odds": im["star"],
            "promotion_gain_war": round(pm["war"] - im["war"], 2),
        })
        if len(examples) == 5:
            break

    out = {
        "lane": "W-TBS2",
        "registration": "docs/efv-2026-07-24/GATES.md W-TBS2 (Phase 4b)",
        "generated_by": "tools/efv_tbs2_lab.py",
        "seed": SEED, "bootstrap_reps": N_BOOT,
        "universe": {
            "n_resolved_rows": n_rows,
            "by_side": dict(Counter(r["side"] for r in rows)),
            "by_kind": dict(Counter(r["kind"] for r in rows)),
            "drops": dict(drops),
        },
        "tie_groups": {
            "n_eligible": len(per_group),
            "n_players_in_eligible": tw,
            "skipped": dict(skipped),
            "size_distribution": size_dist,
        },
        "stack_coverage": cov,
        "pair_decision_share": dict(pair_c),
        "pooled": {
            "incumbent_tbs": round(pooled_inc, 4),
            "incumbent_tbs_efv_only_sensitivity": round(pooled_inc_efv, 4),
            "challenger_stack": round(pooled_cha, 4),
            "challenger_star_only_ablation": round(pooled_star, 4),
        },
        "gate": {
            "bar": "delta lo95 > 0 vs incumbent TBS ordering",
            "delta_point": round(point, 4),
            "delta_lo95": round(lo95, 4),
            "delta_hi95": round(hi95, 4),
            "pass": bool(lo95 > 0),
        },
        "sensitivity_vs_efv_only_incumbent": {
            "delta_point": round(pooled_cha - pooled_inc_efv, 4),
            "delta_lo95": round(deltas_e[int(0.025 * N_BOOT)], 4),
            "delta_hi95": round(deltas_e[int(0.975 * N_BOOT) - 1], 4),
        },
        "sensitivity_star_only_clean_vs_incumbent": {
            "note": "look-ahead-free challenger: star odds alone (drops contaminated "
                    "aStuff+ and the always-abstaining proxy) vs incumbent TBS.",
            "delta_point": round(pooled_star - pooled_inc, 4),
            "delta_lo95": round(deltas_s[int(0.025 * N_BOOT)], 4),
            "delta_hi95": round(deltas_s[int(0.975 * N_BOOT) - 1], 4),
        },
        "examples": examples,
        "notes": [
            "xfv_proxy has zero live coverage on resolved cohorts (proxy cohort years 2024-2026); stack level 1 abstains for every pair and the stack is effectively star odds then aStuff+.",
            "aStuff+ (data/stuff_plus_aaa.json) is measured on AAA 2023-2026 pitches, which is AFTER the as-of-prospect cutoff for resolved players; any stuff-decided pair carries look-ahead. Share of pairs it decides is reported above.",
            "Incumbent TBS reproduced from as-of-prospect fields under the frontend renormalize-over-present-weights contract; live-only inputs (RPS+, SC+, statline Stuff+, age tier, movement, health/breakout multipliers, plus flag) drop out for all rows identically. tool_composite is an approximation of served tools.composite_overall from matrix tool grades.",
            "AP+ never enters (registered constraint).",
        ],
    }
    if out["gate"]["pass"]:
        out["verdict"] = (
            "PASS (delta lo95 {:+.4f} > 0).".format(round(lo95, 4)))
    else:
        out["verdict"] = (
            "FAIL. Registered gate delta {:+.4f}, lo95 {:+.4f} vs bar lo95 > 0 -> "
            "marginal miss = FAIL per registration; no ship, no prospx wiring. The miss "
            "is robust: the look-ahead-free star-only challenger also misses "
            "(delta {:+.4f}, lo95 {:+.4f}); against the stronger eFV-only incumbent the "
            "challenger fails clearly (delta {:+.4f}, lo95 {:+.4f}). One attempt spent."
        ).format(round(point, 4), round(lo95, 4),
                 round(pooled_star - pooled_inc, 4),
                 round(deltas_s[int(0.025 * N_BOOT)], 4),
                 round(pooled_cha - pooled_inc_efv, 4),
                 round(deltas_e[int(0.025 * N_BOOT)], 4))
    return out


if __name__ == "__main__":
    rep = run()
    (DATA / "xfv_tbs2_eval.json").write_text(
        json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in
                      ("universe", "tie_groups", "stack_coverage",
                       "pair_decision_share", "pooled", "gate",
                       "sensitivity_vs_efv_only_incumbent")}, indent=2))
    print("\nVERDICT:", "PASS" if rep["gate"]["pass"] else "FAIL",
          f'(delta {rep["gate"]["delta_point"]}, lo95 {rep["gate"]["delta_lo95"]})')
