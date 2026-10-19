# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The SG_6 one-look crash protocol's dry run (tools/hitter_lean_c6_probe.py): every
printing and file-writing function of the probe runs on fixtures that carry None and NaN
in every printed cell. No frame row, list row, outcome or label is read here."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from tools import hitter_lean_c6_probe as P

NAN = float("nan")
BAD = (None, NAN, float("inf"))


@pytest.mark.parametrize("v", BAD)
def test_fmt_prints_na_for_missing_cells(v):
    assert P.fmt(v) == "NA"
    assert P.fmt([v, v]) == "[NA, NA]"


def test_fmt_numbers_and_flags():
    assert P.fmt(-0.08561) == "-0.0856"
    assert P.fmt(12) == "12"
    assert P.fmt(True) == "yes"
    assert P.fmt("x") == "x"


@pytest.mark.parametrize("v", BAD)
def test_verdict_is_undefined_on_missing(v):
    assert P.verdict(v, -0.1) == "UNDEFINED"
    assert P.verdict(-0.1, v) == "UNDEFINED"


def test_verdict_reads_the_declared_rule():
    assert P.verdict(-0.08, -0.01) == "REPLICATED"
    assert P.verdict(-0.08, 0.02) == "SAME SIGN, NOT RESOLVED"
    assert P.verdict(0.0, 0.05) == "NOT REPLICATED"


def _fit_fixture(v):
    return {"n": v, "n_players": v, "coef": v, "ols_t": v, "ci95": [v, v]}


@pytest.mark.parametrize("v", BAD)
def test_every_line_builder_prints_na(v):
    lines = (P.count_lines({"a": v, "b": v})
             + P.fit_lines("primary_LEAN_given_TALL", _fit_fixture(v))
             + P.fit_lines("empty", None)
             + P.fit_lines("no_ci", {"ci95": None})
             + P.strata_lines({d: {"cell": {"n": v, "rho": v}, "none": None}
                               for d in P.STRATA})
             + P.strata_lines(None))
    assert lines
    for ln in lines:
        assert "nan" not in ln.lower() and "inf" not in ln.lower(), ln
    assert all("NA" in ln for ln in lines if not ln.startswith("  ") or ": " in ln)


@pytest.mark.parametrize("v", BAD)
def test_emit_log_and_write_on_missing_cells(tmp_path: Path, v):
    seen = []
    P.emit(P.fit_lines("x", _fit_fixture(v)), out=seen.append)
    P.emit("one line", out=seen.append)
    assert len(seen) == 2
    probes = tmp_path / "PROBES.jsonl"
    P.log_probe(probes, kind="probe", n=v, result=v, ci95=[v, v],
                strata={"age_band": {"x": {"n": v, "rho": v}}})
    P.log_probe(probes, kind="read_spent_crash", traceback="Traceback: fixture")
    recs = [json.loads(ln) for ln in probes.read_text(encoding="utf-8").splitlines()]
    assert len(recs) == 2 and recs[0]["result"] is None and recs[0]["ci95"] == [None, None]
    out = tmp_path / "sg6_result.json"
    P.write_result(out, {"fits": {k: _fit_fixture(v) for k in P.MODELS},
                         "strata": {d: {"c": {"n": v, "rho": v}} for d in P.STRATA},
                         "counts": {"a": v}, "primary_reading": P.verdict(v, v)})
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["primary_reading"] == "UNDEFINED"
    assert doc["fits"]["primary_LEAN_given_TALL"]["coef"] is None


def test_clean_handles_numpy_scalars():
    import numpy as np
    doc = P.clean({"a": np.float64("nan"), "b": np.int64(3), "c": (np.float32(1.5),)})
    assert doc == {"a": None, "b": 3, "c": [1.5]}
    assert not math.isnan(doc["c"][0])


@pytest.mark.parametrize("label", ["2020report", "2021report"])
def test_reserved_lists_are_refused_before_any_read(label):
    with pytest.raises(RuntimeError, match="reserved"):
        P.fg_list(label)


def test_first_line_says_descriptive():
    assert P.FIRST_LINE.startswith("SG_6 C6 hitter-lean probe: DESCRIPTIVE, not a driver, "
                                   "not a ledger row")


def test_no_fv_cell_stratum_in_the_source():
    src = Path(P.__file__).read_text(encoding="utf-8").lower()
    assert not re.search(r"\bfv ?(35|40|45|50|55|60|65)\+? (cell|band|bucket|tier)", src)
    assert "cons" not in P.STRATA and all("fv" not in s for s in P.STRATA)
    assert "—" not in src and "–" not in src


def _synthetic_rows(n=80):
    """Synthetic rows (no frame row, no list row): every field the fits read."""
    import numpy as np
    rng = np.random.default_rng(1)
    lv = [None, "DSL", "CPX", "A", "A+", "AA", "AAA"]
    rows = []
    for i in range(n):
        rows.append({"pid": i % (n - 5), "O1": float(rng.normal()),
                     "raw": 50.0 + i % 3, "game": 45.0 + i % 4, "hit": 40.0 + i % 5,
                     "p_raw": 30.0 + i % 2, "p_game": 20.0 + i % 3, "age": 19.0 + i % 5,
                     "cons": 40.0 + i % 4, "base": None if i % 7 == 0 else float(rng.normal()),
                     "lvl": lv[i % 7], "TALL": float(rng.normal()), "LEAN": float(rng.normal()),
                     "PROJ": float(rng.normal()), "side": "hit", "age_band": P.age_band(19.0 + i % 5),
                     "last_level": P.level_band(lv[i % 7]), "route": "hs_draft",
                     "bonus_band": "unknown" if i % 2 else "under_250k"})
    return rows


def test_fits_and_strata_run_on_synthetic_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(P, "B", 50)
    rows = _synthetic_rows()
    fits = {name: P.fit(rows, feats, tgt) for name, (feats, tgt) in P.MODELS.items()}
    for res in fits.values():
        assert res["coef"] is not None and len(res["ci95"]) == 2
    st = P.strata(rows)
    assert set(st) == set(P.STRATA)
    rows[0]["LEAN"] = rows[1]["LEAN"]
    small = P.fit(rows[:10], ("LEAN",), "LEAN")
    assert small["coef"] is None
    assert P.strata(rows[:10]) == {d: {} for d in P.STRATA}
    P.write_result(tmp_path / "r.json", {"fits": fits, "strata": st, "small": small})
    P.emit(P.strata_lines(st) + P.fit_lines("small", small), out=lambda s: None)


def test_constant_lean_cell_prints_na(monkeypatch):
    rows = _synthetic_rows()
    for r in rows:
        if r["bonus_band"] == "unknown":
            r["LEAN"] = 0.5
    st = P.strata(rows)
    cell = st["bonus_band"]["unknown"]
    assert cell["n"] >= P.STRATUM_MIN_N
    line = [ln for ln in P.strata_lines(st) if "bonus_band=unknown" in ln][0]
    assert "nan" not in line.lower()


class _FakeStore:
    NO_MILB_SEASONS = frozenset({2020})

    def __init__(self, lines, norms):
        self.lines, self.norms = lines, norms

    def _season_index(self, season, group):
        return self.lines.get(season, {})

    def _line_level(self, ln, season, convention):
        return ln.get("level")

    def _pure_norms(self, season, level, group):
        return self.norms.get((season, level))

    def _mlb_event_ids(self, season, group):
        return frozenset({7}) if season == 2026 else frozenset()


def test_iso_rel_and_levels_on_missing_cells():
    lines = {2025: {7: [{"level": "AA", "row": {"pa": 100, "slg": 0.45, "avg": 0.25}},
                        {"level": "AA", "row": {"pa": None, "slg": 0.4, "avg": 0.2}},
                        {"level": "A", "row": {"pa": 80, "slg": "nan", "avg": 0.2}},
                        {"level": "MLB", "row": {"pa": 300, "slg": 0.5, "avg": 0.3}}]},
             2026: {7: [{"level": "AAA", "row": {"pa": 60, "slg": 0.40, "avg": 0.25}}]}}
    S = _FakeStore(lines, {(2025, "AA"): {"iso": 0.15}, (2026, "AAA"): {"iso": None}})
    v, pa = P.iso_rel(S, 7, (2025, 2026), 150)
    assert v is None and pa == 100
    v, pa = P.iso_rel(S, 7, (2025, 2026), 50)
    assert pa == 100 and abs(v - 0.05) < 1e-9
    assert P.top_level(S, 7, 2026) == "AAA" and P.top_level(S, 8, 2026) is None
    assert P.first_mlb_season(S, 7) == 2026 and P.first_mlb_season(S, 8) is None
    assert P.age_band(None) == "unknown" and P.level_band(None) == "none"
    assert P.bonus_band(None) == "unknown" and P.bonus_band({"year": 2025}) == "unknown"
    assert P.route_of(None, None) == "other_or_unknown"
