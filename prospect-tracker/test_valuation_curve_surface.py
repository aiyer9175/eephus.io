# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Guards for the eFV valuation-curve surface.

efv_export._valuation_curve writes data/xfv_valuation_curve.json on every eFV
regen (wired best-effort into regen_all): per FV tier and role, the value
engine's own surplus / expected WAR / star odds under the production valuation
set, side by side with the published FanGraphs 2026 anchor table and the live
board's medians. The glossary Methodology view surfaces it as the "What an eFV
grade is worth" card (assets/glossary.js renderMethodology ->
_methValuationCurveHTML). Mirrors test_reliability_surface.py: these pins keep
the producer, the consumer, and the deploy wiring from silently drifting apart:

  * the artifact must SHIP (not be added to deploy/data_exclude.txt), or the
    glossary fetch would 404 in production while working in dev;
  * the writer's output path and the frontend fetch path must be the SAME
    file, or the card would go permanently empty on a rename.

Diagnostic-only surface: nothing here regenerates a served model number."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent
VALUATION_CURVE_ARTIFACT = "xfv_valuation_curve.json"


def _excluded_data_files() -> list[str]:
    out = []
    for line in (ROOT / "deploy" / "data_exclude.txt").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_valuation_curve_artifact_is_not_excluded_so_it_ships():
    """data/xfv_valuation_curve.json rides the deploy '/data/*.json' include;
    if it were ever added to deploy/data_exclude.txt the glossary's valuation
    curve fetch would 404 in production. Keep it out of the exclude list."""
    assert VALUATION_CURVE_ARTIFACT not in _excluded_data_files(), (
        f"deploy/data_exclude.txt excludes {VALUATION_CURVE_ARTIFACT}, but the "
        "glossary Methodology view fetches /data/xfv_valuation_curve.json at "
        "runtime - it must ship")


def test_glossary_methodology_fetches_the_valuation_curve_artifact():
    """The valuation-curve card must actually wire the fetch. Guards against
    the surface being silently dropped (the reliability monitor's finding 37
    was exactly this: an artifact computed nightly but never displayed)."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"/data/{VALUATION_CURVE_ARTIFACT}" in js, (
        "assets/glossary.js no longer fetches /data/xfv_valuation_curve.json - "
        "the valuation-curve surface was removed")
    assert "_methValuationCurveHTML" in js, (
        "assets/glossary.js is missing the _methValuationCurveHTML renderer")


def test_glossary_valuation_curve_renders_defensively():
    """The card must degrade gracefully: hide the whole section when the
    payload is absent/errored/an unexpected shape, and render each role table
    only when its tiers are present. Pin the graceful-degradation markers so a
    future refactor can't turn a missing artifact into a visible error."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    # The renderer body between its declaration and the next top-level function.
    start = js.index("function _methValuationCurveHTML()")
    end = js.index("function ", start + 1)
    body = js[start:end]
    # The shape it reads: per-role tiers with published / model / live blocks,
    # and the live star column labeled as the bucket probability (a different
    # quantity from the published-definition star odds - both stay).
    assert "tiers" in body
    assert "published" in body and "model" in body and "live" in body
    assert "p_star_median" in body and "p(star bucket)" in body
    # Guards that hide the section instead of erroring on a bad/absent payload.
    assert "__error" in body
    assert 'return "";' in body


def test_writer_output_path_matches_the_frontend_fetch():
    """The producer (efv_export.VALUATION_CURVE_PATH) and the consumer (the
    glossary fetch) must point at the SAME filename, so a rename can never
    leave the card fetching a file the pipeline no longer writes."""
    import efv_export
    assert efv_export.VALUATION_CURVE_PATH.name == VALUATION_CURVE_ARTIFACT
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"/data/{efv_export.VALUATION_CURVE_PATH.name}" in js
