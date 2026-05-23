"""Tests for the rookie-eligibility graduation rules + MLB-debut marker
injected into level_changes."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scrapers import Snapshot
from consensus import build_timeseries
from stats import (
    derive_roster_status,
    ROOKIE_AB_THRESHOLD, ROOKIE_IP_THRESHOLD, DEFAULT_OPTIONS,
)


# ---------------------------------------------------------------------------
# Roster-status graduation gates
# ---------------------------------------------------------------------------

class TestRosterStatusGraduationGates:
    """`rookie_exhausted` should flip when AB / IP / options gates fire,
    and `graduation_reason` should explain which one did."""

    def _select_contract_tx(self, date_iso):
        # The MLB transactions API marks an MLB debut with this verb.
        return {
            "date": date_iso,
            "type_code": "SE",
            "description": "Selected the contract of Player",
        }

    def _option_tx(self, date_iso):
        return {
            "date": date_iso,
            "type_code": "OPT",
            "description": "Optioned to AAA",
        }

    def test_no_mlb_activity_keeps_prospect_active(self):
        rs = derive_roster_status([], [{"season": 2025, "level": "AA",
                                        "is_pitcher": False, "ab": 400}])
        assert rs["rookie_exhausted"] is False
        assert rs["graduation_reason"] is None

    def test_single_mlb_game_below_threshold_stays_active(self):
        """The whole point of this rewrite — one MLB game must not flip
        a prospect to graduated."""
        txs = [self._select_contract_tx("2026-04-15")]
        career = [
            {"season": 2026, "level": "MLB",  "is_pitcher": False, "ab": 4,  "games": 1},
            {"season": 2026, "level": "AAA",  "is_pitcher": False, "ab": 110, "games": 30},
        ]
        rs = derive_roster_status(txs, career)
        assert rs["mlb_debut_date"] == "2026-04-15"
        assert rs["rookie_exhausted"] is False
        assert rs["graduation_reason"] is None

    def test_at_bat_threshold_crossed_graduates(self):
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": ROOKIE_AB_THRESHOLD + 1, "games": 40}]
        txs = [self._select_contract_tx("2026-04-15")]
        rs = derive_roster_status(txs, career)
        assert rs["rookie_exhausted"] is True
        assert rs["graduation_reason"] == "ab_threshold"

    def test_at_bat_exactly_at_threshold_does_not_graduate(self):
        """The rule is `> 130 AB`, not `>= 130`. A player with exactly the
        threshold AB is still a rookie."""
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": ROOKIE_AB_THRESHOLD, "games": 40}]
        rs = derive_roster_status([self._select_contract_tx("2026-04-15")], career)
        assert rs["rookie_exhausted"] is False
        assert rs["graduation_reason"] is None

    def test_innings_threshold_crossed_graduates_pitcher(self):
        career = [{"season": 2026, "level": "MLB", "is_pitcher": True,
                   "ip": ROOKIE_IP_THRESHOLD + 0.1, "games": 30}]
        rs = derive_roster_status([self._select_contract_tx("2026-04-15")], career)
        assert rs["rookie_exhausted"] is True
        assert rs["graduation_reason"] == "ip_threshold"

    def test_options_exhausted_with_debut_graduates(self):
        """Out of MiLB options + has debuted → the team has committed the
        roster spot. Treat as graduated even with no AB/IP threshold hit.

        v15 — the new active_days_threshold gate may fire first if the
        player has accumulated >45 days on the active roster. Both gates
        are valid "this player is graduated" signals; the test just
        verifies that SOMETHING triggers (options is the legacy proxy
        but the new days gate is more faithful to the MLB rule)."""
        txs = [
            self._select_contract_tx("2024-09-01"),
            self._option_tx("2024-05-05"),
            self._option_tx("2025-06-10"),
            self._option_tx("2026-04-15"),
        ]
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": 60, "games": 20}]
        rs = derive_roster_status(txs, career)
        assert rs["options_used"] == DEFAULT_OPTIONS
        assert rs["rookie_exhausted"] is True
        assert rs["graduation_reason"] in ("options_exhausted",
                                           "active_days_threshold")

    def test_options_exhausted_without_debut_does_not_graduate(self):
        """A prospect with three option years but no MLB debut hasn't
        been on the active roster — options-exhaustion alone is meaningless
        without a debut."""
        txs = [
            self._option_tx("2024-05-05"),
            self._option_tx("2025-06-10"),
            self._option_tx("2026-04-15"),
        ]
        rs = derive_roster_status(txs, [])
        assert rs["mlb_debut_date"] is None
        assert rs["rookie_exhausted"] is False
        assert rs["graduation_reason"] is None

    def test_api_debut_date_overrides_contract_selection(self):
        """When the MLB Stats API gives us an authoritative mlbDebutDate
        (via PlayerIndex), we surface that instead of the first 40-man
        selection — the two can differ by months for Rule 5 protected
        players."""
        txs = [{
            # Rule 5 protection on the November deadline; player hasn't
            # debuted yet but is on the 40-man.
            "date": "2025-11-18", "type_code": "SE",
            "description": "Selected the contract of Player",
        }]
        rs = derive_roster_status(txs, [], api_debut_date="2026-06-04")
        assert rs["mlb_debut_date"] == "2026-06-04"

    def test_contract_selection_without_mlb_activity_yields_no_debut(self):
        """Rule 5 protection on November 18 with zero MLB games on file
        must NOT register as an MLB debut — the player hasn't played."""
        txs = [{
            "date": "2025-11-18", "type_code": "SE",
            "description": "Selected the contract of Player",
        }]
        rs = derive_roster_status(txs, [])  # empty career_rows
        assert rs["mlb_debut_date"] is None
        # 40-man flag still flips, but the debut marker stays empty so
        # the front-end doesn't pin a phantom debut star on the chart.
        assert rs["on_40_man"] is True

    def test_contract_selection_plus_mlb_activity_yields_debut_fallback(self):
        """No API debut date but the player has MLB games on record —
        use the contract-selection date as the debut fallback."""
        txs = [{
            "date": "2024-09-01", "type_code": "SE",
            "description": "Selected the contract of Player",
        }]
        career = [{"season": 2024, "level": "MLB", "is_pitcher": False,
                   "ab": 50, "games": 18}]
        rs = derive_roster_status(txs, career)  # api_debut_date=None
        assert rs["mlb_debut_date"] == "2024-09-01"

    def test_ab_threshold_wins_over_options(self):
        """If both gates would fire, the reason reports the AB-threshold
        path (more authoritative — it's directly in the rookie rules)."""
        txs = [
            self._select_contract_tx("2024-09-01"),
            self._option_tx("2024-05-05"),
            self._option_tx("2025-06-10"),
            self._option_tx("2026-04-15"),
        ]
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": ROOKIE_AB_THRESHOLD + 50, "games": 80}]
        rs = derive_roster_status(txs, career)
        assert rs["graduation_reason"] == "ab_threshold"


# ---------------------------------------------------------------------------
# v15 — 45-day active-roster gate (official MLB rule, third OR-gate)
# ---------------------------------------------------------------------------

class TestActiveDaysGate:
    def _activate(self, date_iso, verb="Recalled"):
        return {"date": date_iso, "type_code": "ACT",
                "description": f"{verb} from AAA"}

    def _option(self, date_iso):
        return {"date": date_iso, "type_code": "OPT",
                "description": "Optioned to AAA"}

    def _il(self, date_iso, kind="10-day"):
        return {"date": date_iso, "type_code": "ILS",
                "description": f"Placed on the {kind} IL"}

    def _activate_il(self, date_iso):
        return {"date": date_iso, "type_code": "ACT",
                "description": "Activated from the 10-day IL"}

    def _select(self, date_iso):
        return {"date": date_iso, "type_code": "SE",
                "description": "Selected the contract of Player"}

    def test_45_day_active_roster_graduates(self):
        """Player active for 60 days (no AB threshold hit) should graduate
        via the new active_days_threshold gate."""
        txs = [
            self._select("2026-03-01"),  # Apr 1 → Apr 30 = 30 days, May 1 → end = ...
            self._option("2026-05-30"),
        ]
        # 2026-03-01 → 2026-05-30 = 91 days, all before Sept 1 → counts
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": 50, "games": 25}]
        rs = derive_roster_status(txs, career)
        assert rs["active_roster_days"] >= 45
        assert rs["rookie_exhausted"] is True
        assert rs["graduation_reason"] == "active_days_threshold"

    def test_under_45_active_days_stays_active(self):
        """30 active days, well below 45 → still a prospect."""
        txs = [
            self._select("2026-04-01"),
            self._option("2026-04-29"),  # ~29 days active
        ]
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": 30, "games": 12}]
        rs = derive_roster_status(txs, career)
        assert rs["active_roster_days"] < 45
        assert rs["graduation_reason"] is None

    def test_il_days_excluded_from_45_day_count(self):
        """A player who was active 20 days, then went on IL for 30 days,
        then was activated for 15 more days has 35 active days (not 65)."""
        txs = [
            self._select("2026-04-01"),
            self._il("2026-04-21"),               # 20 active days
            self._activate_il("2026-05-21"),      # IL gap: 30 days (NOT counted)
            self._option("2026-06-05"),           # +15 active days = 35 total
        ]
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": 50, "games": 25}]
        rs = derive_roster_status(txs, career)
        assert rs["active_roster_days"] < 45  # 20 + 15 = 35
        assert rs["graduation_reason"] is None

    def test_september_callup_excluded_from_45_day_count(self):
        """Post-Sept-1 active days don't count (roster expansion). A player
        called up Aug 15, on roster through end of season, has only 17 days
        (Aug 15 → Sept 1) that count toward the gate."""
        txs = [
            self._select("2026-08-15"),
            # Never optioned — currently active through end of year.
        ]
        career = [{"season": 2026, "level": "MLB", "is_pitcher": False,
                   "ab": 60, "games": 30}]
        # Mock today = end of season to simulate the rollover.
        from datetime import date as _date
        rs = derive_roster_status(txs, career, today=_date(2026, 10, 5))
        # Aug 15 → Sept 1 = 18 days inclusive; everything after Sept 1 dropped.
        assert rs["active_roster_days"] < 30
        assert rs["graduation_reason"] is None

    def test_active_days_requires_mlb_activity(self):
        """Active-days gate doesn't fire without actual MLB activity —
        a Rule 5 add who never played isn't a rookie burn."""
        txs = [
            self._select("2025-11-18"),  # Rule 5 protection
            # Optioned next April but never played
            self._option("2026-04-15"),
        ]
        # No MLB career row → has_mlb_activity is False
        rs = derive_roster_status(txs, [])
        # Even though active_days might exceed 45, no MLB activity → not graduated
        assert rs["graduation_reason"] != "active_days_threshold"


# ---------------------------------------------------------------------------
# Storage export — premature "any MLB game → graduated" bypass is gone
# ---------------------------------------------------------------------------

def _snap(source, name, *, fv=None, date_, label="upd", status="active"):
    return Snapshot(
        source=source, snapshot_date=date_, interval_label=label,
        player_key=name.lower().replace(" ", "_"), player_name=name,
        position="SS", org="PIT", rank=10, fv=fv, status=status,
    )


class TestSubThresholdMlbStaysActive:
    """A prospect with stale FV who appeared in MLB but didn't cross the
    rookie threshold should NOT be graduated — they go to inactives at
    worst, but ideally stay active if their FV cards are recent."""

    def test_stale_fv_with_minor_mlb_time_does_not_graduate(self, tmp_path):
        from storage import export_timeseries_json
        # Snapshot from a year-plus ago so the FV gate is "stale" by the
        # _inactive_cutoff used in storage.export.
        snaps = [_snap("fangraphs", "Cup of Coffee Guy",
                       fv=50.0, date_="2024-08-01", label="FG 2024")]
        ts = build_timeseries(snaps)
        career = {
            "cup_of_coffee_guy": [
                {"season": 2026, "level": "MLB", "is_pitcher": False,
                 "ab": 12, "games": 5},   # well below 130
                {"season": 2025, "level": "AAA", "is_pitcher": False,
                 "ab": 380, "games": 95},
            ],
        }
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out, career_stats=career)
        from storage import load_export_unified as _leu; payload = _leu(out)
        names_active = {p["player_name"] for p in payload["players"]}
        names_grad   = {p["player_name"] for p in payload["graduates"]}
        names_inact  = {p["player_name"] for p in payload.get("inactives", [])}
        # The pre-fix behavior pushed this player into graduates because
        # the FV was stale AND any MLB row was present. Post-fix they
        # land in inactives — never graduates.
        assert "Cup of Coffee Guy" not in names_grad
        assert "Cup of Coffee Guy" in (names_inact | names_active)


# ---------------------------------------------------------------------------
# Debut event injection on level_changes
# ---------------------------------------------------------------------------

class TestDebutMarkerInLevelChanges:
    """The exporter should mark the first MLB promotion as `kind: "debut"`
    OR synthesize a debut entry when no MLB promotion is in the level-
    changes feed."""

    def test_first_mlb_promotion_is_marked_debut(self, tmp_path):
        from storage import export_timeseries_json
        snaps = [_snap("fangraphs", "Star Rookie", fv=60.0, date_="2026-04-01")]
        ts = build_timeseries(snaps)
        level_changes = {
            "star_rookie": [
                {"date": "2025-07-01", "kind": "promotion",
                 "from_level": "AA", "to_level": "AAA",
                 "from_team": "Altoona Curve", "to_team": "Indianapolis Indians"},
                {"date": "2026-04-15", "kind": "promotion",
                 "from_level": "AAA", "to_level": "MLB",
                 "from_team": "Indianapolis Indians", "to_team": "Pittsburgh Pirates"},
                {"date": "2026-05-01", "kind": "demotion",
                 "from_level": "MLB", "to_level": "AAA",
                 "from_team": "Pittsburgh Pirates", "to_team": "Indianapolis Indians"},
            ],
        }
        # roster_status confirms this is a real debut (vs. a Rule 5 add).
        roster_status = {
            "star_rookie": {
                "mlb_debut_date": "2026-04-15",
                "options_used": 1,
                "rookie_exhausted": False,
            },
        }
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out,
                               level_changes=level_changes,
                               roster_status=roster_status)
        from storage import load_export_unified as _leu; payload = _leu(out)
        player = next(p for p in payload["players"]
                      if p["player_name"] == "Star Rookie")
        lcs = player["level_changes"]
        # The 2026-04-15 AAA→MLB row is converted to the debut entry.
        debut = next((lc for lc in lcs if lc.get("kind") == "debut"), None)
        assert debut is not None
        assert debut["date"] == "2026-04-15"
        assert debut.get("is_debut") is True
        # The earlier AA→AAA promotion stays a promotion.
        promos = [lc for lc in lcs if lc.get("kind") == "promotion"]
        assert len(promos) == 1 and promos[0]["date"] == "2025-07-01"
        # And the subsequent MLB→AAA demotion stays a demotion (only the
        # FIRST MLB move converts to debut; later cup-of-coffee bounces
        # render normally).
        demos = [lc for lc in lcs if lc.get("kind") == "demotion"]
        assert len(demos) == 1 and demos[0]["date"] == "2026-05-01"

    def test_rule5_add_without_real_debut_does_not_mark_debut(self, tmp_path):
        """A Rule 5 protection add appears as an MLB promotion in
        level_changes (the transactions feed marks the to_team as the
        parent MLB club), but if the player never actually played in MLB
        the roster_status has mlb_debut_date=None — so no debut entry."""
        from storage import export_timeseries_json
        snaps = [_snap("fangraphs", "Rule 5 Add", fv=45.0, date_="2026-04-01")]
        ts = build_timeseries(snaps)
        level_changes = {
            "rule_5_add": [
                {"date": "2025-11-18", "kind": "promotion",
                 "from_level": "AAA", "to_level": "MLB",
                 "from_team": "AAA Affiliate", "to_team": "Big Club"},
            ],
        }
        roster_status = {
            "rule_5_add": {
                "mlb_debut_date": None,  # never actually played
                "options_used": 1,
                "rookie_exhausted": False,
            },
        }
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out,
                               level_changes=level_changes,
                               roster_status=roster_status)
        from storage import load_export_unified as _leu; payload = _leu(out)
        player = next(p for p in payload["players"]
                      if p["player_name"] == "Rule 5 Add")
        # The spurious MLB promotion stays as a normal promotion (we
        # don't drop it — the transactions feed says it happened).
        # But no row gets converted to or labelled as "debut".
        assert all(lc.get("kind") != "debut"
                   for lc in player["level_changes"])

    def test_synthesizes_debut_when_no_mlb_promotion_present(self, tmp_path):
        from storage import export_timeseries_json
        snaps = [_snap("fangraphs", "Quiet Debut", fv=50.0, date_="2026-04-01")]
        ts = build_timeseries(snaps)
        # Empty level_changes but roster_status has a debut date — the
        # SE transaction wasn't captured but we know they debuted.
        roster_status = {
            "quiet_debut": {
                "mlb_debut_date": "2026-04-20",
                "options_used": 0,
                "options_remaining": 3,
                "rookie_exhausted": False,
            },
        }
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out, roster_status=roster_status)
        from storage import load_export_unified as _leu; payload = _leu(out)
        player = next(p for p in payload["players"]
                      if p["player_name"] == "Quiet Debut")
        lcs = player["level_changes"]
        assert len(lcs) == 1
        assert lcs[0]["kind"] == "debut"
        assert lcs[0]["date"] == "2026-04-20"
        assert lcs[0]["to_level"] == "MLB"
        assert lcs[0].get("is_debut") is True

    def test_no_debut_when_no_mlb_activity(self, tmp_path):
        from storage import export_timeseries_json
        snaps = [_snap("fangraphs", "Pure Prospect", fv=55.0, date_="2026-04-01")]
        ts = build_timeseries(snaps)
        roster_status = {
            "pure_prospect": {
                "mlb_debut_date": None,
                "options_used": 0,
                "options_remaining": 3,
                "rookie_exhausted": False,
            },
        }
        level_changes = {
            "pure_prospect": [
                {"date": "2025-07-01", "kind": "promotion",
                 "from_level": "A", "to_level": "A+",
                 "from_team": "Fredericksburg", "to_team": "Wilmington"},
            ],
        }
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out,
                               level_changes=level_changes,
                               roster_status=roster_status)
        from storage import load_export_unified as _leu; payload = _leu(out)
        player = next(p for p in payload["players"]
                      if p["player_name"] == "Pure Prospect")
        # No MLB promotion + no debut_date → no debut row added.
        assert all(lc.get("kind") != "debut" for lc in player["level_changes"])


# ---------------------------------------------------------------------------
# revalidate_auto_graduations — self-healing cleanup of legacy auto_detect
# graduation snapshots from pre-fix pipeline runs
# ---------------------------------------------------------------------------

class TestRevalidateAutoGraduations:
    """Older versions of the pipeline auto-graduated any prospect with an
    MLB debut, then wrote a synthetic snapshot to the DB. Those rows
    persist across runs, so even after we tightened the rules the
    affected players still read as graduates. revalidate_auto_graduations
    strips those rows when the player no longer meets current rules."""

    def _setup_db(self, tmp_path, monkeypatch):
        # Point storage at a fresh test DB so we don't clobber the real one.
        db = tmp_path / "test.db"
        import storage
        monkeypatch.setattr(storage, "DB_PATH", db)
        storage.init_db()
        return storage

    def test_clears_sub_threshold_player(self, tmp_path, monkeypatch):
        storage = self._setup_db(tmp_path, monkeypatch)
        # Seed a snapshot for the player + an auto_detect graduated row.
        with storage.connect() as con:
            con.execute(
                """INSERT INTO snapshots (player_key, player_name, source,
                   snapshot_date, interval_label, position, org, rank, fv, status)
                   VALUES ('cup_of_coffee','Cup Coffee','fangraphs',
                           '2026-01-01','FG 2026','OF','PIT',50,55.0,'active')"""
            )
        storage.auto_graduate_player("cup_of_coffee", grad_date="2026-05-18")

        # Player doesn't qualify under current rules → empty set.
        cleared = storage.revalidate_auto_graduations(set())
        assert cleared == 1

        # Confirm the auto_detect row is gone, the fangraphs row remains.
        with storage.connect() as con:
            rows = con.execute(
                "SELECT source, status FROM snapshots WHERE player_key='cup_of_coffee'"
            ).fetchall()
        sources = sorted((r["source"], r["status"]) for r in rows)
        assert sources == [("fangraphs", "active")]

    def test_keeps_legitimately_exhausted_player(self, tmp_path, monkeypatch):
        storage = self._setup_db(tmp_path, monkeypatch)
        with storage.connect() as con:
            con.execute(
                """INSERT INTO snapshots (player_key, player_name, source,
                   snapshot_date, interval_label, position, org, rank, fv, status)
                   VALUES ('real_grad','Real Grad','fangraphs',
                           '2024-01-01','FG 2024','OF','PIT',5,60.0,'active')"""
            )
        storage.auto_graduate_player("real_grad", grad_date="2024-08-15")

        # This player IS in the qualified set, so their auto_detect row stays.
        cleared = storage.revalidate_auto_graduations({"real_grad"})
        assert cleared == 0
        with storage.connect() as con:
            n_auto = con.execute(
                """SELECT COUNT(*) AS n FROM snapshots
                   WHERE player_key='real_grad' AND source='auto_detect'"""
            ).fetchone()["n"]
        assert n_auto == 1

    def test_leaves_fangraphs_graduated_status_alone(self, tmp_path, monkeypatch):
        """A FG-sourced 'graduated' snapshot is external authority — even
        if our local roster_status disagrees, we don't delete it."""
        storage = self._setup_db(tmp_path, monkeypatch)
        with storage.connect() as con:
            con.execute(
                """INSERT INTO snapshots (player_key, player_name, source,
                   snapshot_date, interval_label, position, org, rank, fv, status)
                   VALUES ('fg_graduate','FG Graduate','fangraphs',
                           '2025-10-01','FG 2025 Graduates','OF','PIT',NULL,60.0,'graduated')"""
            )
        # Player not in qualified set, but the only graduated row is the
        # FG one — revalidation must not touch it.
        cleared = storage.revalidate_auto_graduations(set())
        assert cleared == 0
        with storage.connect() as con:
            n_grad = con.execute(
                """SELECT COUNT(*) AS n FROM snapshots
                   WHERE player_key='fg_graduate' AND status='graduated'"""
            ).fetchone()["n"]
        assert n_grad == 1

    def test_idempotent_on_empty_db(self, tmp_path, monkeypatch):
        """No graduation rows present → no-op, returns 0."""
        storage = self._setup_db(tmp_path, monkeypatch)
        assert storage.revalidate_auto_graduations(set()) == 0
        assert storage.revalidate_auto_graduations({"anyone"}) == 0


# ---------------------------------------------------------------------------
# Graduation-date derivation — the clump-fix path
# ---------------------------------------------------------------------------

class TestGraduationDateDerivation:
    """When a graduate has an authoritative MLB API debut date, that wins
    over the stored snapshot date and over the {first_year}-07-01
    placeholder. This is what dissolves the date clumps."""

    def _grad_payload(self, tmp_path, *, name, key,
                      stored_grad_date, api_debut, mlb_seasons):
        from storage import export_timeseries_json
        snaps = [Snapshot(
            source="fangraphs", snapshot_date=stored_grad_date,
            interval_label="FG Graduates",
            player_key=key, player_name=name,
            position="SS", org="PIT", rank=10, fv=55.0,
            status="graduated",
        )]
        ts = build_timeseries(snaps)
        career = {key: [{"season": s, "level": "MLB",
                         "is_pitcher": False, "ab": 200, "games": 60}
                        for s in mlb_seasons]} if mlb_seasons else {}
        roster_status = {key: {"mlb_debut_date": api_debut}} if api_debut else {}
        out = tmp_path / "out.json"
        export_timeseries_json(
            ts, out,
            career_stats=career,
            roster_status=roster_status,
        )
        from storage import load_export_unified as _leu; payload = _leu(out)
        return next(g for g in payload["graduates"] if g["player_name"] == name)

    def test_api_debut_overrides_stored_grad_date(self, tmp_path):
        """The classic clump-dissolving case: stored snapshot says
        2022-07-01 but the API knows the actual debut was 2022-08-17."""
        g = self._grad_payload(
            tmp_path,
            name="Freddy Tarnok", key="freddy_tarnok",
            stored_grad_date="2022-07-01",
            api_debut="2022-08-17",
            mlb_seasons=[2022, 2023],
        )
        assert g["graduation_date"] == "2022-08-17"

    def test_rule5_protection_rolls_forward_to_first_real_season(self, tmp_path):
        """Rule 5 protection adds land on the Nov 18-20 deadline and the
        MLB API sometimes stamps them as `mlbDebutDate`. When the player
        actually played in a LATER season we roll forward instead of
        clumping dozens of players on the same Rule 5 deadline date."""
        g = self._grad_payload(
            tmp_path,
            name="Sixto Sanchez", key="sixto_sanchez",
            stored_grad_date="2019-11-20",
            api_debut="2019-11-20",     # Rule 5 protection day
            mlb_seasons=[2020],         # actually played in 2020
        )
        # Should display 2020 mid-season, not 2019-07-01.
        assert g["graduation_date"] == "2020-07-01"

    def test_late_season_debut_kept_when_career_agrees(self, tmp_path):
        """A regular-season-end debut (Oct 1-5 is the last week of the
        season) is real — we keep the date if career_stats confirms MLB
        activity that same year."""
        g = self._grad_payload(
            tmp_path,
            name="October Debut", key="october_debut",
            stored_grad_date="2024-09-15",
            api_debut="2024-10-05",
            mlb_seasons=[2024],
        )
        # career_stats confirms 2024 MLB activity → keep the API date.
        assert g["graduation_date"] == "2024-10-05"

    def test_offseason_api_debut_with_no_career_collapses(self, tmp_path):
        """If the API says Nov 15 AND career_stats has NO record of MLB
        activity that year, the date is almost certainly a 40-man add
        the API misclassified — collapse to mid-season placeholder."""
        g = self._grad_payload(
            tmp_path,
            name="Phantom Debut", key="phantom_debut",
            stored_grad_date="2024-09-15",
            api_debut="2024-11-15",
            mlb_seasons=[],
        )
        # No MLB games on file → don't trust the November date.
        assert g["graduation_date"] == "2024-07-01"

    def test_falls_back_to_career_year_when_no_api_debut(self, tmp_path):
        """No api_debut available — use the player's first MLB season
        as a mid-season placeholder, ignoring any offseason snapshot
        date."""
        g = self._grad_payload(
            tmp_path,
            name="Kodai Senga", key="kodai_senga",
            stored_grad_date="2025-11-01",   # offseason FG flag
            api_debut=None,
            mlb_seasons=[2023, 2024],
        )
        # First MLB season is 2023; no api_debut to take precedence.
        # Stored grad_date starts with "2025-", not "2023-", so
        # fallback returns "2023-07-01".
        assert g["graduation_date"] == "2023-07-01"

    def test_stored_date_kept_when_inside_debut_year(self, tmp_path):
        """When we don't have an api_debut but the stored snapshot date
        falls inside the player's first MLB season, that snapshot is
        usually a FG mid-season "graduates" flag — keep it as-is."""
        g = self._grad_payload(
            tmp_path,
            name="Mid Season FG", key="mid_season_fg",
            stored_grad_date="2024-06-15",
            api_debut=None,
            mlb_seasons=[2024],
        )
        assert g["graduation_date"] == "2024-06-15"

    def test_no_clumps_for_diverse_api_debuts(self, tmp_path):
        """Sanity sweep: a handful of graduates with distinct API debut
        dates should each surface their own date — no clumping back to
        a shared placeholder."""
        from storage import export_timeseries_json
        cohort = [
            ("Player A", "player_a", "2022-08-17"),
            ("Player B", "player_b", "2022-09-22"),
            ("Player C", "player_c", "2022-06-04"),
            ("Player D", "player_d", "2022-09-04"),
        ]
        snaps = [Snapshot(
            source="fangraphs", snapshot_date="2022-07-01",
            interval_label="FG Graduates",
            player_key=key, player_name=name,
            position="SS", org="PIT", rank=i + 1, fv=55.0,
            status="graduated",
        ) for i, (name, key, _) in enumerate(cohort)]
        ts = build_timeseries(snaps)
        roster_status = {key: {"mlb_debut_date": debut}
                         for _, key, debut in cohort}
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out, roster_status=roster_status)
        from storage import load_export_unified as _leu; payload = _leu(out)
        by_name = {g["player_name"]: g for g in payload["graduates"]}
        dates = sorted(by_name[n]["graduation_date"] for n, _, _ in cohort)
        # All four distinct — no clump on 2022-07-01.
        assert dates == ["2022-06-04", "2022-08-17", "2022-09-04", "2022-09-22"]
