# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""Collinear-factor grouping for the eFV per-prospect explainer. DISPLAY ONLY.

WHY THIS EXISTS (owner bug, 2026-07-25: "why is Franklin Arias punished for
contact when he has great contact?"). The shipped eFV model is a ridge, and the
hitter feature set carries BOTH k_rel (final-season strikeout rate vs level) and
peak_k_rel (best-season strikeout rate vs level). Those are the same statistic
over two windows and they are strongly collinear on the live board (Pearson
r = +0.76 hitters, +0.68 pitchers, measured on the 2026 live matrices), so the
ridge is free to split them with OPPOSITE signs: it fitted k_rel +0.229 and
peak_k_rel -0.160 (raw weights), which together price the DIFFERENCE between the
current and peak read, not the level of either. The declared monotone direction
in efv_model does not bind the ridge (it constrains the LightGBM challenger
only), so nothing prevents the split.

That is defensible inside the fit. It is indefensible in the explainer, which
reported each ridge term SEPARATELY and then kept only the top-N by absolute
magnitude: for Arias (k_rel -0.088, peak_k_rel -0.127, i.e. elite contact on
BOTH windows) the k_rel term made the cut, its offsetting peak_k_rel partner did
not, and the card told a plus-contact hitter that his contact hurt him.

The rule here: features that measure the SAME underlying statistic over
different windows are ONE explainer factor whose contribution is the SUM of the
member ridge contributions, so the reported direction is the NET direction and a
group is shown or hidden WHOLE (the top-N cut runs on groups, never on halves).

Grouping is declared STRUCTURALLY (what the features measure), not from the
current fitted signs, so it keeps holding after any refit that flips a sign.

DELIBERATELY NOT GROUPED (measured on the same live matrices):
  obp_rel / ops_rel  (r = +0.80 hitters) - collinear but DIFFERENT statistics
      (OPS carries slugging that OBP does not), and the ridge prices both with
      the SAME sign (+0.012 / +0.263), so neither half can misreport the other's
      direction. Two distinct, readable reasons; merging them would destroy
      information instead of restoring it.
  ops_rel / iso_rel  (r = +0.78, provisional hitter set) - same argument.
  k_rel / x_era_k    (r = +0.36 pitchers) - an interaction term, a different
      construct from the rate itself, and well under any collinearity bar.
  age / age_rel_level (r = +0.78 hitters, +0.74 pitchers) - genuinely different
      readings (absolute age vs age relative to the level), same fitted sign on
      hitters; kept separate as two honest reasons.
  is_ifa / is_college (r = -0.76) - both already excluded from the explainer.
"""
from __future__ import annotations

# group id -> (members, side label overrides). The FIRST member is the group's
# primary: the display label defaults to whatever label the calling module
# already used for it, so grouping never silently re-words a shipped chip.
# Overrides exist only where the primary's inherited label is side-wrong.
GROUPS: dict[str, dict] = {
    # strikeout rate vs level, final season + multi-season peak. Shipped in the
    # flagship hitter set, the flagship pitcher set, and BOTH provisional sets.
    # The pitcher override: for an arm a high K% is missing bats, not "contact".
    "k_rate": {"members": ("k_rel", "peak_k_rel"),
               "labels": {"pit": "Strikeout rate vs level"}},
    # walk rate vs level. peak_bb_rel is not in any shipped feature set today
    # (it is only in the label tables); declared so it cannot ship un-grouped.
    "bb_rate": {"members": ("bb_rel", "peak_bb_rel"), "labels": {}},
    # on-base vs level: current + peak. Both ship in the provisional hitter set.
    "obp": {"members": ("obp_rel", "peak_obp_rel"), "labels": {}},
    # OPS / ISO current+peak pairs: peak_ops_rel and peak_iso_rel are labelled
    # but not in a shipped set today; declared for the same reason as bb_rate.
    "ops": {"members": ("ops_rel", "peak_ops_rel"), "labels": {}},
    "iso": {"members": ("iso_rel", "peak_iso_rel"), "labels": {}},
}

# feature key -> group id
GROUP_OF: dict[str, str] = {m: gid for gid, g in GROUPS.items() for m in g["members"]}


def group_id(feature_key: str) -> str | None:
    """The collinear group a model feature belongs to, or None if it stands alone."""
    return GROUP_OF.get(feature_key)


def display_label(display_key: str, side: str, label_of) -> str:
    """Label for one explainer row. `display_key` is either a group id or a bare
    feature key; `label_of` is the calling module's own feature -> label lookup
    (so each surface keeps its own established copy)."""
    g = GROUPS.get(display_key)
    if g is None:
        return label_of(display_key)
    override = (g.get("labels") or {}).get(side)
    return override if override else label_of(g["members"][0])


def collapse(contributions, side: str, label_of, min_mag: float = 0.05, top: int | None = None):
    """Collinear-aware explainer rows.

    `contributions` is an iterable of (feature_key, signed_contribution) in model
    key order. Members of a declared group are SUMMED into one row before the
    magnitude floor and the top-N cut are applied, so:
      * the reported direction is the NET direction of the group, and
      * a group is emitted whole or not at all (no half of a collinear pair can
        reach the card on its own, which was the Arias defect).
    Returns [{label, dir, mag}], largest magnitude first, ties broken by first
    appearance in model key order (deterministic across runs).
    """
    net: dict[str, float] = {}
    for k, c in contributions:
        dk = GROUP_OF.get(k, k)
        net[dk] = net.get(dk, 0.0) + c
    rows = [(dk, c) for dk, c in net.items() if abs(c) >= min_mag]
    rows.sort(key=lambda kc: -abs(kc[1]))
    if top is not None:
        rows = rows[:top]
    return [{"label": display_label(dk, side, label_of),
             "dir": "up" if c > 0 else "down", "mag": round(abs(c), 2)}
            for dk, c in rows]
