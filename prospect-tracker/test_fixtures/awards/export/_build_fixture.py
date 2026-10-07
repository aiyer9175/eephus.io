# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Builds test_fixtures/awards/export/ from test_fixtures/awards/core/ (AWARDS_3_EXPORTER).

The core fixtures hold a synthetic 2026 season in the shapes awards_core reads (stint
records, data/ewar.json blocks, the war board, a rookies block, standings and the team
outlook). This script lays the SAME world out in the shapes awards_export.py reads by
path: the five /mlbstats/ boards and their history files, mlb_projections.json,
management_board.json, model_registry.json, xfv.json, debuts_lite.json, the StatsAPI
standings cache, the team map, the rookies file and the projection bundle meta. Every
number is deterministic (seeded) so the fixture is stable across rebuilds; no file here
is a served artifact and nothing is fetched.

Run: python test_fixtures/awards/export/_build_fixture.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent / "core"
SEASON = 2026
GEN = "2026-10-05T06:00:00+00:00"
LEAGUE_ID = {"AL": 103, "NL": 104}


def _load(name):
    return json.loads((CORE / name).read_text(encoding="utf-8"))


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    rng = random.Random(20261005)
    board = _load(f"board_{SEASON}.json")
    ewar = _load(f"ewar_{SEASON}.json")
    rookies = _load(f"rookies_{SEASON}.json")
    standings = _load(f"standings_{SEASON}.json")
    outlook = _load(f"team_outlook_{SEASON}.json")
    wpa = _load(f"wpa_{SEASON}.json")
    skill = _load(f"skill_raw_{SEASON}.json")
    bat = _load(f"stint_bat_{SEASON}.json")
    pit = _load(f"stint_pit_{SEASON}.json")

    data = HERE / "data"
    cache = HERE / "cache"
    labs = HERE / "labs"
    model = HERE / "model"

    players = board["players"]
    hitters, starters, relievers, fielders, lev_bat, lev_sp = [], [], [], [], [], []
    for p in players:
        m = p["mlbam"]
        is_h = p.get("role") in ("H", "TWP") or (p.get("pa") or 0) >= 100
        is_p = p.get("role") in ("SP", "RP", "TWP") or (p.get("ip") or 0) > 0
        if is_h:
            hem = rng.randint(70, 180)
            gap = round(rng.uniform(-0.06, 0.05), 3)
            hitters.append({"mlbam": m, "name": p["name"], "team": p["team"], "pa": p.get("pa"),
                            "hem_plus": hem, "hem_plus_raw": round(hem + rng.uniform(-0.5, 0.5), 2),
                            "xhem_plus": hem + rng.randint(-20, 25), "luck_gap": gap,
                            "xwoba": round(0.330 + gap, 3), "woba": 0.330,
                            "wrc_plus": hem + rng.randint(-10, 10), "qualified": (p.get("pa") or 0) >= 200,
                            "war": p.get("war")})
            dem = round(rng.uniform(80.0, 140.0), 2)
            fielders.append({"mlbam": m, "name": p["name"], "team": p["team"], "pos": p.get("pos") or "DH",
                             "inn": round(rng.uniform(300.0, 1300.0), 1), "dem_plus": int(round(dem)),
                             "dem_plus_raw": dem, "def_runs": round((dem - 100) / 4.0, 1),
                             "qualified": True})
            lev_bat.append({"mlbam": m, "name": p["name"], "wpa": wpa.get(str(m), 0.0), "pa": p.get("pa")})
        if is_p:
            ip = float(p.get("ip") or 0.0)
            sraw = skill.get(str(m))
            era, fip = round(rng.uniform(2.0, 5.5), 2), round(rng.uniform(2.5, 5.0), 2)
            if ip >= 100:
                sem = round(sraw if sraw is not None else rng.uniform(85.0, 165.0), 1)
                starters.append({"mlbam": m, "name": p["name"], "team": p["team"], "ip": ip,
                                 "sem_plus": int(round(sem)), "sem_plus_raw": sem,
                                 "xsem_plus": int(round(sem)) + rng.randint(-15, 15),
                                 "era": era, "fip": fip, "wpa": wpa.get(str(m)), "qualified": True,
                                 "role": "SP"})
                lev_sp.append({"mlbam": m, "name": p["name"], "wpa": wpa.get(str(m), 0.0)})
            else:
                rem = round(sraw if sraw is not None else rng.uniform(80.0, 190.0), 1)
                relievers.append({"mlbam": m, "name": p["name"], "team": p["team"], "ip": ip,
                                  "rem_plus": int(round(rem)), "rem_plus_raw": rem,
                                  "gmli": round(rng.uniform(0.6, 2.1), 2), "wpa": round(rng.uniform(-1.0, 5.0), 2),
                                  "saves": rng.randint(0, 40), "qualified": True, "era": era, "fip": fip})

    vint = {"artifact_generated_at": "2026-10-04T11:06:57", "label_build_at": "2026-09-03T12:35:09",
            "as_of": "2026-10-04", "stale": False, "cadence": {"mode": "nightly", "live_season": SEASON}}
    _dump(data / "ewar.json", dict(ewar, generated_at="2026-09-03T12:35:09"))
    _dump(data / "war_leaderboards.json",
          dict(board, generated_at=GEN, as_of="2026-10-04", ewar_vintage=vint,
               qualified_rule="PA >= 100 or IP >= 30"))
    _dump(data / "hitter_leaderboards.json",
          {"generated_at": GEN, "season": SEASON, "ewar_vintage": vint, "team_basis": "current_roster",
           "hitters": hitters})
    _dump(data / "starter_leaderboards.json",
          {"generated_at": GEN, "season": SEASON, "ewar_vintage": vint, "starters": starters})
    _dump(data / "bullpen_leaderboards.json",
          {"generated_at": GEN, "season": SEASON, "ewar_vintage": vint, "relievers": relievers})
    _dump(data / "defense_leaderboards.json",
          {"generated_at": GEN, "season": SEASON, "ewar_vintage": vint,
           "scale": {"qualify_min_inn": 400}, "fielders": fielders})
    _dump(data / "leverage_leaderboards.json",
          {"generated_at": GEN, "season": SEASON, "batters": lev_bat, "starters": lev_sp})

    # history: one closed season (2025) with a handful of rows so the closed shard
    # exercises the history path and the raw-value fallback (raw None in history)
    def _hist(block, rows, extra=None):
        h = {"season": 2025, "n_qualified": len(rows), block: rows}
        if extra:
            h.update(extra)
        return {"generated_at": GEN, "seasons": [2021, 2022, 2023, 2024, 2025],
                "history": {str(y): ({"season": y, block: []} if y != 2025 else h)
                            for y in (2021, 2022, 2023, 2024, 2025)}}
    _dump(data / "hitter_history.json",
          _hist("hitters", [dict(r, hem_plus_raw=None, xhem_plus=None, luck_gap=None)
                            for r in hitters[:6]]))
    _dump(data / "starter_history.json", _hist("starters", [dict(r, sem_plus_raw=None, xsem_plus=None)
                                                            for r in starters[:4]]))
    _dump(data / "bullpen_history.json", _hist("relievers", [dict(r, rem_plus_raw=None) for r in relievers[:4]]))
    _dump(data / "defense_history.json", _hist("fielders", [dict(r, dem_plus_raw=None) for r in fielders[:6]]))
    _dump(data / "leverage_history.json",
          {"generated_at": GEN, "history": {"2025": {"season": 2025, "batters": lev_bat[:6],
                                                      "starters": lev_sp[:3]}}})

    # projections: one forward path per player (first_season S + 1), the season closed
    vets = []
    for p in players:
        war_now = float(p.get("war") or 0.0)
        nxt = round(war_now * 0.6 + rng.uniform(-1.0, 1.5), 2)
        vets.append({"mlbam": p["mlbam"], "name": p["name"], "team": p["team"],
                     "war": [nxt, round(nxt * 0.9, 2)], "warP10": [round(nxt - 2.0, 2)] * 2,
                     "warP90": [round(nxt + 2.5, 2)] * 2})
    to = []
    for t in outlook["team_outlook"]:
        cur = dict(t["current"], remGames=0)
        to.append(dict(t, current=cur, byYear=[{"wins": 81}]))
    _dump(data / "mlb_projections.json",
          {"generated_at": "2026-10-04", "first_season": SEASON + 1, "mc_schedule_source": "season_complete",
           "vets": vets, "team_outlook": to})

    # management: 2026 club rows for the first eight clubs, two under the family floor
    rows = []
    for i, c in enumerate(standings["clubs"][:8]):
        n = 80 if i == 7 else 400 + i * 20
        rows.append({"club": c["club"], "season": SEASON, "agent": "club-season", "games": 162,
                     "n_pitching_change": n, "mwpa_pitching_change": round(rng.uniform(-3.0, 9.0), 3),
                     "n_pinch_hit": 150, "mwpa_pinch_hit": round(rng.uniform(-1.0, 1.5), 3),
                     "n_pinch_run": 10, "mwpa_pinch_run": 0.2,
                     "n_intentional_walk": 12, "mwpa_intentional_walk": -0.1,
                     "n_bunt": 50, "mwpa_bunt": 0.3, "n_steal": 100, "mwpa_steal": 0.5})
    _dump(data / "management_board.json",
          {"generated_at": GEN, "clubs": {"rows": rows, "floors": {"pitching_change": 100, "pinch_hit": 40,
                                                                 "pinch_run": 15, "intentional_walk": 8,
                                                                 "bunt": 20, "steal": 30}},
           "decisions": {"seasons": [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026],
                         "through_by_season": {"2025": "2025-09-28", str(SEASON): "2026-09-27"}},
           "managers": {"live": False, "blocked_on": "mgmt_managers ingest (M-MWAR-2)"}})

    # the registry: every row the payload cites except the selection row, which lands at the flip
    ids = ["ewar", "hem_plus", "sem_plus", "rem_plus", "dem_plus", "xhem_plus", "xsem_plus",
           "leverage_board", "mlb_projections_vets", "xfv_backgrade", "mgmt_decision_ledger"]
    _dump(data / "model_registry.json",
          {"version": 1, "checked_at": GEN,
           "models": [{"model_id": i, "verdict": "validated" if i in ("hem_plus", "sem_plus", "rem_plus",
                                                                       "dem_plus", "xhem_plus",
                                                                       "mlb_projections_vets")
                       else "provisional",
                       "eval_artifact": f"data/{i}_eval.json", "artifact_age_days": 10 + k,
                       "stale": i == "rem_plus"} for k, i in enumerate(ids)]})

    # prospects: debut cohorts before 2020 (open), one 2021 debut and one 2025 debut (closed)
    debuts, by_player = [], {}
    cohort = [2015, 2016, 2017, 2018, 2019, 2016, 2017, 2018, 2019, 2015, 2021, 2025]
    picks = [p for p in players if (p.get("pa") or 0) >= 300 or (p.get("ip") or 0) >= 80][:len(cohort)]
    for p, y in zip(picks, cohort):
        key = p["name"].lower().replace(" ", "_").replace(".", "")
        debuts.append({"player_key": key, "player_name": p["name"], "mlbam_id": p["mlbam"],
                       "debut_date": f"{y}-06-15", "status": "debuted"})
        grade = 20.0 if p["mlbam"] % 7 == 0 else float(rng.choice([35, 40, 45, 50, 55, 60]))
        by_player[key] = {"kind": "debuted", "xfv_grade": grade, "xfv_grade_at_debut": grade,
                          "consensus_fv": grade + 2.0}
    _dump(data / "debuts_lite.json", debuts)
    _dump(data / "xfv.json", {"meta": {"generated_at": GEN}, "by_player": by_player})

    # the StatsAPI standings cache, the team map and the teams file
    codes = sorted({c["club"] for c in standings["clubs"]})
    team_id = {c: 100 + i for i, c in enumerate(codes)}
    pyth = {t["team"]: t["current"] for t in outlook["team_outlook"]}
    recs = {}
    for c in standings["clubs"]:
        lg = c["league"]
        gp = c["w"] + c["l"]
        xw = int(round((pyth.get(c["club"]) or {}).get("pythagPct", 0.5) * gp))
        recs.setdefault(lg, []).append({
            "team": {"id": team_id[c["club"]], "name": f"{c['club']} club", "link": f"/api/v1/teams/{team_id[c['club']]}"},
            "season": str(SEASON), "gamesPlayed": gp, "wins": c["w"], "losses": c["l"],
            "runDifferential": int(round((c["w"] - gp / 2) * 10)), "lastUpdated": "2026-09-27T21:21:55Z",
            "leagueRecord": {"wins": c["w"], "losses": c["l"]},
            "records": {"expectedRecords": [{"wins": xw, "losses": gp - xw, "type": "xWinLoss"}]}})
    _dump(cache / f"statsapi_standings_{SEASON}.json",
          {"copyright": "Copyright 2026 MLB Advanced Media, L.P. (fixture)",
           "records": [{"standingsType": "regularSeason", "league": {"id": LEAGUE_ID[lg]},
                        "teamRecords": rows_} for lg, rows_ in recs.items()]})
    _dump(cache / "team_abbrev_map.json", {str(v): k for k, v in team_id.items()})
    _dump(cache / f"statsapi_teams_{SEASON}.json",
          {"teams": [{"id": v, "abbreviation": k, "league": {"id": LEAGUE_ID[next(c['league'] for c in standings['clubs'] if c['club'] == k)]}}
                     for k, v in team_id.items()]})

    _dump(labs / "rookies.json", {"schema": 1, "produced_by": "fixture", "seasons": [rookies]})
    _dump(model / "meta.json", {"war_provider": "ewar_v2", "label_shape": "side_keyed_v1",
                                "train_hash": "fixture0000000"})
    _dump(HERE / "stints.json", {"bat": bat, "pit": pit})
    print("fixture written:", sum(1 for _ in HERE.rglob("*.json")), "files")


if __name__ == "__main__":
    main()
