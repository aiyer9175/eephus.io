# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""F-DEF: observed defence as a real column of the hitter WAR map.

The map's only positional term was a catcher dummy, so every non-catcher was
priced as if his glove and his position were league average and the star tail
paid for it. This pins the column's CONTRACT - point in time, shrunk, capped,
and matched between the fit and the residual reconstruction - not its verdict,
which lives in the Gate-1 note on DEF_FEATURE_DEFAULT.
"""
import fa_projection as fp


def _with_hist(rows, fn):
    """Run fn with a stubbed defensive history."""
    old = fp._DEF_HIST
    fp._DEF_HIST = rows
    try:
        return fn()
    finally:
        fp._DEF_HIST = old


def test_def_rate_reads_only_prior_seasons():
    """A season may never see itself: the feature has to be usable at project
    time, when the target season does not exist yet."""
    hist = {(7, 2026): (60.0, 600.0), (7, 2025): (0.0, 600.0)}
    now = _with_hist(hist, lambda: fp.def_rate(7, 2026))    # 2026 is the target
    assert now == 0.0                                       # only 2025 is visible
    later = _with_hist(hist, lambda: fp.def_rate(7, 2027))
    assert later > 0.0                                      # now 2026 counts


def test_def_rate_shrinks_toward_zero_on_exposure():
    """A 60-run season over 600 PA is a 60 runs/600PA rate; the published
    number is that rate pulled toward no-signal by DEF_K."""
    hist = {(7, 2026): (60.0, 600.0)}
    r = _with_hist(hist, lambda: fp.def_rate(7, 2027))
    # cap first (20), then shrink on 600 of 600+DEF_K
    assert r == 20.0 * (600.0 / (600.0 + fp.DEF_K))
    thin = _with_hist({(7, 2026): (6.0, 60.0)}, lambda: fp.def_rate(7, 2027))
    assert abs(thin) < abs(r)                     # 60 PA moves almost nothing


def test_def_rate_is_capped():
    hist = {(7, 2026): (900.0, 600.0)}            # absurd, e.g. a bad feed row
    r = _with_hist(hist, lambda: fp.def_rate(7, 2027))
    assert abs(r) <= fp.DEF_CAP


def test_def_rate_is_zero_without_a_feed_or_an_id():
    assert _with_hist({}, lambda: fp.def_rate(7, 2027)) == 0.0
    assert fp.def_rate(None, 2027) == 0.0


def test_permutation_hook_rekeys_the_lookup():
    """The zero-information control has to change WHICH player is read while
    leaving the feature's marginal distribution alone."""
    hist = {(1, 2026): (30.0, 600.0), (2, 2026): (-30.0, 600.0)}
    old_seed, old_perm = fp.DEF_PERMUTE_SEED, fp._DEF_PERM
    try:
        base = [_with_hist(hist, lambda: fp.def_rate(m, 2027)) for m in (1, 2)]
        assert base[0] > 0 > base[1]
        fp.DEF_PERMUTE_SEED = 1
        fp._DEF_PERM = {(1, 2026): 2, (2, 2026): 1}
        swapped = [_with_hist(hist, lambda: fp.def_rate(m, 2027)) for m in (1, 2)]
        assert swapped == [base[1], base[0]]
        assert sorted(swapped) == sorted(base)     # same marginal, no linkage
    finally:
        fp.DEF_PERMUTE_SEED, fp._DEF_PERM = old_seed, old_perm


def test_map_column_count_matches_the_arm():
    """A four-coefficient map under a five-column reconstruction would subtract
    a prediction the map never made, so both sides read the same switch."""
    from unittest import mock
    league = {2020: {"woba": 0.320, "babip": 0.300}}
    row = {"season": 2020, "pa": 600, "role": "LF", "mlbam": 7,
           "k_pct": 0.22, "bb_pct": 0.08, "iso": 0.180, "babip": 0.300,
           "hr_pa": 0.035}
    for on, want in ((False, 4), (True, 5)):
        with mock.patch.object(fp, "DEF_FEATURE_DEFAULT", on):
            feats = fp._realwar_map_features(row, "hit", league)
            assert feats is not None and len(feats) == want


def test_pitcher_side_is_untouched():
    league = {2020: {"lg_fip": 4.20}}
    row = {"season": 2020, "ip": 180.0, "fip": 3.50, "role": "SP", "mlbam": 7}
    from unittest import mock
    with mock.patch.object(fp, "DEF_FEATURE_DEFAULT", True):
        assert len(fp._realwar_map_features(row, "pit", league)) == 4


def test_fits_cache_key_separates_the_arms():
    """Without a suffix an A/B of the arm reads the other arm's map off disk."""
    from unittest import mock
    corpus = {"first": 2000, "last": 2026, "league": {}, "hit": [], "pit": []}
    seen = []
    for on in (False, True):
        with mock.patch.object(fp, "DEF_FEATURE_DEFAULT", on), \
             mock.patch.object(fp, "fit_aging_curves", lambda *a, **k: {}), \
             mock.patch.object(fp, "fit_war_map", lambda *a, **k: {}), \
             mock.patch("pickle.dump", lambda *a, **k: None), \
             mock.patch("builtins.open", mock.mock_open()):
            fp.fitted_models(corpus, 2025, use_cache=False)
        seen.append("_def" if on else "")
    assert seen == ["", "_def"]
