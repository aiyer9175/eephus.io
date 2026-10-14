# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA destination build leaves Gate 2, Gate 3 and the served FA files alone.

docs/fa-2026-10/FA_DESTINATION_GATE.md section 3: data/fa_class.json,
fa_meta.json, fa_gate2_eval.json, fa_dpw_series.json and fa_gate3_eval.json
stay byte-identical; the lab reads Gate 2 only through GATE2_COLLECT with
persist=False, persist_dpw=False, never calls run_fit_gate or fa_export, and
never triggers the auto re-export a saved gate runs (owner answer M14-1).
Section 4.2: build_rows() with no price override returns the Gate 3 rows
unchanged, pinned here by a row hash.

The real-data tests below read only what section 15 lets the build task read:
build_rows() with no override, the registered Gate 3 arms on that realized
frame, and Gate 2's collection. No destination arm (P, N, L_perm,
payroll_level, incumbency_only) is computed on the real chain.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import fa_backtest as fbt  # noqa: E402
import fa_fit_backtest as fb  # noqa: E402
import fa_destination_lab as lab  # noqa: E402

DATA = ROOT / "data"
FROZEN = ("fa_class.json", "fa_meta.json", "fa_gate2_eval.json", "fa_dpw_series.json",
          "fa_gate3_eval.json")

#: sha256 of json.dumps(build_rows(), sort_keys=True, separators=(",", ":")) on
#: the 2026-10-09 frame: 35,190 rows, 1,173 signings, winters 2018-2026. A
#: change means the Gate 3 frame itself moved (code or data); the look's step 0
#: discloses any drift beside the registered values.
GATE3_ROWS_SHA256 = "e583b8611e91af9405fa63f6ccbd96da5196cb65ee64a370a9bfe85eed658a0f"

#: Today's values of the three registered arms that read the park or prior-wins
#: terms. They drift from the 2026-08-19 artifact because commit 218560e0
#: (2026-09-06) repaired two Arizona lookups inside build_rows (StatsAPI prior
#: wins by team id, Savant park by the override map) after the artifact was
#: written; test_the_drift_is_exactly_the_arizona_repairs reverts both and
#: reproduces every registered number bit-exact.
DRIFT_TODAY = {
    "live_analog": {"n": 1173, "top1": 0.052, "top3": 0.1449, "top5": 0.2327, "mrr": 0.1672},
    "fitted_full": {"n": 1080, "top1": 0.1787, "top3": 0.2435, "top5": 0.3083, "mrr": 0.269},
    "banded_twin": {"n": 1173, "top1": 0.0546, "top3": 0.1364, "top5": 0.2097, "mrr": 0.163},
}


def _stamps() -> dict:
    return {n: hashlib.sha256((DATA / n).read_bytes()).hexdigest()
            for n in FROZEN if (DATA / n).exists()}


def _boom(*_a, **_k):
    raise AssertionError("the FA destination lab must not reach this call")


@pytest.fixture
def forbidden(monkeypatch, tmp_path):
    """fa_export, the M14-1 re-export and run_fit_gate all raise; Gate 3's
    output path points into tmp so any write through it would show."""
    import fa_export
    monkeypatch.setattr(fa_export, "export_all", _boom)
    monkeypatch.setattr(fbt, "reexport_fa_sidecars", _boom)
    monkeypatch.setattr(fb, "run_fit_gate", _boom)
    sentinel = tmp_path / "gate3_sentinel.json"
    monkeypatch.setattr(fb, "OUT_PATH", sentinel)
    return sentinel


def _real_rows():
    import scrapers
    import storage
    if not storage.load_fa_signings(2024):
        pytest.skip("no stored FA signings in this checkout")
    with scrapers.cache_only():
        rows = fb.build_rows()
    if not rows:
        pytest.skip("the Gate 3 inputs are not cached in this checkout")
    return rows


def _rows_hash(rows) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# no write, no export, no re-export
# --------------------------------------------------------------------------

def test_the_lab_leaves_the_frozen_fa_files_byte_identical(forbidden, tmp_path):
    before = _stamps()
    assert set(before) == set(FROZEN)
    # The look wrote data/fa_destination_eval.json once (2026-10-14); a fixture
    # run must leave it as the look wrote it.
    art = DATA / "fa_destination_eval.json"
    art_before = art.read_bytes() if art.exists() else None
    doc = lab.run(lab.fixture_inputs(), tmp_path / "eval.json", "2026-10-09")
    assert doc["order"][-1] == "industry"
    assert _stamps() == before
    assert not forbidden.exists()
    assert (art.read_bytes() if art.exists() else None) == art_before


def test_the_collection_hook_is_read_without_persisting(monkeypatch):
    calls = []

    def fake_gate(**kw):
        calls.append(kw)
        fbt.GATE2_COLLECT.append((2019, "k", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))
        return {}

    monkeypatch.setattr(fbt, "run_market_gate", fake_gate)
    assert lab.collect_gate2() == [(2019, "k", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)]
    assert calls == [{"persist": False, "persist_dpw": False}]
    assert fbt.GATE2_COLLECT is None

    def failing(**kw):
        raise RuntimeError("x")

    monkeypatch.setattr(fbt, "run_market_gate", failing)
    with pytest.raises(RuntimeError):
        lab.collect_gate2()
    assert fbt.GATE2_COLLECT is None


def test_the_real_gate2_collection_writes_nothing(forbidden):
    """The look's own collection call on the real chain: tuples come back,
    the hook is reset, no re-export runs and the five files do not move."""
    import scrapers
    import storage
    if not storage.load_fa_signings(2024):
        pytest.skip("no stored FA signings in this checkout")
    before = _stamps()
    with scrapers.cache_only():
        tuples = lab.collect_gate2()
    assert tuples and all(len(t) == 8 for t in tuples)
    assert fbt.GATE2_COLLECT is None
    assert _stamps() == before
    assert not forbidden.exists()


# --------------------------------------------------------------------------
# the Gate 3 rows and the five registered arms
# --------------------------------------------------------------------------

def test_build_rows_without_the_override_reproduces_the_gate3_rows():
    rows = _real_rows()
    assert _rows_hash(rows) == GATE3_ROWS_SHA256
    assert len(rows) == 35190 and len({(r["winter"], r["signing"]) for r in rows}) == 1173
    import scrapers
    with scrapers.cache_only():
        assert fb.build_rows(price_override=None) == rows


def test_the_registered_arms_reproduce_or_drift_as_disclosed():
    rows = _real_rows()
    s0 = lab.step0(types.SimpleNamespace(realized_rows=rows,
                                         registered_step0=lab.registered_step0()))
    for arm in ("random", "payroll_only", "behavior_only"):
        assert s0["arms"][arm]["bit_exact"], arm
    assert sorted(s0["drift"]) == sorted(DRIFT_TODAY)
    for arm, today in DRIFT_TODAY.items():
        assert s0["arms"][arm]["today"] == today, arm
    assert s0["rows_sha256"] == GATE3_ROWS_SHA256


def test_the_drift_is_exactly_the_arizona_repairs(monkeypatch):
    """With the two 218560e0 Arizona repairs reverted, all five registered
    arms and the banded twin reproduce data/fa_gate3_eval.json bit-exact."""
    _real_rows()
    import fa_fit
    from trades import canonical_org
    import scrapers
    monkeypatch.setattr(fa_fit, "_SAVANT_CLUB_OVERRIDES", {})
    monkeypatch.setattr(fb, "canonical_org_from_id", lambda _id, name: canonical_org(name))
    with scrapers.cache_only():
        rows = fb.build_rows()
    s0 = lab.step0(types.SimpleNamespace(realized_rows=rows,
                                         registered_step0=lab.registered_step0()))
    assert s0["drift"] == [], {a: s0["arms"][a] for a in s0["drift"]}
    reg = json.loads((DATA / "fa_gate3_eval.json").read_text(encoding="utf-8"))["results"]
    assert s0["arms"]["live_analog"]["today"]["mrr"] == reg["live_analog"]["mrr"] == 0.1669
    assert s0["arms"]["fitted_full"]["today"]["mrr"] == reg["fitted_full"]["mrr"] == 0.2679
