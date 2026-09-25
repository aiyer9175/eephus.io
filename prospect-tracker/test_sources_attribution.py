# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/sources/ names every upstream the ingest code calls (census X07-08).

The upstream list on /sources/ omitted MLB Trade Rumors (the arbitration
comparator and results tracker), The Odds API (the prices on /betting/) and
Open-Meteo (the nightly weather capture, whose data licence requires
attribution). Each external host written in an ingest module must map, by
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
    "weather.gov": ("betting_weather.SOURCES['nws'] is a configured alternative; "
                    "FORECAST_SOURCE names Open-Meteo, so no request reaches it "
                    "(guarded below)"),
}


def _registered(host: str) -> str:
    return ".".join(host.lower().split(".")[-2:])


def _ingest_files() -> list[Path]:
    files = list(ROOT.glob("*_ingest.py")) + list(ROOT.glob("betting_*.py"))
    files += list((ROOT / "tools").glob("ingest_*.py"))
    return sorted(p for p in files if not p.name.startswith("test_"))


def _sources_domains() -> set[str]:
    html = build_site.build_sources()
    return {_registered(h) for h in re.findall(r'<h3><a href="https?://([^/"]+)', html)}


def test_every_ingest_host_has_a_sources_row():
    rows = _sources_domains()
    missing = {}
    for p in _ingest_files():
        for host in _HOST_RE.findall(p.read_text(encoding="utf-8")):
            reg = _registered(host)
            if reg in rows or reg in _NOT_CALLED:
                continue
            missing.setdefault(reg, p.name)
    assert not missing, (
        "external hosts the ingest code names with no /sources/ row: "
        + ", ".join(f"{h} ({f})" for h, f in sorted(missing.items()))
    )


def test_the_not_called_allowance_still_holds():
    import betting_weather
    assert betting_weather.FORECAST_SOURCE != "nws", (
        "the forecast capture now calls weather.gov: give NWS a /sources/ row "
        "and drop it from _NOT_CALLED")


def test_the_three_missing_upstreams_are_named():
    rows = _sources_domains()
    for reg in ("mlbtraderumors.com", "the-odds-api.com", "open-meteo.com"):
        assert reg in rows, f"/sources/ has no row for {reg}"
