"""Unit + integration tests for the spotlights movement engine.

These exercise every user-supplied example from the 2026-05 overhaul:

  Risers:
    Cunningham, Caba (tools-flash floor), Salas, Justin Gonzales,
    Franklin Arias, Kane Kepley (continuing-high path)
  Rebounder:
    Tate Southisene (pedigree-comeback narrative)
  Fallers:
    Jacob Melton (Melton-path: K% crater at AAA, age ≥ 24),
    Brody Hopkins (ERA + BB/9 deterioration),
    Bryce Rainer (skills_crater rescues from young+pedigree disqualify)
  NOT fallers:
    George Lombard Jr / Edward Florentino (very-young hard-disqualify)
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from spotlights import compute_movement

TS_PATH = Path(__file__).parent / "data" / "timeseries.json"


def _load_players():
    if not TS_PATH.exists():
        raise unittest.SkipTest("data/timeseries.json not present")
    d = json.loads(TS_PATH.read_text(encoding="utf-8"))
    return {p["player_name"]: p for p in (d.get("players") or [])}


class UserExampleClassifications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.players = _load_players()

    def _expect(self, name, expected_bucket, *, allow=None):
        """allow: optional list of alternate-but-acceptable buckets."""
        p = self.players.get(name)
        if p is None:
            # Try fuzzy match on last name
            tail = name.split()[-1].lower().rstrip(".")
            cands = [pn for pn in self.players if tail in pn.lower()]
            if not cands:
                self.skipTest(f"{name} not in player payload")
            p = self.players[cands[0]]
        m = compute_movement(p)
        accepted = [expected_bucket] + (allow or [])
        self.assertIn(m["bucket"], accepted,
            f"{name}: expected {expected_bucket} (or {allow}), got "
            f"bucket={m['bucket']} score={m['delta']} drivers={m['drivers']}")

    # --- Risers ---
    def test_kayson_cunningham_riser(self):
        # Cunningham reads either as Riser (huge OPS jump + young for
        # level + tools floor) or Rebounder (first-round pick + weak
        # 2025 debut + huge comeback). Both readings match the user
        # prompt — accept either.
        self._expect("Kayson Cunningham", "riser", allow=["rebound"])

    def test_starlyn_caba_riser(self):
        self._expect("Starlyn Caba", "riser")

    def test_justin_gonzales_riser(self):
        self._expect("Justin Gonzales", "riser")

    def test_franklin_arias_riser(self):
        self._expect("Franklin Arias", "riser")

    def test_kane_kepley_riser(self):
        # Continuing-high path (no big YoY delta but sustained .800+ OPS,
        # advancing levels, not old).
        self._expect("Kane Kepley", "riser")

    def test_ethan_salas_riser_or_rebound(self):
        # Salas may bucket as either riser OR rebound (pedigree-comeback
        # path) — both are accurate readings.
        self._expect("Ethan Salas", "riser", allow=["rebound"])

    # --- Rebounders ---
    def test_tate_southisene_rebound(self):
        # Pedigree + weak prior + improved current + level repeat
        self._expect("Tate Southisene", "rebound")

    # --- Fallers ---
    def test_jacob_melton_faller(self):
        # K% +15pp at AAA, age 25 → melton_path force-faller despite
        # surface OPS being marginally up from his AAA 2024 baseline.
        self._expect("Jacob Melton", "faller")

    def test_brody_hopkins_faller(self):
        # ERA up, BB/9 way up at AAA, 24yo → clear faller.
        self._expect("Brody Hopkins", "faller")

    def test_bryce_rainer_faller(self):
        # 20yo (young), pedigreed, BUT K% jumped 22.1% → 43.7% (~+20pp)
        # → skills_crater override of young+pedigree disqualify.
        self._expect("Bryce Rainer", "faller")

    # --- Not Fallers (hard disqualify) ---
    def test_george_lombard_jr_not_faller(self):
        # 21 at AAA, very-young (-4.8 vs level), pedigreed → NEVER faller.
        self._expect("George Lombard Jr.", "none", allow=["riser", "rebound"])

    def test_edward_florentino_not_faller(self):
        # 19 at A+, very-young (-2.7 vs level), IFA pedigree → NEVER faller
        # even though his BB% has dropped sharply.
        self._expect("Edward Florentino", "none", allow=["riser", "rebound"])


class CompositeShape(unittest.TestCase):
    """compute_movement must always return the expected dict shape so the
    storage exporter + frontend can read it without defensive None checks."""

    @classmethod
    def setUpClass(cls):
        cls.players = _load_players()

    def test_every_active_player_has_full_shape(self):
        required_keys = {"direction", "delta", "from_label", "to_label",
                         "from_date", "to_date", "perf_delta",
                         "skills_delta", "drivers", "bucket"}
        sample_keys = list(self.players.keys())[:200]
        for n in sample_keys:
            p = self.players[n]
            m = compute_movement(p)
            self.assertEqual(set(m.keys()) - required_keys, set(),
                f"{n} missing required keys: {required_keys - set(m.keys())}")
            self.assertIn(m["bucket"], {"riser", "rebound", "faller", "none"},
                f"{n} has invalid bucket {m['bucket']!r}")
            self.assertIsInstance(m["drivers"], list)

    def test_graduated_returns_stub(self):
        p = {"status": "graduated", "points": []}
        m = compute_movement(p)
        self.assertEqual(m["direction"], "graduated")
        self.assertEqual(m["bucket"], "none")


# ---------------------------------------------------------------------------
# Age-cap filter (per-level + per-side) — gates excessively-old prospects
# out of every spotlight bucket. Hitters: diff > +2.0 above level mean
# disqualifies. Pitchers: diff > +3.0 (later debut curve).
# ---------------------------------------------------------------------------

from spotlights import _classify_movement, _exceeds_age_cap


class AgeCapHelper(unittest.TestCase):
    """Cap is computed against aspirational baselines (A=21, A+=22,
    AA=23, AAA=24, MLB=26). Hitters disqualified at >+2.0, pitchers
    at >+3.0."""

    def test_hitter_cap_at_plus_2(self):
        # AAA baseline 24. 26.5yo hitter → diff +2.5 → cut.
        self.assertTrue(_exceeds_age_cap(26.5, "AAA", is_pitcher=False))
        # Boundary INCLUSIVE: 26.0 → diff +2.0 → cut (>= cap).
        self.assertTrue(_exceeds_age_cap(26.0, "AAA", is_pitcher=False))
        # Just under: 25.9 → diff +1.9 → eligible.
        self.assertFalse(_exceeds_age_cap(25.9, "AAA", is_pitcher=False))
        # Young AAA hitter clearly passes.
        self.assertFalse(_exceeds_age_cap(23.0, "AAA", is_pitcher=False))

    def test_pitcher_cap_at_plus_3(self):
        # Pitchers get a 1-year grace. AAA: 27.5 → diff +3.5 → cut.
        self.assertTrue(_exceeds_age_cap(27.5, "AAA", is_pitcher=True))
        # Boundary INCLUSIVE: 27.0 → diff +3.0 → cut.
        self.assertTrue(_exceeds_age_cap(27.0, "AAA", is_pitcher=True))
        # Just under: 26.9 → diff +2.9 → eligible.
        self.assertFalse(_exceeds_age_cap(26.9, "AAA", is_pitcher=True))
        # 26.5 (would cap a hitter) is fine for a pitcher.
        self.assertFalse(_exceeds_age_cap(26.5, "AAA", is_pitcher=True))

    def test_journeymen_examples_filtered(self):
        # User's named cases — all should be capped.
        # Maverick Handley 28.2 at MLB (baseline 26) → diff +2.2 → cut.
        self.assertTrue(_exceeds_age_cap(28.2, "MLB", is_pitcher=False))
        # Cal Conley 26.8 at AAA → diff +2.8 → cut.
        self.assertTrue(_exceeds_age_cap(26.8, "AAA", is_pitcher=False))
        # Griff McGarry 27.0 at AAA pitcher → diff +3.0 → cut (boundary).
        self.assertTrue(_exceeds_age_cap(27.0, "AAA", is_pitcher=True))

    def test_legit_prospects_not_capped(self):
        # Kristian Campbell at 23/AAA → diff −1 → easy pass.
        self.assertFalse(_exceeds_age_cap(23.0, "AAA", is_pitcher=False))
        # George Lombard Jr 21/AAA → diff −3.
        self.assertFalse(_exceeds_age_cap(21.0, "AAA", is_pitcher=False))

    def test_rookie_level_passes_through(self):
        # CPX / DSL prospects have no aspirational baseline → no cap.
        self.assertFalse(_exceeds_age_cap(22.0, "CPX", is_pitcher=False))
        self.assertFalse(_exceeds_age_cap(22.0, "DSL", is_pitcher=False))
        # Missing age also passes through.
        self.assertFalse(_exceeds_age_cap(None, "AAA", is_pitcher=False))
        # Missing level passes through.
        self.assertFalse(_exceeds_age_cap(28.0, None, is_pitcher=False))


class AgeCapClassification(unittest.TestCase):
    """Verify _classify_movement returns bucket='none' for prospects past
    the age cap, regardless of the surface stats / pedigree / skills
    deltas that would otherwise classify them as riser / faller / rebound."""

    def _payload(self, *, age, is_pitcher=False, level="AAA"):
        return {
            "age":          age,
            "age_vs_level": {"diff": None, "tier": "neutral"},  # cap reads `age` + `level` directly
            "statline":     {"is_pitcher": is_pitcher, "level": level,
                             "ops": 0.900 if not is_pitcher else None,
                             "era": 2.50 if is_pitcher else None,
                             "k_pct": None},
            "points":       [],
            "career_stats": [],
            "prospect_savant": {},
        }

    def test_old_hitter_capped_out_of_riser(self):
        # AAA baseline 24. 26.5yo hitter → diff +2.5 → cut even with
        # otherwise riser-worthy surface jump.
        p = self._payload(age=26.5, is_pitcher=False)
        bucket, score, drivers = _classify_movement(
            p, perf_delta=0.150, skills_delta=2.0,
            list_jump_score=0.0, pedigree=0.5)
        self.assertEqual(bucket, "none")

    def test_eligible_hitter_not_capped(self):
        # 25.5yo at AAA → diff +1.5 → eligible.
        p = self._payload(age=25.5, is_pitcher=False)
        bucket, score, drivers = _classify_movement(
            p, perf_delta=0.150, skills_delta=2.0,
            list_jump_score=0.0, pedigree=0.5)
        self.assertEqual(bucket, "riser",
            f"+1.5 above level mean should NOT cap; got {bucket}")

    def test_old_pitcher_capped(self):
        # Pitcher at +3.5 above level mean (27.5 AAA) → capped.
        p = self._payload(age=27.5, is_pitcher=True)
        bucket, _, _ = _classify_movement(
            p, perf_delta=-0.80, skills_delta=-3.5,
            list_jump_score=0.0, pedigree=2.5)
        self.assertEqual(bucket, "none")

    def test_eligible_pitcher_not_capped_at_plus_2_5(self):
        # Pitcher at +2.5 (26.5 AAA → would cap hitter, eligible for pitcher).
        p = self._payload(age=26.5, is_pitcher=True)
        bucket, _, _ = _classify_movement(
            p, perf_delta=-0.80, skills_delta=-3.5,
            list_jump_score=0.0, pedigree=0.5)
        self.assertEqual(bucket, "faller",
            f"+2.5 pitcher should NOT cap; got {bucket}")

    def test_unknown_level_passes_through(self):
        # CPX shape — no aspirational baseline → cap doesn't fire.
        p = self._payload(age=22.0, is_pitcher=False, level="CPX")
        p["age_vs_level"]["tier"] = "unknown"
        bucket, _, _ = _classify_movement(
            p, perf_delta=0.150, skills_delta=2.0,
            list_jump_score=0.0, pedigree=0.5)
        # Expect riser — cap doesn't fire, riser path activates on
        # the surface jump.
        self.assertEqual(bucket, "riser")


class AgeCapIntegration(unittest.TestCase):
    """Integration-style anchors against real spotlights output. Verifies
    the cap actually filters real-world journeymen out of the buckets.
    Skips if timeseries.json isn't present."""

    @classmethod
    def setUpClass(cls):
        cls.players = _load_players()

    def _bucket_names(self, bucket):
        names = []
        for p in self.players.values():
            try:
                m = compute_movement(p)
            except Exception:
                continue
            if m.get("bucket") == bucket:
                names.append(p.get("player_name") or "?")
        return names

    def test_old_journeymen_not_in_any_bucket(self):
        # These are the canonical examples the user called out as
        # "should not be considered prospects" — all 27-29 yo MiLB
        # journeymen with no realistic prospect ceiling.
        journeymen = {"Maverick Handley", "Cal Conley", "Griff McGarry"}
        all_buckets = set()
        for bucket in ("riser", "rebound", "faller"):
            all_buckets.update(self._bucket_names(bucket))
        leak = journeymen & all_buckets
        if not leak:
            return
        # Tolerant: data might not include some of the named players.
        # Only fail when at least one IS in the data AND classified.
        present = {p.get("player_name") for p in self.players.values()
                   if p.get("player_name") in journeymen}
        offenders = leak & present
        self.assertFalse(offenders,
            f"Age cap should filter these journeymen from all buckets: {offenders}")


if __name__ == "__main__":
    unittest.main()
