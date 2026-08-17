"""Ablation framework scaffolding (Part AK). Declares families; does not decide membership.

Which families a future pitch-quality model actually uses is explicitly out
of scope for Program 0 -- this only makes per-family ablation mechanically
possible once that's decided.
"""
from __future__ import annotations

FEATURE_FAMILIES = (
    "VELOCITY",
    "MOVEMENT",
    "RELEASE",
    "SPIN",
    "LOCATION",
    "COUNT",
    "SEQUENCE",
    "ARSENAL",
    "PITCHER_IDENTITY",
    "CONTEXT",
)


class UnknownFeatureFamilyError(ValueError):
    pass


def tag_features(mapping: dict[str, str]) -> dict[str, list[str]]:
    """Group {feature_name: family} into {family: [feature_names]}.

    Raises if any family isn't one of FEATURE_FAMILIES -- catches a typo'd
    family name at tagging time instead of silently dropping it from every
    future ablation.
    """
    unknown = {fam for fam in mapping.values() if fam not in FEATURE_FAMILIES}
    if unknown:
        raise UnknownFeatureFamilyError(
            f"Unknown feature families: {sorted(unknown)}. "
            f"Valid families: {FEATURE_FAMILIES}"
        )
    grouped: dict[str, list[str]] = {fam: [] for fam in FEATURE_FAMILIES}
    for feature, family in mapping.items():
        grouped[family].append(feature)
    return grouped


def ablate(feature_list: list[str], mapping: dict[str, str], drop_family: str) -> list[str]:
    """Return feature_list with every feature tagged `drop_family` removed."""
    if drop_family not in FEATURE_FAMILIES:
        raise UnknownFeatureFamilyError(drop_family)
    return [f for f in feature_list if mapping.get(f) != drop_family]
