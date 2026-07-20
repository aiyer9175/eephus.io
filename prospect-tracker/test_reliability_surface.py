# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Guards for the eFV live-calibration-monitor surface (finding 37).

efv_reliability.build writes data/xfv_reliability.json nightly (the shipped
5-bucket outcome distribution re-scored forward-chained out-of-fold, plus a
bust-bucket ECE drift tripwire). The glossary Methodology view surfaces it as
the "Live calibration monitor" card (assets/glossary.js renderMethodology ->
_methReliabilityHTML). These pins keep the producer, the consumer, and the
deploy wiring from silently drifting apart:

  * the artifact must SHIP (not be added to deploy/data_exclude.txt), or the
    glossary fetch would 404 in production while working in dev;
  * the writer's output path and the frontend fetch path must be the SAME
    file, or the card would go permanently empty on a rename.

Diagnostic-only surface: nothing here regenerates a served model number."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent
RELIABILITY_ARTIFACT = "xfv_reliability.json"


def _excluded_data_files() -> list[str]:
    out = []
    for line in (ROOT / "deploy" / "data_exclude.txt").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_reliability_artifact_is_not_excluded_so_it_ships():
    """data/xfv_reliability.json rides the deploy '/data/*.json' include; if it
    were ever added to deploy/data_exclude.txt the glossary's Live calibration
    monitor fetch would 404 in production. Keep it out of the exclude list."""
    assert RELIABILITY_ARTIFACT not in _excluded_data_files(), (
        f"deploy/data_exclude.txt excludes {RELIABILITY_ARTIFACT}, but the "
        "glossary Methodology view fetches /data/xfv_reliability.json at "
        "runtime - it must ship")


def test_glossary_methodology_fetches_the_reliability_artifact():
    """The Live calibration monitor card must actually wire the fetch. Guards
    against the surface being silently dropped (finding 37 was that the artifact
    was computed nightly but never displayed)."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"/data/{RELIABILITY_ARTIFACT}" in js, (
        "assets/glossary.js no longer fetches /data/xfv_reliability.json - the "
        "Live calibration monitor surface was removed")
    assert "_methReliabilityHTML" in js, (
        "assets/glossary.js is missing the _methReliabilityHTML renderer")


def test_glossary_reliability_renders_defensively():
    """The card is dark-launched against a degraded dev artifact and a fresh
    box artifact, so it must degrade gracefully: hide the whole section when the
    payload is absent/unexpected, and read the tripwire + per-tier fields that
    only the fresh vintage carries. Pin the graceful-degradation markers so a
    future refactor can't turn a missing artifact into a visible error."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    # The renderer body between its declaration and the next top-level function.
    start = js.index("function _methReliabilityHTML()")
    end = js.index("function ", start + 1)
    body = js[start:end]
    assert "reliability_curves_pooled" in body   # shape it reads
    assert "tripwire" in body and "per_tier_reliability" in body
    # Guards that hide the section instead of erroring on a bad/absent payload.
    assert '__error' in body
    assert 'return "";' in body


def test_writer_output_path_matches_the_frontend_fetch():
    """The producer (efv_reliability.OUT_PATH) and the consumer (the glossary
    fetch) must point at the SAME filename, so a rename can never leave the card
    fetching a file the pipeline no longer writes."""
    import efv_reliability
    assert efv_reliability.OUT_PATH.name == RELIABILITY_ARTIFACT
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"/data/{efv_reliability.OUT_PATH.name}" in js
