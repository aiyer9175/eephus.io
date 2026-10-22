"""tools/rbridge.py: R found or cleanly absent, JSON in and JSON out, failures raised.

Every test that needs R skips when Rscript is not installed (the live box and the port never
need R; docs/r/R_BAKEOFF.md section 0)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import rbridge  # noqa: E402

needs_r = pytest.mark.skipif(not rbridge.available(), reason="R is not installed")


def test_find_rscript_is_a_path_or_none():
    got = rbridge.find_rscript()
    assert got is None or Path(got).exists()


def test_absent_r_raises_cleanly(monkeypatch):
    monkeypatch.setattr(rbridge, "find_rscript", lambda: None)
    assert rbridge.available() is False
    with pytest.raises(rbridge.RError):
        rbridge.run_r("echo.R", {"x": [1]})


@needs_r
def test_json_round_trip():
    out = rbridge.run_r("echo.R", {"x": [1.0, 2.0, 3.5]})
    assert out["n"] == 3
    assert out["sum"] == pytest.approx(6.5)
    assert out["mean"] == pytest.approx(6.5 / 3, abs=1e-12)
    assert out["r"].startswith("4.")


@needs_r
def test_missing_script_raises():
    with pytest.raises(rbridge.RError):
        rbridge.run_r("no_such_script.R", {"x": [1]})


@needs_r
def test_script_error_raises(tmp_path):
    bad = tmp_path / "bad.R"
    bad.write_text("stop('planted failure')\n", encoding="utf-8")
    with pytest.raises(rbridge.RError, match="planted failure"):
        rbridge.run_r(bad, {"x": [1]})


@needs_r
def test_pinned_versions_match_the_env_doc():
    """docs/r/R_ENV.md and docs/r/renv.lock pin what is installed."""
    v = rbridge.versions()
    lock = json.loads((ROOT / "docs" / "r" / "renv.lock").read_text(encoding="utf-8"))
    env = (ROOT / "docs" / "r" / "R_ENV.md").read_text(encoding="utf-8")
    assert lock["R"]["Version"] == v["R"]
    for p in rbridge.PACKAGES:
        locked = lock["Packages"][p]["Version"]
        assert locked.replace("-", ".") == v["packages"][p], p
        assert f"| {p} | {locked} |" in env, p
        assert lock["Packages"][p].get("Repository") == "CRAN", p


def test_no_served_path_imports_rbridge():
    """R is offline only: no exporter, page builder or pipeline script reads rbridge."""
    offenders = []
    for py in ROOT.glob("*.py"):
        if py.name.startswith("test_"):
            continue
        if "rbridge" in py.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(py.name)
    for name in ("run_monthly.py", "build_site.py"):
        p = ROOT / name
        if p.exists():
            assert "rbridge" not in p.read_text(encoding="utf-8", errors="ignore")
    assert offenders == []
