"""Vertical approach angle helpers from Statcast pitch physics.

The formula mirrors the public R examples linked in the VAA notes:

    vy_f = -sqrt(vy0^2 - (2 * ay * (y0 - yf)))
    t = (vy_f - vy0) / ay
    vz_f = vz0 + (az * t)
    VAA = -atan(vz_f / vy_f) * (180 / pi)

MLB Stats API game feeds expose these values under
``pitchData.coordinates`` as ``vY0``, ``vZ0``, ``aY``, ``aZ``, and ``y0``.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Iterable

from statcast_metrics import MLB_GAME_FEED_API, _game_logs, _get_json


HOME_PLATE_Y_FT = 17 / 12


PITCH_TYPE_NAMES = {
    "FF": "Four-Seam Fastball",
    "SI": "Sinker",
    "FT": "Two-Seam Fastball",
    "FC": "Cutter",
    "SL": "Slider",
    "ST": "Sweeper",
    "CU": "Curveball",
    "KC": "Knuckle Curve",
    "CH": "Changeup",
    "FS": "Splitter",
    "SV": "Slurve",
}


@dataclass
class VaaPitch:
    game_pk: int
    game_date: str | None
    pitch_type: str
    pitch_name: str
    vaa: float
    release_speed: float | None
    plate_x: float | None
    plate_z: float | None
    description: str | None
    event: str | None


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_vaa(
    *,
    vy0: float,
    vz0: float,
    ay: float,
    az: float,
    y0: float = 50.0,
    yf: float = HOME_PLATE_Y_FT,
) -> float:
    """Return VAA in degrees for one pitch.

    More negative values are steeper. Raises ``ValueError`` if the physics
    fields are unusable, which lets callers skip partial pitch rows.
    """
    discriminant = (vy0 * vy0) - (2 * ay * (y0 - yf))
    if discriminant < 0:
        raise ValueError("VAA discriminant is negative")
    if ay == 0:
        raise ValueError("VAA requires non-zero y acceleration")
    vy_f = -math.sqrt(discriminant)
    t = (vy_f - vy0) / ay
    vz_f = vz0 + (az * t)
    return -math.atan(vz_f / vy_f) * (180 / math.pi)


def vaa_from_pitch_event(event: dict) -> float | None:
    coords = ((event.get("pitchData") or {}).get("coordinates") or {})
    try:
        return calculate_vaa(
            vy0=float(coords["vY0"]),
            vz0=float(coords["vZ0"]),
            ay=float(coords["aY"]),
            az=float(coords["aZ"]),
            y0=float(coords.get("y0") or 50.0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def fetch_player_vaa_pitches(
    *,
    mlbam_id: int,
    season: int,
    level: str | None = "MLB",
    is_pitcher: bool = True,
) -> list[VaaPitch]:
    """Fetch pitch-level VAA rows for one player/season/level."""
    rows: list[VaaPitch] = []
    logs = _game_logs(mlbam_id, season, is_pitcher=is_pitcher)
    for split in logs:
        split_level = split.get("_level")
        if level and split_level != level:
            continue
        game_pk = int((split.get("game") or {}).get("gamePk") or 0)
        if not game_pk:
            continue
        data = _get_json(f"{MLB_GAME_FEED_API}/{game_pk}/feed/live", ttl_seconds=86400)
        game_date = ((data.get("gameData") or {}).get("datetime") or {}).get("officialDate") or split.get("date")
        for play in ((data.get("liveData") or {}).get("plays") or {}).get("allPlays", []):
            matchup = play.get("matchup") or {}
            player = matchup.get("pitcher") if is_pitcher else matchup.get("batter")
            if int((player or {}).get("id") or 0) != int(mlbam_id):
                continue
            result = play.get("result") or {}
            for event in play.get("playEvents", []):
                if not event.get("isPitch"):
                    continue
                vaa = vaa_from_pitch_event(event)
                if vaa is None:
                    continue
                pitch_data = event.get("pitchData") or {}
                coords = pitch_data.get("coordinates") or {}
                details = event.get("details") or {}
                pitch_type = (details.get("type") or {}).get("code") or ""
                if not pitch_type:
                    continue
                rows.append(
                    VaaPitch(
                        game_pk=game_pk,
                        game_date=game_date,
                        pitch_type=pitch_type,
                        pitch_name=(details.get("type") or {}).get("description") or PITCH_TYPE_NAMES.get(pitch_type, pitch_type),
                        vaa=vaa,
                        release_speed=_safe_float(pitch_data.get("startSpeed")),
                        plate_x=_safe_float(coords.get("pX")),
                        plate_z=_safe_float(coords.get("pZ")),
                        description=details.get("description"),
                        event=result.get("eventType") or result.get("event"),
                    )
                )
    return rows


def summarize_vaa_by_pitch_type(rows: Iterable[VaaPitch], min_pitches: int = 1) -> list[dict]:
    buckets: dict[str, list[VaaPitch]] = {}
    for row in rows:
        buckets.setdefault(row.pitch_type, []).append(row)

    out = []
    for pitch_type, vals in buckets.items():
        if len(vals) < min_pitches:
            continue
        vaas = [row.vaa for row in vals]
        speeds = [row.release_speed for row in vals if row.release_speed is not None]
        out.append(
            {
                "pitch_type": pitch_type,
                "pitch_name": vals[0].pitch_name,
                "pitches": len(vals),
                "avg_vaa": round(mean(vaas), 2),
                "median_vaa": round(median(vaas), 2),
                "min_vaa": round(min(vaas), 2),
                "max_vaa": round(max(vaas), 2),
                "avg_speed": round(mean(speeds), 1) if speeds else None,
            }
        )
    return sorted(out, key=lambda row: (-row["pitches"], row["pitch_type"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate vertical approach angle from MLB Stats API game feeds.")
    parser.add_argument("--mlbam-id", type=int, default=702273)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--level", default="MLB")
    parser.add_argument("--min-pitches", type=int, default=1)
    parser.add_argument("--csv", action="store_true", help="Print pitch-level rows as CSV instead of summary JSON lines.")
    args = parser.parse_args()

    rows = fetch_player_vaa_pitches(
        mlbam_id=args.mlbam_id,
        season=args.season,
        level=args.level or None,
        is_pitcher=True,
    )
    if args.csv:
        import csv
        import sys

        writer = csv.DictWriter(sys.stdout, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        return 0

    import json

    for row in summarize_vaa_by_pitch_type(rows, min_pitches=args.min_pitches):
        print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
