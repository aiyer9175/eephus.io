"""FV Tape (Tier 1) math guard. Extracts computeFvTape from prospx/index.html
and exercises it in an isolated JS engine: candles derive from the consensus
path (first open == close, source spread widens the wicks), momentum is the
3-interval net change, and RSI drops flat re-confirmations so a static grade
never pins the gauge. Skips cleanly if py_mini_racer is unavailable.
"""
import re
import json
import warnings

import pytest

warnings.filterwarnings("ignore")
mr = pytest.importorskip("py_mini_racer")


def _ctx():
    src = open("prospx/index.html", encoding="utf-8").read()
    m = re.search(r"function computeFvTape\(points\) \{.*?\n\}\n", src, re.S)
    assert m, "computeFvTape not found in prospx/index.html"
    c = mr.MiniRacer()
    c.eval(m.group(0))
    return c


def _run(ctx, pts):
    out = ctx.eval("JSON.stringify(computeFvTape(%s))" % json.dumps(pts))
    return json.loads(out) if out else None


def _pts(vals, spread=3, sd=2.5):
    return [{"snapshot_date": f"2025-{i + 1:02d}-01", "consensus_fv_raw": v,
             "fv_min": v - spread, "fv_max": v + spread, "fv_stddev": sd}
            for i, v in enumerate(vals)]


def test_needs_four_points():
    ctx = _ctx()
    assert _run(ctx, _pts([45, 46, 47])) is None
    assert _run(ctx, _pts([45, 46, 47, 48])) is not None


def test_candles_and_momentum():
    ctx = _ctx()
    out = _run(ctx, _pts([45, 45, 47, 50, 50, 52, 55, 53, 50, 48]))
    assert len(out["candles"]) == 10
    c0, cL = out["candles"][0], out["candles"][-1]
    assert c0["o"] == c0["c"] == 45              # first open seeds to close
    assert cL["up"] is False                     # 50 -> 48 is a down candle
    assert cL["h"] >= max(cL["o"], cL["c"])      # source spread widens the wick
    assert cL["l"] <= min(cL["o"], cL["c"])
    assert out["momentum"] == round(48 - 55, 2)  # last minus close 3 intervals back
    assert out["vol"] == 2.5


def test_rsi_drops_flat_confirmations():
    ctx = _ctx()
    # Seven identical grades = zero real changes; RSI must be null, not pinned.
    out = _run(ctx, _pts([50, 50, 50, 50, 50, 50, 50]))
    assert out is not None and out["rsi"] is None
    assert out["momentum"] == 0
    # A genuinely trending series clears the >=6-change gate.
    out2 = _run(ctx, _pts([40, 42, 44, 46, 48, 50, 52, 54]))
    assert out2["rsi"] is not None and 0 <= out2["rsi"] <= 100
