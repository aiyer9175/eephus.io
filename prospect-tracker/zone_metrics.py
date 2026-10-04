# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Approximate MiLB hitter zone metrics from MLB Stats API pitch feeds.

This is an experimental implementation of the workflow described by Thomas
Nestico's MLB zone-classification project:

1. Train a zone classifier on MLB pitches that expose both Gameday pixel
   coordinates (x/y) and official zone labels.
2. Apply the classifier to MiLB pitch rows using only Gameday x/y plus the
   batter-specific strike-zone top/bottom.
3. Aggregate hitter zone metrics and compare against MiLB feed zone labels
   when they are available, which gives us an accuracy check for AAA.
"""

from __future__ import annotations

import argparse
import bisect
import concurrent.futures
import csv
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import feed_cache

if TYPE_CHECKING:
    from sklearn.ensemble import RandomForestClassifier


MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
MLB_GAME_FEED_API = "https://statsapi.mlb.com/api/v1.1/game"
CACHE_DIR = Path(__file__).parent / ".cache" / "zone_metrics"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

IN_ZONE = {1, 2, 3, 4, 5, 6, 7, 8, 9}
OUT_ZONE = {11, 12, 13, 14}
# v20 — MLB added so debuted prospects with both AAA + MLB experience
# get level_splits for both. The pixel-coordinate zone classifier was
# trained on MLB pitches in the first place, so applying it to MLB
# games is more accurate than the MiLB approximation. Frontend already
# iterates level_splits with per-level chips, so adding MLB here
# surfaces it automatically on the player detail page once the
# pipeline re-runs.
ZONE_LEVELS = ("MLB", "AAA", "AA", "A+", "A", "CPX")
SPORT_LEVELS = {
    1: "MLB",
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "CPX",
    17: "DSL",
}
PERCENTILE_MIN_PITCHES = 100
HITTER_PERCENTILE_METRICS = {
    "zone_rate": True,
    "z_swing_pct": True,
    "o_swing_pct": False,
    "z_contact_pct": True,
    "o_contact_pct": True,
    "overall_contact_pct": True,
    "whiff_pct": False,
}
PITCHER_PERCENTILE_METRICS = {
    "zone_rate": True,
    "z_swing_pct": False,
    "o_swing_pct": True,
    "z_contact_pct": False,
    "o_contact_pct": False,
    "overall_contact_pct": False,
    "whiff_pct": True,
}
SWING_CODES = {
    "S",   # swinging strike
    "W",   # swinging strike, blocked
    "F",   # foul
    "T",   # foul tip
    "L",   # foul bunt
    "M",   # missed bunt
    "X",   # in play
    "D",   # in play, no out
    "E",   # in play, runs
}
WHIFF_CODES = {"S", "W", "M"}
TAKEN_IN_ZONE_CODES = {"C"}
TAKEN_OUT_ZONE_CODES = {"B", "I", "H"}
CPX_PSEUDO_ZONE_MIN_TAKES = 80
# Rows per predict call when the bulk fetcher labels every split in one
# pass per model. Each forest thread holds a (rows x classes) float64
# block for its tree, so a 6M-row batch on 32 threads would need tens of
# GB; 200k rows keeps that under 1 GB while cutting thousands of calls
# to a few dozen. Prediction is row-independent, so the chunk size never
# changes a label.
PREDICT_CHUNK_ROWS = 200_000


SESSION = requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)


@dataclass
class PitchRow:
    game_pk: int
    batter_id: int
    batter_name: str
    pitcher_id: int
    pitcher_name: str
    pitch_x_gameday: float
    pitch_y_gameday: float
    k_zone_top: float
    k_zone_bot: float
    actual_zone: int | None
    call_code: str

    @property
    def features(self) -> list[float]:
        return [
            self.pitch_x_gameday,
            self.pitch_y_gameday,
            self.k_zone_top,
            self.k_zone_bot,
        ]


@dataclass
class ZoneMetricRow:
    player_key: str | None
    player_name: str
    mlbam_id: int
    season: int
    level: str
    is_pitcher: bool
    leagues: list[str]
    games: int
    pitches: int
    actual_zone_accuracy: float | None
    actual_in_zone_accuracy: float | None
    zone_rate: float | None
    z_swing_pct: float | None
    o_swing_pct: float | None
    z_contact_pct: float | None
    o_contact_pct: float | None
    overall_contact_pct: float | None
    whiff_pct: float | None
    actual_zone_rate: float | None
    actual_z_swing_pct: float | None
    actual_o_swing_pct: float | None
    actual_z_contact_pct: float | None
    actual_o_contact_pct: float | None
    source: str
    fetched_at: str
    qualified: bool = False
    percentile_sample_size: int | None = None
    qualifier_min_pitches: int = PERCENTILE_MIN_PITCHES
    percentiles: dict[str, float] = field(default_factory=dict)
    level_splits: list[dict] = field(default_factory=list)


def _get_json(url: str, params: dict | None = None, ttl_seconds: int = 7 * 86400) -> dict:
    key = requests.Request("GET", url, params=params).prepare().url or url
    safe = hashlib.md5(key.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds:
        return json.loads(path.read_text(encoding="utf-8"))
    time.sleep(0.05)
    resp = SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def player_id_for_name(name: str) -> int:
    data = _get_json(
        f"{MLB_STATS_API}/people/search",
        {"names": name, "sportIds": "1,11,12,13,14"},
    )
    people = data.get("people", [])
    if not people:
        raise ValueError(f"No MLBAM match for {name!r}")
    return int(people[0]["id"])


def game_log(player_id: int, season: int, level: str = "AAA", is_pitcher: bool = False) -> list[dict]:
    return [
        split for split in all_game_logs(player_id, season, is_pitcher=is_pitcher)
        if (split.get("sport") or {}).get("abbreviation") == level
    ]


def all_game_logs(player_id: int, season: int, is_pitcher: bool = False) -> list[dict]:
    group = "pitching" if is_pitcher else "hitting"
    base_params = {
        "stats": "gameLog",
        "group": group,
        "season": str(season),
    }
    # The Stats API does not reliably expose MLB + MiLB game logs through a
    # single query for players who moved levels. Merge all known shapes.
    param_sets = [
        base_params | {"leagueListId": "mlb_milb"},
        base_params | {"leagueListId": "milb_full"},
        base_params,
    ]
    out: list[dict] = []
    seen: set[tuple] = set()
    for params in param_sets:
        try:
            data = _get_json(
                f"{MLB_STATS_API}/people/{player_id}/stats",
                params,
                ttl_seconds=86400,
            )
        except Exception:
            continue
        for block in data.get("stats") or []:
            for split in block.get("splits", []) or []:
                game_pk = (split.get("game") or {}).get("gamePk")
                level = _normalized_game_log_level(split)
                date_value = split.get("date")
                key = (game_pk, level, date_value)
                if key in seen:
                    continue
                seen.add(key)
                split.setdefault("sport", {})["abbreviation"] = level
                out.append(split)
    for sport_id, fallback_level in SPORT_LEVELS.items():
        if fallback_level not in ZONE_LEVELS:
            continue
        try:
            data = _get_json(
                f"{MLB_STATS_API}/people/{player_id}",
                {
                    "hydrate": (
                        f"stats(group={group},type=gameLog,season={season},"
                        f"sportId={sport_id},gameType=[R]),hydrations"
                    )
                },
                ttl_seconds=86400,
            )
        except Exception:
            continue
        people = data.get("people") or []
        stats = (people[0].get("stats") or []) if people else []
        for block in stats:
            for split in block.get("splits", []) or []:
                game_pk = (split.get("game") or {}).get("gamePk")
                level = _normalized_game_log_level(split, fallback_level)
                date_value = split.get("date")
                key = (game_pk, level, date_value)
                if key in seen:
                    continue
                seen.add(key)
                split.setdefault("sport", {})["abbreviation"] = level
                out.append(split)
    return out


def _normalized_game_log_level(split: dict, fallback_level: str | None = None) -> str | None:
    league_name = ((split.get("league") or {}).get("name") or "").lower()
    raw = (split.get("sport") or {}).get("abbreviation") or fallback_level
    if raw == "ROK":
        if "complex" in league_name or "arizona" in league_name or "florida" in league_name:
            return "CPX"
    return raw


def mlb_game_pks(season: int, limit: int, start_date: str | None = None) -> list[int]:
    """Return MLB regular-season gamePks, walking backward from start_date."""
    start = date.fromisoformat(start_date) if start_date else date(season, 5, 15)
    pks: list[int] = []
    current = start
    while len(pks) < limit and current >= date(season, 3, 1):
        data = _get_json(
            f"{MLB_STATS_API}/schedule",
            {
                "sportId": "1",
                "date": current.isoformat(),
                "gameTypes": "R",
            },
            ttl_seconds=86400,
        )
        for day in data.get("dates", []):
            for game in day.get("games", []):
                status = (game.get("status") or {}).get("detailedState", "")
                if status in {"Final", "Completed Early"}:
                    pks.append(int(game["gamePk"]))
                    if len(pks) >= limit:
                        return pks
        current -= timedelta(days=1)
    return pks


def pitches_from_game(
    game_pk: int,
    batter_ids: set[int] | None = None,
    pitcher_ids: set[int] | None = None,
    game_date: str | None = None,
) -> list[PitchRow]:
    # Shared, game_pk-keyed cache (deduped against statcast et al). game_date
    # lets completed games be cached permanently; omit it (callers without a
    # date in scope) and it falls back to the safe 24h TTL.
    data = feed_cache.get_game_feed(game_pk, game_date=game_date)
    rows: list[PitchRow] = []
    for play in data.get("liveData", {}).get("plays", {}).get("allPlays", []):
        matchup = play.get("matchup") or {}
        batter = matchup.get("batter") or {}
        pitcher = matchup.get("pitcher") or {}
        batter_id = batter.get("id")
        pitcher_id = pitcher.get("id")
        if not batter_id or not pitcher_id:
            continue
        batter_id = int(batter_id)
        pitcher_id = int(pitcher_id)
        batter_match = batter_ids is not None and batter_id in batter_ids
        pitcher_match = pitcher_ids is not None and pitcher_id in pitcher_ids
        if batter_ids is not None or pitcher_ids is not None:
            if not (batter_match or pitcher_match):
                continue
        elif not batter_id:
            continue
        for event in play.get("playEvents", []):
            if not event.get("isPitch"):
                continue
            pitch_data = event.get("pitchData") or {}
            coords = pitch_data.get("coordinates") or {}
            try:
                rows.append(
                    PitchRow(
                        game_pk=game_pk,
                        batter_id=batter_id,
                        batter_name=batter.get("fullName") or "",
                        pitcher_id=pitcher_id,
                        pitcher_name=pitcher.get("fullName") or "",
                        pitch_x_gameday=float(coords["x"]),
                        pitch_y_gameday=float(coords["y"]),
                        k_zone_top=float(pitch_data["strikeZoneTop"]),
                        k_zone_bot=float(pitch_data["strikeZoneBottom"]),
                        actual_zone=(
                            int(pitch_data["zone"])
                            if pitch_data.get("zone") not in (None, "")
                            else None
                        ),
                        call_code=(event.get("details") or {}).get("code") or "",
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def train_zone_classifier(season: int, train_games: int, start_date: str | None = None) -> "RandomForestClassifier":
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required for zone classifier training. "
            "Install prospect-tracker/requirements.txt or run with the project Python environment."
        ) from exc

    pks = mlb_game_pks(season, train_games, start_date)
    rows: list[PitchRow] = []
    for pk in pks:
        rows.extend(p for p in pitches_from_game(pk) if p.actual_zone in IN_ZONE | OUT_ZONE)
    if len(rows) < 500:
        raise RuntimeError(f"Only found {len(rows)} MLB training pitches; need a larger sample")
    clf = RandomForestClassifier(
        n_estimators=250,
        max_depth=14,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    clf.fit([r.features for r in rows], [r.actual_zone for r in rows])
    return clf


def _rate(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def _metric_set(rows: list[tuple[PitchRow, int | None]], use_predicted: bool) -> dict:
    zone_values = []
    swings = []
    contacts = []
    for pitch, predicted_zone in rows:
        zone = predicted_zone if use_predicted else pitch.actual_zone
        if zone not in IN_ZONE | OUT_ZONE:
            continue
        is_zone = zone in IN_ZONE
        is_swing = pitch.call_code in SWING_CODES
        is_whiff = pitch.call_code in WHIFF_CODES
        zone_values.append(is_zone)
        swings.append((is_zone, is_swing, is_whiff))
        contacts.append(is_swing and not is_whiff)

    z_pitches = sum(zone_values)
    o_pitches = len(zone_values) - z_pitches
    z_swings = sum(1 for is_zone, is_swing, _ in swings if is_zone and is_swing)
    o_swings = sum(1 for is_zone, is_swing, _ in swings if not is_zone and is_swing)
    z_contacts = sum(
        1 for is_zone, is_swing, is_whiff in swings if is_zone and is_swing and not is_whiff
    )
    o_contacts = sum(
        1 for is_zone, is_swing, is_whiff in swings if not is_zone and is_swing and not is_whiff
    )
    all_swings = sum(1 for _, is_swing, _ in swings if is_swing)
    all_whiffs = sum(1 for _, is_swing, is_whiff in swings if is_swing and is_whiff)
    return {
        "zone_rate": _rate(z_pitches, len(zone_values)),
        "z_swing_pct": _rate(z_swings, z_pitches),
        "o_swing_pct": _rate(o_swings, o_pitches),
        "z_contact_pct": _rate(z_contacts, z_swings),
        "o_contact_pct": _rate(o_contacts, o_swings),
        "overall_contact_pct": _rate(all_swings - all_whiffs, all_swings),
        "whiff_pct": _rate(all_whiffs, all_swings),
    }


def _train_taken_pitch_zone_model(
    rows: list[PitchRow],
    *,
    min_samples: int = CPX_PSEUDO_ZONE_MIN_TAKES,
) -> "RandomForestClassifier | None":
    """Fit a CPX in/out-zone model from called strikes and called balls.

    CPX feeds expose Gameday pitch coordinates but often omit official
    `pitchData.zone`. Their coordinate scale also differs from MLB, so the
    MLB-trained classifier can classify every pitch as out of zone. Taken
    pitches give us same-feed labels: called strikes are in-zone, called balls
    are out-zone.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        return None

    labeled: list[tuple[PitchRow, int]] = []
    for row in rows:
        if row.actual_zone in IN_ZONE | OUT_ZONE:
            continue
        if row.call_code in TAKEN_IN_ZONE_CODES:
            labeled.append((row, 1))
        elif row.call_code in TAKEN_OUT_ZONE_CODES:
            labeled.append((row, 0))

    labels = [label for _row, label in labeled]
    if len(labeled) < min_samples or len(set(labels)) < 2:
        return None

    clf = RandomForestClassifier(
        n_estimators=150,
        max_depth=8,
        min_samples_leaf=4,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    clf.fit([row.features for row, _label in labeled], labels)
    return clf


def _predict_zone_ids(
    rows: list[PitchRow],
    clf: "RandomForestClassifier",
    *,
    taken_pitch_model: "RandomForestClassifier | None" = None,
) -> list[int]:
    if not rows:
        return []
    if taken_pitch_model is not None:
        return [5 if int(label) == 1 else 14 for label in taken_pitch_model.predict([r.features for r in rows])]
    return [int(z) for z in clf.predict([r.features for r in rows])]


def _zone_labels(model: object, features: list[list[float]], is_taken_pitch: bool) -> list[int]:
    """Map one model's predictions to zone ids exactly as `_predict_zone_ids` does."""
    labels = model.predict(features)
    if is_taken_pitch:
        return [5 if int(label) == 1 else 14 for label in labels]
    return [int(z) for z in labels]


def _predict_zone_ids_by_split(
    pitches_by_split: dict[tuple[str, str, bool], list[PitchRow]],
    clf: "RandomForestClassifier",
    taken_pitch_models: dict[str, "RandomForestClassifier | None"],
    *,
    chunk_rows: int = PREDICT_CHUNK_ROWS,
) -> dict[tuple[str, str, bool], list[int]]:
    """Label every split's pitches with one predict pass per model.

    Equivalent to calling `_predict_zone_ids` once per split: a split at a
    level with a taken-pitch model is labelled by that model (1 -> zone 5,
    else 14), every other split by `clf`. Random forest prediction is
    row-independent, so the rows of every split that shares a model are
    stacked in split order with the same feature columns, predicted in
    chunks of `chunk_rows`, and the labels are sliced back by offset. The
    per-split variant pays a thread-pool spin-up per call; thousands of
    (player, level) splits made that the long pole of the monthly step.
    """
    groups: list[tuple[object, bool, list[tuple[tuple[str, str, bool], list[PitchRow]]]]] = []
    group_by_model: dict[int, int] = {}
    for split_key, rows in pitches_by_split.items():
        if not rows:
            continue
        taken_pitch_model = taken_pitch_models.get(split_key[1])
        model = taken_pitch_model if taken_pitch_model is not None else clf
        idx = group_by_model.get(id(model))
        if idx is None:
            idx = group_by_model[id(model)] = len(groups)
            groups.append((model, taken_pitch_model is not None, []))
        groups[idx][2].append((split_key, rows))

    out: dict[tuple[str, str, bool], list[int]] = {}
    chunk_rows = max(1, int(chunk_rows))
    for model, is_taken_pitch, members in groups:
        flat: list[int] = []
        pending: list[list[float]] = []
        for _split_key, rows in members:
            for row in rows:
                pending.append(row.features)
                if len(pending) >= chunk_rows:
                    flat.extend(_zone_labels(model, pending, is_taken_pitch))
                    pending = []
        if pending:
            flat.extend(_zone_labels(model, pending, is_taken_pitch))

        offset = 0
        for split_key, rows in members:
            out[split_key] = flat[offset:offset + len(rows)]
            offset += len(rows)
    return out


def _build_metric_row(
    *,
    player_key: str | None,
    player_name: str,
    mlbam_id: int,
    season: int,
    level: str,
    is_pitcher: bool,
    leagues: list[str],
    games: int,
    rows: list[PitchRow],
    predicted: list[int],
    source: str = "mlb_stats_api_gameday_rf",
) -> ZoneMetricRow:
    pairs = list(zip(rows, predicted))
    pred_metrics = _metric_set(pairs, use_predicted=True)
    actual_metrics = _metric_set(pairs, use_predicted=False)
    display_metrics = {
        key: actual_metrics.get(key) if actual_metrics.get(key) is not None else pred_metrics.get(key)
        for key in pred_metrics
    }
    labeled = [(r, p) for r, p in pairs if r.actual_zone in IN_ZONE | OUT_ZONE]
    zone_acc = _rate(sum(1 for r, p in labeled if r.actual_zone == p), len(labeled))
    in_zone_acc = _rate(
        sum(1 for r, p in labeled if (r.actual_zone in IN_ZONE) == (p in IN_ZONE)),
        len(labeled),
    )
    return ZoneMetricRow(
        player_key=player_key,
        player_name=player_name,
        mlbam_id=mlbam_id,
        season=season,
        level=level,
        is_pitcher=is_pitcher,
        leagues=leagues,
        games=games,
        pitches=len(rows),
        actual_zone_accuracy=zone_acc,
        actual_in_zone_accuracy=in_zone_acc,
        actual_zone_rate=actual_metrics["zone_rate"],
        actual_z_swing_pct=actual_metrics["z_swing_pct"],
        actual_o_swing_pct=actual_metrics["o_swing_pct"],
        actual_z_contact_pct=actual_metrics["z_contact_pct"],
        actual_o_contact_pct=actual_metrics["o_contact_pct"],
        source=source,
        fetched_at=date.today().isoformat(),
        qualified=len(rows) >= PERCENTILE_MIN_PITCHES,
        percentile_sample_size=None,
        qualifier_min_pitches=PERCENTILE_MIN_PITCHES,
        percentiles={},
        level_splits=[],
        **display_metrics,
    )


def player_zone_metrics(
    player_name: str,
    player_id: int,
    season: int,
    clf: "RandomForestClassifier",
    level: str = "AAA",
    player_key: str | None = None,
    is_pitcher: bool = False,
) -> ZoneMetricRow:
    logs = game_log(player_id, season, level, is_pitcher=is_pitcher)
    game_pks = [int(s["game"]["gamePk"]) for s in logs if s.get("game", {}).get("gamePk")]
    date_by_pk = {int(s["game"]["gamePk"]): s.get("date")
                  for s in logs if s.get("game", {}).get("gamePk")}
    leagues = sorted({(s.get("league") or {}).get("name") for s in logs if (s.get("league") or {}).get("name")})
    rows: list[PitchRow] = []
    for pk in game_pks:
        if is_pitcher:
            rows.extend(pitches_from_game(pk, pitcher_ids={player_id}, game_date=date_by_pk.get(pk)))
        else:
            rows.extend(pitches_from_game(pk, batter_ids={player_id}, game_date=date_by_pk.get(pk)))
    taken_pitch_model = _train_taken_pitch_zone_model(rows) if level == "CPX" else None
    predicted = _predict_zone_ids(rows, clf, taken_pitch_model=taken_pitch_model)
    source = "mlb_stats_api_cpx_taken_pitch_rf" if taken_pitch_model is not None else "mlb_stats_api_gameday_rf"
    return _build_metric_row(
        player_key=player_key,
        player_name=player_name,
        mlbam_id=player_id,
        season=season,
        level=level,
        is_pitcher=is_pitcher,
        leagues=leagues,
        games=len(game_pks),
        rows=rows,
        predicted=predicted,
        source=source,
    )


def fetch_zone_metrics_for_players(
    players: Iterable[tuple[str, str, int, str | None, bool]],
    season: int,
    levels: Iterable[str] = ZONE_LEVELS,
    train_games: int = 30,
    train_start_date: str | None = None,
) -> dict[str, ZoneMetricRow]:
    """Fetch estimated zone metrics for many tracked hitters.

    `players` tuples are `(player_key, player_name, mlbam_id, level, is_pitcher)`.
    Missing ids are skipped.
    """
    eligible_levels = set(levels)
    eligible = [
        (key, name, int(mlbam_id), level, bool(is_pitcher))
        for key, name, mlbam_id, level, is_pitcher in players
        if mlbam_id is not None
    ]
    if not eligible:
        return {}
    clf = train_zone_classifier(season, train_games, train_start_date)
    return fetch_zone_metrics_for_players_with_model(eligible, season, clf, levels=eligible_levels)


def fetch_zone_metrics_for_players_with_model(
    eligible: Iterable[tuple[str, str, int, str, bool]],
    season: int,
    clf: "RandomForestClassifier",
    levels: Iterable[str] = ZONE_LEVELS,
    max_workers: int = 16,
) -> dict[str, ZoneMetricRow]:
    """Bulk version that dedupes game-feed fetches across players."""
    eligible = list(eligible)
    allowed_levels = set(levels)
    logs_by_key: dict[str, list[dict]] = {}
    meta_by_key: dict[str, tuple[str, int, str, bool]] = {}

    def fetch_logs(item: tuple[str, str, int, str, bool]) -> tuple[str, list[dict]]:
        key, _name, mlbam_id, _level, is_pitcher = item
        try:
            return key, all_game_logs(mlbam_id, season, is_pitcher=is_pitcher)
        except Exception:
            return key, []

    workers = max(1, min(max_workers, len(eligible))) if eligible else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for key, logs in ex.map(fetch_logs, eligible):
            logs_by_key[key] = logs

    game_to_batters: dict[int, set[int]] = {}
    game_to_pitchers: dict[int, set[int]] = {}
    game_date_by_pk: dict[int, str] = {}
    game_to_player_levels: dict[int, set[tuple[str, str, bool]]] = {}
    leagues_by_split: dict[tuple[str, str, bool], set[str]] = {}
    games_by_split: dict[tuple[str, str, bool], set[int]] = {}
    current_level_by_key: dict[str, str | None] = {}
    for key, name, mlbam_id, level, is_pitcher in eligible:
        meta_by_key[key] = (name, mlbam_id, level, is_pitcher)
        current_level_by_key[key] = level
        for split in logs_by_key.get(key, []):
            split_level = (split.get("sport") or {}).get("abbreviation")
            if split_level not in allowed_levels:
                continue
            game_pk = (split.get("game") or {}).get("gamePk")
            if not game_pk:
                continue
            game_pk = int(game_pk)
            gd = split.get("date")
            if gd and game_pk not in game_date_by_pk:
                game_date_by_pk[game_pk] = gd
            if is_pitcher:
                game_to_pitchers.setdefault(game_pk, set()).add(mlbam_id)
            else:
                game_to_batters.setdefault(game_pk, set()).add(mlbam_id)
            game_to_player_levels.setdefault(game_pk, set()).add((key, split_level, is_pitcher))
            games_by_split.setdefault((key, split_level, is_pitcher), set()).add(game_pk)
            league_name = (split.get("league") or {}).get("name")
            if league_name:
                leagues_by_split.setdefault((key, split_level, is_pitcher), set()).add(league_name)

    pitches_by_split: dict[tuple[str, str, bool], list[PitchRow]] = {}

    def fetch_game_rows(game_pk: int) -> tuple[int, list[PitchRow]]:
        try:
            return game_pk, pitches_from_game(
                game_pk,
                batter_ids=game_to_batters.get(game_pk),
                pitcher_ids=game_to_pitchers.get(game_pk),
                game_date=game_date_by_pk.get(game_pk),
            )
        except Exception:
            return game_pk, []

    game_pks = sorted(set(game_to_batters) | set(game_to_pitchers))
    # v19 — Per-batch progress logging so this step doesn't go silent
    # when the cache is cold. Each game-feed fetch is sequential per
    # worker (MLB API doesn't batch), so a 3000-game cohort can run
    # several minutes without any signal of life. Logs every 200 games.
    import logging, time as _time
    _log = logging.getLogger(__name__)
    _zone_start = _time.monotonic()
    _zone_done = 0
    _ZONE_PROGRESS_EVERY = 200
    if game_pks:
        workers = max(1, min(max_workers, len(game_pks)))
        _log.info("zone metrics: fetching %d game feeds (%d workers)",
                  len(game_pks), workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for game_pk, rows in ex.map(fetch_game_rows, game_pks):
                _zone_done += 1
                if _zone_done % _ZONE_PROGRESS_EVERY == 0 or _zone_done == len(game_pks):
                    elapsed = _time.monotonic() - _zone_start
                    rate = _zone_done / max(elapsed, 0.001)
                    remaining = len(game_pks) - _zone_done
                    eta = remaining / rate if rate > 0 else 0
                    _log.info(
                        "zone metrics: %d/%d game feeds done · %.0fs elapsed · ~%.0fs left",
                        _zone_done, len(game_pks), elapsed, eta,
                    )
                player_levels = game_to_player_levels.get(game_pk, set())
                for row in rows:
                    for key, split_level, is_pitcher in player_levels:
                        _name, mlbam_id, _level, _is_pitcher = meta_by_key[key]
                        matched = row.pitcher_id == mlbam_id if is_pitcher else row.batter_id == mlbam_id
                        if matched:
                            pitches_by_split.setdefault((key, split_level, is_pitcher), []).append(row)

    taken_pitch_models: dict[str, RandomForestClassifier | None] = {}
    for level in allowed_levels:
        if level != "CPX":
            continue
        level_rows: list[PitchRow] = []
        for (_key, split_level, _is_pitcher), rows in pitches_by_split.items():
            if split_level == level:
                level_rows.extend(rows)
        taken_pitch_models[level] = _train_taken_pitch_zone_model(level_rows)

    # One predict pass per model (the MLB classifier, the CPX taken-pitch
    # model) instead of one call per split; labels are identical.
    predicted_by_split = _predict_zone_ids_by_split(pitches_by_split, clf, taken_pitch_models)

    split_rows: dict[tuple[str, str, bool], ZoneMetricRow] = {}
    for (key, level, is_pitcher), rows in pitches_by_split.items():
        if not rows:
            continue
        name, mlbam_id, _current_level, _is_pitcher = meta_by_key[key]
        taken_pitch_model = taken_pitch_models.get(level)
        predicted = predicted_by_split[(key, level, is_pitcher)]
        split_rows[(key, level, is_pitcher)] = _build_metric_row(
            player_key=key,
            player_name=name,
            mlbam_id=mlbam_id,
            season=season,
            level=level,
            is_pitcher=is_pitcher,
            leagues=sorted(leagues_by_split.get((key, level, is_pitcher), set())),
            games=len(games_by_split.get((key, level, is_pitcher), set())),
            rows=rows,
            predicted=predicted,
            source=(
                "mlb_stats_api_cpx_taken_pitch_rf"
                if taken_pitch_model is not None
                else "mlb_stats_api_gameday_rf"
            ),
        )

    _attach_level_percentiles(split_rows)

    out: dict[str, ZoneMetricRow] = {}
    by_key: dict[str, list[ZoneMetricRow]] = {}
    for (key, _level, _is_pitcher), row in split_rows.items():
        by_key.setdefault(key, []).append(row)
    for key, rows in by_key.items():
        current_level = current_level_by_key.get(key)
        rows.sort(key=lambda r: (r.level != current_level, -r.pitches))
        primary = rows[0]
        primary.level_splits = [
            asdict(row) | {"level_splits": []}
            for row in sorted(rows, key=lambda r: (ZONE_LEVELS.index(r.level), -r.pitches))
        ]
        out[key] = primary
    return out


def _sorted_peers(values: list[float]) -> list[float] | None:
    """A sorted copy of a cohort's peer values for _percentile_rank, or None when
    a NaN is among them (its order is undefined, so the linear count stays the
    source of truth for that cohort)."""
    if any(v != v for v in values):
        return None
    return sorted(values)


def _percentile_rank(value: float, values: list[float], higher_is_better: bool,
                     sorted_values: list[float] | None = None) -> float:
    """Share of peers at or below the value (higher is better) or at or above it,
    in percent to one decimal. With `sorted_values` (from _sorted_peers) the count
    comes from bisect: bisect_right counts the peers <= value and n - bisect_left
    the peers >= value, the same integers the pass produced."""
    n = len(values)
    if not n:
        return 0.0
    if sorted_values is not None and value == value:
        if higher_is_better:
            better_or_equal = bisect.bisect_right(sorted_values, value)
        else:
            better_or_equal = n - bisect.bisect_left(sorted_values, value)
    elif higher_is_better:
        better_or_equal = sum(1 for v in values if v <= value)
    else:
        better_or_equal = sum(1 for v in values if v >= value)
    return round(100.0 * better_or_equal / n, 1)


def _attach_level_percentiles(rows: dict[tuple[str, str], ZoneMetricRow]) -> None:
    by_level_side: dict[tuple[str, bool], list[ZoneMetricRow]] = {}
    for row in rows.values():
        if row.pitches >= PERCENTILE_MIN_PITCHES:
            by_level_side.setdefault((row.level, row.is_pitcher), []).append(row)
    for (_level, is_pitcher), level_rows in by_level_side.items():
        n = len(level_rows)
        metric_directions = PITCHER_PERCENTILE_METRICS if is_pitcher else HITTER_PERCENTILE_METRICS
        # The peer list depends on (cohort, metric) only, never on the row being
        # ranked, so it is built once per cohort instead of once per row.
        peers: dict[str, tuple[list[float], list[float] | None]] = {}
        for metric in metric_directions:
            vals = [v for v in (getattr(peer, metric) for peer in level_rows) if v is not None]
            peers[metric] = (vals, _sorted_peers(vals))
        for row in level_rows:
            row.qualified = True
            row.percentile_sample_size = n
            for metric, higher_is_better in metric_directions.items():
                value = getattr(row, metric)
                if value is None:
                    continue
                vals, sorted_vals = peers[metric]
                row.percentiles[metric] = _percentile_rank(value, vals, higher_is_better, sorted_vals)


def run(
    names: Iterable[str],
    season: int,
    level: str,
    train_games: int,
    train_start_date: str | None,
) -> list[ZoneMetricRow]:
    clf = train_zone_classifier(season, train_games, train_start_date)
    out = []
    for name in names:
        player_id = player_id_for_name(name)
        out.append(player_zone_metrics(name, player_id, season, clf, level))
    return out


def write_csv(rows: list[ZoneMetricRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", default=["Pedro Ramirez", "Mikey Romero", "Kristian Campbell"])
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--level", default="AAA")
    parser.add_argument("--train-games", type=int, default=30)
    parser.add_argument("--train-start-date", default="2026-05-15")
    parser.add_argument("--out", default="prospect-tracker/data/zone_metrics_aaa_test.csv")
    args = parser.parse_args()

    rows = run(args.names, args.season, args.level, args.train_games, args.train_start_date)
    write_csv(rows, Path(args.out))
    for row in rows:
        print(json.dumps(asdict(row), ensure_ascii=False))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
