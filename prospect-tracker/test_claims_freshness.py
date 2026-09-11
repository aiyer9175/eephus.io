# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Claims-freshness guards (2026-08-19): ARTIFACTS ARE THE SOURCE OF TRUTH.

copy_lint catches voice; this file catches CLAIM drift, in three layers:

1. PHRASE RATCHET: static claim fragments that were live and contradicted
   on 2026-08-19 may never return to a copy surface. Each fragment in
   BANNED_CLAIM_FRAGMENTS carries its own history.
2. GLOSSARY NUMBER CHECKS: the few glossary entries that legitimately
   hand-quote numbers are pinned to their artifacts via GLOSSARY_CLAIMS.
   Adding a check is one table line.
3. REGISTRY NOTE POLICY: rows whose eval artifacts regenerate nightly rot
   if their notes quote bare undated figures. Such notes must carry a
   dated reading marker ("YYYY-MM-DD reading:") no older than 45 days
   against the artifact's own generated date. One seeded stable-gate
   check pins fa_market's card guarantee figure to data/fa_gate2_eval.json.
4. CODE-CONSTANT PINS (Part 4) and the DISCOUNT RATE (Part 5): copy is held to
   the shipped constant it describes, and the Gate-2 note to the rate its own
   table was priced at.

Import-safe and deterministic: no network, no rebuilds, every file read
happens inside a test function.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Part 1: phrase ratchet.
# Every fragment below was a LIVE, artifact-contradicted static claim on
# 2026-08-19. A concurrent repair lane removed the occurrences; this ratchet
# is the guarantee they never return. Matching is case-insensitive substring.
BANNED_CLAIM_FRAGMENTS = (
    # glossary.js hero copy claimed eFV beat all public sources; the
    # vintage-matched head-to-head (2026-08-13) reads +0.0014 at 0.046x,
    # a tie. Copy may say "indistinguishable", never "better".
    "out-predicts every public source",
    # glossary.js source-comparison strings claimed an out-of-sample rank
    # win over consensus FV; B-L6 (2026-08-10) found the shipped win GONE
    # (NULL both estimators). The AUC_FLOOR_GATE contract bans the claim.
    "out-ranks consensus",
    # glossary.js methodology bullet claimed a clean per-archetype Spearman
    # sweep; the pooled comparison never cleared its own noise floor and
    # the rank-equivalence verdict is UNRESOLVED (must not be cited).
    "ahead on Spearman in every archetype",
    # glossary.js consensus copy claimed the pooled blend beats its best
    # single input; the hardened re-measurement (consensus_weight_eval,
    # ship=False) resolved no such gap.
    "beats its best individual",
    # glossary.json consensus_fv methodology carried the same claim in a
    # second wording, citing data/source_backtest.json past its verdict.
    "still beats the best single source",
    # older hero variant of fragment 1; already scrubbed before 2026-08-19,
    # ratcheted here so it cannot be reintroduced from stale drafts.
    "out-predicts the consensus",
    # glossary.js _methAccuracyChart opened with this as FIXED prose and then
    # printed MLB Pipeline ABOVE eFV in the same sentence: on
    # accuracy.pooled_efv_common_vintage_matched the artifact reads eFV 0.3983
    # against Pipeline 0.3990. Derived on 2026-09-04 (design audit F46) to the
    # same three branches _methHeroBanner already uses.
    "ahead of the field",
    # A-CLAIM-9, added 2026-09-06 as a FORWARD ban rather than a repair: none of
    # the five below has ever appeared on a surface, and the point is that they
    # never do.
    #
    # A Bayesian companion artifact is registered for this claim family, and the
    # moment one exists somebody will want to write the sentence it appears to
    # license: "there is an 85 percent probability that eFV is better than the
    # consensus". That is a posterior over a parameter, and a served surface
    # cannot carry it honestly, for two reasons that hold no matter how good the
    # posterior is.
    #
    # First, the number is only as good as its prior, and this platform has no
    # defensible prior on a rank-correlation gap: every prior it could pick is a
    # choice a reader cannot see and cannot argue with. Second, the whole claim
    # frame here is frequentist and pre-registered, with detection floors and an
    # alpha-spending clause, and mixing a posterior probability into copy written
    # against that frame invites a reader to read one as the other. The measured
    # position on 2026-09-06 is that THREE instruments put eFV and the consensus
    # apart by -0.0071, +0.0145 and -0.0001 and NONE of them resolves, which is
    # the sentence the page is entitled to.
    "probability that efv is better",
    "probability efv is better",
    "chance that efv is better",
    "posterior probability that efv",
    "odds that efv beats",
)

# Copy surfaces the ratchet scans. content/*.json is globbed at test time.
CLAIM_SURFACES = (
    "assets/glossary.js",
    "data/glossary.json",
    "index.html",
)

# ---------------------------------------------------------------------------
# Part 2: glossary entries that legitimately retain hand-quoted numbers,
# pinned to their artifacts. One line per check:
#   (entry_id, label, pattern, artifact_rel_path, keypath, tol_mode, tol)
# pattern: regex with ONE capture group, run with findall over the entry's
#   definition + methodology text; every match must agree with the artifact.
#   Zero matches fails loudly (the copy changed shape; update the table).
# tol_mode "abs": |claim - actual| <= tol.
# tol_mode "rel": |claim - actual| <= tol * |actual| (copy rounds).
GLOSSARY_CLAIMS = (
    # war_pa_plus quotes its own honest loss: forward Spearman 0.3711 for
    # the rate index vs 0.4058 for plain season WAR (v2 convention, hit
    # pool). Measured on eWAR since the lab's 2026-09-11 re-point (audit
    # F10-01); the batting side reads the same as bWAR, so these two did not
    # move. Tight abs tolerance: these are quoted to four decimals.
    ("war_pa_plus", "hit rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_pa_plus", "hit war_total baseline (v2)", r"predicts the same thing at (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
    # The pitcher entries and the three 3-year entries quote the same ledger and
    # were unpinned, which is how their bWAR-era figures (0.2688 / 0.0886 and
    # the 0.1335 window read) would have outlived the eWAR re-point that moved
    # them to 0.4726 / 0.2323 / 0.259. Pinned from 2026-09-11.
    ("war_ip_plus_sp", "SP rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_ip_plus_sp", "SP war_total baseline (v2)", r"plain season WAR \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
    ("war_ip_plus_sp", "SP rate baseline (v2)", r"unstandardized \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "results_by_convention", "v2", "rho_baselines", "rate"), "abs", 0.005),
    ("war_ip_plus_rp", "RP rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_ip_plus_rp", "RP war_total baseline (v2)", r"plain season WAR \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
    ("war_ip_plus_rp", "RP rate baseline (v2)", r"unstandardized \((0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "results_by_convention", "v2", "rho_baselines", "rate"), "abs", 0.005),
    ("war_pa_plus_3yr", "hit 3yr window rho (v2)", r"Spearman correlation of (0\.\d+) against",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "window_gate", "results_by_convention", "v2", "rho_window"), "abs", 0.005),
    ("war_pa_plus_3yr", "hit one-season rho (v2)", r"against (0\.\d+) for one season",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "window_gate", "results_by_convention", "v2", "rho_one_season"), "abs", 0.005),
    ("war_ip_plus_sp_3yr", "SP 3yr window rho (v2)", r"Spearman correlation of (0\.\d+) against",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "window_gate", "results_by_convention", "v2", "rho_window"), "abs", 0.005),
    ("war_ip_plus_sp_3yr", "SP one-season rho (v2)", r"against (0\.\d+) for one season",
     "data/war_rate_plus_eval.json",
     ("pools", "SP", "window_gate", "results_by_convention", "v2", "rho_one_season"), "abs", 0.005),
    ("war_ip_plus_rp_3yr", "RP 3yr window rho (v2)", r"Spearman correlation of (0\.\d+) against",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "window_gate", "results_by_convention", "v2", "rho_window"), "abs", 0.005),
    ("war_ip_plus_rp_3yr", "RP one-season rho (v2)", r"against (0\.\d+) for one season",
     "data/war_rate_plus_eval.json",
     ("pools", "RP", "window_gate", "results_by_convention", "v2", "rho_one_season"), "abs", 0.005),
    # milb_translation quotes its LOO validation block. MAE rows use a
    # relative 0.15 band (copy rounds 3.937 to ~4.0). r2 rows use abs 0.02:
    # loose enough for two-decimal rounding (0.32 vs 0.319 passes), tight
    # enough that the observed 0.35-vs-0.319 drift FAILS.
    # The copy phrases these as dated readings ("2026-08 fit: ..."), so the
    # patterns tolerate a date prefix and comma-separated (unparenthesised)
    # validation clauses.
    ("milb_translation", "hit_k r2 (definition)", r"reliable read \([^)]*r2 ~?(0\.\d+)\)",
     "data/milb_translation.json", ("validation", "hit_k", "r2"), "abs", 0.02),
    ("milb_translation", "hit_k LOO MAE", r"K% LOO MAE ~?(\d+\.?\d*)",
     "data/milb_translation.json", ("validation", "hit_k", "mae"), "rel", 0.15),
    ("milb_translation", "hit_k r2 (methodology)", r"K% LOO MAE [^;]*?r2 ~?(0\.\d+)",
     "data/milb_translation.json", ("validation", "hit_k", "r2"), "abs", 0.02),
    ("milb_translation", "hit_bb MAE", r"BB% MAE ~?(\d+\.?\d*)",
     "data/milb_translation.json", ("validation", "hit_bb", "mae"), "rel", 0.15),
    ("milb_translation", "hit_bb r2", r"BB% MAE [^;(]*?r2 ~?(0\.\d+)",
     "data/milb_translation.json", ("validation", "hit_bb", "r2"), "abs", 0.02),
    # ewar quotes its gate record (eWAR epoch 2026-09-03). The four numbers
    # are the basis-decision record: the descriptive loss and the persistence
    # gain must always be printed together, so both sides of each are pinned.
    ("ewar", "gate 1 team wins r (eWAR)", r"team wins over 300 team-seasons, r (0\.\d+)",
     "data/ewar_eval.json", ("gate_1_team_wins", "ewar", "r"), "abs", 0.0005),
    ("ewar", "gate 1 team wins r (bWAR)", r"team-seasons, r 0\.\d+ against bWAR (0\.\d+)",
     "data/ewar_eval.json", ("gate_1_team_wins", "bwar", "r"), "abs", 0.0005),
    ("ewar", "gate 2 persistence (eWAR FIP)", r"\(min 50 IP\), (0\.\d+)",
     "data/ewar_eval.json", ("gate_2_pitcher_persistence", "self_r_ewar_fip"), "abs", 0.0005),
    ("ewar", "gate 2 persistence (bWAR RA)", r"\(min 50 IP\), 0\.\d+ against (0\.\d+)",
     "data/ewar_eval.json", ("gate_2_pitcher_persistence", "self_r_bwar_ra"), "abs", 0.0005),
    # bust_prob names its training size because the provenance IS the claim
    # (design audit F07): the curve is fitted on the Clemens 2025 published
    # percentage tables, not on our resolved cohorts. Integer counts, so the
    # tolerance is sub-unit.
    ("bust_prob", "training_n hitter", r"training_n is (\d+) hitter",
     "data/value_framework_fitted.json", ("training_n", "hitter"), "abs", 0.5),
    ("bust_prob", "training_n pitcher", r"training_n is \d+ hitter and (\d+) pitcher",
     "data/value_framework_fitted.json", ("training_n", "pitcher"), "abs", 0.5),
    # Audit L16-16 (2026-09-11): three unpinned entries had drifted from their
    # artifacts (sem_plus quoted 0.39 / 0.26 / 0.36 against 0.4167 / 0.2843 /
    # 0.3821; riv_plus 0.21 / 0.35 against 0.2023 / 0.3601), and the FV -> WAR
    # EV table quoted FV 40 at 0.09 against a served 0.071. Each quoted number
    # is now held to its artifact. Two-decimal copy, so abs 0.005; the FV 40
    # knot is quoted to three decimals and held tighter.
    ("sem_plus", "forward rho SEM+", r"at a Spearman correlation of (0\.\d+), beating ERA",
     "data/sem_plus_eval.json", ("forward_spearman_vs_RA9_next", "sem_plus"), "abs", 0.005),
    ("sem_plus", "forward rho ERA", r"beating ERA \((0\.\d+)",
     "data/sem_plus_eval.json", ("forward_spearman_vs_RA9_next", "era"), "abs", 0.005),
    ("sem_plus", "forward rho raw FIP", r"raw-FIP parent \((0\.\d+)\)",
     "data/sem_plus_eval.json", ("forward_spearman_vs_RA9_next", "raw_fip"), "abs", 0.005),
    ("riv_plus", "RIV+ year-to-year rho", r"rank correlation is (0\.\d+) against",
     "data/riv_plus_eval.json", ("forward_stability_check", "riv_plus_y_to_y1_rho"), "abs", 0.005),
    ("riv_plus", "REM+ year-to-year rho", r"rank correlation is 0\.\d+ against (0\.\d+) for REM\+",
     "data/riv_plus_eval.json", ("forward_stability_check", "rem_plus_y_to_y1_rho"), "abs", 0.005),
    ("fv_to_war_table", "EV anchor FV 40", r"FV 40 (\d\.\d+)",
     "data/value_framework_fitted.json", ("empirical_anchors", "anchors", "40"), "abs", 0.0005),
    ("fv_to_war_table", "EV anchor FV 50", r"FV 50 (\d\.\d+)",
     "data/value_framework_fitted.json", ("empirical_anchors", "anchors", "50"), "abs", 0.005),
    ("fv_to_war_table", "EV anchor FV 60", r"FV 60 (\d\.\d+)",
     "data/value_framework_fitted.json", ("empirical_anchors", "anchors", "60"), "abs", 0.005),
)

# ---------------------------------------------------------------------------
# Part 3: registry note policy.
# Rows whose eval artifact regenerates nightly: bare undated performance
# numbers in notes ALWAYS rot. Policy: the notes must carry at least one
# dated reading marker, and the newest marker must sit within
# READING_MAX_AGE_DAYS of the artifact's generated date.
NIGHTLY_NOTE_MODELS = ("betting_game_prob", "betting_elo_benchmark", "stuff_plus_aaa")
READING_RE = re.compile(r"(20\d\d-\d\d-\d\d) reading:")
READING_MAX_AGE_DAYS = 45

# Stable-gate figure pins. One line per check:
#   (model_id, headline label substring, artifact_rel_path, keypath, abs_tol)
# The row's card.headline champion figure must match the gate artifact.
STABLE_GATE_CHECKS = (
    ("fa_market", "guarantee", "data/fa_gate2_eval.json",
     ("pooled", "guarantee", "mae_model"), 0.05),
)


# ---------------------------------------------------------------------------
# helpers (pure readers; no file IO at import time)

def _read_json(rel):
    with open(ROOT / rel, encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _dig(obj, keypath):
    for key in keypath:
        obj = obj[key]
    return obj


def _glossary_entry(entry_id):
    entries = _read_json("data/glossary.json")["entries"]
    hits = [e for e in entries if e.get("id") == entry_id]
    assert hits, f"glossary entry missing: {entry_id} (update GLOSSARY_CLAIMS if renamed)"
    return hits[0]


def _entry_text(entry):
    return (entry.get("definition") or "") + "\n" + (entry.get("methodology") or "")


def _registry_row(model_id):
    models = _read_json("data/model_registry.json")["models"]
    hits = [m for m in models if m.get("model_id") == model_id]
    assert hits, f"registry row missing: {model_id}"
    return hits[0]


def _parse_iso_date(stamp):
    """First 10 chars of an ISO stamp ('2026-08-19' or '2026-08-19T19:16:25+00:00')."""
    return date.fromisoformat(str(stamp)[:10])


def _within(claimed, actual, tol_mode, tol):
    if tol_mode == "abs":
        return abs(claimed - actual) <= tol
    if tol_mode == "rel":
        return abs(claimed - actual) <= tol * abs(actual)
    raise ValueError(f"unknown tol_mode {tol_mode!r}")


# ---------------------------------------------------------------------------
# Part 1 tests

def _ratchet_surfaces():
    surfaces = list(CLAIM_SURFACES)
    surfaces += sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in (ROOT / "content").glob("*.json")
    )
    return surfaces


def test_banned_claim_fragments_absent():
    """The ratchet: contradicted static claims never return to a copy surface."""
    violations = []
    for rel in _ratchet_surfaces():
        text = _read_text(rel).lower()
        for frag in BANNED_CLAIM_FRAGMENTS:
            if frag.lower() in text:
                violations.append(f"{rel}: {frag!r}")
    assert not violations, (
        "banned static claim fragment(s) present (each was a live "
        "contradicted claim on 2026-08-19; accuracy copy derives from "
        "artifacts at render time, it is never hand-written): "
        + "; ".join(violations)
    )


def test_ratchet_surfaces_exist():
    """A ratchet over a missing file is a silent no-op; refuse that."""
    for rel in _ratchet_surfaces():
        assert (ROOT / rel).is_file(), f"ratchet surface missing: {rel}"


# ---------------------------------------------------------------------------
# Part 2 tests

def test_glossary_numbers_match_artifacts():
    """Every hand-quoted glossary number in GLOSSARY_CLAIMS agrees with its
    artifact. Zero regex matches is itself a failure: the copy changed shape
    and the table must follow it, not silently stop checking."""
    problems = []
    for entry_id, label, pattern, artifact, keypath, tol_mode, tol in GLOSSARY_CLAIMS:
        text = _entry_text(_glossary_entry(entry_id))
        actual = float(_dig(_read_json(artifact), keypath))
        matches = re.findall(pattern, text)
        if not matches:
            problems.append(
                f"{entry_id}/{label}: pattern {pattern!r} found no number; "
                f"the entry copy changed, update GLOSSARY_CLAIMS"
            )
            continue
        for raw in matches:
            claimed = float(raw)
            if not _within(claimed, actual, tol_mode, tol):
                problems.append(
                    f"{entry_id}/{label}: copy quotes {claimed} but {artifact} "
                    f"{'/'.join(keypath)} = {actual} (tol {tol_mode} {tol})"
                )
    assert not problems, "glossary claim drift: " + "; ".join(problems)


# ---------------------------------------------------------------------------
# Part 3 tests

def test_nightly_registry_notes_carry_dated_readings():
    """Rows over nightly-regenerating artifacts must date-stamp every quoted
    reading and keep the newest stamp within READING_MAX_AGE_DAYS of the
    artifact's generated date."""
    problems = []
    for model_id in NIGHTLY_NOTE_MODELS:
        row = _registry_row(model_id)
        notes = row.get("notes") or ""
        stamps = READING_RE.findall(notes)
        if not stamps:
            problems.append(
                f"{model_id}: notes carry no 'YYYY-MM-DD reading:' marker; "
                f"its eval artifact regenerates nightly, so undated "
                f"performance numbers in notes always rot"
            )
            continue
        newest = max(date.fromisoformat(s) for s in stamps)
        artifact = row.get("eval_artifact")
        assert artifact, f"{model_id}: nightly row with no eval_artifact"
        generated = _parse_iso_date(_read_json(artifact)["generated_at"])
        age = abs((generated - newest).days)
        if age > READING_MAX_AGE_DAYS:
            problems.append(
                f"{model_id}: newest dated reading {newest} is {age} days "
                f"from {artifact} generated_at {generated} "
                f"(max {READING_MAX_AGE_DAYS}); refresh the reading"
            )
    assert not problems, "stale nightly registry notes: " + "; ".join(problems)


def test_stable_gate_figures_match_artifacts():
    """Seeded stable-gate pins: the registry card headline figure must match
    the gate artifact it summarizes."""
    problems = []
    for model_id, label_frag, artifact, keypath, tol in STABLE_GATE_CHECKS:
        row = _registry_row(model_id)
        card = row.get("card") or {}
        headlines = [
            h for h in card.get("headline", [])
            if label_frag.lower() in str(h.get("label", "")).lower()
        ]
        if not headlines:
            problems.append(
                f"{model_id}: no card headline whose label contains "
                f"{label_frag!r}; the gate figure must live on the card"
            )
            continue
        actual = float(_dig(_read_json(artifact), keypath))
        for h in headlines:
            claimed = float(h["champion"])
            if abs(claimed - actual) > tol:
                problems.append(
                    f"{model_id}: card headline {h.get('label')!r} quotes "
                    f"champion {claimed} but {artifact} {'/'.join(keypath)} "
                    f"= {actual} (abs tol {tol})"
                )
    assert not problems, "stable gate figure drift: " + "; ".join(problems)


# ---------------------------------------------------------------------------
# Part 4: code-constant pins (2026-09-04, design audit section 6).
# Layer 2 pins copy to ARTIFACTS. These pin copy to SHIPPED CODE CONSTANTS,
# which is where the two worst stale claims lived: a retired calibration
# described as live, and a borrowed training set described as our own.

# Phrases that only make sense while the served dispersion correction is a LIVE
# affine map. efv_score._DISPERSION_CORRECTION has been identity since
# 2026-08-14 (C-7 revert), so while it is identity none of these may appear on a
# copy surface, and the retirement must be disclosed instead.
LIVE_SLOPE_CLAIMS = (
    "brings the calibration slope to about 1.0",
    "an affine correction fitted out of fold",
    "the affine dispersion correction now",
)
RETIRED_SLOPE_DISCLOSURES = (
    "level calibration, retired 2026-08-14",
    "the served war is the model's war",
)


# The surfaces that state the valuation conventions in prose. assets/fa.js
# joined 2026-09-11 (audit F12-04): its deferral tooltip quoted a 9% rate that
# no pin could see because the file was never scanned. The Gate-2 artifacts
# (data/fa_gate2_eval.json, data/fa_meta.json) are NOT here: they are pipeline
# output, and test_served_gate2_note_names_the_rate_its_table_was_priced_at
# holds them to the rate they were priced at instead.
_VALUATION_COPY_SURFACES = ("data/glossary.json", "assets/glossary.js",
                            "docs/METHODOLOGY.md", "assets/fa.js")


def _copy_text_lower():
    """The valuation copy surfaces, lowercased, one blob."""
    return ("\n".join(_read_text(rel)
                      for rel in _VALUATION_COPY_SURFACES)).lower()


def test_glossary_dispersion_claim_matches_served_constant():
    """The glossary may not describe a live slope correction while
    efv_score._DISPERSION_CORRECTION is identity, and may not describe the
    correction as retired while it is armed. Reads the CONSTANT, not a doc."""
    import efv_score

    corr = efv_score._DISPERSION_CORRECTION
    assert set(corr) == {"hit", "pit"}, f"unexpected correction keys: {sorted(corr)}"
    identity = all(abs(float(a)) <= 1e-12 and abs(float(b) - 1.0) <= 1e-12
                   for a, b in corr.values())
    text = _copy_text_lower()
    live_hits = [f for f in LIVE_SLOPE_CLAIMS if f in text]
    retired_hits = [f for f in RETIRED_SLOPE_DISCLOSURES if f in text]
    if identity:
        assert not live_hits, (
            "efv_score._DISPERSION_CORRECTION is identity "
            f"({corr}) but copy still describes a live slope correction: "
            + "; ".join(repr(f) for f in live_hits)
        )
        assert retired_hits, (
            "efv_score._DISPERSION_CORRECTION is identity but no copy surface "
            "discloses the retirement; one of "
            + "; ".join(repr(f) for f in RETIRED_SLOPE_DISCLOSURES)
            + " must be present so the reader is not left with the pre-revert story"
        )
    else:
        assert not retired_hits, (
            f"efv_score._DISPERSION_CORRECTION is armed ({corr}) but copy still "
            "says the correction is retired / identity: "
            + "; ".join(repr(f) for f in retired_hits)
        )


def test_glossary_platt_constants_match_module():
    """bust_prob quotes the served odds Platt map. Pin it to the module the
    scoring seams actually call."""
    import efv_odds_calibration

    text = _entry_text(_glossary_entry("bust_prob"))
    m = re.search(r"A/B (\d\.\d+)/(\d\.\d+) hitter and (\d\.\d+)/(\d\.\d+) pitcher", text)
    assert m, ("bust_prob no longer quotes the Platt map in the pinned shape; "
               "update this test with the copy")
    claimed = {"hit": (float(m.group(1)), float(m.group(2))),
               "pit": (float(m.group(3)), float(m.group(4)))}
    for side, (a, b) in claimed.items():
        act_a, act_b = efv_odds_calibration._PLATT[side]
        assert abs(a - act_a) <= 5e-4 and abs(b - act_b) <= 5e-4, (
            f"bust_prob quotes {side} Platt ({a}, {b}) but "
            f"efv_odds_calibration._PLATT[{side!r}] = ({act_a}, {act_b})"
        )


# The accuracy verdict under the head-to-head bars is DERIVED from the backtest
# artifact at render time. A hard-coded accuracy NUMBER in that template is the
# defect that produced "eFV orders realized WAR ahead of the field" printed
# beside a Pipeline figure above eFV, so the guard is structural: no literal
# with three or more decimals may appear inside the function.
_ACC_FN_RE = re.compile(
    r"function _methAccuracyChart\(bt\) \{(.*?)\n\}\n", re.S)
_HARDCODED_DECIMAL_RE = re.compile(r"\b\d+\.\d{3,}\b")


def test_accuracy_chart_verdict_is_derived():
    js = _read_text("assets/glossary.js")
    m = _ACC_FN_RE.search(js.replace("\r\n", "\n"))
    assert m, "_methAccuracyChart not found in assets/glossary.js (renamed?)"
    body = m.group(1)
    # Strip comments: the block comment ABOVE the copy is allowed to cite the
    # measurement that motivated the fix; the rendered copy is not.
    code = "\n".join(ln for ln in body.split("\n")
                     if not ln.lstrip().startswith("//"))
    bad = _HARDCODED_DECIMAL_RE.findall(code)
    assert not bad, (
        "_methAccuracyChart carries hard-coded accuracy constant(s) "
        f"{bad}; the verdict must be derived from the backtest artifact "
        "(banned-experiment ledger item 9)"
    )
    assert "bestPub" in code and "reduce(" in code, (
        "_methAccuracyChart no longer derives the best public rater by "
        "max over the rater list; the three-branch verdict depends on it"
    )


# Control-window and discount copy must track the ACTIVE valuation set, not the
# base config. The shipped set is clemens_2026 (7 control years, net 7%); the
# base config still carries the legacy 6 / 9% and copy kept quoting those.
_CONTROL_PHRASES = (
    "control years", "controlled seasons", "years of team control",
    "cost-controlled years",
)
_NUMWORD = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
            8: "eight", 9: "nine", 10: "ten"}

# Every phrasing that binds a number to THE platform discount rate. Until
# 2026-09-11 the pin below matched only "net N percent", so it saw three correct
# 7s and none of the stale 9s phrased without the word "net" (audit F12-04):
# "discounts at 9%", "the platform 9% rate", "the platform's 9% rate", "the same
# 9% NPV currency", "(1+0.09)^years-out". Each pattern captures ONE number:
# "pct" rows a percent, "dec" rows a decimal rate. test_the_discount_ratchet_
# sees_every_retired_phrasing proves every retired string trips it.
#
# Deliberately NOT matched, because each is true on the current copy: "a 10
# percent discount rate minus 3 percent annual win-cost growth" (the gross rate
# the net one is built from), "the base config's 6 control years and 9 percent
# discount are the legacy prospx_current values" and "discount_rate: 0.09" (the
# disclosed legacy value), and "the CBT's ~4.4% statutory rate" (a different
# rate, named as one).
_PCT = r"(\d+(?:\.\d+)?)\s*(?:%|percent)"
DISCOUNT_RATE_PATTERNS = (
    ("net N%", "pct", r"\bnet " + _PCT),
    ("platform N%", "pct",
     r"\bplatform(?:'s)?\s+(?:configured\s+)?(?:net\s+)?" + _PCT),
    ("discounts at N%", "pct",
     r"\bdiscount(?:s|ed|ing)?\s+at\s+(?:the\s+)?(?:platform(?:'s)?\s+)?"
     r"(?:configured\s+)?(?:net\s+)?" + _PCT),
    ("N% NPV", "pct", _PCT + r"\s+npv\b"),
    ("N% platform rate", "pct", _PCT + r"\s+platform\s+rate\b"),
    ("(1+r)^t literal", "dec", r"\(\s*1\s*\+\s*(0\.\d+)\s*\)\s*\^"),
    ("net rate decimal", "dec", r"\bnet[ _]rate:?\s+(0\.\d+)"),
)


def _discount_rate_claims(text):
    """[(pattern label, claimed rate in percent, snippet)] over LOWERCASED text."""
    out = []
    for label, kind, pat in DISCOUNT_RATE_PATTERNS:
        for m in re.finditer(pat, text):
            v = float(m.group(1)) * (100.0 if kind == "dec" else 1.0)
            out.append((label, v, text[max(0, m.start() - 40):m.end() + 20]))
    return out


def test_control_window_and_discount_copy_match_valuation_set():
    import value_framework

    cfg = value_framework._config()
    control_years = int(cfg["service_time"]["control_years"])
    discount_pct = float(cfg["discount_rate"]) * 100
    text = _copy_text_lower()

    wrong = []
    for n, word in _NUMWORD.items():
        if n == control_years:
            continue
        for phrase in _CONTROL_PHRASES:
            if f"{word} {phrase}" in text:
                wrong.append(f"{word} {phrase}")
    assert not wrong, (
        f"the active valuation set serves {control_years} control years "
        f"(value_framework._config service_time.control_years) but copy says: "
        + "; ".join(sorted(set(wrong)))
    )

    claims = _discount_rate_claims(text)
    nets = [c for c in claims if c[0] == "net N%"]
    assert nets, ("no copy surface states the net discount rate; the surplus "
                  "copy must name it so this pin has something to check")
    off = [c for c in claims if abs(c[1] - discount_pct) > 0.05]
    assert not off, (
        f"the active valuation set discounts at {discount_pct:g} percent "
        f"(value_framework._config discount_rate) but copy quotes: "
        + "; ".join(f"{label} -> {v:g} in {snip!r}" for label, v, snip in off)
    )


def test_the_forward_bans_actually_fire(tmp_path, monkeypatch):
    """A ratchet nobody has tripped is a ratchet nobody has tested, and the five
    A-CLAIM-9 fragments are FORWARD bans: none has ever appeared on a surface, so
    unlike the rest of the tuple they have no history proving they match.

    This writes each one into a scratch surface and asserts the scan catches it.
    """
    surf = tmp_path / "fake_surface.js"
    forward = ("probability that eFV is better",
               "probability eFV is better",
               "chance that eFV is better",
               "posterior probability that eFV",
               "odds that eFV beats")
    for frag in forward:
        surf.write_text(f"var hero = 'There is an 85% {frag} the consensus';",
                        encoding="utf-8")
        text = surf.read_text(encoding="utf-8").lower()
        hits = [f for f in BANNED_CLAIM_FRAGMENTS if f.lower() in text]
        assert hits, f"the ratchet does not catch {frag!r}"


def test_a_posterior_claim_is_banned_even_though_no_posterior_exists_yet():
    """The ban is deliberately AHEAD of the artifact it constrains. The Bayesian
    companion is registered and unbuilt, and the sentence it appears to license
    is the one a served surface must never carry: the number is only as good as
    a prior a reader cannot see, and the rest of this claim frame is
    pre-registered and frequentist."""
    joined = " ".join(BANNED_CLAIM_FRAGMENTS).lower()
    assert "probability that efv is better" in joined
    assert "posterior probability that efv" in joined


# ---------------------------------------------------------------------------
# Part 5: the discount rate (audit F12-01 to F12-04, 2026-09-09).
#
# value_framework._config()["discount_rate"] is 0.07 under clemens_2026. Six
# served strings quoted the legacy 9 percent beside it, one of them on the Free
# Agency Model Accountability page over a 1,199-row table priced at 7, and the
# deferral_npv card named an Ohtani figure ($197M) that was the 9 percent rate
# AND a retired count-from-1 offset at once. No test compared any of them with
# the engine. These do.

# Verbatim retired strings (lowercased), one per surface they lived on.
_RETIRED_DISCOUNT_PHRASINGS = (
    "each control season still escalates with $/war inflation and discounts at 9%.",
    "schedules in the curated deferral ledger discount at the platform 9% rate",
    "because rational value and pick values share the same 9% npv currency",
    "escalated per season and discounted at the platform's 9% rate",
    "contract dollars discounted for deferral schedules at the platform 9% rate",
    "npv = sum of scheduled payments / (1+0.09)^years-out",
    "the 9% platform rate is deliberately harsher than the cbt's ~4.4% statutory rate",
    "seasons and discounts at the platform 9%; arb/pre-arb seasons",
    'title="deferral-adjusted npv at the platform 9% rate - the basis the prediction speaks"',
    "guarantee/aav in $m npv (deferral-adjusted at the platform 9% rate; "
    "no-schedule deals keep sticker)",
)
# True sentences that sit next to a discount rate and must NOT trip it.
_TRUE_RATE_NEIGHBOURS = (
    "a 10 percent discount rate minus 3 percent annual win-cost growth",
    "a 10% discount rate minus 3% annual win-cost growth",
    "the base config's 6 control years and 9 percent discount are the legacy "
    "prospx_current values",
    "the base config's 6 years / 9% are the legacy prospx_current values",
    "`discount_rate: 0.09` and `dollars_per_war_inflation: 0.05`",
    "harsher than the cbt's ~4.4% statutory rate",
    "a 97%-deferred sticker is not the same liability as level cash",
)


def test_the_discount_ratchet_sees_every_retired_phrasing():
    """A ratchet nobody has tripped is a ratchet nobody has tested. Every string
    the net-only pin let through must now produce a 9, and every true neighbour
    must produce nothing, or the pin turns red on correct copy."""
    for s in _RETIRED_DISCOUNT_PHRASINGS:
        vals = [v for _, v, _ in _discount_rate_claims(s)]
        assert vals and all(abs(v - 9.0) < 1e-9 for v in vals), (s, vals)
    for s in _TRUE_RATE_NEIGHBOURS:
        assert not _discount_rate_claims(s), (s, _discount_rate_claims(s))


def test_deferral_npv_ohtani_figure_matches_the_engine():
    """The card's worked example is a served number, so it is held to the
    function the payload calls, at the configured rate."""
    import fa_market as fm

    text = _entry_text(_glossary_entry("deferral_npv")).lower()
    quoted = re.findall(r"ohtani's \$700m prices as ~?\$(\d+(?:\.\d+)?)m", text)
    assert quoted, ("deferral_npv no longer quotes Ohtani's present liability in "
                    "the pinned shape; update this test with the copy")
    npv, had = fm.npv_guarantee_usd("shohei_ohtani", 2024, 700_000_000)
    assert had, "the deferral ledger lost Ohtani's schedule; the example has nothing under it"
    for raw in quoted:
        assert abs(float(raw) - npv / 1e6) <= 0.05, (
            f"deferral_npv says Ohtani prices at ${raw}M but "
            f"fa_market.npv_guarantee_usd reads ${npv / 1e6:.1f}M at "
            f"{fm._discount_rate():g}")


def test_deferral_npv_rescale_clause_describes_the_serving_path(monkeypatch):
    """The audit proposed deleting "schedules rescaled to the sticker total" as a
    rescale the code does not do, measuring deferral_npv_usd alone. The serving
    path is npv_guarantee_usd, and it rescales. This keeps the clause and the
    behaviour together: if the rescale is ever removed, the clause goes too."""
    import fa_market as fm

    text = _entry_text(_glossary_entry("deferral_npv")).lower()
    assert "rescaled to the sticker total" in text
    fake = {"x:2030": {"schedule": [{"year_offset": 0, "amount_usd": 60_000_000},
                                    {"year_offset": 5, "amount_usd": 60_000_000}]}}
    monkeypatch.setattr(fm, "_deferral_ledger", lambda: fake)
    npv, had = fm.npv_guarantee_usd("x", 2030, 100_000_000)
    r = fm._discount_rate()
    want = int(50_000_000 + 50_000_000 / (1 + r) ** 5)   # 120M nominal -> 100M sticker
    assert had and abs(npv - want) <= 1, (npv, want)


def test_no_copy_surface_types_a_fallback_discount_rate():
    """A missing rate renders as words, never as a legacy number: the surplus
    walk in assets/glossary.js printed 9%/yr whenever the payload lacked one."""
    bad = []
    for rel in ("assets/glossary.js", "assets/fa.js"):
        for m in re.finditer(r"discount_rate\s*(?:\|\||\?\?)\s*\d*\.\d+", _read_text(rel)):
            bad.append(f"{rel}: {m.group(0)!r}")
    assert not bad, "typed fallback discount rate(s): " + "; ".join(bad)


def test_gate2_npv_note_is_interpolated_from_the_rate_it_is_given():
    """The SOURCE half of F12-01. fa_backtest used to type "platform 9% rate"
    into the Gate-2 notes; the note must now move with the rate, and the
    production call must hand it the engine's own rate and stamp it."""
    import inspect

    import fa_backtest as fb

    for rate in (0.07, 0.09, 0.075):
        npv_notes = [n for n in fb.gate2_notes(rate) if "deferral-adjusted" in n]
        assert len(npv_notes) == 1, fb.gate2_notes(rate)
        vals = [v for _, v, _ in _discount_rate_claims(npv_notes[0].lower())]
        assert vals and all(abs(v - rate * 100) < 1e-6 for v in vals), (rate, npv_notes, vals)
    src = inspect.getsource(fb.run_market_gate)
    for needle in ("disc_rate = fm._discount_rate()", '"discount_rate": disc_rate',
                   '"notes": gate2_notes(disc_rate)'):
        assert needle in src, f"run_market_gate no longer carries {needle!r}"
    assert not re.search(r"platform(?:'s)?\s+\d+(?:\.\d+)?\s*%", src), (
        "run_market_gate types a platform rate again")


def _gate2_ohtani_rows(g):
    return [m for k in ("biggest_misses", "biggest_misses_years", "biggest_misses_aav")
            for m in (g.get(k) or [])
            if m.get("player") == "Shohei Ohtani" and m.get("winter") == 2024]


def test_gate2_table_is_priced_at_the_configured_discount_rate():
    """The table the note describes, checked from inside. Ohtani's 2024 signing
    is a deferral-scheduled actual, so its NPV names the rate the table was
    priced at: 274.8 at 7 percent, 214.9 at 9. This is what shows the note was
    wrong and the table right, and it goes red if the engine's rate moves
    without a Gate-2 regen."""
    import fa_market as fm

    g = _read_json("data/fa_gate2_eval.json")
    rows = _gate2_ohtani_rows(g)
    if not rows:
        pytest.skip("Ohtani's 2024 signing is not among the published misses, so "
                    "no row inside the table names its rate")
    npv, had = fm.npv_guarantee_usd("shohei_ohtani", 2024, 700_000_000)
    assert had
    for m in rows:
        assert abs(float(m["actual_guar_mm"]) - npv / 1e6) <= 0.051, (
            f"Gate-2 prices Ohtani's actual at ${m['actual_guar_mm']}M; the engine "
            f"reads ${npv / 1e6:.1f}M at {fm._discount_rate():g}. Regenerate Gate 2.")


_GATE2_SURFACES = (("data/fa_gate2_eval.json", ()), ("data/fa_meta.json", ("gate2",)))


def test_served_gate2_note_names_the_rate_its_table_was_priced_at():
    """The SERVED half of F12-01. assets/fa.js renders gate2.notes verbatim.

    An artifact written before the source fix carries no discount_rate stamp
    and still holds the typed literal; that is a regen owed, not a new defect,
    so it xfails (the repo's stamp-gated pattern, as in
    test_trade_board_coverage.py) and turns into a real assertion the first
    time Gate 2 is re-persisted."""
    import value_framework

    engine_pct = float(value_framework._config()["discount_rate"]) * 100
    problems, owed = [], []
    for rel, keypath in _GATE2_SURFACES:
        g = _dig(_read_json(rel), keypath)
        if not g:
            continue                      # fa_meta written with no Gate-2 artifact
        claims = [c for n in (g.get("notes") or []) for c in _discount_rate_claims(n.lower())]
        stamp = g.get("discount_rate")
        if stamp is None:
            owed.append(f"{rel} (generated {g.get('generated_at')}) quotes "
                        f"{sorted({v for _, v, _ in claims})}")
            continue
        stamp_pct = float(stamp) * 100
        if abs(stamp_pct - engine_pct) > 1e-6:
            problems.append(f"{rel}: table priced at {stamp_pct:g}% but the engine "
                            f"discounts at {engine_pct:g}%; regenerate Gate 2")
        if not claims:
            problems.append(f"{rel}: no note names the discount rate")
        for label, v, snip in claims:
            if abs(v - stamp_pct) > 1e-6:
                problems.append(f"{rel}: note says {v:g}% ({label}: {snip!r}) over a "
                                f"table priced at {stamp_pct:g}%")
    assert not problems, "Gate-2 discount note drift: " + "; ".join(problems)
    if owed:
        pytest.xfail(
            "Gate-2 artifact predates the discount_rate stamp (audit F12-01), so "
            "its NPV note is still the literal the source used to type: "
            + "; ".join(owed)
            + ". Regen owed: python -c \"import fa_backtest as fb; "
              "fb.run_market_gate(persist=True, persist_dpw=False)\", then the "
              "nightly fa_export carries it into fa_meta.json")


_DPW_TIER_SHAPES = (("lt_1", r"\$(\d+\.\d+)m \(0-1 war\)"),
                    ("1_to_2", r"\$(\d+\.\d+)m \(1-2\)"),
                    ("2plus", r"\$(\d+\.\d+)m \(2\+\)"))


def test_dpw_tier_rates_match_the_valuation_set():
    """The second half of F12-04: the four published $/WAR rates were pinned to
    nothing. They are held to the engine's loaded config (clemens_2026
    win_cost.rates_musd), and any two-decimal $M figure on the card must be one
    of the configured rates."""
    import value_framework

    dpw = value_framework._config()["dollars_per_war"]
    rates = {k: float(v) / 1e6 for k, v in dpw["tiered"]["rates"].items()}
    flat = float(dpw["flat"]) / 1e6
    entry = _glossary_entry("dpw_tier")
    formula = (entry.get("formula") or "").lower()
    problems = []
    for key, pat in _DPW_TIER_SHAPES:
        got = re.findall(pat, formula)
        if not got:
            problems.append(f"formula no longer quotes the {key} tier in the pinned shape")
        problems += [f"formula quotes ${raw}M for {key}; engine {rates[key]:.2f}"
                     for raw in got if abs(float(raw) - rates[key]) > 0.005]
    problems += [f"formula quotes ${raw}M overall; engine {flat:.2f}"
                 for raw in re.findall(r"\$(\d+\.\d+)m overall", formula)
                 if abs(float(raw) - flat) > 0.005]
    allowed = list(rates.values()) + [flat]
    every = " ".join(v for v in entry.values() if isinstance(v, str)).lower()
    problems += [f"dpw_tier quotes ${raw}M, none of the configured rates {sorted(allowed)}"
                 for raw in re.findall(r"\$(\d+\.\d\d)m\b", every)
                 if not any(abs(float(raw) - a) <= 0.005 for a in allowed)]
    assert not problems, "dpw_tier rate drift: " + "; ".join(problems)
