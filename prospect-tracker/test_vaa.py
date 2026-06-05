import pytest

from vaa import calculate_vaa, summarize_vaa_by_pitch_type, VaaPitch


def test_calculate_vaa_matches_stats_api_schultz_pitch():
    vaa = calculate_vaa(
        vy0=-141.88051222402854,
        vz0=-8.358292137377004,
        ay=27.913067237094754,
        az=-15.419559917976526,
        y0=50.000683758692006,
    )

    assert vaa == pytest.approx(-5.98, abs=0.01)


def test_summarize_vaa_by_pitch_type_groups_and_rounds():
    rows = [
        VaaPitch(1, "2026-01-01", "FF", "Four-Seam Fastball", -4.8, 95.0, None, None, None, None),
        VaaPitch(1, "2026-01-01", "FF", "Four-Seam Fastball", -5.0, 97.0, None, None, None, None),
        VaaPitch(1, "2026-01-01", "SI", "Sinker", -5.7, 94.0, None, None, None, None),
    ]

    out = summarize_vaa_by_pitch_type(rows)

    assert out[0]["pitch_type"] == "FF"
    assert out[0]["pitches"] == 2
    assert out[0]["avg_vaa"] == -4.9
    assert out[0]["median_vaa"] == -4.9
    assert out[0]["avg_speed"] == 96.0
