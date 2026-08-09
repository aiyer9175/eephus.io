# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Guards on the one-time MLB Trade Rumors arbitration ingest.

Two classes of guard here, and the second is the one that matters:
  * the parser reads the real vocabulary correctly (settled vs projected vs
    extension vs club option vs unresolved), and
  * the ingest can NEVER run from the pipeline and NEVER touches the network in
    check mode.

The second exists because this IP was firewalled by MLBTR at the TCP level after
roughly 14 rapid requests during planning. A scraper that creeps into a nightly
job would rediscover that at 3am, and a silent re-fetch could change the corpus a
scored model was fitted on without anything recording that it moved.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location(
    "ingest_arbitration_ledger", ROOT / "tools" / "ingest_arbitration_ledger.py")
ingest = importlib.util.module_from_spec(_SPEC)
sys.modules["ingest_arbitration_ledger"] = ingest
_SPEC.loader.exec_module(ingest)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

def _li(name: str, bref: str, svc: str, tail: str) -> str:
    return (f'<li><a href="https://www.baseball-reference.com/players/'
            f'{bref[0]}/{bref}.shtml">{name}</a> ({svc}): {tail}</li>')


FIXTURE = "<ul>" + "".join([
    _li("Brock Burke", "burkebr01", "5.045", "Team announced $2.325MM agreement"),
    _li("Hayden Wesneski", "wesneha01", "3.021", "$975K agreement today"),
    _li("Reid Detmers", "detmere01", "3.159",
        "No agreement reached, likely heading to hearing"),
    _li("Maikel Garcia", "garcima05", "2.168",
        "Five-year, $57.5MM extension signed in December"),
    _li("Alex Vesia", "vesiaal01", "5.078",
        "Dodgers exercised $3.55MM club option in November"),
    _li("Taylor Trammell", "trammta01", "2.144",
        "Agreed to split deal in November, $900K in majors and $500K in minors"),
]) + "</ul>"


def _rows(kind="tracker"):
    return ingest.parse_post(FIXTURE, class_year=2026, kind=kind,
                             source_url="test")


def test_every_entry_with_a_service_token_is_parsed():
    assert len(_rows()) == 6


def test_service_time_is_years_and_days_not_a_float():
    r = {x["bbref_id"]: x for x in _rows()}["burkebr01"]
    assert r["service_years"] == 5 and r["service_days"] == 45
    assert r["service_time"] == "5.045"


def test_millions_and_thousands_both_parse():
    by = {x["bbref_id"]: x for x in _rows()}
    assert by["burkebr01"]["settled_usd"] == 2_325_000
    # 20 of the 2026 tracker's 191 entries are in K. A MM-only regex silently
    # drops them, and they are the arb-1 minimum-salary population the panel is
    # thinnest on.
    assert by["wesneha01"]["settled_usd"] == 975_000


def test_an_extension_is_never_a_settled_award():
    # The tracker lists arbitration-ELIGIBLE players and some of them sign an
    # extension instead of settling. Letting one through would put an $11.5MM
    # average annual value into the label set as an arb-1 award.
    r = {x["bbref_id"]: x for x in _rows()}["garcima05"]
    assert r["outcome"] == "extension"
    assert r["settled_usd"] is None


def test_a_club_option_is_not_an_arbitration_award():
    r = {x["bbref_id"]: x for x in _rows()}["vesiaal01"]
    assert r["outcome"] == "club_option"
    assert r["settled_usd"] is None


def test_an_unresolved_exchange_carries_no_settled_figure():
    r = {x["bbref_id"]: x for x in _rows()}["detmere01"]
    assert r["outcome"] == "exchanged"
    assert r["settled_usd"] is None


def test_a_split_deal_takes_the_major_league_half():
    # FIRST money figure, not max: the minors half follows it in the same line.
    r = {x["bbref_id"]: x for x in _rows()}["trammta01"]
    assert r["outcome"] == "split_deal"
    assert r["settled_usd"] == 900_000
    assert r["split_contract"] is True


def test_projection_posts_never_produce_a_settled_figure():
    # A projection is the Swartz COMPARATOR. Scoring the model against its own
    # comparator's input would be circular, so the two kinds stay separate.
    rows = _rows(kind="projection")
    assert all("settled_usd" not in r for r in rows)
    assert any(r.get("projected_usd") for r in rows)


def test_no_outcome_is_unknown_on_the_real_vocabulary():
    assert [r for r in _rows() if r["outcome"] == "unknown"] == []


def test_url_classification_covers_both_slug_shapes():
    cy, kind = ingest._classify_url(
        "https://www.mlbtraderumors.com/2026/01/2026-arbitration-tracker.html")
    assert (cy, kind) == (2026, "tracker")
    cy, kind = ingest._classify_url(
        "https://www.mlbtraderumors.com/2025/10/projected-arbitration-salaries-for-2026.html")
    assert (cy, kind) == (2026, "projection")
    # 2023 used a different slug order from every other year.
    cy, kind = ingest._classify_url(
        "https://www.mlbtraderumors.com/2022/10/mlb-projected-arbitration-salaries-2023.html")
    assert (cy, kind) == (2023, "projection")


def test_trackers_are_fetched_before_projections():
    # The request budget is the scarce resource. An alphabetical queue spends it
    # on 2011 single-team posts before reaching a settled-figure tracker.
    urls = [
        "https://www.mlbtraderumors.com/2021/10/projected-arbitration-salaries-for-2022.html",
        "https://www.mlbtraderumors.com/2024/01/2024-arbitration-tracker.html",
    ]
    assert sorted(urls, key=ingest._fetch_priority)[0].endswith(
        "2024-arbitration-tracker.html")


# --------------------------------------------------------------------------- #
# Containment
# --------------------------------------------------------------------------- #

def test_check_mode_cannot_reach_the_network():
    ingest._OFFLINE = True
    try:
        with pytest.raises(RuntimeError, match="offline"):
            ingest.fetch_one("https://www.mlbtraderumors.com/does-not-matter.html",
                             force=True)
    finally:
        ingest._OFFLINE = False


def test_a_404_is_a_dead_url_and_a_timeout_is_a_block():
    # Distinct exceptions, because the correct responses are opposite: a 404
    # means stop asking for that URL, a timeout means stop asking this host
    # anything at all.
    assert issubclass(ingest.DeadURL, Exception)
    assert issubclass(ingest.Blocked, Exception)
    assert not issubclass(ingest.DeadURL, ingest.Blocked)


def test_the_pipeline_never_imports_the_ingest():
    """run_monthly must not be able to reach this module, directly or through
    any repo module it imports."""
    seen: set[str] = set()
    banned = "ingest_arbitration_ledger"
    stack = ["run_monthly"]
    imp_re = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.M)
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        p = ROOT / f"{mod.replace('.', '/')}.py"
        if not p.exists():
            continue
        src = p.read_text("utf-8", errors="ignore")
        assert banned not in src, f"{mod} reaches the one-time ingest"
        for m in imp_re.finditer(src):
            name = m.group(1).split(".")[0]
            if (ROOT / f"{name}.py").exists():
                stack.append(name)


def test_the_ingest_is_not_a_scheduled_export():
    import run_monthly
    assert not any("arb_ledger" in s or "ingest_arbitration" in s
                   for s in run_monthly.SCHEDULED_EXPORTS)
