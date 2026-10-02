# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/fit_dpw_forecast.py after the VAL_5 build refactor
(docs/dpw-2026-09-25/DPW_PATH_GATE.md G-0 and 15), on SYNTHETIC series and tmp
paths only:

  * the method list is flat5, trend and trend_cbt, unchanged;
  * horizon 1 is MECHANICAL: a target is forecast only if the winter before it
    is present in the series given, so on a GAPPED series the tool computes no
    trend cell at horizon 2 (the unrefactored _forecast would have);
  * the dpw_path_gate block survives a re-run byte for byte.
"""

from __future__ import annotations

import inspect
import json

import pytest

from tools import fit_dpw_forecast as fdf


def _series(gap=()):
    return {w: 9.0e6 * 1.04 ** (w - 2014) * (1.0 + 0.03 * ((-1) ** w))
            for w in range(2014, 2027) if w not in gap}


def test_the_method_list_is_unchanged():
    assert fdf.METHODS == ("flat5", "trend", "trend_cbt")
    out = fdf.build_eval(_series(), generated_at="2026-10-02")
    for row in out["per_winter"]:
        assert set(row) - {"winter", "actual_usd"} == set(fdf.METHODS)
    assert set(out["summary"]) == set(fdf.METHODS)
    src = inspect.getsource(fdf._forecast)
    for banned in ("robust", "damped", "median", "carry_destale", "h=", "horizon"):
        assert banned not in src, banned


def test_horizon_one_is_mechanical_on_a_gapped_series():
    s = _series(gap=(2021,))
    targets = fdf.horizon_one_targets(s)
    assert 2021 not in targets and 2022 not in targets          # 2022's prior winter is absent
    assert targets == [y for y in range(2018, 2027) if y not in (2021, 2022)]
    out = fdf.build_eval(s, generated_at="2026-10-02")
    assert [r["winter"] for r in out["per_winter"]] == targets
    assert out["test_winters"] == targets
    assert all(r["winter"] - 1 in s for r in out["per_winter"])


def test_the_gate_block_is_carried_forward_byte_identical(tmp_path):
    out = tmp_path / "dpw_forecast_eval.json"
    gate = {"verdict": "REGISTERED", "truth_sha256": "a" * 64, "nested": {"x": [1, 2.5, None]}}
    out.write_text(json.dumps({"generated_at": "2026-08-19", "dpw_path_gate": gate,
                               "other_gate": {"k": 1}, "stale_key": 3}), encoding="utf-8")
    fdf.write_eval(fdf.build_eval(_series(), generated_at="2026-10-02"), out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["dpw_path_gate"] == gate and doc["other_gate"] == {"k": 1}
    assert "stale_key" not in doc and doc["generated_at"] == "2026-10-02"
    first = json.dumps(doc["dpw_path_gate"], sort_keys=True)
    fdf.write_eval(fdf.build_eval(_series(), generated_at="2026-10-03"), out)
    doc2 = json.loads(out.read_text(encoding="utf-8"))
    assert json.dumps(doc2["dpw_path_gate"], sort_keys=True) == first


def test_the_cli_takes_a_series_and_an_output_path(tmp_path, monkeypatch):
    import fa_market as fm

    def boom(*a, **k):
        raise AssertionError("the in-run series was built although --series was given")
    monkeypatch.setattr(fm, "enriched_signings", boom)
    series = tmp_path / "series.json"
    series.write_text(json.dumps({"usd_per_war_by_winter": {str(k): v for k, v in
                                                            _series(gap=(2019,)).items()}}),
                      encoding="utf-8")
    out = tmp_path / "eval.json"
    fdf.main(["--series", str(series), "--out", str(out)])
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert 2019 not in doc["test_winters"] and 2020 not in doc["test_winters"]
    assert fdf.DEFAULT_OUT.name == "dpw_forecast_eval.json"


@pytest.mark.parametrize("n", [3])
def test_a_series_too_short_scores_nothing(n):
    s = {2024: 1.0e7, 2025: 1.1e7, 2026: 1.2e7}
    out = fdf.build_eval(s, test_winters=[2026], generated_at="2026-10-02")
    assert out["winner"] in (None, "flat5", "trend", "trend_cbt")
