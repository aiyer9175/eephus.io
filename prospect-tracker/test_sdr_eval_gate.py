# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fixture tests for the in-house SDR path: the adapter (tools/sdr_inhouse.py)
and the gate read (tools/sdr_eval_gate.py). Offline; no fetch, no real data.
The fixture carries nulls on purpose (catchers without OAA, players without a
B-Ref row, seasons without UZR) so the dry run exercises every refusal path."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import sdr_eval_gate as G  # noqa: E402
import sdr_inhouse as S  # noqa: E402


def fixture_inputs(seed: int = 7) -> "G.Inputs":
    rng = np.random.default_rng(seed)
    seasons = list(range(2017, 2023))
    pos_cycle = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
    players = [(1000 + i, pos_cycle[i % 8], rng.normal()) for i in range(64)]
    drop, fg, split, rf, team, nd, ns = [], {}, {}, [], {}, [], []
    for s in seasons:
        rows = []
        for pid, pos, talent in players:
            if rng.random() < 0.1:
                continue                                  # missing season
            inn = float(rng.uniform(300, 1400))
            noise = rng.normal(scale=0.8)
            sdr = (talent + noise) * inn / 1000
            rows.append({"player_id": pid, "Pos": pos, "Inn": inn,
                         "OAA": np.nan if pos == "C" else (talent + rng.normal()) * inn / 900,
                         "DRS": (talent + rng.normal()) * inn / 900,
                         "FRP": (talent + rng.normal()) * inn / 900,
                         "UZR": np.nan if (pos == "C" or s >= 2021) else (talent + rng.normal()) * inn / 900,
                         "Defense": (talent + rng.normal()) * inn / 900})
            drop.append({"player_id": pid, "season": s, "primary_position": pos, "innings": inn,
                         "sdr_runs": sdr, "player_name": f"P{pid}",
                         "framing_runs": rng.normal() if pos == "C" else np.nan,
                         "blocking_runs": rng.normal() if pos == "C" and s >= 2018 else np.nan})
            nd.append({"player_id": pid, "season": s, "Pos": pos,
                       "sdr_runs": np.nan if pos == "C" else sdr + rng.normal(scale=0.1)})
            ns.append({"player_id": pid, "season": s, "Pos": pos, "sdr_runs": sdr * 0.9})
            if pid % 11 != 0:                             # some players lack a B-Ref row
                rf.append({"player_id": pid, "season": s,
                           "runs_field": (talent + rng.normal()) * inn / 1000, "inn": inn})
        f = pd.DataFrame(rows)
        fg[s] = f
        sp = f[["player_id", "Pos", "Inn"]].copy()
        sp["teamid"] = sp.player_id % 6 + 1
        split[s] = sp
        team[s] = pd.DataFrame({"teamid": range(1, 7), "R": rng.normal(700, 40, 6),
                                "FIP": rng.normal(4.2, 0.3, 6), "IP": [1440.1] * 6})
    return G.Inputs(drop=pd.DataFrame(drop), fg=fg, split=split, rfield=pd.DataFrame(rf),
                    team=team, variants={"no_drs": pd.DataFrame(nd), "no_statcast": pd.DataFrame(ns)},
                    meta={"fixture": True})


def test_dry_run_reports_every_block_on_fixtures_with_nulls():
    res = G.evaluate(fixture_inputs(), b=30)
    assert res["verdict"] in {"PASS", "PARTIAL", "FAIL"}
    for k in ("C1", "C2"):
        c = res["clauses"][k]
        assert "holm" in c and "twin" in c and isinstance(c["passes"], bool)
    assert res["clauses"]["C1"]["n_pairs"] > 0
    # catchers leave the pooled C1 set (OAA does not rate them)
    assert res["per_position"]["C"]["n_pairs"] >= 0
    assert "oaa" not in res["per_position"]["C"]["self_persistence"]
    assert res["C5"]["disposition"] in {"WIN", "LOSS", "UNRESOLVED", "UNRESOLVED (twin also clears)"}
    assert set(res["C4"]["by_position"]) == set(G.POS)
    assert res["C6"].get("n_pairs", 0) >= 0


def test_twin_permutes_within_position_season_only():
    inp = fixture_inputs()
    t = G.permute_sdr(inp.drop, 1)
    a = inp.drop.groupby(["primary_position", "season"]).sdr_runs.apply(sorted)
    b = t.groupby(["primary_position", "season"]).sdr_runs.apply(sorted)
    assert (a == b).all()
    assert not np.allclose(inp.drop.sdr_runs.to_numpy(), t.sdr_runs.to_numpy())


def test_holm_steps_down():
    h = G.holm({"C1": 0.01, "C2": 0.04})
    assert h["C1"]["rejects"] and h["C2"]["rejects"]
    h = G.holm({"C1": 0.03, "C2": 0.04})
    assert not h["C1"]["rejects"] and not h["C2"]["rejects"]
    assert G.holm({"C1": None, "C2": 0.001})["C1"]["rejects"] is False


def test_fg_innings_thirds():
    assert G.fg_ip("1440.1") == pytest.approx(1440 + 1 / 3)
    assert G.fg_ip(536.0) == 536.0


# ---------------------------------------------------------------- adapter

def test_window_is_trailing_and_starts_at_statcast():
    assert S.window(2017) == (2016, 2017)
    assert S.window(2026) == (2022, 2026)
    assert S.COVERAGE[0] == 2017 and S.COVERAGE[-1] == 2026


def test_patches_match_wills_files_exactly_once():
    src06 = (S.WILL / "pipeline" / "06_total_defense_plus.py").read_text(encoding="utf-8")
    for v in S.TOT_VARIANTS:
        out = S.apply_patches(src06, S.patches_06(2019, v))
        assert "YEARS = list(range(2016, 2020))" in out
        assert "cur = F[F.year == 2019].copy()" in out
        if v != "full":
            assert 'TOT = ["OAA", "DRS", "FRP"]' in out      # diagnostics keep every system
            assert "else 0.0) for c in TOT}" in out
    card = (S.WILL / "build_defense_card.py").read_text(encoding="utf-8")
    out = S.apply_patches(card, S.patches_card(2018))
    assert '"defense_card_2018.parquet"' in out


def test_patch_that_misses_refuses():
    with pytest.raises(RuntimeError):
        S.apply_patches("YEARS = [1]\n", [("YEARS = list(range(2021, 2026))", "x")])
    with pytest.raises(RuntimeError):
        S.apply_patches("a a\n", [("a", "b")])


def test_patches_touch_only_config_lines():
    src06 = (S.WILL / "pipeline" / "06_total_defense_plus.py").read_text(encoding="utf-8")
    out = S.apply_patches(src06, S.patches_06(2020, "full"))
    changed = [(a, b) for a, b in zip(src06.splitlines(), out.splitlines()) if a != b]
    assert len(changed) == 4
    for a, _ in changed:
        assert a.startswith(("YEARS", "cur = F", "pd.DataFrame(rows).to_csv", "board[[",
                             "    os.path.join(REP"))


def test_milb_fielding_cache_shape(tmp_path, monkeypatch):
    import json
    d = tmp_path / "sf"
    d.mkdir()
    (d / "fld_v2_11_2019.json").write_text(json.dumps([
        {"mlbam": 5, "pos": "SS", "gs": 40, "season": 2019, "sport": 11},
        {"mlbam": 5, "pos": "2B", "gs": 10, "season": 2019, "sport": 11},
        {"mlbam": 5, "pos": "P", "gs": 3, "season": 2019, "sport": 11}]), encoding="utf-8")
    (d / "fld_v2_12_2018.json").write_text(json.dumps([
        {"mlbam": 6, "pos": "C", "gs": 30, "season": 2018, "sport": 12}]), encoding="utf-8")
    monkeypatch.setattr(S, "STATSAPI_MILB", d)
    m = S.build_milb_fielding([5, 6, 7]).set_index("mlbam_id")
    assert m.loc[5, "pos"] == "SS" and m.loc[5, "total"] == 50 and m.loc[5, "milb_level"] == "AAA"
    assert m.loc[6, "milb_level"] == "AA" and m.loc[6, "played_c"] == 30
    assert m.loc[7, "milb_level"] == "none"
