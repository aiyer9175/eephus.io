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

Import-safe and deterministic: no network, no rebuilds, every file read
happens inside a test function.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

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
    # pool; measured on the bWAR series, identical on the batting side under
    # eWAR). Tight abs tolerance: these are quoted to four decimals.
    ("war_pa_plus", "hit rho_primary (v2)", r"Spearman correlation of (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "results_by_convention", "v2", "rho_primary"), "abs", 0.005),
    ("war_pa_plus", "hit war_total baseline (v2)", r"predicts the same thing at (0\.\d+)",
     "data/war_rate_plus_eval.json",
     ("pools", "hit", "results_by_convention", "v2", "rho_baselines", "war_total"), "abs", 0.005),
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


# The three surfaces that state the valuation conventions in prose.
_VALUATION_COPY_SURFACES = ("data/glossary.json", "assets/glossary.js",
                            "docs/METHODOLOGY.md")


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


def test_control_window_and_discount_copy_match_valuation_set():
    import value_framework

    cfg = value_framework._config()
    control_years = int(cfg["service_time"]["control_years"])
    discount_pct = round(float(cfg["discount_rate"]) * 100)
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

    nets = [int(v) for v in re.findall(r"net (\d+)\s*(?:%|percent)", text)]
    assert nets, ("no copy surface states the net discount rate; the surplus "
                  "copy must name it so this pin has something to check")
    off = sorted({v for v in nets if v != discount_pct})
    assert not off, (
        f"the active valuation set discounts at net {discount_pct} percent "
        f"(value_framework._config discount_rate) but copy quotes net {off}"
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
