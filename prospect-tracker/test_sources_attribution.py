# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/sources/ names every upstream the ingest code calls (census X07-08).

The upstream list on /sources/ omitted MLB Trade Rumors (the arbitration
comparator and results tracker), The Odds API (the prices on /betting/) and
Open-Meteo (the nightly weather capture, whose data licence required
attribution). Since 2026-10-08 the capture reads the National Weather Service
(owner answer FP5-2), whose row replaced Open-Meteo's. Each external host written in an ingest module must map, by
registered domain, to a row on the page. A host the code names but never calls
is listed in _NOT_CALLED with the reason.
"""
from __future__ import annotations

import re
from pathlib import Path

import build_site

ROOT = Path(__file__).parent

_HOST_RE = re.compile(r"https?://([A-Za-z0-9.-]+)")

# host -> why no /sources/ row is owed
_NOT_CALLED = {
    "open-meteo.com": ("betting_weather.SOURCES['open-meteo'] and PREVIOUS_RUNS are "
                       "retired: FORECAST_SOURCE names NWS since 2026-10-08 and the "
                       "backfill is off, so no request reaches it (guarded below)"),
}

# Our own domain is not an upstream (staff_ingest.py's links, the scores job's
# User-Agent page).
_OWN = {"eephus.io"}

# registered domain -> the registered domain of the /sources/ row that credits it
# (SCORES_5a_LIVE_FLIP): MLB's poster images load from MLB's static media host,
# and under owner answer SC-VIDEO (a) a clip plays in MLB's own embed player,
# framed from streamable.com/m/<slug>; the MLB Stats API row credits both.
_ALIASES = {"mlbstatic.com": "mlb.com", "streamable.com": "mlb.com"}

# A host written as a bare string literal ("img.mlbstatic.com") in the scores
# files, where the allowlists name hosts without a scheme.
_BARE_HOST_RE = re.compile(r'"((?:[a-z0-9-]+[.])+(?:com|net|org|io|tv))"')


def _registered(host: str) -> str:
    reg = ".".join(host.lower().split(".")[-2:])
    return _ALIASES.get(reg, reg)


def _scores_files() -> list[Path]:
    files = list(ROOT.glob("scores_*.py")) + [ROOT / "tools" / "scores_job.py"]
    return sorted(p for p in files if p.exists() and not p.name.startswith("test_"))


def _ingest_files() -> list[Path]:
    files = list(ROOT.glob("*_ingest.py")) + list(ROOT.glob("betting_*.py"))
    files += list((ROOT / "tools").glob("ingest_*.py"))
    files += _scores_files()
    return sorted(p for p in files if not p.name.startswith("test_"))


def _hosts(p: Path) -> list[str]:
    # a regex literal escapes each dot with a backslash; read it as a host
    text = p.read_text(encoding="utf-8").replace(chr(92) + ".", ".")
    hosts = _HOST_RE.findall(text)
    if p in _scores_files():
        hosts += _BARE_HOST_RE.findall(text)
    return hosts


def _sources_domains() -> set[str]:
    html = build_site.build_sources()
    return {_registered(h) for h in re.findall(r'<h3><a href="https?://([^/"]+)', html)}


def test_every_ingest_host_has_a_sources_row():
    rows = _sources_domains()
    missing = {}
    for p in _ingest_files():
        for host in _hosts(p):
            reg = _registered(host)
            if reg in rows or reg in _NOT_CALLED or reg in _OWN:
                continue
            missing.setdefault(reg, p.name)
    assert not missing, (
        "external hosts the ingest code names with no /sources/ row: "
        + ", ".join(f"{h} ({f})" for h, f in sorted(missing.items()))
    )


def test_the_not_called_allowance_still_holds():
    import betting_weather
    assert betting_weather.FORECAST_SOURCE != "open-meteo", (
        "the forecast capture calls Open-Meteo again: give it a /sources/ row with "
        "its CC BY 4.0 attribution and drop it from _NOT_CALLED")
    assert betting_weather.backfill_arming_state()["armed"] is False, (
        "the Previous Runs backfill calls Open-Meteo again: give it a /sources/ row "
        "and drop it from _NOT_CALLED")


def test_the_three_missing_upstreams_are_named():
    rows = _sources_domains()
    for reg in ("mlbtraderumors.com", "the-odds-api.com", "weather.gov"):
        assert reg in rows, f"/sources/ has no row for {reg}"


def test_the_scores_files_hosts_are_credited():
    """SCORES_5a_LIVE_FLIP (2026-10-07; SCORES_PLAN 6.9): every host the scores
    core and job name, with or without a scheme, maps to the MLB Stats API row,
    and that row names what the Scores / Standings page serves."""
    files = _scores_files()
    assert {p.name for p in files} >= {"scores_core.py", "scores_job.py"}
    seen = set()
    for p in files:
        for host in _hosts(p):
            if _registered(host) not in _OWN:
                seen.add(host)
    assert {"img.mlbstatic.com", "streamable.com", "statsapi.mlb.com"} <= seen, seen
    assert {_registered(h) for h in seen} == {"mlb.com"}, seen
    html = build_site.build_sources()
    assert "On Scores / Standings: live scores, win probability, box scores, highlight video" in html


def test_the_awards_results_are_credited():
    """AWARDS_11_FLIP_RENAME (2026-10-09; AW-Q4): the writers' results come from MLB's
    StatsAPI awards endpoint, so the MLB Stats API row names what the Awards / HoF page
    reads, and the ingest's only host is MLB's."""
    seen = {_registered(h) for h in _hosts(ROOT / "tools" / "award_winners_ingest.py")} - _OWN
    assert seen == {"mlb.com"}, seen
    html = build_site.build_sources()
    assert ("The Awards / HoF page reads the writers' MVP, Cy Young, Rookie and Manager of the "
            "Year results from MLB's awards endpoint.").replace("'", "&#x27;") in html


def test_the_standings_files_hosts_are_credited():
    """STANDINGS_7_FLIP (2026-10-15; STANDINGS_PLAN 5.11): standings_core.py names no host
    (a pure module) and the job's standings call goes to statsapi.mlb.com, which the MLB
    Stats API row credits; that row names the standings the Standings page prints."""
    core, job = ROOT / "standings_core.py", ROOT / "tools" / "scores_job.py"
    assert core.exists() and job.exists()
    assert [h for h in _HOST_RE.findall(core.read_text(encoding="utf-8")) if _registered(h) not in _OWN] == []
    assert "/api/v1/standings" in job.read_text(encoding="utf-8")
    assert {_registered(h) for h in _hosts(job) if _registered(h) not in _OWN} == {"mlb.com"}
    assert "mlb.com" in _sources_domains()
    html = build_site.build_sources()
    assert "live scores, standings and video" in html
    assert "the standings, records, splits and expected records the Standings page prints" in html
