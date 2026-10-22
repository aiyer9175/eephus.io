# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Stats module - the ABS challenges board (eABS v0; task EWAR_T4_EABS, the
ewar-map plan T4 steps 2 and 3, registered in docs/eabs-2026-10-15/EABS_GATE.md
before any number).

WHAT IT READS. The ABS challenge ledger tools/build_abs_ledger.py wrote
(data/_labs/abs_ledger/mlb_2026.json: one row per zone challenge of the 2026 MLB
regular season, its invariant against gameData.absChallenges passed in every feed),
the RE288 and RE24 tables of data/count_value.json, and the 2026 pbp corpus plays
(.cache/pbp_corpus/plays) for the score at the start of every half-inning (the
option-value model's state).

WHAT IT WRITES. data/eabs_leaderboards.json (while MLBSTATS_EABS_LIVE; the preview
directory otherwise): three boards (batters, catchers, pitchers), the league
figures, the option-value table, the constant C0, the exclusions and the invariant
receipts. Every number is computed by eabs.py; the build refuses on any gate
part 4 invariant.

DESCRIPTIVE. What a player's challenges were worth this season. No year-to-year or
forward statistic is computed here (tools/eabs_stability.py alone does that, once),
nothing here enters a label, a fitted model, a price or a betting input. eWAR v3
carries a challenge part built from this frame (owner override EW3-32,
docs/ebr-2026-09-30/EBR_GATE.md 11.10.2, tools/build_ewar_v3.py); the board says
so through the payload's ewar_part block while war_source.EWAR_V3_LIVE is on.

Run:  python eabs_export.py
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import eabs as E

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PREVIEW_DIR = ROOT / ".cache" / "eabs" / "preview"
LEDGER = DATA_DIR / "_labs" / "abs_ledger" / "mlb_2026.json"
COUNT_VALUE = DATA_DIR / "count_value.json"
CORPUS_PLAYS = ROOT / ".cache" / "pbp_corpus" / "plays"
STABILITY = DATA_DIR / "_labs" / "eabs" / "stability.json"

#: The board's flag. Display needs no gate (ewar-map plan T4); on once its tests pass.
MLBSTATS_EABS_LIVE = True

OUT_NAME = "eabs_leaderboards.json"
SEASON = 2026
ROLE_BOARD = {"batter": "batters", "catcher": "catchers", "pitcher": "pitchers"}


def out_dir() -> Path:
    return DATA_DIR if MLBSTATS_EABS_LIVE else PREVIEW_DIR


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _r(x, d=3):
    return None if x is None else round(float(x), d)


def half_starts(plays_path: Path, season: int = SEASON) -> dict:
    """{game_pk: [((inning, half), (away, home) at the half's start)]} from the corpus
    plays (scores there are after each play)."""
    import pandas as pd
    p = Path(plays_path) / str(season) / f"plays-{season}.parquet"
    df = pd.read_parquet(p, columns=["game_pk", "inning", "half", "at_bat_index", "away_score", "home_score"])
    df = df.sort_values(["game_pk", "at_bat_index"])
    out = {}
    for g, grp in df.groupby("game_pk", sort=False):
        seq, seen = [], set()
        away = home = 0
        for inn, half, aw, hm in zip(grp["inning"], grp["half"], grp["away_score"], grp["home_score"]):
            key = (int(inn), str(half))
            if key not in seen:
                seen.add(key)
                seq.append((key, (away, home)))
            away = 0 if aw != aw else int(aw)
            home = 0 if hm != hm else int(hm)
        out[int(g)] = seq
    return out


def frame(ledger_path: Path = LEDGER, count_value_path: Path = COUNT_VALUE,
          plays_path: Path = CORPUS_PLAYS, halves: dict | None = None) -> dict:
    """The valued frame: every usable challenge row with v, k_before, p, c_fail and
    o, the option model, C0, the cell rates, the exclusions and the budget walk's
    violations. Refuses on the budget walk (gate 2.1)."""
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    cvdoc = json.loads(Path(count_value_path).read_text(encoding="utf-8"))
    all_rows = E.as_dicts(ledger)
    excluded = defaultdict(int)
    rows = []
    for r in all_rows:
        why = E.exclusion(r)
        if why:
            excluded[why] += 1
        else:
            rows.append(r)
    if not rows:
        raise E.EabsRefusal("no usable challenge rows in the ledger")
    t288, re24 = E.season_tables(cvdoc, SEASON)

    # values and the budget walk, per game
    by_game = defaultdict(list)
    for r in rows:
        r["v"] = E.challenge_value(r, t288, re24)
        by_game[int(r["game_pk"])].append(r)
    violations = []
    for g, grp in by_game.items():
        kb = E.budget_walk(grp)
        for r, k in zip(grp, kb):
            r["k_before"] = k
            if k <= 0:
                violations.append([g, r["inning"], r["half"], r["at_bat_index"]])
    if len(violations) > E.BUDGET_VIOLATION_MAX * len(rows):
        raise E.EabsRefusal(f"budget walk: {len(violations)} of {len(rows)} challenges taken with none left "
                            f"(limit {E.BUDGET_VIOLATION_MAX:.0%})")

    # the option-value model over every game of the frame
    if halves is None:
        halves = half_starts(plays_path)
    points = []
    games_without_plays = sorted(g for g in by_game if g not in halves)
    for g, seq in halves.items():
        grp = by_game.get(g, [])
        hs = [h for h, _ in seq]
        sc = {h: s for h, s in seq}
        points.extend(E.half_points(grp, [r.get("k_before") for r in grp], hs, sc, [r["v"] for r in grp]))
    model = E.OptionModel(points)
    club_games = 2 * len(halves)
    total_ov = sum(r["v"] for r in rows if r["overturned"])
    c0 = E.constant_cost(total_ov, club_games)

    # cells and costs: c_fail is the cost a failure would have had at the
    # challenge, carried on every row because eABS prices (o - p)(v + c).
    p_cell = E.cell_rates(rows)
    for r in rows:
        r["p"] = p_cell[E.mix_cell(r)]
        h = E.half_index(r["inning"], r["half"])
        r["c_fail"] = model.cost(h, r["k_before"], E.margin_bucket(E.club_margin(r)))
        r["c0"] = c0
        r["o"] = 1 if r["overturned"] else 0
    return {"rows": rows, "names": ledger.get("names") or {}, "excluded": dict(excluded),
            "violations": violations, "model": model, "c0": c0, "club_games": club_games,
            "p_cell": p_cell, "games_without_plays": games_without_plays}


def stability_block(path: Path = STABILITY) -> dict | None:
    """The registered look's dispositions (gate part 5), for the board's one
    derived sentence (gate part 6). None when the look has not run."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    prim = doc.get("primary") or {}
    seasons = (doc.get("constants") or {}).get("seasons") or []
    return {"registration": doc.get("registration"), "generated_at": doc.get("generated_at"),
            "frame": (f"AAA {seasons[0]} to {seasons[-1]} (consecutive seasons)" if seasons else None),
            "dispositions": {k: v.get("disposition") for k, v in prim.items()},
            "rho": {k: _r((v.get("real") or {}).get("rho"), 4) for k, v in prim.items()},
            "mde95": {k: _r((v.get("real") or {}).get("mde95"), 4) for k, v in prim.items()}}


def ewar_part_block() -> dict:
    """{"in_ewar": bool, ...}: whether the displayed eWAR carries the challenge part
    (EBR_GATE.md 11.10.2), read from war_source.EWAR_V3_LIVE and data/ewar_v3.json's
    meta, never typed on the page."""
    try:
        import war_source
        if not war_source.EWAR_V3_LIVE:
            return {"in_ewar": False}
        import ewar_v3
        part = ((ewar_v3.meta() or {}).get("parts") or {}).get("eabs")
    except Exception:   # noqa: BLE001 - absence is a reportable state
        return {"in_ewar": False}
    if not part:
        return {"in_ewar": False}
    return {"in_ewar": True, "first_season": part.get("first_season"), "label": part.get("label"),
            "series": part.get("series"), "registration": "docs/ebr-2026-09-30/EBR_GATE.md 11.10.2"}


def build(ledger_path: Path = LEDGER, count_value_path: Path = COUNT_VALUE,
          plays_path: Path = CORPUS_PLAYS, out_path: Path | None = None, *, write: bool = True,
          halves: dict | None = None, stability_path: Path = STABILITY) -> dict:
    fr = frame(ledger_path, count_value_path, plays_path, halves)
    rows, names, model, c0, p_cell = fr["rows"], fr["names"], fr["model"], fr["c0"], fr["p_cell"]
    excluded, violations, club_games = fr["excluded"], fr["violations"], fr["club_games"]
    games_without_plays = fr["games_without_plays"]

    # gate part 4 invariants
    inv = {}
    cell_sum = defaultdict(float)
    for r in rows:
        cell_sum[E.mix_cell(r)] += r["o"] - r["p"]
    worst_cell = max(abs(v) for v in cell_sum.values())
    inv["cell_rate_sum_max_abs"] = worst_cell
    if worst_cell > E.TOL:
        raise E.EabsRefusal(f"invariant 3: a cell's (o - p) sums to {worst_cell}")
    bad = [r for r in rows if not (r["v"] >= 0 and r["c_fail"] >= 0 and r["v"] == r["v"] and r["c_fail"] == r["c_fail"])]
    inv["negative_or_nonfinite_values"] = len(bad)
    if bad:
        raise E.EabsRefusal(f"invariant 4: {len(bad)} challenges carry a negative or non-finite value or cost")

    # players, per role. Items use c = cost if failed (for an overturned challenge
    # the cost term enters eABS through (o - p) c, so the item carries the cost a
    # failure there would have had).
    by_player = defaultdict(list)
    for r in rows:
        role = r.get("role")
        if role not in ROLE_BOARD or r.get("challenger_id") is None:
            continue
        by_player[(role, int(r["challenger_id"]))].append(r)
    boards = {b: [] for b in ROLE_BOARD.values()}
    for (role, pid), grp in by_player.items():
        items = [{"o": r["o"], "v": r["v"], "c": r["c_fail"], "c0": c0, "p": r["p"]} for r in grp]
        line = E.player_line(items)
        if abs(line["raw"] - (line["rg"] - line["fc"])) > E.TOL:
            raise E.EabsRefusal(f"invariant 2: player {pid}")
        grp_sorted = sorted(grp, key=lambda r: (str(r.get("official_date") or ""), int(r["game_pk"])))
        clubs = []
        for r in grp_sorted:
            c = r.get("challenge_org")
            if c and c not in clubs:
                clubs.append(c)
        team = grp_sorted[-1].get("challenge_org")
        row = {"mlbam": pid, "name": names.get(str(pid)), "team": team,
               "n": line["n"], "won": line["won"], "lost": line["lost"],
               "ovr": _r(line["ovr"], 4), "x_ovr": _r(line["x_ovr"], 4),
               "rg": _r(line["rg"]), "fc": _r(line["fc"]), "raw": _r(line["raw"]), "eabs": _r(line["eabs"]),
               "fc0": _r(line["fc0"]), "raw0": _r(line["raw0"]),
               "stake": _r(sum(r["v"] for r in grp))}
        if len(clubs) > 1:
            row["clubs"] = clubs
        boards[ROLE_BOARD[role]].append(row)
    for b in boards.values():
        b.sort(key=lambda x: (-(x["eabs"] or 0.0), str(x["name"] or "")))

    # invariant 1: board counts reconcile with the ledger frame per role
    recon = {}
    for role, b in ROLE_BOARD.items():
        in_frame = [r for r in rows if r.get("role") == role and r.get("challenger_id") is not None]
        nb = sum(x["n"] for x in boards[b])
        wb = sum(x["won"] for x in boards[b])
        recon[role] = {"ledger_n": len(in_frame), "board_n": nb,
                       "ledger_won": sum(r["o"] for r in in_frame), "board_won": wb}
        if nb != len(in_frame) or wb != recon[role]["ledger_won"]:
            raise E.EabsRefusal(f"invariant 1: {role} board does not reconcile with the ledger")
    inv["reconcile"] = recon
    inv["budget_violations"] = len(violations)

    # league figures
    def league(sub):
        n = len(sub)
        won = sum(r["o"] for r in sub)
        return {"n": n, "won": won, "ovr": _r(won / n, 4) if n else None,
                "rg": _r(sum(r["v"] for r in sub if r["o"])),
                "fc": _r(sum(r["c_fail"] for r in sub if not r["o"])),
                "v_mean": _r(sum(r["v"] for r in sub) / n, 4) if n else None}
    lg = {"all": league(rows),
          "by_role": {role: league([r for r in rows if r.get("role") == role]) for role in
                      ("batter", "catcher", "pitcher", "unresolved")},
          "by_side": {s: league([r for r in rows if r["challenge_side"] == s]) for s in ("batting", "fielding")}}
    cells = {f"{s}|{b}-{k}": {"n": sum(1 for r in rows if E.mix_cell(r) == (s, b, k)), "p": _r(p, 4)}
             for (s, b, k), p in sorted(p_cell.items())}
    dates = sorted(str(r.get("official_date")) for r in rows if r.get("official_date"))
    payload = {
        "schema": 1,
        "version": E.EABS_VERSION,
        "generated_at": _now(),
        "registration": E.GATE_DOC,
        "season": SEASON,
        "as_of": dates[-1] if dates else None,
        "frame": ("MLB 2026 regular season zone challenges from the ABS challenge ledger "
                  "(data/_labs/abs_ledger/mlb_2026.json), valued on RE288 (data/count_value.json)"),
        "descriptive": "what a player's challenges were worth this season; not a forecast",
        "ewar_part": ewar_part_block(),
        "values": {"c0": _r(c0, 4), "k_opt": E.K_OPT, "club_games": club_games,
                   "option_points": model.n_points, "games_without_plays": len(games_without_plays),
                   "margin_buckets": list(E.MARGIN_BUCKETS),
                   "option_table": {k: {"n": v["n"], "v": _r(v["v"], 4)} for k, v in model.table().items()},
                   "mean_fail_cost": _r(sum(r["c_fail"] for r in rows if not r["o"])
                                        / max(1, sum(1 for r in rows if not r["o"])), 4)},
        "league": lg,
        "cells": cells,
        "exclusions": dict(sorted(excluded.items())),
        "invariants": inv,
        "stability": stability_block(stability_path),
        "boards": boards,
    }
    if write:
        out = Path(out_path) if out_path is not None else out_dir() / OUT_NAME
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, out)
    return payload


def main(argv=None) -> int:
    p = build()
    b = p["boards"]
    print(f"eabs: {p['league']['all']['n']} challenges; boards batters {len(b['batters'])}, "
          f"catchers {len(b['catchers'])}, pitchers {len(b['pitchers'])}; C0 {p['values']['c0']}; "
          f"written to {out_dir() / OUT_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
