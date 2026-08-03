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


def test_monitor_scores_the_recalibrated_distribution():
    """The monitor must grade the odds the site SERVES.

    Until 2026-08-03 this module reproduced efv_score's path up to the grade
    inversion and then read the raw p_bucket_given_fv curve, while the scorer
    applies the odds-dispersion Platt map at all three seams. The public card
    therefore published a pre-fix miscalibration (bust ECE 0.128) that the
    scorer had already corrected (0.075), and its tripwire threshold had been
    tuned to the pre-fix band, so it reported "within the documented standing
    miscalibration band" about a defect that no longer existed.

    Pin the wiring, not the numbers: the OOF row builder must apply the
    recalibration, and the curve/tier scorers must default to the served key.
    """
    import inspect
    import efv_reliability

    src = inspect.getsource(efv_reliability._oof_rows)
    assert "recalibrate_bucket" in src, (
        "efv_reliability._oof_rows no longer applies the odds-dispersion "
        "recalibration, so the monitor is grading a distribution the site "
        "does not serve (see efv_score seams 1292/1812/2191)")
    assert "p_after" in src, "the OOF rows must carry the served distribution"

    for fn in (efv_reliability._reliability_bins, efv_reliability._tier_reliability):
        assert inspect.signature(fn).parameters["key"].default == "p_after", (
            f"{fn.__name__} must default to the served distribution")


def test_tripwire_threshold_can_actually_fire():
    """A threshold above the value it watches is not a tripwire.

    The old 0.14 sat 1.9x above the served bust ECE and could not fire. The
    re-derived value must (a) leave headroom over the served baseline and
    (b) sit BELOW the pre-recalibration level, so that silently dropping the
    Platt map from the scoring seams trips the wire instead of going unnoticed.
    """
    import efv_reliability
    # Measured on the current tree, forward-chained OOF, pooled n=2825.
    served, pre_map = 0.0754, 0.1281
    thr = efv_reliability.BUST_ECE_TRIPWIRE
    assert served < thr < pre_map, (
        f"BUST_ECE_TRIPWIRE={thr} must sit between the served bust ECE "
        f"({served}) and the pre-recalibration value ({pre_map}); outside that "
        "band it either fires constantly or can never fire at all")


def test_writer_output_path_matches_the_frontend_fetch():
    """The producer (efv_reliability.OUT_PATH) and the consumer (the glossary
    fetch) must point at the SAME filename, so a rename can never leave the card
    fetching a file the pipeline no longer writes."""
    import efv_reliability
    assert efv_reliability.OUT_PATH.name == RELIABILITY_ARTIFACT
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"/data/{efv_reliability.OUT_PATH.name}" in js
