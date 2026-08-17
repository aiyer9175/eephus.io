from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def clustered_df() -> pd.DataFrame:
    """20 'pitchers' x 15 'pitches' each, with a real feature/target relationship, for split/leakage tests."""
    rng = np.random.default_rng(42)
    n_pitchers = 20
    n_per_pitcher = 15
    pitcher_id = np.repeat(np.arange(n_pitchers), n_per_pitcher)
    game_id = np.repeat(np.arange(n_pitchers * 3), n_per_pitcher // 3 + 1)[: len(pitcher_id)]
    velocity = rng.normal(93, 3, size=len(pitcher_id))
    date = pd.to_datetime("2026-04-01") + pd.to_timedelta(
        np.repeat(np.arange(n_pitchers), n_per_pitcher) * 3, unit="D"
    )
    outcome = 0.3 * velocity + rng.normal(0, 1, size=len(pitcher_id))
    pitch_id = np.arange(len(pitcher_id))
    return pd.DataFrame(
        {
            "pitch_id": pitch_id,
            "pitcher_id": pitcher_id,
            "game_id": game_id,
            "date": date,
            "velocity": velocity,
            "outcome": outcome,
        }
    )
