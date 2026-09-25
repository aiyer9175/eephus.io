import fielding


def test_mlb_detail_position_overrides_db_for_debuted_player(monkeypatch):
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {"alex_freeland": "2B"})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    position, source = fielding.resolve_position("alex_freeland", 690976, "SS", is_mlb_player=True)

    assert position == "2B"
    assert source == "mlb_detail"


def test_manual_override_still_beats_mlb_detail(monkeypatch):
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {"alex_freeland": "LF"})
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage", lambda: {690976: {"2B": {"games": 33, "innings": 280}}})
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {"alex_freeland": "2B"})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    position, source = fielding.resolve_position("alex_freeland", 690976, "SS", is_mlb_player=True)

    assert position == "LF"
    assert source == "override"


def test_active_prospect_uses_parquet_before_mlb_detail(monkeypatch):
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage", lambda: {12345: {"2B": {"games": 20, "innings": 150}}})
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {"future_regular": "2B"})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {12345: "CF"})

    position, source = fielding.resolve_position("future_regular", 12345, "SS", is_mlb_player=False)

    assert position == "CF"
    assert source == "parquet"


def test_invalid_mlb_detail_position_falls_back_to_db(monkeypatch):
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    assert fielding._valid_position("H") is False

    position, source = fielding.resolve_position("christian_koss", 683766, "INF", is_mlb_player=True)

    assert position == "INF"
    assert source == "db"


def test_mlb_fielding_usage_beats_mlb_detail_for_debuted_player(monkeypatch):
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {})
    monkeypatch.setattr(
        fielding,
        "_load_mlb_fielding_usage",
        lambda: {701398: {"1B": {"games": 49, "innings": 368.2}, "3B": {"games": 28, "innings": 189.2}}},
    )
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {"sal_stewart": "3B"})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    position, source = fielding.resolve_position("sal_stewart", 701398, "3B", is_mlb_player=True)

    assert position == "1B"
    assert source == "mlb_fielding"

def test_usage_is_joined_on_the_mlbam_id_not_the_slug(monkeypatch):
    # Two players share a slug: the usage of id 571970 must not reach 691777.
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage",
                        lambda: {571970: {"1B": {"games": 90, "innings": 700.0}}})
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    assert fielding.resolve_position("max_muncy", 691777, "3B", is_mlb_player=True) == ("3B", "db")
    assert fielding.resolve_position("max_muncy", 571970, "3B", is_mlb_player=True) == ("1B", "mlb_fielding")
    assert fielding.position_usage("max_muncy") == {}
    assert fielding.position_usage("max_muncy", 571970)["1B"]["games"] == 90


def test_the_loader_reads_the_nightly_feed_at_its_latest_season(tmp_path, monkeypatch):
    import json
    data = tmp_path / "data"
    data.mkdir()
    (data / "fielding_innings.json").write_text(json.dumps({
        "last_season": 2026,
        "seasons": {"2025": {"1": {"SS": {"g": 150, "gs": 150, "inn": 1300.0}}},
                    "2026": {"1": {"2B": {"g": 40, "gs": 38, "inn": 330.3},
                                   "DH": {"g": 5, "gs": 5, "inn": 0.0},
                                   "XX": {"g": 1, "gs": 0, "inn": 1.0}}}}}), encoding="utf-8")
    monkeypatch.setattr(fielding, "_HERE", tmp_path)
    fielding._load_mlb_fielding_usage.cache_clear()
    try:
        usage = fielding._load_mlb_fielding_usage()
    finally:
        fielding._load_mlb_fielding_usage.cache_clear()
    assert usage == {1: {"2B": {"games": 40.0, "games_started": 38.0, "innings": 330.3},
                         "DH": {"games": 5.0, "games_started": 5.0, "innings": 0.0}}}


def test_the_june_snapshot_is_no_longer_read():
    from pathlib import Path
    src = (Path(fielding.__file__).read_text(encoding="utf-8"))
    assert '"mlb_fielding_positions.json"' not in src
