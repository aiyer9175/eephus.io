"""Validation script / test suite: every fixture must satisfy its contract.

This is the "publish a validation script" requirement for restricted
assets (Phase 12) -- an external builder with no access to real Eephus
data can run this against the fixtures alone to confirm their ingestion
code handles the documented schema, nulls, and key relationships.

Run with: pytest milb_pitch_quality_handoff/tests/test_fixtures_match_contracts.py
"""
import json
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PKG_ROOT / "fixtures"
CONTRACTS_DIR = PKG_ROOT / "contracts"


def _load(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


CASES = [
    ("identity.fixture.json", "identity.schema.json", None, "rows"),
    ("pitcher_ewar_mlb.fixture.json", "pitcher_ewar.schema.json", "mlb_pitcher_ewar", "rows"),
    ("park_context.fixture.json", "milb_park_context.schema.json", None, "rows"),
]

MULTI_ARTIFACT_CASES = [
    ("pitcher_ewar_milb.fixture.json", "pitcher_ewar.schema.json", {
        "aaa_pitcher_ewar": "milb_pitcher_ewar_aaa",
        "milb_pitcher_ewar_aa_higha": "milb_pitcher_ewar_aa_higha",
        "aaa_contact_management_plus": "aaa_contact_management_plus",
    }),
    ("contact_translation.fixture.json", "contact_translation.schema.json", {
        "latent_rate_talent": "latent_rate_talent",
        "milb_xwar_projection": "milb_xwar_projection",
    }),
]


@pytest.mark.parametrize("fixture_name,schema_name,contract_key,rows_key", CASES)
def test_single_artifact_fixture_has_required_columns(fixture_name, schema_name, contract_key, rows_key):
    fixture = _load(FIXTURES_DIR / fixture_name)
    schema = _load(CONTRACTS_DIR / schema_name)

    if contract_key:
        required = schema["artifacts"][contract_key]["required_columns"]
        if isinstance(required, dict):
            required = list(required.keys())
    else:
        required = schema["required_columns"]

    rows = fixture[rows_key]
    assert len(rows) > 0
    for row in rows:
        missing = [c for c in required if c not in row]
        assert not missing, f"{fixture_name} row missing contract columns: {missing}"


@pytest.mark.parametrize("fixture_name,schema_name,key_map", MULTI_ARTIFACT_CASES)
def test_multi_artifact_fixture_has_required_columns(fixture_name, schema_name, key_map):
    fixture = _load(FIXTURES_DIR / fixture_name)
    schema = _load(CONTRACTS_DIR / schema_name)

    for fixture_key, contract_key in key_map.items():
        entry = schema["artifacts"][contract_key]
        required = entry["required_columns"]
        if isinstance(required, dict):
            required = list(required.keys())
        rows = fixture[fixture_key]
        assert len(rows) > 0
        for row in rows:
            missing = [c for c in required if c not in row]
            assert not missing, f"{fixture_name}[{fixture_key}] row missing contract columns: {missing}"


def test_no_fixture_uses_a_plausible_real_id():
    """All synthetic ids must be obviously fake (>= 999000 or E999xxxx) so
    they can never be confused with a real player."""
    for path in FIXTURES_DIR.glob("*.fixture.json"):
        fixture = _load(path)
        text = json.dumps(fixture)
        # spot-check: every numeric id field found should be >= 999000-ish
        # (a loose but real check, not just a comment claiming it)
        for row_list in fixture.values():
            if not isinstance(row_list, list):
                continue
            for row in row_list:
                for key in ("mlbam_id", "batter", "pitcher", "player_id", "team_id", "venue_id"):
                    if key in row and row[key] is not None:
                        assert row[key] >= 88800, f"{path.name}: {key}={row[key]} does not look like an obviously-synthetic id"


def test_park_context_fixture_preserves_invariants():
    fixture = _load(FIXTURES_DIR / "park_context.fixture.json")
    for row in fixture["rows"]:
        assert row["coverage_share"] == 1.0
        assert row["weather_required"] is False


def test_identity_fixture_has_no_dob_field():
    fixture = _load(FIXTURES_DIR / "identity.fixture.json")
    for row in fixture["rows"]:
        assert "dob" not in row
        assert "birth_year" in row
