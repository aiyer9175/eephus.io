# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Publication schema + provenance contracts for Advancement Pace+ (descriptive only)."""

import re

import numpy as np
import pandas as pd

STAT_TYPE = "descriptive"
MODEL_ELIGIBLE = False

PUBLIC_SCHEMA = [
    "player_id", "season", "as_of_date",
    "advancement_pace_plus", "advancement_percentile",
    "raw_advancement_pace", "expected_peer_pace", "advancement_residual",
    "sample_quality", "active_pro_seasons", "meaningful_assignments",
    "meaningful_promotions", "starting_level", "current_level",
    "position_group", "entry_pathway", "reference_population",
    "methodology_version", "data_version", "generated_at",
    "stat_type", "model_eligible",
]

# names that could be mistaken for model features / predictive quantities
FORBIDDEN_COLUMN_NAMES = {"velocity", "development_score", "future_value",
                          "development_velocity", "readiness", "opportunity",
                          "p_reach", "xwar", "xfv", "efv", "ewar", "eowar"}

SAMPLE_TIERS = {"Insufficient", "Early", "Developing", "Established"}
LEVELS = {"Rk", "A", "A+", "AA", "AAA"}


def validate_public(df: pd.DataFrame) -> list:
    """Return a list of contract violations (empty list = artifact passes)."""
    errs = []
    missing = [c for c in PUBLIC_SCHEMA if c not in df.columns]
    if missing:
        errs.append(f"missing columns: {missing}")
    extra_forbidden = FORBIDDEN_COLUMN_NAMES & {c.lower() for c in df.columns}
    if extra_forbidden:
        errs.append(f"forbidden ambiguous column names present: {extra_forbidden}")
    if missing:
        return errs

    if df.duplicated(["player_id", "season"]).any():
        errs.append("duplicate player_id x season rows")
    if df.player_id.isna().any() or df.season.isna().any():
        errs.append("null player_id or season")
    if not (df.stat_type == STAT_TYPE).all():
        errs.append("stat_type must be 'descriptive' on every row")
    if not (df.model_eligible == MODEL_ELIGIBLE).all():
        errs.append("model_eligible must be False on every row")
    if not df.methodology_version.map(
            lambda v: bool(re.fullmatch(r"\d+\.\d+\.\d+", str(v)))).all():
        errs.append("methodology_version must be semver")

    ap = df.advancement_pace_plus.dropna()
    if len(ap) and not ap.between(70, 130).all():
        errs.append("public advancement_pace_plus outside display cap 70-130")
    pct = df.advancement_percentile.dropna()
    if len(pct) and not pct.between(0, 100).all():
        errs.append("advancement_percentile outside 0-100")
    if not set(df.sample_quality.dropna()) <= SAMPLE_TIERS:
        errs.append("unknown sample_quality tier")
    if not set(df.starting_level.dropna()) <= LEVELS or not set(df.current_level.dropna()) <= LEVELS:
        errs.append("unknown level code")
    scored = df.advancement_pace_plus.notna()
    if (df.loc[scored, "sample_quality"] == "Insufficient").any():
        errs.append("Insufficient-tier rows must not carry a public score")
    return errs
