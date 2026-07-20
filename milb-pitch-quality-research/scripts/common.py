"""Shared constants and HTTP helpers for the MiLB Stats API pilot pull.

Standard library only -- no third-party dependencies required to run this
pipeline, so it works in any environment with network access and Python 3.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://statsapi.mlb.com"
USER_AGENT = "eephus-milb-pitch-quality-research/0.1 (data audit pilot)"

# sportId mapping, confirmed live against /api/v1/sports before this pipeline
# was written (see PILOT_SCOPE.md).
LEVELS = {
    "AAA": 11,
    "AA": 12,
    "High-A": 13,
    "Low-A": 14,
}

SEASON = 2025

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_CACHE = REPO_ROOT / "data_cache"
REPORTS_DIR = REPO_ROOT / "reports"

DEFAULT_DELAY_SECONDS = 0.4


def get_json(url: str, *, retries: int = 3, backoff: float = 2.0) -> dict:
    """GET a URL and parse JSON, with a small retry/backoff for transient errors."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_err}")


def schedule_url(sport_id: int, season: int = SEASON) -> str:
    return (
        f"{BASE_URL}/api/v1/schedule"
        f"?sportId={sport_id}&season={season}&gameType=R"
        f"&startDate={season}-01-01&endDate={season}-12-31"
    )


def game_feed_url(game_pk: int) -> str:
    return f"{BASE_URL}/api/v1.1/game/{game_pk}/feed/live"


def cache_path(level: str, game_pk: int) -> Path:
    return DATA_CACHE / level / f"{game_pk}.json"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)
