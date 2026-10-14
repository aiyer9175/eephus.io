# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served half of the DvM+ difficulty arm (dvm_difficulty_serve, DVM-5), on fixtures.

Nothing here reads a grade from the store: the steps are the lab's synthetic fixture
pairs and the table is the lab's dry run on them (fixture receipts), so no growth is
computed on real data before the look. The tests pin the wiring storage relies on:
VAL_4 calendars become tenure events and an unaffiliated stretch credits nobody; every
12-month step gets both credits, re-centered per source and step year; the tool rows
cover the modelled traits only; _build_org_dev_residuals writes the DvM+ family with
every key the trajectory method writes plus dev_expectation; the explainer block prints
verdict words only where the registered read resolved; and the glossary copy prepared
for the flip (tools/dvm_difficulty_glossary_flip.py) is lint-clean and idempotent and
touches no repo file before the owner's flip commit.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import dvm_difficulty_serve as dds  # noqa: E402
import storage  # noqa: E402
import dvm_difficulty_lab as lab  # noqa: E402

CLUBS = sorted(storage.MLB_30_ORGS)
MODELLED = {t for side in lab.SIDES for t in lab.TRAITS[side] if t != "FV"}


def _tenure(start, org):
    return SimpleNamespace(start=start, org=org)


# ---------------------------------------------------------------- pure helpers


def test_the_arm_ships_off_and_the_credit_map_matches_storage():
    assert storage.DVM_DIFFICULTY_ARM is None
    assert set(dds.ARM_CREDIT) == set(storage.DVM_DIFFICULTY_ARMS)
    assert dds.ARM_CREDIT["value"][0] == "v" and dds.ARM_CREDIT["difficulty"][0] == "z"


def test_club_events_opens_each_tenure_and_an_unaffiliated_stretch():
    cal = {"a": [_tenure("2019-03-01", "LAD"), _tenure("2021-07-30", None), _tenure("2022-01-10", "NYY")],
           "b": []}
    assert dds.club_events(cal) == {"a": [("2019-03-01", "LAD", "read"),
                                          ("2021-07-30", dds.UNAFFILIATED, "read"),
                                          ("2022-01-10", "NYY", "read")]}


def test_clean_tau_drops_the_unaffiliated_share_without_renormalizing():
    tau = {"LAD": 0.5, dds.UNAFFILIATED: 0.3, "XXX": 0.2, "NYY": 0.0}
    assert dds.clean_tau(tau, ["LAD", "NYY"]) == {"LAD": 0.5}
    assert dds.clean_tau(None, ["LAD"]) == {}


def test_tool_group_traits_cover_the_modelled_traits_only():
    mapped = {t for ts in dds.TOOL_GROUP_TRAITS.values() for t in ts}
    assert mapped == MODELLED
    assert set(dds.TOOL_GROUP_TRAITS) <= set(storage.TOOL_GROUPS)
    for g in ("pitch_sel", "bat_ctrl", "ct"):
        assert g in storage.TOOL_GROUPS and g not in dds.TOOL_GROUP_TRAITS


def test_window_step_years_follow_the_may_first_rule():
    yrs = storage._dvm_window_end_years("2026-10-14", storage.FARM_TRAJECTORY_WINDOWS)
    assert yrs["1y"] == [2026] and yrs["7y"] == list(range(2020, 2027))
    assert storage._dvm_window_end_years("2026-04-30", {"3y": 3 * 365})["3y"] == [2023, 2024, 2025]
    assert storage._dvm_window_end_years("2026-05-01", {"1y": 365})["1y"] == [2026]


def test_club_aggregate_is_a_tenure_weighted_mean_with_kish_n_and_shrinkage():
    rows = [{"tau": {"LAD": 1.0}, "omega": 1.0, "v": 2.0},
            {"tau": {"LAD": 0.5, "NYY": 0.5}, "omega": 1.0, "v": -2.0},
            {"tau": {"NYY": 1.0}, "omega": 0.5, "v": 4.0}]
    agg = storage._dvm_club_aggregate(rows, "v", 10.0, ["LAD", "NYY", "BOS"])
    assert agg["LAD"]["D"] == pytest.approx((2.0 - 1.0) / 1.5)
    assert agg["LAD"]["N"] == pytest.approx(1.5 ** 2 / (1.0 + 0.25))
    assert agg["LAD"]["D_shrunk"] == pytest.approx(agg["LAD"]["D"] * agg["LAD"]["N"] / (agg["LAD"]["N"] + 10.0))
    assert agg["NYY"]["D"] == pytest.approx((-1.0 + 2.0) / 1.0)
    assert agg["BOS"] == {"D": 0.0, "N": 0.0, "D_shrunk": 0.0, "sum_a": 0, "items": []}


def test_plus_of_is_100_plus_10z_rounded_nearest_halves_up():
    plus = storage._dvm_plus_of({"a": 1.0, "b": 3.0, "c": 5.0})
    assert plus == {"a": 88, "b": 100, "c": 112}
    assert storage._dvm_plus_of({"a": 2.0, "b": 2.0}) == {"a": 100, "b": 100}
    assert storage._dvm_round_nearest(100.5) == 101 and storage._dvm_round_nearest(99.5) == 100
    assert storage._dvm_plus_of({}) == {}


# ------------------------------------------------- the frozen table, on fixtures


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("dvm_fixture")
    lab.run_dry(d, B=4, perms=2, players=160)
    return d


class TestOnTheFixtureTable:
    @pytest.fixture(autouse=True)
    def _seam(self, fixture_dir, monkeypatch):
        monkeypatch.setattr(dds, "_FIXTURE", None)
        dds._install_fixture_for_local_render(fixture_dir)
        self.table, self.ev = dds.load_table()
        self.keys = [f"k{i:04d}" for i in range(120)]
        self.pairs, self.census = dds.serve_pairs(None, calendar_of=lambda pk: [], clubs=CLUBS,
                                                  player_keys=self.keys)

    def test_the_fixture_receipt_is_refused_by_the_look_guard_outside_the_seam(self, monkeypatch):
        assert self.table["receipt"]["fixture"] is True
        assert dds.require_look_table(self.table) == self.table["receipt"]
        monkeypatch.setattr(dds, "_FIXTURE", None)
        with pytest.raises(dds.ArmError):
            dds.require_look_table(self.table)

    def test_fixture_steps_land_on_real_clubs_and_the_given_keys(self):
        assert self.census == {"fixture": True}
        assert self.pairs and all(p["h"] == 1 for p in self.pairs)
        assert {c for p in self.pairs for c in p["tau"]} <= set(CLUBS)
        assert {p["pk"] for p in self.pairs} <= set(self.keys)

    def test_score_gives_every_step_both_credits_recentered_per_source_and_year(self):
        fv_rows, tool_rows = dds.score(self.pairs, self.table, "value")
        assert fv_rows
        groups: dict = {}
        for r in fv_rows:
            assert r["s_hat"] > 0 and r["step_end"] == r["V"] + 1 and r["side"] in lab.SIDES
            assert set(r) >= {"pk", "src", "omega", "tau", "y", "w", "E", "EW", "v", "z",
                              "origin", "rung", "level", "age_rel"}
            groups.setdefault((r["src"], r["step_end"], r["side"]), []).append(r)
        for g in groups.values():
            om = sum(r["omega"] for r in g)
            assert abs(sum(r["omega"] * r["v"] for r in g) / om) < 1e-6
            assert abs(sum(r["omega"] * r["z"] for r in g) / om) < 1e-6
        assert tool_rows and set(tool_rows) <= MODELLED
        for t, rows in tool_rows.items():
            assert all(set(r) == {"pk", "step_end", "side", "omega", "tau", "z"} for r in rows), t

    def test_the_difficulty_arm_reads_the_same_steps_and_an_unknown_arm_is_refused(self):
        fv_v, _ = dds.score(self.pairs, self.table, "value")
        fv_z, _ = dds.score(self.pairs, self.table, "difficulty")
        assert [(r["pk"], r["src"], r["V"]) for r in fv_v] == [(r["pk"], r["src"], r["V"]) for r in fv_z]
        with pytest.raises(dds.ArmError):
            dds.score(self.pairs, self.table, "both")

    def _res(self, arm="value"):
        fv_rows, tool_rows = dds.score(self.pairs, self.table, arm)
        return storage._build_org_dev_residuals(
            fv_rows, tool_rows, table=self.table, arm=arm, as_of="2026-10-14", clubs=CLUBS,
            bucket_of={}, actives=self.keys, tool_group_traits=dds.TOOL_GROUP_TRAITS)

    def test_build_org_dev_residuals_writes_the_family_for_every_club_and_window(self):
        res = self._res()
        assert res["arm"] == "value" and res["credit"] == "v"
        assert res["k_org"] == self.table["k_org"]["DV"]["k_org"]
        assert set(res["by_org"]) == set(CLUBS)
        for win in storage.FARM_TRAJECTORY_WINDOWS:
            vals = [res["by_org"][c]["dvm_plus"][win] for c in CLUBS]
            assert all(isinstance(v, int) for v in vals)
            assert abs(sum(vals) / len(vals) - 100) <= 1
            assert abs(sum(res["by_org"][c]["delta_above_mean"][win] for c in CLUBS)) < 0.01
            for c in CLUBS:
                o = res["by_org"][c]
                for key in ("hitter_dvm_plus", "pitcher_dvm_plus", "hitter_delta_above_mean",
                            "pitcher_delta_above_mean"):
                    assert win in o[key]
                assert set(o["pos_bucket_fv_dvm_plus"]) == set(storage._DVM_DIFF_BUCKETS)
                de = o["dev_expectation"][win]
                assert set(de) >= {"actual", "expected", "residual", "n_eff", "pairs", "publish",
                                   "mix", "step_years", "credit", "credit_shrunk"}
                assert de["step_years"] == storage._dvm_window_end_years(
                    "2026-10-14", storage.FARM_TRAJECTORY_WINDOWS)[win]
                if de["actual"] is not None:
                    assert abs(de["actual"] - de["expected"] - de["residual"]) < 2e-3
                    assert set(de["mix"]) == {"origin", "rung", "level", "mean_age_rel"}
                assert de["publish"] == (de["n_eff"] >= storage.DVM_DIFFICULTY_MIN_PUBLISH_N)

    def test_the_per_tool_pass_keeps_every_tool_group_key_and_blanks_unmodelled_tools(self):
        res = self._res()
        for c in CLUBS:
            o = res["by_org"][c]
            assert set(o["per_tool_dvm_plus"]) == set(storage.TOOL_GROUPS)
            assert set(o["per_tool_dvm_plus_by_bucket"]) == set(storage._DVM_DIFF_BUCKETS)
            for g in ("pitch_sel", "bat_ctrl", "ct"):
                assert o["per_tool_dvm_plus"][g] is None
        modelled_groups = [g for g in storage.TOOL_GROUPS if g in dds.TOOL_GROUP_TRAITS]
        assert any(res["by_org"][c]["per_tool_dvm_plus"][g] is not None
                   for c in CLUBS for g in modelled_groups)

    def test_the_player_index_covers_the_actives_in_steps_as_integers(self):
        res = self._res()
        assert res["player_index"] and set(res["player_index"]) <= set(self.keys)
        assert all(isinstance(v, int) for v in res["player_index"].values())
        stepped = {r["pk"] for r in dds.score(self.pairs, self.table, "value")[0]}
        assert set(res["player_index"]) == stepped & set(self.keys)

    def test_apply_writes_the_arm_family_over_org_summary_with_every_key_kept(self):
        res = self._res()
        org_summary = [{"org": c, "dvm_plus": {"7y": 100}, "delta_above_mean": {"7y": 0.0},
                        "hitter_dvm_plus": {}, "pitcher_dvm_plus": {}, "hitter_delta_above_mean": {},
                        "pitcher_delta_above_mean": {}, "_pos_bucket_fv_dvm_plus": {},
                        "tool_dev": {"per_tool_dvm_plus": {g: 100 for g in storage.TOOL_GROUPS},
                                     "per_tool_dvm_plus_by_bucket": {}, "tools_dvm_plus": 100}}
                       for c in CLUBS] + [{"org": "ZZZ", "dvm_plus": {"7y": 77}}]
        storage._apply_dvm_difficulty_fv(org_summary, res)
        storage._apply_dvm_difficulty_tools(org_summary, res)
        for entry in org_summary[:-1]:
            o = res["by_org"][entry["org"]]
            assert entry["dvm_plus"] == o["dvm_plus"] and entry["delta_above_mean"] == o["delta_above_mean"]
            assert entry["_pos_bucket_fv_dvm_plus"] == o["pos_bucket_fv_dvm_plus"]
            assert entry["dev_expectation"] == {"arm": "value", "windows": o["dev_expectation"]}
            assert set(entry["tool_dev"]["per_tool_dvm_plus"]) == set(storage.TOOL_GROUPS)
            assert entry["tool_dev"]["tools_dvm_plus"] == 100, "the composite is formed later, as today"
        assert org_summary[-1] == {"org": "ZZZ", "dvm_plus": {"7y": 77}}, "an unknown org is left alone"

    def test_spec_block_prints_verdict_words_only_where_the_read_resolved(self):
        spec = dds.spec_block(self.table, self.ev, "value", "7y")
        assert spec["fixture"] is True and spec["arm"] == "value"
        assert spec["credit_units"] == "expected WAR" and spec["principal_window"] == "7y"
        h2_resolved = [t for t in self.ev["h2"]["tests"]
                       if t["verdict"] == "list grades rise less often from higher rungs"]
        assert len(spec["h2_verdicts"]) == len(h2_resolved)
        h1_resolved = [c for fam, blk in self.ev["h1"]["families"].items() if fam.startswith("12m|")
                       for c in blk["cells"] if c["verdict"] not in (None, "not resolved", "unpowered")]
        assert len(spec["h1_verdicts"]) == len(h1_resolved)
        for side in ("hit", "pit"):
            assert {r["rung"] for r in spec["difficulty_table"][side]} <= {"<=35", "40", "45", "50", "55", "60+"}
        assert set(spec["ratio_60_70_over_40_50"]) == {"hit", "pit"}
        assert spec["decision"]["verdict"] == self.ev["decision"]["verdict"]
        ev2 = json.loads(json.dumps(self.ev))
        ev2["h2"]["tests"][0]["verdict"] = "list grades rise less often from higher rungs"
        ev2["h1"]["families"]["12m|total"]["cells"][0]["verdict"] = "easier for HS hitters"
        ev2["h1"]["families"]["24m|total"]["cells"][0]["verdict"] = "easier for HS hitters"
        spec2 = dds.spec_block(self.table, ev2, "difficulty", "7y")
        assert len(spec2["h2_verdicts"]) == len(h2_resolved) + 1
        assert len(spec2["h1_verdicts"]) == len(h1_resolved) + 1, "the 24-month family prints no verdict"
        assert spec2["h1_verdicts"][-1]["estimand"] == "total"
        assert spec2["credit_units"] == "grade-point spreads"


# ----------------------------------------------------- serve_pairs wiring


def test_serve_pairs_splits_each_step_by_the_val4_calendar_and_keeps_12_month_steps(monkeypatch):
    ty = date.today().year
    calls: dict = {}

    class ID:
        GROUPS = ("mlb", "milb")

    def pairs_from_frame(frame, *, debut, club_events, canon, active_in):
        calls["events"] = club_events
        calls["active"] = (active_in(1, ty - 2), active_in(2, ty - 2), active_in(2, ty))
        calls["canon"] = canon
        return ([{"pk": "a", "h": 1, "tau": {"LAD": 0.6, dds.UNAFFILIATED: 0.4}},
                 {"pk": "a", "h": 2, "tau": {"LAD": 1.0}},
                 {"pk": "b", "h": 1, "tau": {"ZZZ": 1.0}}], {"n": 3})

    stub = SimpleNamespace(
        ID=ID,
        load_debut_days=lambda d: {"a": "2030-01-01"},
        build_frame=lambda con, debut: {"starts": {("fg", "a", ty - 3): {"person": 1},
                                                   ("fg", "b", ty - 3): {"person": 2}}},
        load_person_seasons=lambda ids, last: {1: {"milb": {ty - 2: 1, ty - 1: 1}}, 2: {}},
        pairs_from_frame=pairs_from_frame)
    monkeypatch.setattr(dds, "_lab", lambda: stub)
    monkeypatch.setattr(dds, "_FIXTURE", None)
    cal = {"a": [_tenure("2022-01-01", "LAD")], "b": []}
    pairs, census = dds.serve_pairs(None, calendar_of=lambda pk: cal.get(pk, []), clubs=["LAD", "NYY"])
    assert census == {"n": 3}
    assert [(p["pk"], p["tau"]) for p in pairs] == [("a", {"LAD": 0.6}), ("b", {})]
    assert calls["events"] == {"a": [("2022-01-01", "LAD", "read")]}
    assert calls["active"] == (True, False, None)
    from trades import canonical_org
    assert calls["canon"] is canonical_org


def test_load_table_refuses_a_missing_table_and_reads_the_eval_beside_it(tmp_path, monkeypatch):
    monkeypatch.setattr(dds, "_FIXTURE", None)
    with pytest.raises(dds.ArmError):
        dds.load_table(tmp_path)
    (tmp_path / dds.TABLE_FILE).write_text('{"frame_receipt": {"today": "2027-02-01"}}', encoding="utf-8")
    table, ev = dds.load_table(tmp_path)
    assert table["frame_receipt"]["today"] == "2027-02-01" and ev == {}
    (tmp_path / dds.EVAL_FILE).write_text('{"decision": {"verdict": "SHIP"}}', encoding="utf-8")
    assert dds.load_table(tmp_path)[1] == {"decision": {"verdict": "SHIP"}}


# ------------------------------------------- the glossary copy prepared for the flip


def _flip_module():
    p = ROOT / "tools" / "dvm_difficulty_glossary_flip.py"
    spec = importlib.util.spec_from_file_location("dvm_difficulty_glossary_flip", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_prepared_glossary_copy_is_lint_clean_and_its_see_also_resolves():
    flip = _flip_module()
    assert flip.check() == []
    assert "dvm_expected_growth" in flip.NEW_ENTRIES
    ids = {e["id"] for e in json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))["entries"]}
    assert "dvm_expected_growth" not in ids, "the new entry lands only in the owner's flip commit (DVM-6)"
    assert set(flip.REWRITES) <= ids


def test_the_flip_script_is_idempotent_and_keeps_the_file_line_endings(tmp_path):
    flip = _flip_module()
    src = ROOT / "data" / "glossary.json"
    before = src.read_bytes()
    dst = tmp_path / "glossary.json"
    dst.write_bytes(before)
    n1 = flip.apply(dst, version="2027-01-01")
    n2 = flip.apply(dst, version="2027-01-01")
    assert n1 == len(flip.REWRITES) + len(flip.NEW_ENTRIES) and n2 == 0
    out = dst.read_bytes()
    assert out.count(b"\r\n") == out.count(b"\n") == (before.count(b"\r\n") and out.count(b"\n"))
    g = json.loads(out.decode("utf-8"))
    ids = {e["id"]: e for e in g["entries"]}
    assert g["version"] == "2027-01-01" and ids["dvm_expected_growth"]["term"] == "Expected growth"
    assert ids["fin_dollar_dvm"]["term"] == "Org DvM+ (player)"
    assert src.read_bytes() == before, "the repo glossary is untouched before the flip"
