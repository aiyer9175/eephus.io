"""The induction-ledger repair, and the resolution layer built on it.

WHAT WAS WRONG, AND IT WAS A LIVE DEFECT IN A SHIPPED LABEL. StatsAPI names Hall of Fame
inductees by MLBAM id and Baseball-Reference names ballot rows by bbref id. Where the
ingest could not bridge the two, the inductee never entered the ledger, and `label_any`
then reported him as NOT in the Hall. Measured 2026-09-06: 130 of 354 unresolved, 63 of
them inside the eligible universe, 33 carrying a resolved zero and 30 reading as censored.
Charlie Gehringer, Ed Delahanty, Eddie Plank, Buck Ewing and Jesse Burkett were all
labelled non-Hall-of-Famers.

Both war_daily parquets carry both ids. The bridge was on disk the whole time.

THE FIVE MISTAKES THESE TESTS EXIST FOR, and two of them were made:

  1. LETTING THE REPAIR FLIP A ONE TO A ZERO. It may only add.
  2. MOVING label_bbwaa. The writers' verdict cannot change because a committee induction
     was recovered, so any movement there is a bug in the repair itself.
  3. CACHING ON THE WRONG KEY. `_BALLOT_CACHE` was keyed on the path alone while the
     crosswalk changes the RESULT, so inside one process the first call won.
  4. HANDING OUT THE CACHE'S INTERIOR. `crosswalk_bbref_mlbam` returned `_XWALK_CACHE`
     itself, so `clear_cache()` emptied a live reference a caller was holding. The ledger
     producer serialized zero pairs into its own artifact this way while the repair it was
     documenting had worked perfectly.
  5. RESOLVING A DEPARTED CANDIDATE AT last + 1. The writers voted only every other year
     from 1956 to 1966, so the BBWAA panel has TEN empty years and last + 1 can name a
     year in which no verdict could have been observed. Measured: 224 players.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import hof_data as hd                              # noqa: E402

ART = ROOT / "data" / "hof_ledger_eval.json"


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("run tools/hof_ledger_check.py")
    return json.loads(ART.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def frames():
    hd.clear_cache()
    after = hd.label_frame(offline=True, as_of_year=2026).set_index("player_ID")
    before = hd.label_frame(offline=True, as_of_year=2026,
                            ballots_=hd.ballots(crosswalk={})).set_index("player_ID")
    return before, after


# --------------------------------------------------------------------------
# L1: the crosswalk
# --------------------------------------------------------------------------

def test_the_crosswalk_is_one_to_one(art):
    x = art["crosswalk"]
    assert x["pairs"] > 20000
    assert x["distinct_bbref"] == x["pairs"]
    assert x["distinct_mlbam"] == x["pairs"]
    assert x["is_one_to_one"] is True, (
        "the crosswalk maps two players onto one id somewhere, so the repair "
        "would credit one man's induction to another")


def test_the_crosswalk_never_touches_the_network(monkeypatch):
    """label_frame(offline=True) must stay offline. pybaseball's pitching side
    carries no disk cache, so one careless call turns every test run into a
    download."""
    import war_source
    def boom(*a, **k):
        raise AssertionError("stint_frame was called on the offline path")
    monkeypatch.setattr(war_source, "stint_frame", boom)
    hd.clear_cache()
    x = hd.crosswalk_bbref_mlbam()
    assert x, "the crosswalk came back empty, so the repair silently did nothing"
    df = hd.label_frame(offline=True, as_of_year=2026)
    assert len(df) > 3000


def test_the_crosswalk_hands_out_a_copy_not_its_own_cache():
    """MISTAKE 4, and it was made. A caller that holds the returned dict must
    not see it emptied by an unrelated clear_cache()."""
    hd.clear_cache()
    first = hd.crosswalk_bbref_mlbam()
    n = len(first)
    assert n > 0
    hd.clear_cache()
    assert len(first) == n, (
        "clear_cache() emptied a dict the caller was still holding, which is "
        "how zero pairs got serialized into an artifact documenting 23,681")


# --------------------------------------------------------------------------
# L2, L3: what the repair may and may not do
# --------------------------------------------------------------------------

def test_the_repair_only_adds_and_never_flips_a_one_to_a_zero(frames):
    before, after = frames
    b1 = set(before.index[before["label_any"] == 1])
    a1 = set(after.index[after["label_any"] == 1])
    assert b1 <= a1, f"the repair LOST {len(b1 - a1)} inductees: {sorted(b1 - a1)[:10]}"
    assert len(a1 - b1) > 50, "the repair added almost nothing; check the crosswalk"


def test_no_inducted_player_carries_a_resolved_zero(frames, art):
    """The 33 false zeros. Named because a reader may know them."""
    _before, after = frames
    b = hd.ballots()
    bad = [p for p in b["inducted"] if p in after.index and after.loc[p, "label_any"] == 0]
    assert not bad, (
        f"{len(bad)} players in the induction ledger are labelled NOT in the "
        f"Hall: {sorted(str(after.loc[p, 'name']) for p in bad)[:10]}")
    names = art["repair_effect"]["false_zero_names"]
    assert "Charlie Gehringer" in names or "Ed Delahanty" in names, (
        "the repair no longer recovers the named false zeros, so either the "
        "ledger changed upstream or the crosswalk stopped working")


def test_label_bbwaa_is_byte_identical_before_and_after_the_repair(frames, art):
    """MISTAKE 2. label_bbwaa reads only the ballot rows; the inducted ledger is
    read at exactly one site, inside label_any."""
    before, after = frames
    assert before["label_bbwaa"].equals(after["label_bbwaa"])
    assert art["label_bbwaa_invariance"]["is_byte_identical"] is True
    assert art["labels_before"]["label_bbwaa"] == art["labels_after"]["label_bbwaa"]


def test_the_repair_is_not_claimed_to_buy_accuracy(art):
    txt = art["what_this_does_not_show"].lower()
    assert "correctness repair" in txt and "negative" in txt, (
        "the artifact must say plainly that this buys no accuracy and may cost "
        "some, or the next reader will quote it as a win")


# --------------------------------------------------------------------------
# L4, L5: nothing is dropped silently
# --------------------------------------------------------------------------

def test_unresolved_inductees_are_named_not_dropped(art):
    led = art["ledger"]
    assert led["resolution"]["unresolved"] == len(led["unresolved_names"])
    assert led["unresolved_names"], "the residual is empty, which is implausible"


def test_the_unresolved_residual_is_mostly_people_who_never_played(art):
    """A crosswalk built from playing records cannot find an umpire, and should
    not. Recorded so the residual is not mistaken for a coverage failure."""
    names = set(art["ledger"]["unresolved_names"])
    known_non_players = {"Bill Klem", "Bud Selig", "Marvin Miller", "Bud Fowler",
                         "Alexander Cartwright", "Bill Veeck"}
    assert known_non_players & names, (
        "the residual no longer contains the known non-players, so it is now "
        "made of something else and the explanation in the artifact is stale")


def test_out_of_universe_inductees_are_named_not_dropped(art):
    for r in art["ledger"]["out_of_universe"]:
        assert r.get("reason"), f"unexplained drop: {r}"


def test_the_plaque_role_unverified_set_is_published_and_non_empty(art):
    pr = art["plaque_role_unverified"]
    assert pr["n"] > 0 and pr["n_in_eligible_universe"] > 0
    assert pr["blocking_lane"] == "H-DATA-PLAQUE"
    assert "no Hall-sized line" in pr["what_must_not_happen"]


def test_the_repair_makes_the_plaque_problem_larger_not_smaller(art):
    """Pre-registered in the spec and worth pinning: the players it recovers
    include managers who also played."""
    names = set(art["repair_effect"]["added_names"])
    managers = {"Connie Mack", "Casey Stengel", "Bucky Harris", "Al Lopez",
                "Billy Southworth"}
    assert managers & names, (
        "the repair no longer recovers the manager-players, so the claim that "
        "it enlarges the plaque-role problem needs re-measuring")


# --------------------------------------------------------------------------
# L6: the censoring invariant
# --------------------------------------------------------------------------

def test_no_censored_player_carries_a_zero(frames):
    _before, after = frames
    for col, cens in (("label_bbwaa", "censored_bbwaa"), ("label_any", "censored_any")):
        both = after[(after[cens].astype(bool)) & (after[col] == 0)]
        assert not len(both), f"{len(both)} rows are censored AND zero on {col}"


# --------------------------------------------------------------------------
# The caches
# --------------------------------------------------------------------------

def test_the_ballot_cache_key_includes_the_crosswalk():
    """MISTAKE 3, and it was made. Reading the unrepaired ledger first must not
    poison the repaired read."""
    hd.clear_cache()
    unrep = hd.ballots(crosswalk={})
    rep = hd.ballots()
    assert len(rep["inducted"]) > len(unrep["inducted"]), (
        "the second call returned the first call's result, so the cache key "
        "does not include the crosswalk")


def test_clear_cache_clears_all_four_caches():
    hd.clear_cache()
    hd.ballots()
    hd.crosswalk_bbref_mlbam()
    assert hd._BALLOT_CACHE and hd._XWALK_CACHE
    hd.clear_cache()
    assert not hd._FRAME_CACHE and not hd._CAREER_CACHE
    assert not hd._BALLOT_CACHE, "the ballot cache survived clear_cache()"
    assert not hd._XWALK_CACHE, "the crosswalk cache survived clear_cache()"


# --------------------------------------------------------------------------
# L7 and the resolution layer
# --------------------------------------------------------------------------

def test_the_dropped_off_route_ignores_a_pre_1979_flag():
    """The five percent retention rule began in 1979 and the ingest applies the
    flag back to 1936. A player resolved on a 1950s drop flag would resolve
    decades before the writers had finished with him."""
    b = hd.ballots()
    for pid in list(b["by_pid"])[:4000]:
        if hd.resolution_route(pid, ballots_=b) != "dropped_off":
            continue
        y = hd.resolution_year(pid, ballots_=b)
        assert y >= hd.BBWAA_DROP_RULE_FIRST_YEAR, (
            f"{pid} resolves at {y}, before the drop rule existed")


def test_the_correction_actually_fires_on_real_players(art):
    r = art["resolution_year"]
    assert r["players_with_a_pre_1979_drop_flag"] > 100
    assert r["players_whose_drop_flag_precedes_their_last_appearance"] > 100, (
        "no player's drop flag precedes his last appearance, so the 1979 "
        "correction is a no-op and its justification is wrong")


def test_the_bbwaa_panel_has_ten_gap_years_not_five(art):
    """MISTAKE 5. The ingest's own years_with_no_election lists five. The writers
    also voted biennially from 1956 to 1966 while the committees kept meeting."""
    gaps = art["resolution_year"]["bbwaa_panel_gap_years"]
    assert set(gaps) == {1940, 1941, 1943, 1944, 1946, 1957, 1959, 1961, 1963, 1965}
    assert art["resolution_year"][
        "left_ballot_cases_where_last_plus_one_is_a_gap_year"] > 100


def test_the_left_ballot_route_resolves_at_the_next_panel_election():
    """Hand panel with a gap: a player last seen in 1956 must resolve at 1958,
    because there was no BBWAA election in 1957."""
    b = hd.ballots()
    panel = hd._bbwaa_panel_years(b)
    assert 1957 not in panel and 1958 in panel
    fake = {
        "by_pid": {"gapguy01": [
            {"player_id": "gapguy01", "election_year": 1954, "route": "BBWAA",
             "elected": False, "dropped_off": False},
            {"player_id": "gapguy01", "election_year": 1956, "route": "BBWAA",
             "elected": False, "dropped_off": False},
        ]},
        "inducted": {},
        "doc": b["doc"],
    }
    assert hd.resolution_year("gapguy01", ballots_=fake) == 1958
    assert hd.resolution_route("gapguy01", ballots_=fake) == "left_ballot"


def test_resolution_year_is_never_before_the_last_ballot_appearance_for_a_non_elected_player():
    b = hd.ballots()
    checked = 0
    for pid, rows in b["by_pid"].items():
        bb = [r for r in rows
              if (r.get("route") or "").upper() == "BBWAA" and r.get("election_year")]
        if not bb or any(r.get("elected") for r in bb):
            continue
        y = hd.resolution_year(pid, ballots_=b)
        if y is None:
            continue
        checked += 1
        assert y >= max(int(r["election_year"]) for r in bb), (
            f"{pid} resolves at {y}, before his last appearance")
    assert checked > 500, "the check ran on almost nobody"


def test_the_elected_route_matches_the_shipped_window_close():
    """Clause (c): where the player was elected, the new function must agree
    with the shipped one exactly, or two forward chains disagree about the same
    fact."""
    b = hd.ballots()
    n = 0
    for pid in list(b["by_pid"]):
        if hd.resolution_route(pid, ballots_=b) != "elected":
            continue
        n += 1
        assert hd.resolution_year(pid, ballots_=b) == hd.bbwaa_window_close_year(
            pid, ballots_=b)
    assert n > 100


def test_the_as_of_identity_is_not_claimed_generally(art):
    """label_any is non-monotone in Y, so a general as-of identity would be
    false. The artifact must publish the exceptions rather than assert past
    them."""
    r = art["resolution_year"]
    assert r["n_label_any_non_monotone"] > 0
    assert r["label_any_non_monotone_players"]
    names = {x["name"] for x in r["label_any_non_monotone_players"]}
    assert "Joe Gordon" in names, (
        "Joe Gordon closed in 1945 and was inducted in 2009, the widest case; "
        "if he is gone the non-monotone census is measuring something else")
    assert "not claimed" in r["why_non_monotone"] or "holds at 2026" in r["why_non_monotone"]


def test_exhausted_is_deliberately_absent_from_the_route_tuple():
    """It is a real route and we cannot separate it from left_ballot without the
    era-varying ballot cap. A route that mixed two mechanisms would be worse
    than one honest name."""
    assert "exhausted" not in hd.RESOLUTION_ROUTES
    src = (ROOT / "hof_data.py").read_text(encoding="utf-8")
    i = src.index("RESOLUTION_ROUTES")
    assert "deliberately ABSENT" in src[i:i + 900]


def test_resolution_frame_has_the_four_columns(art):
    assert art["resolution_year"]["frame_shape"][1] == 34
    for k in ("res_route_bbwaa", "res_route_any"):
        assert art["resolution_year"][f"route_census_{k.split('_')[-1]}"]


# --------------------------------------------------------------------------
# The contract text
# --------------------------------------------------------------------------

def test_the_label_contract_no_longer_claims_the_route_field_separates_contributors():
    src = (ROOT / "hof_data.py").read_text(encoding="utf-8")
    assert "the route field separates them." not in src, (
        "the label contract still claims the route field separates contributors "
        "from players. It does not: route is the ELECTORATE, and no field in "
        "the source names the plaque.")
    assert "PLAQUE ROLE\n#   UNVERIFIED" in src or "PLAQUE ROLE UNVERIFIED" in src


def test_the_module_no_longer_says_the_ballot_source_does_not_exist():
    src = (ROOT / "hof_data.py").read_text(encoding="utf-8")
    for stale in ("There is no ballot source in\n     this repo",
                  "Neither has been ingested.",
                  "the ballot source does not exist"):
        assert stale not in src, f"stale docstring survives: {stale!r}"


def test_the_label_frame_docstring_states_the_nan_trap():
    import inspect
    doc = inspect.getdoc(hd.label_frame) or ""
    assert "NaN" in doc and "bool(nan) is True" in doc, (
        "a caller writing `if row.label_any:` treats every censored player as "
        "an inductee, and the docstring used to say the opposite")


def test_a_drop_flag_on_a_year_the_player_survived_does_not_resolve_him(art):
    """The defect a test found rather than reasoning caught. The 1979 rule alone
    does not fix it: Harvey Haddix is flagged in 1979 and appears through 1985."""
    r = art["resolution_year"]
    assert r["players_with_a_drop_flag_on_a_year_they_survived"] > 20, (
        "no player carries a drop flag on a year he survived, so the "
        "final-appearance condition is a no-op and its justification is wrong")
    names = {x["name"] for x in r["drop_flag_on_a_survived_year_examples"]}
    assert names, "the examples list is empty"
    b = hd.ballots()
    for x in r["drop_flag_on_a_survived_year_examples"]:
        y = hd.resolution_year(x["player_id"], ballots_=b)
        if y is None:
            continue
        assert y >= x["last_appearance"], (
            f"{x['name']} resolves at {y}, on a flag from "
            f"{x['drop_years']} that he survived through {x['last_appearance']}")
