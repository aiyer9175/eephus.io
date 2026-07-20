"""Step 4: build the Field Availability, Coverage, Missingness, and Trust
matrices from the cached game feeds.

Grain is level x venue (not just level) -- see PILOT_SCOPE.md for why a
venue-only or level-only grain would hide the actual coverage pattern.

Outputs (all under reports/):
  FIELD_AVAILABILITY_MATRIX.json / .md
  COVERAGE_MATRIX.json / .md
  MISSINGNESS_MATRIX.json / .md
  TRUST_MATRIX.json / .md

Usage: python build_matrices.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import pstdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LEVELS, DATA_CACHE, REPORTS_DIR, load_json, save_json  # noqa: E402

PITCH_FIELDS = [
    "pitch_type_code",
    "type_confidence",
    "start_speed",
    "end_speed",
    "pfx_x",
    "pfx_z",
    "break_vertical",
    "break_vertical_induced",
    "break_horizontal",
    "break_angle",
    "break_length",
    "spin_rate",
    "spin_direction",
    "extension",
    "release_x0",
    "release_y0",
    "release_z0",
    "plate_x",
    "plate_z",
    "zone",
    "plate_time",
]

HIT_FIELDS = [
    "launch_speed",
    "launch_angle",
    "total_distance",
    "trajectory",
    "hardness",
]

# Coverage-rate thresholds used to assign a trust label at (level, venue, field) grain.
TRUST_THRESHOLDS = [
    (0.98, "TRUSTED"),
    (0.50, "USABLE_WITH_FILTER"),
    (0.0001, "PARTIAL"),
]
TRUST_ZERO = "UNAVAILABLE"


def extract_pitch(event: dict) -> dict:
    details = event.get("details", {}) or {}
    pdata = event.get("pitchData", {}) or {}
    coords = pdata.get("coordinates", {}) or {}
    breaks = pdata.get("breaks", {}) or {}
    return {
        "pitch_type_code": details.get("type", {}).get("code") if details.get("type") else None,
        "type_confidence": pdata.get("typeConfidence"),
        "start_speed": pdata.get("startSpeed"),
        "end_speed": pdata.get("endSpeed"),
        "pfx_x": coords.get("pfxX"),
        "pfx_z": coords.get("pfxZ"),
        "break_vertical": breaks.get("breakVertical"),
        "break_vertical_induced": breaks.get("breakVerticalInduced"),
        "break_horizontal": breaks.get("breakHorizontal"),
        "break_angle": breaks.get("breakAngle"),
        "break_length": breaks.get("breakLength"),
        "spin_rate": breaks.get("spinRate"),
        "spin_direction": breaks.get("spinDirection"),
        "extension": pdata.get("extension"),
        "release_x0": coords.get("x0"),
        "release_y0": coords.get("y0"),
        "release_z0": coords.get("z0"),
        "plate_x": coords.get("pX"),
        "plate_z": coords.get("pZ"),
        "zone": pdata.get("zone"),
        "plate_time": pdata.get("plateTime"),
    }


def extract_hit(hit_data: dict) -> dict:
    return {
        "launch_speed": hit_data.get("launchSpeed"),
        "launch_angle": hit_data.get("launchAngle"),
        "total_distance": hit_data.get("totalDistance"),
        "trajectory": hit_data.get("trajectory"),
        "hardness": hit_data.get("hardness"),
    }


def trust_label(rate: float) -> str:
    if rate <= 0:
        return TRUST_ZERO
    for threshold, label in TRUST_THRESHOLDS:
        if rate >= threshold:
            return label
    return "PARTIAL"


class VenueAgg:
    def __init__(self, venue_name: str):
        self.venue_name = venue_name
        self.n_games = 0
        self.n_pitches = 0
        self.n_hits = 0
        self.pitch_nonnull = defaultdict(int)
        self.hit_nonnull = defaultdict(int)
        self.per_game_pitch_coverage = []  # for missingness all-or-nothing check


def process_level(level: str) -> dict:
    samples = load_json(DATA_CACHE / "samples" / f"{level}.json")
    window_by_pk = {s["gamePk"]: s["window"] for s in samples}
    venue_name_by_pk = {s["gamePk"]: s["venue_name"] for s in samples}

    venue_dir = DATA_CACHE / level
    venues: dict[int, VenueAgg] = {}

    for s in samples:
        game_pk = s["gamePk"]
        feed_path = venue_dir / f"{game_pk}.json"
        if not feed_path.exists():
            continue  # not yet pulled -- fine during partial/smoke runs
        feed = load_json(feed_path)

        game_data = feed.get("gameData", {}) or {}
        venue_info = game_data.get("venue", {}) or {}
        venue_id = venue_info.get("id", s["venue_id"])
        venue_name = venue_info.get("name") or venue_name_by_pk.get(game_pk, "unknown")

        agg = venues.setdefault(venue_id, VenueAgg(venue_name))
        agg.n_games += 1

        plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        game_pitches = 0
        game_pitch_hits = 0
        for p in plays:
            for e in p.get("playEvents", []):
                if e.get("isPitch"):
                    game_pitches += 1
                    agg.n_pitches += 1
                    fields = extract_pitch(e)
                    for k, v in fields.items():
                        if v is not None:
                            agg.pitch_nonnull[k] += 1
                hit_data = e.get("hitData")
                if hit_data:
                    game_pitch_hits += 1
                    agg.n_hits += 1
                    fields = extract_hit(hit_data)
                    for k, v in fields.items():
                        if v is not None:
                            agg.hit_nonnull[k] += 1

        # per-game coverage of the single highest-signal field (start_speed) --
        # used for the missingness all-or-nothing check.
        game_speed_nonnull = 0
        for p in plays:
            for e in p.get("playEvents", []):
                if e.get("isPitch") and (e.get("pitchData", {}) or {}).get("startSpeed") is not None:
                    game_speed_nonnull += 1
        rate = (game_speed_nonnull / game_pitches) if game_pitches else None
        if rate is not None:
            agg.per_game_pitch_coverage.append(rate)

    return {"venues": venues, "window_by_pk": window_by_pk}


def build_all() -> None:
    field_availability = {}
    coverage = {}
    missingness = {}
    trust = {}

    for level in LEVELS:
        print(f"Aggregating {level}...")
        result = process_level(level)
        venues = result["venues"]

        fa_level = {}
        cov_level = {}
        trust_level = {}

        for venue_id, agg in venues.items():
            n = agg.n_pitches
            nh = agg.n_hits

            pitch_rates = {f: (agg.pitch_nonnull[f] / n if n else 0.0) for f in PITCH_FIELDS}
            hit_rates = {f: (agg.hit_nonnull[f] / nh if nh else 0.0) for f in HIT_FIELDS}

            fa_level[str(venue_id)] = {
                "venue_name": agg.venue_name,
                "n_games": agg.n_games,
                "n_pitches": n,
                "n_battedballs": nh,
                "pitch_fields_present": {f: pitch_rates[f] > 0 for f in PITCH_FIELDS},
                "hit_fields_present": {f: hit_rates[f] > 0 for f in HIT_FIELDS},
            }
            cov_level[str(venue_id)] = {
                "venue_name": agg.venue_name,
                "n_games": agg.n_games,
                "n_pitches": n,
                "n_battedballs": nh,
                "pitch_coverage": pitch_rates,
                "hit_coverage": hit_rates,
            }
            trust_level[str(venue_id)] = {
                "venue_name": agg.venue_name,
                "pitch_trust": {f: trust_label(pitch_rates[f]) for f in PITCH_FIELDS},
                "hit_trust": {f: trust_label(hit_rates[f]) for f in HIT_FIELDS},
            }

        field_availability[level] = fa_level
        coverage[level] = cov_level
        trust[level] = trust_level

        # Missingness: is tracking-data presence all-or-nothing per venue (games
        # within a venue either fully covered or fully uncovered), or does it
        # vary game-to-game within the same venue?
        all_or_nothing_venues = 0
        mixed_venues = 0
        no_data_venues = 0
        venue_summaries = {}
        for venue_id, agg in venues.items():
            rates = agg.per_game_pitch_coverage
            if not rates:
                no_data_venues += 1
                continue
            spread = pstdev(rates) if len(rates) > 1 else 0.0
            is_all_or_nothing = all(r > 0.95 for r in rates) or all(r < 0.05 for r in rates)
            venue_summaries[str(venue_id)] = {
                "venue_name": agg.venue_name,
                "per_game_start_speed_coverage": rates,
                "stdev_across_games": spread,
                "all_or_nothing": is_all_or_nothing,
            }
            if is_all_or_nothing:
                all_or_nothing_venues += 1
            else:
                mixed_venues += 1

        n_venues_total = all_or_nothing_venues + mixed_venues + no_data_venues
        missingness[level] = {
            "n_venues": n_venues_total,
            "all_or_nothing_venues": all_or_nothing_venues,
            "mixed_within_venue_venues": mixed_venues,
            "no_data_yet": no_data_venues,
            "venue_detail": venue_summaries,
        }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    save_json(REPORTS_DIR / "FIELD_AVAILABILITY_MATRIX.json", field_availability)
    save_json(REPORTS_DIR / "COVERAGE_MATRIX.json", coverage)
    save_json(REPORTS_DIR / "MISSINGNESS_MATRIX.json", missingness)
    save_json(REPORTS_DIR / "TRUST_MATRIX.json", trust)

    write_markdown(field_availability, coverage, missingness, trust)
    print("Matrices written to reports/")


def level_core_summary(cov_level: dict) -> list[tuple]:
    """One row per venue: n_pitches, start_speed coverage, spin_rate coverage,
    plate_x coverage, launch_speed coverage -- the four highest-signal fields,
    used for the compact markdown tables (full detail lives in the JSON)."""
    rows = []
    for venue_id, v in sorted(cov_level.items(), key=lambda kv: -kv[1]["n_pitches"]):
        pc = v["pitch_coverage"]
        hc = v["hit_coverage"]
        rows.append(
            (
                v["venue_name"],
                v["n_games"],
                v["n_pitches"],
                pc.get("start_speed", 0.0),
                pc.get("spin_rate", 0.0),
                pc.get("plate_x", 0.0),
                hc.get("launch_speed", 0.0),
            )
        )
    return rows


def write_markdown(field_availability, coverage, missingness, trust) -> None:
    lines = ["# Coverage Matrix (Phase 1 pilot)", ""]
    lines.append(
        "Coverage rate (non-null share) per venue, for the four highest-signal fields. "
        "Full per-field detail for every field is in `COVERAGE_MATRIX.json`.\n"
    )
    for level in LEVELS:
        cov_level = coverage.get(level, {})
        lines.append(f"## {level}")
        lines.append("")
        lines.append("| Venue | Games | Pitches | start_speed | spin_rate | plate_x | launch_speed |")
        lines.append("|---|---|---|---|---|---|---|")
        for name, n_games, n_pitches, sp, spin, px, ls in level_core_summary(cov_level):
            lines.append(
                f"| {name} | {n_games} | {n_pitches} | {sp:.1%} | {spin:.1%} | {px:.1%} | {ls:.1%} |"
            )
        lines.append("")
    (REPORTS_DIR / "COVERAGE_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# Field Availability Matrix (Phase 1 pilot)", ""]
    lines.append(
        "Whether *any* pitch in the sample at this venue had a non-null value for this field "
        "(binary presence, not a rate -- see COVERAGE_MATRIX for rates).\n"
    )
    for level in LEVELS:
        fa_level = field_availability.get(level, {})
        n_venues = len(fa_level)
        n_any = sum(1 for v in fa_level.values() if v["pitch_fields_present"].get("start_speed"))
        lines.append(f"## {level}: {n_any}/{n_venues} venues have any pitch-tracking data present")
        lines.append("")
    (REPORTS_DIR / "FIELD_AVAILABILITY_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# Missingness Matrix (Phase 1 pilot)", ""]
    lines.append(
        "Tests whether missingness is all-or-nothing at the venue grain (a venue either has a "
        "full tracking install for the whole sample or none) vs. mixed within a venue across "
        "games (partial/intermittent coverage).\n"
    )
    lines.append("| Level | Venues | All-or-nothing | Mixed within venue | No data pulled yet |")
    lines.append("|---|---|---|---|---|")
    for level in LEVELS:
        m = missingness.get(level, {})
        lines.append(
            f"| {level} | {m.get('n_venues', 0)} | {m.get('all_or_nothing_venues', 0)} | "
            f"{m.get('mixed_within_venue_venues', 0)} | {m.get('no_data_yet', 0)} |"
        )
    (REPORTS_DIR / "MISSINGNESS_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# Trust Matrix (Phase 1 pilot)", ""]
    lines.append(
        "Trust vocabulary matches `milb-projections/definitions/COVERAGE_AND_TRUST.md`: "
        "`TRUSTED | USABLE_WITH_FILTER | PARTIAL | UNAVAILABLE` (no venue in this pilot showed "
        "`KNOWN_DEFECT`-style partial-field corruption -- coverage was clean rate-based, not "
        "malformed). Assigned per (level, venue, field) from the measured coverage rate; see "
        "TRUST_MATRIX.json for the full per-field breakdown.\n"
    )
    for level in LEVELS:
        trust_level = trust.get(level, {})
        n_venues = len(trust_level)
        n_trusted = sum(
            1 for v in trust_level.values() if v["pitch_trust"].get("start_speed") == "TRUSTED"
        )
        n_unavailable = sum(
            1 for v in trust_level.values() if v["pitch_trust"].get("start_speed") == "UNAVAILABLE"
        )
        lines.append(
            f"## {level}: {n_trusted}/{n_venues} venues TRUSTED, "
            f"{n_unavailable}/{n_venues} venues UNAVAILABLE (start_speed as bellwether field)"
        )
        lines.append("")
    (REPORTS_DIR / "TRUST_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    build_all()
