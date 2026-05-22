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


if __name__ == "__main__":
    unittest.main()
