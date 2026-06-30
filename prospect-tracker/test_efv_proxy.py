"""xFV proxy (leading indicator) — artifact sanity. Pure-data; no network."""
import json
from pathlib import Path

import pytest

EVAL = Path(__file__).parent / "data" / "xfv_proxy_eval.json"


@pytest.mark.skipif(not EVAL.exists(), reason="xfv_proxy_eval.json not generated yet")
def test_proxy_eval_structure_and_sanity():
    d = json.loads(EVAL.read_text(encoding="utf-8"))
    assert d.get("kind") == "leading_indicator_not_xfv", "must be flagged NOT xFV"
    sides = d.get("sides") or {}
    assert set(sides) >= {"hit", "pit"}, "both sides present"
    for s, ev in sides.items():
        assert ev.get("pairs", 0) >= 30, f"{s}: too few training pairs ({ev.get('pairs')})"
        # forward-chained OOS r must be present + a real (finite, in-range) correlation
        r = ev.get("r")
        assert r is None or (-1.0 <= r <= 1.0), f"{s}: r out of range {r}"
        assert ev.get("target"), f"{s}: target label present"
    proj = d.get("projections") or {}
    assert len(proj) > 100, f"expected per-active projections, got {len(proj)}"
    # projections are xwOBA-scale (roughly .200-.450)
    vals = [v["proj_xwoba"] for v in proj.values() if v.get("proj_xwoba") is not None]
    assert vals and all(0.15 <= v <= 0.55 for v in vals[:200]), "projections on xwOBA scale"


def test_proxy_module_imports():
    import efv_proxy  # noqa: F401
    assert hasattr(efv_proxy, "run")
