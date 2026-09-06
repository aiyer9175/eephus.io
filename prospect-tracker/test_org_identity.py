"""Club identity: resolve by StatsAPI id, not by name.

THE LIVE DEFECT THIS CLOSES. StatsAPI has called Arizona "D-backs" since 2008.
`canonical_org` has no alias for it, so it returns the input unchanged, and both
standings readers in fa_fit_backtest then guard on `len(org) <= 3`, see a
seven-character string, and skip the club without a word. The same thing happened
to Cleveland as "Indians" through 2021 and Montreal as "Expos" through 2004.

Measured on 2026-09-06 across the 27 cached standings files: 46 club-seasons
dropped, and Arizona was the ONLY one of 30 rows in the served
`data/mlb_projections.json` team_outlook carrying a null current-season block. A
75-68 club was missing from the live wild-card picture on the site.

Ids do not change and names do. These tests pin the id path and, more
importantly, pin that NO club in any cached file is dropped, which is the check
that would have caught the original defect and which catches the next rename
without anybody having to know it happened.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from trades import canonical_org, canonical_org_from_id   # noqa: E402

STANDINGS = sorted(glob.glob(str(ROOT / ".cache" / "statsapi_standings_*.json")))


def _records(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    for rec in d.get("records") or []:
        for tr in rec.get("teamRecords") or []:
            yield tr


# --------------------------------------------------------------------------
# The resolver
# --------------------------------------------------------------------------

def test_the_three_renamed_clubs_resolve_by_id():
    """The exact three that were being dropped."""
    assert canonical_org_from_id(109) == "ARI"      # D-backs
    assert canonical_org_from_id(114) == "CLE"      # Indians
    assert canonical_org_from_id(120) == "WSN"      # Expos became the Nationals


def test_the_name_path_still_fails_on_them():
    """Recorded so the reason the id path exists cannot be forgotten. If the
    alias table is ever taught these names, this test should be updated
    deliberately, not deleted: the id path is still the right one."""
    assert canonical_org("D-backs") == "D-backs", (
        "the alias table now resolves D-backs. That is fine, and the id path is "
        "still preferred because the NEXT rename will not be in the table either")


def test_an_int_id_and_a_string_id_both_resolve():
    """tjstats keys the map with STRINGS and every teamRecord id is an INT, so
    the cast is load-bearing and a regression here silently drops every club."""
    assert canonical_org_from_id(109) == canonical_org_from_id("109") == "ARI"


def test_a_missing_id_falls_back_to_the_name():
    """Fixtures carry a name and no id; the fallback keeps them working."""
    assert canonical_org_from_id(None, "Boston Red Sox") == "BOS"
    assert canonical_org_from_id(None, None) is None


def test_an_unknown_id_falls_back_rather_than_inventing():
    assert canonical_org_from_id(99999, "Boston Red Sox") == "BOS"
    assert canonical_org_from_id(99999, None) is None


def test_every_club_id_maps_to_a_three_letter_code():
    from trades import _org_by_id
    m = _org_by_id()
    assert len(m) == 30, f"expected 30 clubs, got {len(m)}"
    for club_id, org in m.items():
        assert isinstance(club_id, int)
        assert org and len(org) <= 3, f"{club_id} -> {org!r}"


# --------------------------------------------------------------------------
# No club is dropped, in any cached file
# --------------------------------------------------------------------------

@pytest.mark.skipif(not STANDINGS, reason="no standings cache on this machine")
def test_no_club_season_is_dropped_by_the_length_guard():
    """THE TEST THAT WOULD HAVE CAUGHT IT. Both standings readers resolve a club
    and then require `len(org) <= 3`. Anything the resolver passes through
    unchanged fails that guard silently, so the guard is a drop, not an error."""
    dropped = []
    for path in STANDINGS:
        season = os.path.basename(path).split("_")[-1].split(".")[0]
        for tr in _records(path):
            team = tr.get("team") or {}
            org = canonical_org_from_id(team.get("id"), team.get("name") or "")
            if not org or len(org) > 3:
                dropped.append((season, team.get("name"), team.get("id"), org))
    assert not dropped, (
        f"{len(dropped)} club-seasons are still dropped by the length guard: "
        f"{dropped[:8]}")


@pytest.mark.skipif(not STANDINGS, reason="no standings cache on this machine")
def test_every_modern_season_resolves_thirty_clubs():
    """A season that resolves 29 is the defect's signature. Pre-1998 seasons had
    fewer clubs, so the assertion starts where the league reached thirty."""
    for path in STANDINGS:
        season = int(os.path.basename(path).split("_")[-1].split(".")[0])
        if season < 1998:
            continue
        orgs = set()
        for tr in _records(path):
            team = tr.get("team") or {}
            org = canonical_org_from_id(team.get("id"), team.get("name") or "")
            if org and len(org) <= 3:
                orgs.add(org)
        assert len(orgs) == 30, f"{season}: resolved {len(orgs)} clubs, not 30"


@pytest.mark.skipif(not STANDINGS, reason="no standings cache on this machine")
def test_the_readers_use_the_id_path():
    """Source-level, because the readers cannot be run without a fetch. What is
    checked is that neither one resolves a StatsAPI club by name alone."""
    src = (ROOT / "fa_fit_backtest.py").read_text(encoding="utf-8")
    assert src.count("canonical_org_from_id(") >= 2, (
        "fewer than two standings readers use the id path; standings_wins and "
        "standings_now both need it")
    assert 'canonical_org((tr.get("team") or {}).get("name")' not in src, (
        "a standings reader still resolves a club by name alone")


# --------------------------------------------------------------------------
# The served artifact
# --------------------------------------------------------------------------

def test_no_served_team_outlook_row_has_a_null_current_block():
    """The reader-visible consequence. Arizona carried `current: None` while
    every other club had a live standings block, which is a contender missing
    from the wild-card picture.

    This test reads the SERVED artifact, so it stays red until the projections
    are regenerated on the repaired resolver. That is correct: the resolver fix
    alone does not repair an artifact that was already written wrong.

    IT CHECKS FOR A PARTIAL OVERLAY, NOT A MISSING ONE. `data/mlb_projections.json`
    is gitignored and the overlay is best-effort: with no network, standings_now
    returns nothing, the overlay is skipped wholesale and all 30 clubs carry a
    null block. That is documented behaviour, it is what a suite run leaves
    behind, and reporting it as the resolver defect would make this test red on
    every offline build until a reader stopped looking. Twenty-nine clubs with a
    block and one without is the signature that a club was silently dropped, and
    that is what is asserted.
    """
    p = ROOT / "data" / "mlb_projections.json"
    if not p.exists():
        pytest.skip("data/mlb_projections.json has not been built")
    rows = json.loads(p.read_text(encoding="utf-8")).get("team_outlook") or []
    if not rows:
        pytest.skip("team_outlook is empty")
    null_current = [r.get("team") for r in rows if r.get("current") is None]
    # A FULLY DEGRADED ARTIFACT IS NOT THE DEFECT, and conflating the two makes
    # this test red on every offline build. `_attach_current_season` is
    # best-effort by design: if standings_now returns nothing the overlay is
    # skipped entirely and EVERY club carries a null block, which is the
    # documented offline behaviour and is what a suite run produces.
    #
    # The defect is a PARTIAL overlay: some clubs with a current block and some
    # without, which is what a club the resolver silently dropped looks like.
    # Twenty-nine with and one without is the exact signature.
    if len(null_current) == len(rows):
        pytest.skip(
            "the current-season overlay did not run at all on this build, which "
            "is the documented offline behaviour. Run "
            "`python tools/repair_team_outlook_overlay.py` to attach it.")
    assert not null_current, (
        f"{null_current} carry a null current-season block while "
        f"{len(rows) - len(null_current)} other clubs have one. A PARTIAL "
        "overlay is the resolver-drop signature: the club was skipped by the "
        "len<=3 guard while its neighbours resolved. Repair with "
        "`python tools/repair_team_outlook_overlay.py`.")


# --------------------------------------------------------------------------
# The same defect, one module away
# --------------------------------------------------------------------------

def test_the_park_factor_cache_uses_the_savant_override_map():
    """SAVANT LABELS ARIZONA'S VENUE "D-backs" AND canonical_org HAS NO ALIAS.

    fa_fit._park_factors has handled this since it was written, through
    _SAVANT_CLUB_OVERRIDES. fa_fit_backtest built its own cache one module away
    with canonical_org alone, so every Arizona row landed under the key
    "D-backs" and every ARI lookup missed.

    A miss returns _park_score's neutral 0.5, which is INDISTINGUISHABLE from a
    measured neutral park, so Arizona was scored park-neutral in every test
    winter of the published team-fit gate artifact and nothing looked wrong.
    """
    src = (ROOT / "fa_fit_backtest.py").read_text(encoding="utf-8")
    i = src.index("park_cache[Y - 1]")
    seg = src[max(0, i - 1400):i + 700]
    assert "_SAVANT_CLUB_OVERRIDES" in seg, (
        "the backtest builds its park cache without the override map, so "
        "Arizona keys as 'D-backs' and every lookup falls to neutral")


def test_the_override_map_actually_resolves_arizona():
    import fa_fit
    assert fa_fit._SAVANT_CLUB_OVERRIDES.get("D-backs") == "ARI"
    assert canonical_org("D-backs") != "ARI", (
        "canonical_org now handles D-backs on its own, so the override map is "
        "redundant and this whole class of defect is closed at the source")


def test_a_missing_park_and_a_neutral_park_are_the_same_number():
    """The property that hid the defect, pinned so the next reader knows. It is
    not a bug to fix here: a fit score has to be a number. It is the reason the
    caller has to key correctly rather than rely on the score looking wrong."""
    import fa_fit_backtest as fb
    assert fb._park_score({}, "ARI", False) == 0.5
    assert fb._park_score({"ARI": {"woba": 100, "hr": 100}}, "ARI", False) == 0.5
