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
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage", lambda: {"alex_freeland": {"2B": {"games": 33, "innings": 280}}})
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {"alex_freeland": "2B"})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    position, source = fielding.resolve_position("alex_freeland", 690976, "SS", is_mlb_player=True)

    assert position == "LF"
    assert source == "override"


def test_active_prospect_uses_parquet_before_mlb_detail(monkeypatch):
    monkeypatch.setattr(fielding, "_load_overrides", lambda: {})
    monkeypatch.setattr(fielding, "_load_mlb_fielding_usage", lambda: {"future_regular": {"2B": {"games": 20, "innings": 150}}})
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
        lambda: {"sal_stewart": {"1B": {"games": 49, "innings": 368.2}, "3B": {"games": 28, "innings": 189.2}}},
    )
    monkeypatch.setattr(fielding, "_load_mlb_detail_positions", lambda: {"sal_stewart": "3B"})
    monkeypatch.setattr(fielding, "_load_parquet_positions", lambda: {})

    position, source = fielding.resolve_position("sal_stewart", 701398, "3B", is_mlb_player=True)

    assert position == "1B"
    assert source == "mlb_fielding"
