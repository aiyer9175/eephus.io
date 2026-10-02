"""SRE01: once the regular season is over, the Futures board schedules no game.

THE DEFECT. After the 2026 regular season ended (regularSeasonEndDate
2026-09-27) the live schedule read came back empty, and the overlay fell back
to the balanced schedule, which fills 162 - gamesPlayed per club. NYY finished
93-68 and BAL 79-82 on 161 games, so each drew a phantom game, the mirrored
pairs gave BOS and CHW one too, and CHW 84-78 winning its phantom tied CLE
85-77 for the AL Central on a coin flip. The board served CLE Division 74.9
percent and CHW 25.1 percent beside a bracket seeding CLE 2 and CHW 6.

THE RULE. On or after the season's last date with nothing left on the live
schedule, nothing is scheduled: Division, Bye and Playoffs are 0 or 1 from the
final standings (a wins tie breaks by the league's own ranks, never a draw)
and Proj W is the final win total with a zero-width band.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import fa_fit_backtest as fb
import franchise_export as fe
import proj_current as pc
import proj_export as pe
from trades import _org_by_id

HERE = Path(__file__).resolve().parent

LEAGUE = {"AL": 103, "NL": 104}
DIV_ID = {"AL_W": 200, "AL_E": 201, "AL_C": 202, "NL_W": 203, "NL_E": 204, "NL_C": 205}

# (org, wins, losses) in division order; divisionRank is the list position.
# CLE, CHW and HOU tie at 90 wins: CLE holds the AL Central on rank and the
# second bye on league rank over HOU. NYY ends on 161 games. SEA, BOS and TEX
# tie at 88 for the last AL wild card and SEA holds the best wild-card rank.
FIELD = {
    "AL_E": [("TBR", 98, 64), ("NYY", 93, 68), ("BOS", 88, 74), ("BAL", 79, 83), ("TOR", 79, 83)],
    "AL_C": [("CLE", 90, 72), ("CHW", 90, 72), ("MIN", 77, 85), ("DET", 76, 86), ("KCR", 69, 93)],
    "AL_W": [("HOU", 90, 72), ("SEA", 88, 74), ("TEX", 88, 74), ("ATH", 64, 98), ("LAA", 62, 100)],
    "NL_W": [("LAD", 100, 62), ("SDP", 91, 71), ("ARI", 86, 76), ("SFG", 65, 97), ("COL", 58, 104)],
    "NL_E": [("ATL", 94, 68), ("PHI", 88, 74), ("MIA", 80, 82), ("WSN", 77, 85), ("NYM", 74, 88)],
    "NL_C": [("MIL", 103, 59), ("CHC", 89, 73), ("PIT", 82, 80), ("STL", 77, 85), ("CIN", 75, 87)],
}


def _records():
    ids = {}
    for tid, org in _org_by_id().items():
        ids.setdefault(org, tid)
    by_league: dict[str, list] = {"AL": [], "NL": []}
    for dv, clubs in FIELD.items():
        for rank, (org, w, l) in enumerate(clubs, 1):
            by_league[dv[:2]].append((org, w, l, rank))
    lg_rank, wc_rank = {}, {}
    for lg, clubs in by_league.items():
        # the league's own order: wins, then the fixture's division order
        order = sorted(clubs, key=lambda c: (-c[1], c[3]))
        for i, c in enumerate(order, 1):
            lg_rank[c[0]] = i
        rest = [c for c in order if c[3] != 1]
        for i, c in enumerate(rest, 1):
            wc_rank[c[0]] = i
    records = []
    for dv, clubs in FIELD.items():
        trs = []
        for rank, (org, w, l) in enumerate(clubs, 1):
            trs.append({
                "team": {"id": ids[org], "name": org},
                "wins": w, "losses": l, "gamesPlayed": w + l,
                "winningPercentage": f"{w / (w + l):.3f}",
                "runsScored": 700, "runsAllowed": 700, "runDifferential": 0,
                "divisionRank": str(rank), "leagueRank": str(lg_rank[org]),
                "wildCardRank": None if rank == 1 else str(wc_rank[org]),
                "clinchIndicator": None,
            })
        records.append({"league": {"id": LEAGUE[dv[:2]]}, "division": {"id": DIV_ID[dv]},
                        "teamRecords": trs})
    return records


def _row(tm):
    return {"team": tm, "war": 10.0, "wins": 81.0, "losses": 81.0}


def test_settled_season_schedules_nothing_and_matches_the_final_field(monkeypatch):
    records = _records()

    class FR:
        status = 200
        body = json.dumps({"records": records})
    monkeypatch.setattr(fb, "_fetch", lambda *a, **k: FR())
    standings = fb.standings_now(2026)

    # the live schedule after the season lists nothing; no network in a test
    monkeypatch.setattr(pc, "remaining_schedule",
                        lambda season, today=None, played=None: {})
    monkeypatch.setattr(pc, "remaining_pairs", lambda season, today=None: [])
    seen_pairs = []
    real_sim = pc.simulate_playoffs

    def _spy(teams, pairs, **kw):
        seen_pairs.append(list(pairs))
        return real_sim(teams, pairs, **kw)
    monkeypatch.setattr(pc, "simulate_playoffs", _spy)

    rows = [_row(o) for clubs in FIELD.values() for o, _, _ in clubs]
    src = pe._attach_current_season(rows, standings, season=2026,
                                    regular_season_end="2026-09-27",
                                    today=dt.date(2026, 10, 1))
    fut = pe.build_futures(rows, season=2026, regular_season_end="2026-09-27")
    by = {c["team"]: c for c in fut["clubs"]}

    champs = set(fe.division_champions(records, live=False).values())
    wins = {org: w for clubs in FIELD.values() for org, w, _ in clubs}
    byes, field = set(), set()
    for lg in ("AL", "NL"):
        lg_clubs = [(o, w, r) for dv, cl in FIELD.items() if dv[:2] == lg
                    for r, (o, w, _) in enumerate(cl, 1)]
        leaders = sorted([c for c in lg_clubs if c[0] in champs],
                         key=lambda c: (-c[1], standings[c[0]]["leagueRank"]))
        rest = sorted([c for c in lg_clubs if c[0] not in champs],
                      key=lambda c: (-c[1], standings[c[0]]["wcRank"]))
        byes |= {c[0] for c in leaders[:2]}
        field |= {c[0] for c in leaders} | {c[0] for c in rest[:3]}

    problems = []
    if len(standings) != 30 or standings["NYY"]["gamesPlayed"] != 161:
        problems.append("the fixture did not parse as a thirty-club field with NYY on 161")
    if src != "season_complete":
        problems.append(f"schedule source {src}")
    if any(seen_pairs) or not seen_pairs:
        problems.append(f"games scheduled after the season: {seen_pairs[:1]}")
    if len(by) != 30:
        problems.append(f"{len(by)} clubs on the board")
    for org, c in by.items():
        if c["divisionPct"] != (1.0 if org in champs else 0.0):
            problems.append(f"{org} divisionPct {c['divisionPct']}")
        if c["byePct"] != (1.0 if org in byes else 0.0):
            problems.append(f"{org} byePct {c['byePct']}")
        if c["playoffPct"] != (1.0 if org in field else 0.0):
            problems.append(f"{org} playoffPct {c['playoffPct']}")
        if not (c["projWins"] == c["winTotalP10"] == c["winTotalP90"] == wins[org]):
            problems.append(f"{org} projWins {c['projWins']} band "
                            f"{c['winTotalP10']} to {c['winTotalP90']} at {wins[org]} wins")
    if not ({"CLE", "HOU"} <= champs and "CHW" not in champs and byes >= {"TBR", "CLE"}
            and "SEA" in field and not {"BOS", "TEX"} & field):
        problems.append(f"fixture ties did not resolve as built: {champs} {byes} {field}")
    assert not problems, problems


def test_served_board_after_the_season_is_settled():
    p = HERE / "data" / "futures.json"
    if not p.exists():
        pytest.skip("data/futures.json not built on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    end, built = d.get("regular_season_end"), str(d.get("generated_at") or "")[:10]
    if not d.get("clubs") or not end or built <= str(end)[:10]:
        pytest.skip("futures.json was not generated after the regular season ended")
    bad = [(c["team"], c.get("divisionPct"), c.get("byePct")) for c in d["clubs"]
           if c.get("divisionPct") not in (0.0, 1.0) or c.get("byePct") not in (0.0, 1.0)]
    assert not bad, f"a settled season served a fractional Division or Bye: {bad}"
