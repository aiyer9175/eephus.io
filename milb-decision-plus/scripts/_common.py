# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Shared constants and helpers for the MiLB Decision+ rebuild pipeline."""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
OUTPUTS = PROJECT_ROOT / "outputs"
REPORTS = PROJECT_ROOT / "reports"

API_BASE = "https://statsapi.mlb.com/api/v1"

# sportId -> level label
SPORT_LEVELS = {
    1: "MLB",
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "CPX",
}
LEVEL_SPORTS = {v: k for k, v in SPORT_LEVELS.items()}
LEVEL_ORDER = {"CPX": 0, "A": 1, "A+": 2, "AA": 3, "AAA": 4, "MLB": 5}

# Pitch call codes (details.code on isPitch events)
SWING_CODES = {"S", "W", "F", "T", "L", "M", "X", "D", "E", "O", "Q", "R", "Y", "Z"}
WHIFF_CODES = {"S", "W", "M", "Q"}
CONTACT_CODES = {"F", "T", "L", "X", "D", "E", "O", "R", "Y", "Z"}
FOUL_CODES = {"F", "T", "L", "O", "R"}
INPLAY_CODES = {"X", "D", "E", "Y", "Z"}
CALLED_STRIKE_CODES = {"C"}
BALL_CODES = {"B", "*B", "P", "I", "H", "V"}  # H = HBP, V = automatic ball

IN_ZONE = set(range(1, 10))       # gameday zones 1-9
OUT_ZONE = {11, 12, 13, 14}

# PA-ending eventTypes that belong to the batter (a real plate appearance).
# Baserunning-only events end a play row without consuming the batter's PA.
NON_PA_EVENT_TYPES = {
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b",
    "pickoff_caught_stealing_home",
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "wild_pitch", "passed_ball", "balk", "other_advance",
    "runner_double_play", "pickoff_error_1b", "pickoff_error_2b",
    "pickoff_error_3b", "error", "defensive_indiff", "other_out",
    "ejection", "injury", "game_advisory",
}

K_EVENT_TYPES = {"strikeout", "strike_out", "strikeout_double_play", "strikeout_triple_play"}
BB_EVENT_TYPES = {"walk", "intent_walk"}
HBP_EVENT_TYPES = {"hit_by_pitch"}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "milb-decision-plus/1.0 (research)"})
    return s


def get_json(session: requests.Session, url: str, params: dict | None = None,
             retries: int = 5, timeout: int = 30) -> dict:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404,):
                return {}
            last_err = RuntimeError(f"HTTP {r.status_code} for {url}")
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(min(30.0, (2 ** attempt) * 0.5 + random.random()))
    raise RuntimeError(f"failed after {retries} retries: {url}: {last_err}")


def log_run(experiment_id: str, **fields) -> None:
    """Append a reproducibility record to the run log."""
    REPORTS.mkdir(parents=True, exist_ok=True)
    rec = {
        "experiment_id": experiment_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "pid": os.getpid(),
        **fields,
    }
    with open(REPORTS / "run_log.jsonl", "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
