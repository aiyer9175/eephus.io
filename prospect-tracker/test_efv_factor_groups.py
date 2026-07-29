# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""Guards for the eFV explainer's collinear-factor grouping (efv_factor_groups).

THE DEFECT THESE LOCK DOWN (owner, 2026-07-25): Franklin Arias, whose K% sits 8.8
points BELOW the AA level median (elite contact), was told "Contact (K%) vs level:
down 0.56". The shipped ridge splits the collinear pair k_rel / peak_k_rel with
OPPOSITE signs, so the two terms largely cancel per player; the explainer scored
them SEPARATELY and kept the top-N by magnitude, which surfaced the negative half
and dropped its positive partner. A group must now be summed FIRST and shown or
hidden WHOLE, so no single member of a collinear pair can ever reach a card.

These are display-contract tests: they use synthetic ridges (no data files, no
fits) so they stay fast and cannot be perturbed by a model refit.
"""
from __future__ import annotations

import random

import efv_factor_groups as fg
import efv_score as es
import efv_ungraded as eu
from efv_model import _feature_spec


def _ridge(keys, weights=None):
    """Synthetic standardized ridge: mu=0, sd=1, so contribution == w * feature."""
    return {"keys": list(keys), "mu": [0.0] * len(keys), "sd": [1.0] * len(keys),
            "w": list(weights) if weights is not None else [1.0] * len(keys)}


def _shipped_sets():
    yield "flagship_hit", "hit", _feature_spec("hit")[0], es._factors, es._FACTOR_LABELS
    yield "flagship_pit", "pit", _feature_spec("pit")[0], es._factors, es._FACTOR_LABELS
    yield "ungraded_hit", "hit", eu._keys("hit"), eu._factors, eu._FACTOR_LABELS
    yield "ungraded_pit", "pit", eu._keys("pit"), eu._factors, eu._FACTOR_LABELS


def test_every_shipped_current_plus_peak_pair_is_declared_a_group():
    """Structural guard: if a peak_X feature ships alongside X and nobody declared
    the pair in efv_factor_groups.GROUPS, the explainer would be free to emit one
    half again. This fails the moment such a feature is added un-grouped."""
    for name, _side, keys, _fn, _labels in _shipped_sets():
        for k in keys:
            if not k.startswith("peak_"):
                continue
            base = k[len("peak_"):]
            if base not in keys:
                continue
            assert fg.group_id(k) is not None, f"{name}: {k} ships un-grouped"
            assert fg.group_id(k) == fg.group_id(base), \
                f"{name}: {k} and {base} are the same statistic but are not one group"


def test_member_only_labels_are_unreachable():
    """No label belonging to a NON-primary group member (e.g. 'Peak K rate') may
    ever be emitted: a group renders under ONE label, its primary's."""
    rng = random.Random(20260725)
    for name, side, keys, fn, labels in _shipped_sets():
        member_only = set()
        for gid, g in fg.GROUPS.items():
            for m in g["members"][1:]:
                if m in keys and m in labels:
                    member_only.add(labels[m])
        assert member_only, f"{name}: expected at least one non-primary member label to guard"
        ridge = _ridge(keys, [rng.uniform(-2, 2) for _ in keys])
        for _ in range(300):
            feats = {k: rng.uniform(-3, 3) for k in keys}
            got = {f["label"] for f in fn(ridge, feats, top=len(keys), side=side)}
            leaked = got & member_only
            assert not leaked, f"{name}: partial-group label emitted: {leaked}"


def test_group_is_shown_or_hidden_whole_and_reports_the_net():
    """Exhaustive per-group check on the shipped sets: whatever the fit does, a
    group occupies AT MOST ONE row, and that row's magnitude is the |net| of its
    members, never one member's magnitude."""
    rng = random.Random(4242)
    for name, side, keys, fn, labels in _shipped_sets():
        for gid, g in fg.GROUPS.items():
            present = [m for m in g["members"] if m in keys]
            if len(present) < 2:
                continue
            label = fg.display_label(gid, side, lambda k: labels.get(k, k))
            for _ in range(200):
                w = [rng.uniform(-2, 2) for _ in keys]
                ridge = _ridge(keys, w)
                feats = {k: rng.uniform(-3, 3) for k in keys}
                net = sum(w[keys.index(m)] * feats[m] for m in present)
                rows = [f for f in fn(ridge, feats, top=len(keys), side=side) if f["label"] == label]
                assert len(rows) <= 1, f"{name}/{gid}: group rendered {len(rows)} rows"
                if abs(net) >= 0.05:
                    assert rows, f"{name}/{gid}: net {net:.3f} clears the floor but no row emitted"
                    assert rows[0]["mag"] == round(abs(net), 2), \
                        f"{name}/{gid}: mag {rows[0]['mag']} != |net| {abs(net):.2f}"
                    assert rows[0]["dir"] == ("up" if net > 0 else "down"), \
                        f"{name}/{gid}: direction does not follow the net contribution"
                else:
                    assert not rows, f"{name}/{gid}: cancelling group ({net:.3f}) still rendered"


def test_arias_case_offsetting_halves_never_render_at_a_half_magnitude():
    """The reported bug, reduced to the shipped numbers. Arias's standardized
    k_rel is -2.43 and peak_k_rel -3.17 (elite contact on BOTH windows) against
    ridge weights +0.229 / -0.160: the halves are -0.557 and +0.507, so the NET
    read is -0.05, a wash. The old explainer showed the -0.557 half alone as
    'Contact (K%) vs level down 0.56' while the offsetting half fell outside the
    top-4 cut. Grouped, the pair cancels below the display floor and no contact
    claim of any size may reach the card."""
    keys = ["k_rel", "peak_k_rel", "ops_rel", "tool_hit", "level_rank", "age_rel_level"]
    w = [0.229, -0.160, 1.0, 1.0, 1.0, 1.0]
    # the four companion magnitudes are Arias's real served ones (0.96 / 0.67 /
    # 0.58 / 0.47), so the losing half at 0.56 genuinely made the old top-4 cut.
    feats = {"k_rel": -2.43, "peak_k_rel": -3.17,   # z-scores: both well below level
             "ops_rel": 0.96, "tool_hit": 0.67, "level_rank": 0.58, "age_rel_level": 0.47}
    net = w[0] * feats["k_rel"] + w[1] * feats["peak_k_rel"]
    assert abs(net) < 0.05, "fixture no longer reproduces the cancelling contact read"
    rows = es._factors(_ridge(keys, w), feats, top=4, side="hit")
    # NON-VACUITY: the negative half alone outranks an emitted row, so an
    # ungrouped explainer WOULD have surfaced it. If this ever stops holding the
    # fixture has gone toothless and must be rebuilt, not deleted.
    assert abs(w[0] * feats["k_rel"]) > min(r["mag"] for r in rows), \
        "fixture no longer forces the lone half into the top-N cut"
    assert not [r for r in rows if r["label"] in ("Contact (K%) vs level", "Peak K rate")], \
        f"a cancelling contact pair still reached the card: {rows}"


def test_net_positive_contact_reads_up_not_down():
    """Same collinear pair, a player whose net contact read IS positive: the row
    must say 'up'. Guards the sign, not just the suppression."""
    keys = ["k_rel", "peak_k_rel", "ops_rel", "tool_hit"]
    w = [0.229, -0.160, 1.0, 1.0]
    feats = {"k_rel": -1.0, "peak_k_rel": -3.0, "ops_rel": 0.9, "tool_hit": 0.8}
    net = w[0] * feats["k_rel"] + w[1] * feats["peak_k_rel"]
    assert net > 0.05, "fixture no longer reproduces a net-positive contact read"
    rows = es._factors(_ridge(keys, w), feats, top=4, side="hit")
    contact = [r for r in rows if r["label"] == "Contact (K%) vs level"]
    assert contact and contact[0]["dir"] == "up", rows
    assert contact[0]["mag"] == round(net, 2)


def test_pitcher_k_group_is_not_labelled_contact():
    """For an arm a high K% is missing bats, not contact. The grouped row carries
    the pitcher label so the merged chip is not side-wrong copy."""
    keys = _feature_spec("pit")[0]
    ridge = _ridge(keys, [1.0 if k in ("k_rel", "peak_k_rel") else 0.0 for k in keys])
    feats = {k: (2.0 if k in ("k_rel", "peak_k_rel") else 0.0) for k in keys}
    labels = {f["label"] for f in es._factors(ridge, feats, top=4, side="pit")}
    assert "Strikeout rate vs level" in labels
    assert "Contact (K%) vs level" not in labels
    assert "Peak K rate" not in labels


def test_ungraded_and_flagship_share_one_grouping_rule():
    """Both explainer surfaces must collapse the same pairs; a fix on one surface
    that skips the other leaves the bug live on provisional cards."""
    for side in ("hit", "pit"):
        for keys, fn in ((_feature_spec(side)[0], es._factors), (eu._keys(side), eu._factors)):
            ridge = _ridge(keys, [1.0 if k == "k_rel" else (-1.0 if k == "peak_k_rel" else 0.0)
                                  for k in keys])
            feats = {k: 1.0 for k in keys}
            # k_rel +1 and peak_k_rel -1 cancel exactly -> the group must vanish
            rows = fn(ridge, feats, top=len(keys), side=side)
            assert not [r for r in rows
                        if r["label"] in ("Contact (K%) vs level", "Strikeout rate vs level",
                                          "Peak K rate")], rows
