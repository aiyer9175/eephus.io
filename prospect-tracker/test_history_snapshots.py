"""Tests for the forward-looking history tables added 2026-06:
metric_snapshots (board + Arkmetric state over time), il_history (append-only
IL stint timeline), and the data_freshness two-track stamp.
"""
import storage


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()


class TestMetricSnapshots:
    def _players(self):
        return [
            {"player_key": "a_one", "player_name": "A One", "overall_rank": 1,
             "fv_close": 62.0, "fv_close_plus": True, "org": "MIL", "position": "SS",
             "status": "active", "age": 19.1, "dollar_dvm_plus": 109.6,
             "statcast_plus": 113, "live_score": 66.1, "tool": 61,
             "surplus": {"value_mm": 154.0}},
            {"player_key": "b_two", "player_name": "B Two", "overall_rank": 2,
             "fv_close": 55.0, "fv_close_plus": False, "org": "SEA", "position": "SP",
             "status": "active", "age": 21.4, "dollar_dvm_plus": 90.0},
            # No rank, no FV → skipped.
            {"player_key": "c_skip", "player_name": "C Skip"},
        ]

    def test_capture_and_load(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        n = storage.snapshot_board_metrics(self._players(), snapshot_date="2026-06-01")
        assert n == 2  # c_skip dropped
        rows = storage.load_metric_snapshots(snapshot_date="2026-06-01")
        by_key = {r["player_key"]: r for r in rows}
        assert by_key["a_one"]["fv_tier"] == "60+"     # 62 → 60, plus flag
        assert by_key["a_one"]["consensus_fv"] == 62.0
        assert by_key["a_one"]["dollar_dvm_plus"] == 109.6   # payload unpacked
        assert by_key["a_one"]["surplus_mm"] == 154.0
        assert by_key["b_two"]["fv_tier"] == "55"
        assert by_key["b_two"]["is_pitcher"] == 1

    def test_idempotent_upsert_by_date(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        storage.snapshot_board_metrics(self._players(), snapshot_date="2026-06-01")
        # Re-run same date with a changed value → overwrite, not duplicate.
        players = self._players()
        players[0]["fv_close"] = 60.0
        storage.snapshot_board_metrics(players, snapshot_date="2026-06-01")
        rows = storage.load_metric_snapshots(player_key="a_one")
        assert len(rows) == 1
        assert rows[0]["consensus_fv"] == 60.0
        assert storage.metric_snapshot_dates() == ["2026-06-01"]

    def test_multiple_dates_build_a_series(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        storage.snapshot_board_metrics(self._players(), snapshot_date="2026-05-01")
        storage.snapshot_board_metrics(self._players(), snapshot_date="2026-06-01")
        assert storage.metric_snapshot_dates() == ["2026-05-01", "2026-06-01"]
        assert len(storage.load_metric_snapshots(player_key="a_one")) == 2


class TestILHistory:
    def test_placement_then_activation(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        # Day 1: two players on IL.
        cur = {"p1": {"is_on_il": 1, "since": "2026-04-01", "type": "10-day",
                      "description": "placed"},
               "p2": {"is_on_il": 1, "since": "2026-04-05", "type": "60-day",
                      "description": "placed"}}
        res = storage.record_il_observation(cur, observed_date="2026-04-10")
        assert res["placed"] == 2 and res["activated"] == 0
        # Day 2 (same state) → idempotent, no new activation.
        res2 = storage.record_il_observation(cur, observed_date="2026-04-11")
        assert res2["activated"] == 0
        assert len(storage.load_il_history()) == 2
        # Day 3: p1 comes off the IL → stint stamped activated.
        res3 = storage.record_il_observation({"p2": cur["p2"]},
                                             observed_date="2026-04-20")
        assert res3["activated"] == 1
        p1 = [r for r in storage.load_il_history("p1")][0]
        assert p1["activated_seen"] == "2026-04-20"
        assert p1["placed_seen"] == "2026-04-10"   # first observed, not overwritten
        p2 = [r for r in storage.load_il_history("p2")][0]
        assert p2["activated_seen"] is None        # still on IL

    def test_reinjury_reopens_stint(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        rec = {"is_on_il": 1, "since": "2026-04-01", "type": "10-day"}
        storage.record_il_observation({"p1": rec}, observed_date="2026-04-02")
        storage.record_il_observation({}, observed_date="2026-04-10")  # activated
        # Same stint reappears (rehab setback) → activation cleared.
        storage.record_il_observation({"p1": rec}, observed_date="2026-04-15")
        row = storage.load_il_history("p1")[0]
        assert row["activated_seen"] is None


class TestDataFreshness:
    def test_two_track_stamps(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        with storage.connect() as con:
            con.execute("INSERT INTO runs (started_at, finished_at, notes) "
                        "VALUES ('2026-06-01T10:00:00','2026-06-01T10:20:00','500 players, 40 trades')")
            con.execute("INSERT INTO runs (started_at, finished_at, notes) "
                        "VALUES ('2026-06-05T08:00:00','2026-06-05T08:05:00','DAILY: 12 on IL, 1 debuts, 0 new trades')")
        fresh = storage.data_freshness()
        assert fresh["last_run_kind"] == "daily"
        assert fresh["transactions_updated_at"] == "2026-06-05T08:05:00"
        # grades stamp ignores the DAILY run and points at the monthly one.
        assert fresh["grades_updated_at"] == "2026-06-01T10:20:00"
