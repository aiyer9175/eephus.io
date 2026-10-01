# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pitcher K% challenger: full-season NCAA box K% as the college input.

Registered 2026-10-01 in docs/COLLEGE_PIT_K_CHALLENGER_GATE.md (owner answer
M19-1, census M03-05 and M03-19) BEFORE any fit or look. This file is the
scorer the registration names. It runs ONCE, on the registered look date, and
refuses on any other day or when a result already exists.

    python tools/college_pitk_challenger_lab.py          # the one look
    python tools/college_pitk_challenger_lab.py --check  # preconditions only

The look writes docs/college-pitk-challenger-2026-10-01/result.json and
nothing under data/. It never edits college_translation.py, the served
translations or the registry; the registry row is updated by hand from the
result, as the registration says.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import college_translation as ct  # noqa: E402

REGISTERED_LOOK_DATE = dt.date(2026, 11, 2)
GATE_DOC = "docs/COLLEGE_PIT_K_CHALLENGER_GATE.md"
WORK = ROOT / "docs" / "college-pitk-challenger-2026-10-01"
PAIRS_PATH = WORK / "frozen_pairs.json"
RESULT_PATH = WORK / "result.json"

MIN_PAIRS = 60          # P0 coverage floor on the scored subset S
MIN_NCAA_IP = 20.0      # a full-season line: at least 20 NCAA innings
BOOT_B = 2000
SEED = 20261102
N_PERM = 200


def box_k_pct(payload: dict | None) -> float | None:
    """NCAA box K% = 100 * SO / (outs + H + BB), outs = round(3 * IP).

    The NCAA pitching payload (college_stats._pitching_payload) carries SO,
    BB, H and IP but no batters-faced column, so the denominator is the
    registered estimate; it omits HBP, errors and sacrifices. None when the
    line is under MIN_NCAA_IP or a component is missing."""
    p = payload or {}
    ip, so, h, bb = p.get("ip"), p.get("so"), p.get("h"), p.get("bb")
    if ip is None or so is None or h is None or bb is None:
        return None
    if float(ip) < MIN_NCAA_IP:
        return None
    bf = round(3 * float(ip)) + int(h) + int(bb)
    return 100.0 * int(so) / bf if bf > 0 else None


def _loo_errors(items: list[tuple[float, float]]) -> list[float]:
    """Production protocol: refit college_translation._fit without each pair,
    predict it, keep the absolute error."""
    out = []
    for i in range(len(items)):
        train = items[:i] + items[i + 1:]
        f = ct._fit([a for a, _ in train], [b for _, b in train])
        x, y = items[i]
        out.append(abs(y - ct._predict(f, x)))
    return out


def _null_errors(ys: list[float]) -> list[float]:
    n, total = len(ys), sum(ys)
    return [abs(y - (total - y) / (n - 1)) for y in ys]


def _boot_ci(gains: list[float], rnd: random.Random) -> tuple[float, float]:
    n = len(gains)
    means = sorted(sum(gains[rnd.randrange(n)] for _ in range(n)) / n for _ in range(BOOT_B))
    return round(means[int(0.025 * BOOT_B)], 4), round(means[int(0.975 * BOOT_B) - 1], 4)


def score(rows: list[tuple[float, float, float]], seed: int = SEED) -> dict:
    """rows = [(box_k, tracked_k, single_a_k)] on the scored subset S.

    Returns the registered metrics and the verdict. Pure: no I/O."""
    n = len(rows)
    if n < MIN_PAIRS:
        return {"n": n, "verdict": "COVERAGE-STARVED",
                "reason": f"{n} scored pairs, under the registered floor of {MIN_PAIRS}"}
    ys = [y for _, _, y in rows]
    ch = _loo_errors([(b, y) for b, _, y in rows])
    inc = _loo_errors([(t, y) for _, t, y in rows])
    nul = _null_errors(ys)
    rnd = random.Random(seed)
    g_null = [a - b for a, b in zip(nul, ch)]
    g_inc = [a - b for a, b in zip(inc, ch)]
    ci_null = _boot_ci(g_null, rnd)
    ci_inc = _boot_ci(g_inc, rnd)
    skill_null = sum(g_null) / n
    # Permutation band: the box column shuffled across S (identical marginal,
    # no information), scored by the same LOO protocol.
    xs = [b for b, _, _ in rows]
    perm = []
    for _ in range(N_PERM):
        sx = xs[:]
        rnd.shuffle(sx)
        pe = _loo_errors(list(zip(sx, ys)))
        perm.append(sum(a - b for a, b in zip(nul, pe)) / n)
    perm.sort()
    perm_p95 = perm[int(0.95 * N_PERM) - 1]
    clauses = {
        "P0_coverage": n >= MIN_PAIRS,
        "P1_beats_null": skill_null > 0 and ci_null[0] > 0,
        "P2_beats_incumbent": sum(g_inc) / n > 0 and ci_inc[0] > 0,
        "P3_beats_permutation_band": skill_null > perm_p95,
    }
    return {
        "n": n,
        "mae_challenger": round(sum(ch) / n, 4),
        "mae_incumbent": round(sum(inc) / n, 4),
        "mae_null": round(sum(nul) / n, 4),
        "skill_vs_null": round(skill_null, 4), "ci95_vs_null": ci_null,
        "skill_vs_incumbent": round(sum(g_inc) / n, 4), "ci95_vs_incumbent": ci_inc,
        "permutation_p95_skill_vs_null": round(perm_p95, 4),
        "clauses": clauses,
        "verdict": "PASS" if all(clauses.values()) else "FAIL",
    }


def _load_rows(con) -> tuple[list[tuple[float, float, float]], dict]:
    frozen = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    key_name = ct._key_to_name(con)
    cs_p = ct.load_cs_pitchers()
    _sa_h, sa_p = ct.load_single_a(con, key_name)
    box = {}
    for slug, season, payload in con.execute(
            "SELECT player_slug, season, payload_json FROM collegesavant_box_scores "
            "WHERE side = 'pitching'"):
        try:
            box[(slug, int(season))] = json.loads(payload) if payload else {}
        except (TypeError, ValueError):
            continue
    rows, lost = [], {"no_box_line": 0, "short_or_partial_box": 0, "pair_drifted": 0}
    for p in frozen["pairs"]:
        v, sa = cs_p.get(p["name_key"]), sa_p.get(p["name_key"])
        if not v or not sa or sa[0] != p["single_a_season"] or v.get("year") != p["cs_year"]:
            lost["pair_drifted"] += 1
            continue
        payload = box.get((ct.slugify_cs(p["cs_name"]), int(p["cs_year"])))
        if payload is None:
            lost["no_box_line"] += 1
            continue
        bk = box_k_pct(payload)
        if bk is None:
            lost["short_or_partial_box"] += 1
            continue
        rows.append((bk, float(v["k_pct"]), float(sa[1])))
    return rows, {"frozen_pairs": len(frozen["pairs"]), "scored": len(rows), "lost": lost}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report the preconditions without scoring anything")
    a = ap.parse_args(argv)
    today = dt.date.today()
    if RESULT_PATH.exists():
        print(f"refused: {RESULT_PATH.name} exists; the registration allows one look")
        return 2
    con = sqlite3.connect("file:" + str(ROOT / "prospects.db") + "?mode=ro", uri=True)
    n_box = con.execute("SELECT COUNT(*) FROM collegesavant_box_scores "
                        "WHERE side = 'pitching'").fetchone()[0]
    if a.check:
        print(json.dumps({"today": today.isoformat(),
                          "registered_look_date": REGISTERED_LOOK_DATE.isoformat(),
                          "ncaa_pitching_box_rows": n_box}, indent=1))
        return 0
    if today != REGISTERED_LOOK_DATE:
        print(f"refused: the one look is registered for {REGISTERED_LOOK_DATE} ({GATE_DOC}); "
              f"today is {today}")
        return 2
    rows, acct = _load_rows(con)
    res = score(rows) if rows else {"n": 0, "verdict": "NOT SCORED",
                                    "reason": "no frozen pair carries an NCAA pitching box line"}
    doc = {"registered": "2026-10-01", "look_date": today.isoformat(), "gate": GATE_DOC,
           "accounting": acct, "result": res}
    RESULT_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
