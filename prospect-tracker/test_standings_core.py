# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""standings_core (STANDINGS_1_CORE_RULES): the pure standings core on saved
fixtures and on the tracked copy of the final tables.

Hermetic: every payload comes from test_fixtures/standings/ (trims of the local
StatsAPI standings caches for 2026, 2020, 2016, 2012 and 2024, the 2026-09-20
and 2026-03-25 probes, the last weeks of 2026 from the local game feeds, a
synthetic game list and the 2026 seeds read once from data/bracket_sim.json)
or from the tracked data/_labs/standings/ copy; no network, no clock, and
nothing under data/ or .cache/ is written (writes go to pytest's tmp_path).
This file alone imports trades and franchise_export, to pin the club literal
and the division champion rule; standings_core never imports either.
"""
from __future__ import annotations

import ast
import copy
import json
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

import scores_core as sc
import standings_core as st

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "standings"
LABS = ROOT / "data" / "_labs" / "standings"
GEN = "2026-10-03T12:00:00Z"

FINALS = {2026: "2026-09-27", 2020: "2020-09-27", 2016: "2016-10-02", 2012: "2012-10-03", 2024: "2024-09-30"}
PROBES = {"p1": ("p1_2026-09-20.json", "2026-09-20"), "p3": ("p3_2026-03-25.json", "2026-03-25")}
ALL_FIX = [str(y) for y in FINALS] + list(PROBES)


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fixture(tag):
    """(payload, as_of, final) of a fixture tag."""
    if tag in PROBES:
        name, as_of = PROBES[tag]
        return load(name), as_of, False
    return load(f"standings_{tag}.json"), FINALS[int(tag)], True


def season_file(tag, **kw):
    pay, as_of, final = fixture(tag)
    return st.build_season_file(pay, as_of=as_of, final=final, generated_at=GEN, **kw)


def rows_by_code(obj):
    return {r["code"]: r for r in obj["rows"]}


def labs(y):
    return json.loads((LABS / f"statsapi_standings_{y}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def synth_games():
    return st.games_from_schedule(load("games_synthetic.json"))


@pytest.fixture(scope="module")
def tail_2026():
    return st.games_from_schedule(load("schedule_2026_tail.json"))


# --------------------------------------------------------------------------- #
# A synthetic full season and StatsAPI-shaped standings built from it
# --------------------------------------------------------------------------- #
def synth_season(n_dates=184, seed=7, start="2026-03-26"):
    rng = random.Random(seed)
    ids = sorted(sc.CLUB_BY_ID)
    d0 = date.fromisoformat(start)
    dates, pk = [], 700000
    for i in range(n_dates):
        d = (d0 + timedelta(days=i)).isoformat()
        order = ids[:]
        rng.shuffle(order)
        games = []
        for j in range(0, 30, 2):
            a, h = order[j], order[j + 1]
            ar, hr = rng.randint(0, 12), rng.randint(0, 12)
            if ar == hr:
                hr += 1
            pk += 1
            games.append({"gamePk": pk, "gameType": "R", "officialDate": d, "gameDate": f"{d}T23:05:00Z",
                          "gameNumber": 1, "doubleHeader": "N",
                          "status": {"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Final"},
                          "teams": {"away": {"team": {"id": a}, "score": ar}, "home": {"team": {"id": h}, "score": hr}}})
        dates.append({"date": d, "games": games})
    return st.games_from_schedule({"dates": dates})


def synth_standings(games, through, season=2026):
    """A StatsAPI-shaped standings response through `through` from a game
    list: ranks by PCT (team id breaks ties), GB and WCGB strings with MLB's
    "+", league and division records, the last ten and xWinLoss."""
    fmt = st.format_for(season)
    ids = sorted(sc.CLUB_BY_ID)
    t = {i: {"w": 0, "l": 0, "rs": 0, "ra": 0, "seq": [], "vs": {}} for i in ids}
    for g in st.final_games(games):
        if g["date"] > through:
            break
        for me, opp, mr, orr in ((g["away"], g["home"], g["away_r"], g["home_r"]),
                                 (g["home"], g["away"], g["home_r"], g["away_r"])):
            x = t[me]
            won = mr > orr
            x["w" if won else "l"] += 1
            x["rs"] += mr
            x["ra"] += orr
            x["seq"].append("W" if won else "L")
            od = st.division_of(opp, season)
            x["vs"].setdefault(od, [0, 0])[0 if won else 1] += 1

    def pct(i):
        w, l = t[i]["w"], t[i]["l"]
        return w / (w + l) if w + l else 0.5

    def key(i):
        return (-pct(i), -(t[i]["w"] - t[i]["l"]), i)

    div = {i: st.division_of(i, season) for i in ids}
    lg = {i: st.DIVISION_LEAGUE[div[i]] for i in ids}
    rank = {}
    for d in st.DIVISION_CODE:
        for n, i in enumerate(sorted((i for i in ids if div[i] == d), key=key), start=1):
            rank[i] = n
    lrank, wrank = {}, {}
    for L in (103, 104):
        mem = sorted((i for i in ids if lg[i] == L), key=key)
        for n, i in enumerate(mem, start=1):
            lrank[i] = n
        rest = [i for i in mem if rank[i] != 1]
        for n, i in enumerate(rest, start=1):
            wrank[i] = n
    srank = {i: n for n, i in enumerate(sorted(ids, key=key), start=1)}

    def gbs(x):
        return "-" if x == 0 else f"{x:.1f}"

    recs = []
    for d in st.DIVISION_CODE:
        mem = sorted((i for i in ids if div[i] == d), key=lambda i: rank[i])
        best = max(t[i]["w"] - t[i]["l"] for i in mem)
        trs = []
        for i in mem:
            x = t[i]
            L = lg[i]
            ref = next(j for j in ids if lg[j] == L and wrank.get(j) == fmt["wc_spots"])
            gap = ((x["w"] - x["l"]) - (t[ref]["w"] - t[ref]["l"])) / 2
            wcgb = "-" if rank[i] == 1 or gap == 0 else (f"+{gap:.1f}" if gap > 0 else f"{-gap:.1f}")
            seq = x["seq"][-10:]
            streak = None
            if x["seq"]:
                last = x["seq"][-1]
                n = len(x["seq"]) - len("".join(x["seq"]).rstrip(last))
                streak = {"streakCode": f"{last}{n}"}
            own = [0, 0]
            divrecs = []
            for od in st.DIVISION_CODE:
                if st.DIVISION_LEAGUE[od] != L:
                    continue
                v = x["vs"].get(od, [0, 0])
                own = [own[0] + v[0], own[1] + v[1]]
                divrecs.append({"wins": v[0], "losses": v[1], "division": {"id": od}})
            gp = x["w"] + x["l"]
            xw = st._xw(gp, x["rs"], x["ra"])
            tr = {"team": {"id": i}, "season": str(season), "wins": x["w"], "losses": x["l"], "gamesPlayed": gp,
                  "winningPercentage": (f"{pct(i):.3f}".lstrip("0") if gp else ".000"),
                  "divisionGamesBack": gbs((best - (x["w"] - x["l"])) / 2), "wildCardGamesBack": wcgb,
                  "leagueGamesBack": "-", "sportGamesBack": "-",
                  "divisionRank": str(rank[i]), "leagueRank": str(lrank[i]), "sportRank": str(srank[i]),
                  "runsScored": x["rs"], "runsAllowed": x["ra"], "runDifferential": x["rs"] - x["ra"],
                  "leagueRecord": {"ties": 0},
                  "records": {"splitRecords": [{"type": "lastTen", "wins": seq.count("W"), "losses": seq.count("L")}],
                              "divisionRecords": divrecs,
                              "leagueRecords": [{"wins": own[0], "losses": own[1], "league": {"id": L}},
                                                {"wins": x["w"] - own[0], "losses": x["l"] - own[1],
                                                 "league": {"id": 207 - L}}],
                              "expectedRecords": [{"type": "xWinLoss", "wins": xw, "losses": gp - xw}] if gp else []}}
            if streak:
                tr["streak"] = streak
            if rank[i] != 1:
                tr["wildCardRank"] = str(wrank[i])
            trs.append(tr)
        recs.append({"league": {"id": st.DIVISION_LEAGUE[d]}, "division": {"id": d}, "teamRecords": trs})
    return {"copyright": load("standings_2026.json")["copyright"], "records": recs}


# --------------------------------------------------------------------------- #
# 1. Flags; the import fence at runtime; the dash gate
# --------------------------------------------------------------------------- #
def test_flags_default_off_and_coupled():
    assert st.STANDINGS_LIVE is False and st.STANDINGS_CHARTS is False
    # STANDINGS_LIVE may be True only when SCORES_LIVE is; CHARTS only when LIVE is
    assert (not st.STANDINGS_LIVE) or sc.SCORES_LIVE
    assert (not st.STANDINGS_CHARTS) or st.STANDINGS_LIVE


FENCED = ("requests", "bs4", "pandas", "numpy", "trades", "scrapers", "stats", "franchise_export")


def test_import_fence_at_runtime():
    code = f"""
import json, sys
from pathlib import Path
import standings_core as st
FIX = Path({str(FIX)!r})
ld = lambda n: json.loads((FIX / n).read_text(encoding="utf-8"))
st.parse_standings(ld("p1_2026-09-20.json"), "2026-09-20")
fin = ld("standings_2026.json")
st.parse_standings(fin, "2026-09-27", final=True)
f = st.build_season_file(fin, as_of="2026-09-27", final=True, generated_at="2026-10-03T12:00:00Z")
assert st.validate_standings(st.KIND_SEASON, f, name="standings/2026.json")["ok"]
st.division_champions(fin["records"], live=False)
st.build_race(st.games_from_schedule(ld("games_synthetic.json")), 2026)
print(json.dumps(sorted(m for m in {FENCED!r} if m in sys.modules)))
"""
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == []


def test_source_imports_only_the_standard_library_and_scores_core():
    text = (ROOT / "standings_core.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods <= {"__future__", "datetime", "json", "math", "os", "re", "tempfile", "decimal", "fractions",
                    "scores_core"}, mods
    for name in ("trades", "franchise_export"):
        assert f"import {name}" not in text and f"from {name}" not in text
    assert "importlib" not in text and "__import__" not in text


def test_standings_core_is_a_dash_gate_target():
    sys.path.insert(0, str(ROOT / "tools"))
    import strip_emdashes
    assert "standings_core.py" in strip_emdashes.TARGETS
    for name in ("standings_core.py", "test_standings_core.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text, name


# --------------------------------------------------------------------------- #
# Clubs, divisions, the champion rule
# --------------------------------------------------------------------------- #
def test_club_literal_equals_canonical_org_from_id():
    import trades
    assert len(sc.CLUB_BY_ID) == 30
    for tid, code in sc.CLUB_BY_ID.items():
        assert trades.canonical_org_from_id(tid) == code, tid


def test_division_literal_matches_every_tracked_season():
    for y in range(2000, 2026):
        for rec in labs(y)["records"]:
            for tr in rec["teamRecords"]:
                assert st.division_of(tr["team"]["id"], y) == rec["division"]["id"], (y, tr["team"]["id"])


def test_champion_pin_equals_franchise_export():
    import franchise_export as fe
    for y in range(2000, 2026):
        recs = labs(y)["records"]
        assert st.division_champions(recs, live=False) == fe.division_champions(recs, live=False), y
    for name in ("p1_2026-09-20.json", "p3_2026-03-25.json", "standings_2026.json"):
        recs = load(name)["records"]
        for live in (True, False):
            assert st.division_champions(recs, live) == fe.division_champions(recs, live), (name, live)


def test_parity_with_franchise_export_standings(monkeypatch):
    import franchise_export as fe
    monkeypatch.setattr(fe, "CACHE", LABS)
    out, _ids, _dis = fe._standings()
    n = 0
    for y in range(2000, 2026):
        for r in st.parse_standings(labs(y), f"{y}-10-01", final=True)["rows"]:
            ref = out[r["code"]][y]
            assert (r["w"], r["l"], r["rs"], r["ra"], r["ranks"]["div"]) == \
                (ref["w"], ref["l"], ref["rs"], ref["ra"], ref["rank"]), (y, r["code"])
            n += 1
    assert n == 26 * 30


# --------------------------------------------------------------------------- #
# FORMAT and the tiebreak literals, pinned to the plan text
# --------------------------------------------------------------------------- #
def test_format_table_pinned_to_the_plan():
    for y in range(1995, 2012):
        assert st.FORMAT[y]["wc_spots"] == 1 and st.FORMAT[y]["byes"] == 0
    for y in list(range(2012, 2020)) + [2021]:
        assert st.FORMAT[y]["wc_spots"] == 2 and st.FORMAT[y]["byes"] == 0
    for y in range(2022, 2027):
        assert st.FORMAT[y]["wc_spots"] == 3 and st.FORMAT[y]["byes"] == 2
    f20 = st.FORMAT[2020]
    assert (f20["wc_spots"], f20["division_spots"], f20["per_league"], f20["scheduled"]) == (2, 2, 8, 60)
    assert f20["notes"] == ["2020: a 60-game season; eight clubs per league reached the postseason."]
    for y, f in st.FORMAT.items():
        if y not in (1995, 2020):
            assert f["scheduled"] == 162 and f["notes"] == [] and f["division_spots"] == 1
            assert f["per_league"] == 3 + f["wc_spots"]
    assert st.format_for(2027) == st.FORMAT[2026]
    with pytest.raises(KeyError):
        st.format_for(1990)


def test_tiebreak_literals_pinned_and_keyed_by_season():
    assert st.TIEBREAK_BY_RULE == ("Ties for a postseason spot are broken by rule, not by an extra game, "
                                   "head-to-head record first. The order on this page is MLB's own.")
    assert st.TIEBREAK_2020 == ("Ties for a postseason spot were broken by rule, not by an extra game. "
                                "The order on this page is MLB's own.")
    assert st.TIEBREAK_EXTRA_GAME == ("Ties for a postseason spot were settled by an extra game, counted in "
                                      "the standings. The order on this page is MLB's own.")
    assert st.tiebreak_text(2020) == st.TIEBREAK_2020
    assert st.tiebreak_text(2021) == st.TIEBREAK_EXTRA_GAME
    assert st.tiebreak_text(2000) == st.tiebreak_text(2019) == st.TIEBREAK_EXTRA_GAME
    assert st.tiebreak_text(2022) == st.tiebreak_text(2026) == st.TIEBREAK_BY_RULE
    assert season_file("2020")["tiebreak"]["text"] == st.TIEBREAK_2020
    assert season_file("2026")["tiebreak"]["text"] == st.TIEBREAK_BY_RULE


def test_qualified_text_literal():
    assert st.QUALIFIED_TEXT == {
        "final": {"division": "Division winner", "division_second": "Division second place", "wild_card": "Wild card"},
        "in_season": {"division": "Leads the division", "division_second": "Second in the division",
                      "wild_card": "Holds a wild card spot"}}


# --------------------------------------------------------------------------- #
# Every fixture through the validator (T1 to T9, T11, T14, T15, T17, T19, T20)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tag", ALL_FIX)
def test_every_fixture_builds_and_validates(tag):
    pay, as_of, final = fixture(tag)
    f = season_file(tag)
    res = st.validate_standings(st.KIND_SEASON, f, name=f"standings/{f['season']}.json", source=pay)
    assert res["ok"], res["refused"]
    assert res["bytes"] <= 40 * 1024
    assert len(f["rows"]) == 30 and f["copyright"] == pay["copyright"]
    for r in f["rows"]:
        assert r["w"] + r["l"] + r["t"] == r["gp"]                                   # T1
        if r["w"] + r["l"]:
            assert abs(r["pct"] - r["w"] / (r["w"] + r["l"])) <= 0.0006              # T3
        assert r["rd"] == r["rs"] - r["ra"]                                          # T4
        assert r["x_exp"] == 1.83                                                    # T9
    assert sum(r["w"] for r in f["rows"]) == sum(r["l"] for r in f["rows"])          # T2
    assert f["k90"] == 0.885


def test_league_conservation_on_the_probe_and_the_final():
    assert sum(r["w"] for r in season_file("p1")["rows"]) == 2339
    assert sum(r["w"] for r in season_file("2026")["rows"]) == 2429


def test_t9_fails_closed_to_a_null_exponent():
    pay, as_of, final = fixture("2026")
    bad = copy.deepcopy(pay)
    tr = bad["records"][0]["teamRecords"][0]
    tr["records"]["expectedRecords"][0]["wins"] += 1
    tr["records"]["expectedRecords"][0]["losses"] -= 1
    f = st.build_season_file(bad, as_of=as_of, final=True, generated_at=GEN)
    assert all(r["x_exp"] is None for r in f["rows"]) and f["k90"] is None
    assert st.validate_standings(st.KIND_SEASON, f)["ok"]


# --------------------------------------------------------------------------- #
# Marks, e, GB, WCGB, magic
# --------------------------------------------------------------------------- #
def test_2026_marks_and_phi_never_champion():
    rows = rows_by_code(season_file("2026"))
    marks = {c: r["mark"] for c, r in rows.items() if r["mark"]}
    assert marks == {"TBR": "z", "MIL": "z", "CLE": "y", "HOU": "y", "ATL": "y", "LAD": "y",
                     "NYY": "w", "BOS": "w", "CHW": "w", "PHI": "w", "CHC": "w", "SDP": "w"}
    assert {c for c, r in rows.items() if r["e"]} == set(rows) - set(marks)
    pay = load("standings_2026.json")
    phi = next(tr for rec in pay["records"] for tr in rec["teamRecords"] if tr["team"]["id"] == 143)
    assert phi["divisionChamp"] is True                         # the feed's flag, never read
    for live in (True, False):
        assert "PHI" not in st.division_champions(pay["records"], live).values()
    assert rows["PHI"]["qualified"] == "wild_card"


@pytest.mark.parametrize("y, e_listed", [(2012, set()), (2020, {"SFG"}), (2024, {"ARI"}), (2025, {"HOU", "NYM"})])
def test_completed_seasons_partition_after_the_rule(y, e_listed):
    pay = load(f"standings_{y}.json") if y != 2025 else labs(2025)
    f = st.build_season_file(pay, as_of=f"{y}-10-01", final=True, generated_at=GEN)
    assert sum(1 for r in f["rows"] if r["mark"] or r["e"]) == 30
    assert not any(r["mark"] and r["e"] for r in f["rows"])
    listed = {d["code"] for d in f["accountability"]["feed_disagreements"] if d["field"] == "e"}
    assert listed == e_listed


def test_2020_gb_disagreement_listed_and_computed_gb_served():
    f = season_file("2020")
    gb = [d for d in f["accountability"]["feed_disagreements"] if d["field"] == "gb"]
    assert len(gb) == 30
    rows = rows_by_code(f)
    assert rows["TBR"]["gb"] == 0.0 and rows["TBR"]["gb_feed"] != "-"
    for d in gb:
        assert d["served"] == rows[d["code"]]["gb"]
    by_div = {}
    for r in f["rows"]:
        by_div.setdefault(r["div"], []).append(r)
    for rs in by_div.values():
        best = max(r["w"] - r["l"] for r in rs)
        assert all(r["gb"] == (best - (r["w"] - r["l"])) / 2 for r in rs)


def test_p1_blue_jays_alive_rays_magic_fallback_and_the_wcgb_sign():
    f = season_file("p1")
    rows = rows_by_code(f)
    tor = rows["TOR"]
    assert tor["elim_div"] == "E" and tor["elim_wc"] == 3 and tor["e"] is False and tor["mark"] is None
    assert rows["NYY"]["elim_div"] == 2 and rows["TBR"]["magic"] == 2
    assert {"field": "magic", "code": "TBR", "feed": "-", "served": 2,
            "why": "the division is not clinched; the runner-up's division elimination number"} \
        in f["accountability"]["feed_disagreements"]
    nyy = rows["NYY"]
    assert nyy["wcgb_feed"] == "+9.5" and nyy["wcgb"] == 9.5 and nyy["wc_ahead"] is True
    assert rows["CHW"]["wcgb"] == 0.0 and rows["CHW"]["wc_ahead"] is False
    assert rows["TOR"]["wcgb"] == 3.0 and rows["TOR"]["wc_ahead"] is False
    assert rows["TBR"]["wcgb"] is None and rows["TBR"]["ranks"]["wc"] is None
    assert not [d for d in f["accountability"]["feed_disagreements"] if d["field"] == "wcgb"]


def test_p3_missing_clinch_key_is_no_mark():
    rows = season_file("p3")["rows"]
    assert all(r["mark"] is None and r["e"] is False for r in rows)


# --------------------------------------------------------------------------- #
# Seeds (T19)
# --------------------------------------------------------------------------- #
def _seeds(f):
    return {lg: [r["code"] for r in sorted((r for r in f["rows"] if r["lg"] == lg and r["seed"]),
                                            key=lambda r: r["seed"])] for lg in ("AL", "NL")}


def test_2026_seeds_equal_the_bracket_simulator():
    f = season_file("2026")
    rows = rows_by_code(f)
    want = load("seeds_2026.json")["clubs"]
    assert len(want) == 12
    for c in want:
        assert rows[c["team"]]["seed"] == c["seed"] and rows[c["team"]]["lg"] == c["league"], c
    assert _seeds(f) == {"AL": ["TBR", "CLE", "HOU", "NYY", "BOS", "CHW"],
                         "NL": ["MIL", "LAD", "ATL", "SDP", "CHC", "PHI"]}
    assert rows["PHI"]["qualified"] == "wild_card" and rows["PHI"]["qualified_text"] == "Wild card"
    assert rows["TBR"]["qualified_text"] == "Division winner"


def test_2020_seeds_equal_mlbs():
    f = season_file("2020")
    assert _seeds(f) == {"AL": ["TBR", "ATH", "MIN", "CLE", "NYY", "HOU", "CHW", "TOR"],
                         "NL": ["LAD", "ATL", "CHC", "SDP", "STL", "MIA", "CIN", "MIL"]}
    rows = rows_by_code(f)
    for lg in ("AL", "NL"):
        q = [rows[c]["qualified"] for c in _seeds(f)[lg]]
        assert q == ["division"] * 3 + ["division_second"] * 3 + ["wild_card"] * 2
    assert rows["CLE"]["qualified_text"] == "Division second place"


@pytest.mark.parametrize("tag", ["2012", "2016", "2024", "2026", "2020"])
def test_final_seeded_set_is_the_marked_set_and_division_clubs_are_the_champions(tag):
    f = season_file(tag)
    assert {r["code"] for r in f["rows"] if r["seed"]} == {r["code"] for r in f["rows"] if r["mark"]}
    champs = set(st.division_champions(fixture(tag)[0]["records"], live=False).values())
    assert {r["code"] for r in f["rows"] if r["qualified"] == "division"} == champs


@pytest.mark.parametrize("tag", ALL_FIX)
def test_seed_law_per_league(tag):
    f = season_file(tag)
    fmt = f["format"]
    for lg in ("AL", "NL"):
        rows = [r for r in f["rows"] if r["lg"] == lg]
        assert sorted(r["seed"] for r in rows if r["seed"]) == list(range(1, 3 + fmt["wc_spots"] + (3 if fmt["division_spots"] == 2 else 0) + 1))
        for r in rows:
            assert (r["seed"] is None) == (r["qualified"] is None) == (r["qualified_text"] is None)


@pytest.mark.parametrize("tag", ["p1", "p3"])
def test_in_season_one_division_qualifier_per_division(tag):
    f = season_file(tag)
    divs = {}
    for r in f["rows"]:
        if r["qualified"] == "division":
            divs.setdefault(r["div"], []).append(r["code"])
    assert len(divs) == 6 and all(len(v) == 1 for v in divs.values())
    texts = {r["qualified_text"] for r in f["rows"] if r["seed"]}
    assert texts == {"Leads the division", "Holds a wild card spot"}


# --------------------------------------------------------------------------- #
# League records (T20)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tag", ALL_FIX)
def test_league_records_copied_and_reconciled(tag):
    pay, _a, _f = fixture(tag)
    rows = rows_by_code(season_file(tag))
    for rec in pay["records"]:
        own_lg = rec["league"]["id"]
        for tr in rec["teamRecords"]:
            r = rows[sc.club_code(tr["team"]["id"])]
            lrs = tr["records"]["leagueRecords"]
            own = next(x for x in lrs if x["league"]["id"] == own_lg)
            other = next(x for x in lrs if x["league"]["id"] != own_lg)
            assert r["vs_lg"] == [own["wins"], own["losses"]]
            assert r["intr"] == [other["wins"], other["losses"]]
            dsum = [sum(x["wins"] for x in tr["records"]["divisionRecords"]),
                    sum(x["losses"] for x in tr["records"]["divisionRecords"])]
            assert r["vs_lg"] == dsum
            assert [r["vs_lg"][0] + r["intr"][0], r["vs_lg"][1] + r["intr"][1]] == [r["w"], r["l"]]
            own_div = next(x for x in tr["records"]["divisionRecords"] if x["division"]["id"] == rec["division"]["id"])
            assert r["vs_div"] == [own_div["wins"], own_div["losses"]]


# --------------------------------------------------------------------------- #
# Served derivations (T15) and the game list
# --------------------------------------------------------------------------- #
def test_the_161_game_clubs_have_none_left_in_the_final_file():
    rows = rows_by_code(season_file("2026"))
    assert rows["NYY"]["gp"] == rows["BAL"]["gp"] == 161
    assert rows["NYY"]["left"] == rows["BAL"]["left"] == 0
    assert all(r["left"] == 0 for r in rows.values())


def test_synthetic_postponement_never_made_up(synth_games):
    assert st.games_left(synth_games, "NYY", "2026-04-05") == 1
    assert st.games_left(synth_games, "NYY", "2026-04-06") == 0
    assert st.games_left(synth_games, "TOR", "2026-04-05") == 1
    assert st.games_left(synth_games, "BOS", "2026-04-03") == 3          # suspended, 04-04 and 04-07
    assert st.games_left(synth_games, "BOS", "2026-04-06") == 1
    assert st.games_left(synth_games, "LAD", "2026-04-06") == 0


def test_head_to_head(synth_games):
    h = st.head_to_head(synth_games, "NYY", "BAL")
    assert h == {"NYY": [2, 1], "BAL": [1, 2]}                       # the doubleheader split counts two
    assert st.head_to_head(synth_games, "BOS", "TBR") == {"BOS": [0, 1], "TBR": [1, 0]}    # suspended, once
    assert st.head_to_head(synth_games, "LAD", "NYY") == {"LAD": [0, 0], "NYY": [0, 0]}    # never met
    assert st.head_to_head(synth_games, 147, 110) == h


def test_doubleheader_order_and_the_suspended_date(synth_games):
    fins = st.final_games(synth_games)
    pks = [g["pk"] for g in fins]
    assert pks.index(900003) < pks.index(900004)
    assert len([p for p in pks if p == 900005]) == 1
    assert next(g for g in fins if g["pk"] == 900005)["date"] == "2026-04-04"
    assert st.last_results(synth_games, "NYY") == "WWLW"
    race = st.build_race(synth_games, 2026)
    assert race["dates"] == ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]
    i2, i4 = race["dates"].index("2026-04-02"), race["dates"].index("2026-04-04")
    assert race["clubs"]["TBR"][i2] == [0, 0, 0, 0]
    assert race["clubs"]["TBR"][i4] == [1, 0, 6, 5]
    assert race["clubs"]["NYY"][race["dates"].index("2026-04-03")] == [2, 1, 14, 8]
    assert race["last10"]["NYY"] == "WWLW"


def test_l10_seq_matches_the_feed_on_the_2026_final(tail_2026):
    f = season_file("2026", games=tail_2026)
    for r in f["rows"]:
        assert len(r["l10_seq"]) == 10 and r["l10_seq"].count("W") == r["l10"][0], r["code"]
        assert r["streak"][0] == r["l10_seq"][-1]
    assert rows_by_code(f)["MIL"]["l10_seq"].endswith("WWWWW") and rows_by_code(f)["MIL"]["streak"] == "W5"
    assert st.validate_standings(st.KIND_SEASON, f, games=tail_2026)["ok"]
    assert all(r["l10_seq"] is None for r in season_file("2026")["rows"])     # no game list, no sequence


@pytest.mark.parametrize("tag", ALL_FIX)
def test_served_derivations(tag):
    f = season_file(tag)
    for r in f["rows"]:
        for key, num in (("rdg", r["rd"]), ("rs_g", r["rs"]), ("ra_g", r["ra"])):
            assert r[key] == (None if r["gp"] == 0 else st.round2(num, r["gp"]))
        if r["x_wl"] is not None:
            assert r["w_xw"] == r["w"] - r["x_wl"][0]
    nyy = rows_by_code(season_file("2026"))["NYY"]
    assert nyy["rdg"] == st.round2(nyy["rd"], 161) and isinstance(nyy["rdg"], float)
    assert st.round2(1, 8) == 0.13 and st.round2(-1, 8) == -0.13 and st.round2(5, 0) is None


def test_wc_gap_on_the_last_date_equals_the_signed_wcgb():
    games = synth_season(n_dates=40)
    last = st.final_games(games)[-1]["date"]
    pay = synth_standings(games, last)
    race = st.build_race(games, 2026, {last: pay}, copyright=pay["copyright"], generated_at=GEN)
    f = st.build_season_file(pay, as_of=last, final=False, generated_at=GEN, games=games, race=race)
    assert f["opening_day"] == race["dates"][0] == "2026-03-26"
    res = st.validate_standings(st.KIND_SEASON, f, name="standings/2026.json", games=games, race=race)
    assert res["ok"], res["refused"]
    n_leaders = 0
    for r in f["rows"]:
        gap = race["wc_gap"][r["code"]][-1]
        if r["wcgb"] is None:
            assert gap is None
            n_leaders += 1
        else:
            assert gap == (r["wcgb"] if r["wc_ahead"] else -r["wcgb"]), r["code"]
        assert race["clubs"][r["code"]][-1] == [r["w"], r["l"], r["rs"], r["ra"]]
        assert r["left"] == 0 and r["l10_seq"].count("W") == r["l10"][0]
    assert n_leaders == 6


def test_race_matches_every_snapshot_and_reports_a_middle_date():
    games = synth_season(n_dates=30, seed=11)
    dates = sorted({g["date"] for g in games})
    d1, d2, d3 = dates[5], dates[15], dates[-1]
    snaps = {d: synth_standings(games, d) for d in (d1, d2, d3)}
    race = st.build_race(games, 2026, snaps)
    assert st.race_matches_snapshots(race, snaps) == []
    bad = copy.deepcopy(snaps)
    tr = bad[d2]["records"][2]["teamRecords"][1]
    tr["wins"] += 1
    code = sc.club_code(tr["team"]["id"])
    assert st.race_matches_snapshots(race, bad) == [(d2, code, "w")]
    # a snapshot on a date with no game holds the previous totals
    gap_day = (date.fromisoformat(d3) + timedelta(days=1)).isoformat()
    assert st.race_matches_snapshots(race, {gap_day: snaps[d3]}) == []


# --------------------------------------------------------------------------- #
# Builders, the compact writer, budgets
# --------------------------------------------------------------------------- #
def test_kinds_budgets_and_names():
    k = sc.FILE_KINDS
    assert (k[st.KIND_SEASON]["budget"], k[st.KIND_SEASON]["ceiling"]) == (40 * 1024, 160 * 1024)
    assert (k[st.KIND_RACE]["budget"], k[st.KIND_RACE]["ceiling"]) == (160 * 1024, 640 * 1024)
    assert (k[st.KIND_PHIST]["budget"], k[st.KIND_PHIST]["ceiling"]) == (256 * 1024, 1024 * 1024)
    assert (k[st.KIND_SNAPSHOT]["budget"], k[st.KIND_SNAPSHOT]["ceiling"]) == (40 * 1024, 160 * 1024)
    assert sc.kind_of_name("standings/2026.json") == st.KIND_SEASON
    assert sc.kind_of_name("standings/2026-race.json") == st.KIND_RACE
    assert sc.kind_of_name("standings/2026-phist.json") == st.KIND_PHIST
    assert sc.kind_of_name("standings/2026/2026-06-01.json") == st.KIND_SNAPSHOT
    assert sc.kind_of_name("standings/other.json") is None
    assert "standings" not in sc.FILE_KINDS


def test_phist_builder_starts_empty():
    p = st.build_phist_file(2026, generated_at=GEN, copyright=load("standings_2026.json")["copyright"])
    assert p["regular"]["as_of"] == [] and p["post"]["as_of"] == [] and p["regular"]["clubs"] == {}
    assert p["switch_as_of"] is None and p["closed"] is False
    assert p["regular"]["fields"] == ["p_div", "p_post", "p_bye", "p_pennant", "p_ws"]
    assert p["post"]["fields"] == ["p_pennant", "p_ws"] and p["post"]["sha256"] == []
    assert st.validate_standings(st.KIND_PHIST, p, name="standings/2026-phist.json")["ok"]


def test_snapshot_file_has_no_ours_and_its_name_is_its_date():
    pay, as_of, _f = fixture("p1")
    s = st.build_snapshot_file(pay, as_of=as_of, final=False, generated_at=GEN)
    assert "ours" not in s and "registry" not in s
    assert st.validate_standings(st.KIND_SNAPSHOT, s, name="standings/2026/2026-09-20.json")["ok"]
    res = st.validate_standings(st.KIND_SNAPSHOT, s, name="standings/2026/2026-09-21.json")
    assert any(r == "1" for r, m in res["refused"])


def test_compact_writer_round_trips_every_file_kind(tmp_path, synth_games):
    pay, as_of, _f = fixture("2026")
    files = {
        "standings/2026.json": season_file("2026"),
        "standings/2026/2026-09-20.json": st.build_snapshot_file(load("p1_2026-09-20.json"), as_of="2026-09-20",
                                                                 final=False, generated_at=GEN),
        "standings/2026-race.json": st.build_race_file(synth_games, 2026, copyright=pay["copyright"],
                                                       generated_at=GEN),
        "standings/2026-phist.json": st.build_phist_file(2026, generated_at=GEN, copyright=pay["copyright"]),
    }
    for name, obj in files.items():
        path = tmp_path / name
        n = st.write_file(path, obj)
        b = path.read_bytes()
        assert len(b) == n and b == st.encode(obj)
        assert b == json.dumps(json.loads(b), separators=(",", ":"), ensure_ascii=False).encode("utf-8"), name
        assert b"\n" not in b and b": " not in b
        assert st.validate_standings(sc.kind_of_name(name), json.loads(b), name=name)["ok"], name
    assert not list(tmp_path.rglob(".tmp-*"))


def _phist(n_regular, n_post):
    codes = sorted(sc.CLUB_BY_ID.values())
    d0 = date(2025, 3, 1)
    reg_dates = [(d0 + timedelta(days=i)).isoformat() for i in range(n_regular)]
    post_dates = [(d0 + timedelta(days=n_regular + i)).isoformat() for i in range(n_post)]
    regular = {"source": "futures ledger on this machine", "missing": [], "as_of": reg_dates,
               "clubs": {c: [[0.123] * 5 for _ in reg_dates] for c in codes}}
    post = {"as_of": post_dates, "sha256": ["ab" * 32 for _ in post_dates],
            "clubs": {c: [[0.123456] * 2 for _ in post_dates] for c in codes[:12]}}
    return st.build_phist_file(2025, generated_at=GEN, copyright=load("standings_2026.json")["copyright"],
                               regular=regular, post=post, switch_as_of=post_dates[0] if post_dates else None)


def test_phist_size_bound():
    # Why 240 bounds a real file (plan 4.7 'The two odds blocks'): the blocks
    # are disjoint and both lie between opening_day and the last postseason
    # game, one entry per date, so a season holds at most 229 entries (2025,
    # 2025-03-18 to 2025-11-01) or 221 (2026, 2026-03-25 to 2026-10-31); a
    # regular entry outweighs a post entry, so all-regular is the heaviest.
    p = _phist(240, 35)
    n = len(st.encode(p))
    assert n < 256 * 1024, n
    res = st.validate_standings(st.KIND_PHIST, p, name="standings/2025-phist.json")
    assert res["ok"] and not res["logged"], res
    year = _phist(366, 0)
    n = len(st.encode(year))
    assert n < 1024 * 1024, n
    assert st.validate_standings(st.KIND_PHIST, year, name="standings/2025-phist.json")["ok"]


def test_a_full_season_race_with_wc_gap_fits_its_budget():
    games = synth_season(n_dates=184)
    race = st.build_race_file(games, 2026, copyright=load("standings_2026.json")["copyright"], generated_at=GEN)
    assert len(race["dates"]) == 184 and all(len(v) == 184 for v in race["wc_gap"].values())
    n = len(st.encode(race))
    assert n < 160 * 1024, n
    res = st.validate_standings(st.KIND_RACE, race, name="standings/2026-race.json")
    assert res["ok"] and not res["logged"], res


# --------------------------------------------------------------------------- #
# The validator: forbidden keys, rule 4 as amended, broken laws refused
# --------------------------------------------------------------------------- #
FORBIDDEN_WORDS = ("record", "records", "odds", "price_x", "implied_prob", "market", "decision", "advance", "edge")


def test_no_forbidden_key_in_any_built_file(synth_games):
    built = [season_file(t) for t in ALL_FIX] + [st.build_race(synth_games, 2026),
                                                   st.build_phist_file(2026, generated_at=GEN)]
    for obj in built:
        assert sc.find_forbidden_keys(obj) == []
    f = season_file("2026")
    for key in FORBIDDEN_WORDS:
        bad = copy.deepcopy(f)
        bad["rows"][0][key] = 1
        res = st.validate_standings(st.KIND_SEASON, bad)
        assert any(r == "9" for r, m in res["refused"]), key


def test_rule_4_amended_for_standings_files_only():
    f = season_file("2026")
    line = f["copyright"]
    assert line.startswith("Copyright 2026 MLB Advanced Media, L.P.  Use") and sc.MLB_TERMS_URL in line
    assert st.validate_standings(st.KIND_SEASON, f, name="standings/2026.json")["ok"]
    one_space = copy.deepcopy(f)
    one_space["copyright"] = line.replace("L.P.  Use", "L.P. Use")
    assert any(r == "4" for r, m in st.validate_standings(st.KIND_SEASON, one_space)["refused"])
    elsewhere = copy.deepcopy(f)
    elsewhere["rows"][0]["note"] = line
    assert any(r == "4" for r, m in st.validate_standings(st.KIND_SEASON, elsewhere)["refused"])
    url_only = copy.deepcopy(f)
    url_only["accountability"]["source"] = sc.MLB_TERMS_URL
    assert any(r == "4" for r, m in st.validate_standings(st.KIND_SEASON, url_only)["refused"])
    for kind, obj in ((st.KIND_RACE, st.build_race([], 2026, copyright=line)),
                      (st.KIND_PHIST, st.build_phist_file(2026, generated_at=GEN, copyright=line))):
        assert st.validate_standings(kind, obj)["ok"], kind
    season_index = {"schema": 1, "season": 2026, "dates": [], "bracket": None, "copyright": line}
    res = sc.validate_payload("season_index", season_index, name="index-2026.json")
    assert not res["ok"] and any(r == "4" for r, m in res["refused"])


@pytest.mark.parametrize("mutate, rule", [
    (lambda f: f["rows"][0].__setitem__("w", f["rows"][0]["w"] + 1), "T1"),
    (lambda f: f["rows"][0].__setitem__("gb", 3.5), "T5"),
    (lambda f: f["rows"][3].__setitem__("wc_ahead", not f["rows"][3]["wc_ahead"]), "T6"),
    (lambda f: f["rows"][0].__setitem__("e", True), "T8"),
    (lambda f: f["rows"][0].__setitem__("rdg", 9.99), "T15"),
    (lambda f: f["rows"][0].__setitem__("left", 1), "T15"),
    (lambda f: f.__setitem__("k90", 0.9), "T15"),
    (lambda f: f["tiebreak"].__setitem__("text", st.TIEBREAK_2020), "T17"),
    (lambda f: f["rows"][0].__setitem__("seed", 7), "T19"),
    (lambda f: f["rows"][0].__setitem__("qualified_text", "Leads the division"), "T19"),
    (lambda f: f["rows"][0].__setitem__("intr", [0, 0]), "T20"),
    (lambda f: f.__setitem__("schema", 2), "1"),
    (lambda f: f["format"].__setitem__("wc_spots", 2), "T6"),
])
def test_validator_refuses_a_broken_law(mutate, rule):
    f = season_file("2026")
    assert st.validate_standings(st.KIND_SEASON, f)["ok"]
    bad = copy.deepcopy(f)
    mutate(bad)
    res = st.validate_standings(st.KIND_SEASON, bad)
    assert not res["ok"] and any(r == rule for r, m in res["refused"]), res["refused"]


def test_validator_reconciles_to_the_saved_response():
    pay, as_of, _f = fixture("2026")
    f = season_file("2026")
    assert st.validate_standings(st.KIND_SEASON, f, source=pay)["ok"]
    other = copy.deepcopy(pay)
    other["records"][0]["teamRecords"][0]["runsScored"] += 1
    res = st.validate_standings(st.KIND_SEASON, f, source=other)
    assert any(r == "T11" for r, m in res["refused"])


def test_validator_t12_on_a_copied_odds_block():
    f = season_file("2026")
    f["ours"] = {"clubs": {"TBR": {"p_div": 1.0, "p_post": 1.0, "p_bye": 1.0, "p_pennant": 0.3, "p_ws": 0.1}}}
    assert st.validate_standings(st.KIND_SEASON, f)["ok"]
    f["ours"]["clubs"]["TBR"]["p_ws"] = 0.4
    assert any(r == "T12" for r, m in st.validate_standings(st.KIND_SEASON, f)["refused"])


def test_revs_match():
    files = {"standings/2026.json": st.encode(season_file("2026"))}
    entries = [{"season": 2026, "rev": sc.rev_of(files["standings/2026.json"]), "race_rev": None}]
    assert st.revs_match(entries, files.get) == []
    entries[0]["rev"] = "000000000000"
    assert st.revs_match(entries, files.get) == [("11", "rev of 2026 does not hash the bytes on disk")]


def test_t7_band_miss_is_logged_not_refused():
    # 2020's Reds read a division elimination number of 2 after the last game
    f = season_file("2020")
    res = st.validate_standings(st.KIND_SEASON, f)
    assert res["ok"] and any(r == "T7" and "CIN" in m for r, m in res["logged"])
    assert any(d["field"] == "division_elimination" and d["code"] == "CIN"
               for d in f["accountability"]["feed_disagreements"])
    # in season too (STANDINGS_2's 2026 backfill: early-season numbers sit far
    # below the band), MLB's number is served, logged and listed, never refused
    inseason = copy.deepcopy(season_file("p1"))
    assert not any(d["field"] in ("magic", "division_elimination", "wild_card_elimination")
                   and "G + 1" in d["why"] for d in inseason["accountability"]["feed_disagreements"])
    next(r for r in inseason["rows"] if r["code"] == "CHW")["elim_div"] = 9
    res = st.validate_standings(st.KIND_SEASON, inseason)
    assert res["ok"] and any(r == "T7" and "CHW" in m for r, m in res["logged"])
    assert st.t7_misses(inseason["rows"], inseason["format"])[0][:3] == ("CHW", "division elimination", 9)


# --------------------------------------------------------------------------- #
# 10. The tracked copy
# --------------------------------------------------------------------------- #
def test_tracked_copy_holds_26_trimmed_seasons_under_its_bound():
    files = sorted(LABS.glob("statsapi_standings_*.json"))
    assert [f.name for f in files] == [f"statsapi_standings_{y}.json" for y in range(2000, 2026)]
    assert sum(f.stat().st_size for f in files) < 1.5 * 1024 * 1024
    for y in range(2000, 2026):
        d = labs(y)
        assert d["_source"]["file"] == f".cache/statsapi_standings_{y}.json" and d["_source"]["mtime"]
        assert st.COPYRIGHT_RE.match(d["copyright"])
        tr = d["records"][0]["teamRecords"][0]
        assert set(tr["team"]) == {"id"} and "divisionChamp" not in tr and "clinched" not in tr
        f = st.build_season_file(d, as_of=f"{y}-10-01", final=True, generated_at=GEN)
        res = st.validate_standings(st.KIND_SEASON, f, name=f"standings/{y}.json", source=d)
        assert res["ok"], (y, res["refused"])


def test_write_labs_copy_never_fetches(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "statsapi_standings_2026.json").write_bytes((FIX / "standings_2026.json").read_bytes())
    sizes = st.write_labs_copy(cache, tmp_path / "out", seasons=[2026])
    out = json.loads((tmp_path / "out" / "statsapi_standings_2026.json").read_text(encoding="utf-8"))
    assert sizes[2026] == (tmp_path / "out" / "statsapi_standings_2026.json").stat().st_size
    assert out["_source"]["file"] == ".cache/statsapi_standings_2026.json"
    assert out["records"] == st.trim_payload(load("standings_2026.json"))["records"]
    with pytest.raises(st.MissingCache, match="standings cache 2025 missing"):
        st.write_labs_copy(cache, tmp_path / "out", seasons=[2025])


def test_fixtures_stay_small():
    for f in FIX.glob("*.json"):
        assert f.stat().st_size < 200 * 1024, f.name
