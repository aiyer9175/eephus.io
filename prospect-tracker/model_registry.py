# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Model registry — one committed ledger of every predictive model on the
platform (data/model_registry.json).

Every model that makes a predictive claim gets a row: what it predicts,
which surface renders it, who the champion is, what baseline it must beat,
where its committed eval artifact lives, and an HONEST verdict:

  validated     a forward-chained backtest exists, is committed, and the
                champion beats its stated baseline
  provisional   measured, but partially (synthetic-only harness, short
                window, or descriptive-only correlation)
  unvalidated   makes predictive claims with NO measurement — the audit's
                hit list, listed here precisely so it can't hide
  deprecated    failed its validation and was retired or demoted

The registry is data + a validator, deliberately boring: load() parses,
validate() enforces the schema and that every referenced artifact exists
and parses, freshness() stamps artifact ages so run_monthly can flag
stale evals. The Phase-5 accountability surface renders this file
verbatim — misses and `unvalidated` rows included.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
REGISTRY_PATH = DATA_DIR / "model_registry.json"

VERDICTS = ("validated", "provisional", "unvalidated", "deprecated")
REQUIRED_KEYS = ("model_id", "surface", "predicts", "champion", "baseline",
                 "metric", "eval_artifact", "verdict")
# OPTIONAL row field `provisional_kind`: the sub-state the four-word verdict
# enum cannot express, populated only where the row's notes already state it
# unambiguously (2026-08-19). Never required; validate() checks the enum only
# when the field is present.
#   shipped_partial_measurement  serving, but only part of the claim is measured
#   measured_not_adopted         a real gate ran and the candidate did NOT ship
#   measurement_only             descriptive by design; no forward claim to gate
#   data_blocked_stub            registered and waiting on data that does not exist yet
#   inherits_parent_gate         composition/re-expression of an already-gated parent
PROVISIONAL_KINDS = ("shipped_partial_measurement", "measured_not_adopted",
                     "measurement_only", "data_blocked_stub",
                     "inherits_parent_gate")
# Evals older than this (vs today) get a stale flag at refresh time —
# advisory only; expensive gates run pre-merge, not on a clock.
#
# LOWERED 240 -> 90 on 2026-08-03. At 240 the threshold sat 4.5x above the
# oldest artifact in the tree (53 days), so the stale flag was structurally
# incapable of firing and the freshness map reported "nothing is stale" as a
# tautology rather than a finding. 90 days is roughly one quarter, which is
# the cadence at which a live-surface eval genuinely wants re-running.
STALE_DAYS = 90


def load() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def validate(reg: dict | None = None) -> list[str]:
    """Return a list of problems (empty = valid). Checks: schema keys,
    verdict enum, referenced artifacts exist and parse, no duplicate ids,
    and verdict honesty rules (a `validated` row MUST point at an
    artifact; an `unvalidated` row must NOT — if it has one, it's at
    least provisional and the row is lying)."""
    reg = reg or load()
    problems: list[str] = []
    ids = [m.get("model_id") for m in reg.get("models", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate model_id entries")
    for m in reg.get("models", []):
        mid = m.get("model_id", "?")
        for k in REQUIRED_KEYS:
            if k not in m:
                problems.append(f"{mid}: missing key {k}")
        if m.get("verdict") not in VERDICTS:
            problems.append(f"{mid}: bad verdict {m.get('verdict')!r}")
        pk = m.get("provisional_kind")
        if pk is not None and pk not in PROVISIONAL_KINDS:
            problems.append(f"{mid}: bad provisional_kind {pk!r}")
        art = m.get("eval_artifact")
        if m.get("verdict") == "validated" and not art:
            problems.append(f"{mid}: validated without an eval artifact")
        if m.get("verdict") == "unvalidated" and art:
            problems.append(f"{mid}: claims unvalidated but carries an artifact")
        if art:
            p = Path(__file__).parent / art
            if not p.exists():
                problems.append(f"{mid}: artifact missing: {art}")
            elif p.suffix == ".json":
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                except ValueError:
                    problems.append(f"{mid}: artifact unparseable: {art}")
            elif p.stat().st_size == 0:
                # Non-JSON artifacts (efv_il_severity points at a lane-gates
                # .md) skipped the parse check entirely, so an emptied file
                # would validate clean. Existence is not evidence; at minimum
                # require content.
                problems.append(f"{mid}: artifact is empty: {art}")
        # Optional Report Card block: proof numbers rendered inline on the
        # Models & Proofs view. A card may only exist on a row that has an
        # eval_artifact to trace back to (the honesty rule for cards).
        card = m.get("card")
        if card is not None:
            if not art:
                problems.append(f"{mid}: has a card but no eval_artifact to source it from")
            hl = card.get("headline")
            if not isinstance(hl, list) or not hl:
                problems.append(f"{mid}: card.headline must be a non-empty list")
            else:
                for h in hl:
                    if not isinstance(h.get("champion"), (int, float)) or \
                       not isinstance(h.get("baseline"), (int, float)):
                        problems.append(f"{mid}: card headline champion/baseline must be numeric")
                    if h.get("better") not in ("lower", "higher"):
                        problems.append(f"{mid}: card headline 'better' must be 'lower' or 'higher'")
            if card.get("derived_from") is not None and art:
                problems += _derived_card_problems(mid, card, art)
    return problems


# A card whose eval artifact is regenerated by the pipeline cannot hold typed
# numbers: the numbers go stale on the next run and nothing notices, which is
# how consensus_fv kept a superseded weighted-vs-equal pair, with a star on a
# leg its own artifact calls not resolvable, for six weeks (audit L18-01,
# 2026-09-09). Such a card carries `derived_from`, naming the artifact path of
# every served field, and refresh_stamps() re-reads them from the row's own
# eval_artifact on every run. Only these fields may be derived, and each must
# resolve to this type. `resolvable` and `verdict` are the artifact's own
# resolvability flag and verdict string; the Models and Proofs view withholds
# the star from a headline whose `resolvable` is False.
_CARD_DERIVABLE = {
    "champion": "number",
    "baseline": "number",
    "resolvable": "bool",
    "verdict": "str",
}


def _dig_path(doc, dotted: str):
    """The value at a dotted key path, or KeyError naming the path."""
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def _typed(value, kind: str) -> bool:
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    return isinstance(value, str) and bool(value.strip())


def derive_card(m: dict, doc=None) -> dict | None:
    """The card a row's `card.derived_from` spec reads out of its eval
    artifact, or None when the card has no spec. Labels, `better`, `window`
    and the spec itself are kept; every field the spec names is replaced by
    the artifact's value. Raises (KeyError, ValueError, OSError) rather than
    serving a half-derived card."""
    card = m.get("card") or {}
    spec = card.get("derived_from")
    if not spec:
        return None
    if doc is None:
        doc = json.loads((Path(__file__).parent / m["eval_artifact"])
                         .read_text(encoding="utf-8"))
    out = dict(card)
    if "n" in spec:
        n = _dig_path(doc, spec["n"])
        if not _typed(n, "number"):
            raise ValueError(f"card n path {spec['n']} is not a number")
        out["n"] = n
    heads = card.get("headline") or []
    specs = spec.get("headline") or []
    if len(specs) != len(heads):
        raise ValueError("card.derived_from.headline must pair one-to-one "
                         "with card.headline")
    new_heads = []
    for h, hs in zip(heads, specs):
        nh = dict(h)
        for field, path in hs.items():
            kind = _CARD_DERIVABLE.get(field)
            if kind is None:
                raise ValueError(f"card field {field!r} is not derivable")
            val = _dig_path(doc, path)
            if not _typed(val, kind):
                raise ValueError(f"card {field} path {path} is not a {kind}")
            nh[field] = val
        new_heads.append(nh)
    out["headline"] = new_heads
    return out


def _derived_card_problems(mid: str, card: dict, art: str) -> list[str]:
    """validate() leg for a derived card: the spec must be well-formed and
    every path must resolve, to the right type, in the row's own artifact.
    A missing or unparseable artifact is already reported above."""
    p = Path(__file__).parent / art
    if p.suffix != ".json" or not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return []
    try:
        derive_card({"card": card, "eval_artifact": art}, doc)
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        return [f"{mid}: card.derived_from does not resolve in {art}: {e}"]
    return []


def _rederive_cards(reg: dict) -> None:
    """Refresh every derived card from its artifact, in place. Best-effort by
    design: a card that fails to derive keeps its last good numbers, and
    validate() reports why."""
    for m in reg.get("models", []):
        if not (m.get("card") or {}).get("derived_from"):
            continue
        try:
            m["card"] = derive_card(m)
        except (OSError, KeyError, ValueError, TypeError, AttributeError) as e:
            log.warning("model registry: %s card not re-derived: %s",
                        m.get("model_id"), e)


# Fields an eval artifact may use to state when it was actually produced.
# Preferred over the file mtime: `git checkout` and a fresh clone rewrite every
# mtime to the moment of checkout, so an mtime-only freshness map reports the
# whole registry as brand new on the deploy box - exactly where staleness
# matters most. Read the artifact's own stamp when it carries one.
_GENERATED_AT_KEYS = ("generated_at", "run_at", "fit_date", "as_of", "date")
# Parsing guard: a handful of eval artifacts are multi-MB. Age is advisory, so
# skip the parse rather than pay it, and fall back to mtime for those.
_MAX_STAMP_PARSE_BYTES = 4_000_000


def _parse_stamp(raw: str):
    """Parse an artifact date stamp to NAIVE LOCAL time.

    Stamps are mixed: some are bare dates ("2026-08-03"), some are local
    naive, and some are UTC with a Z suffix ("2026-08-03T23:17:20Z"). Treating
    a Z stamp as local put it hours in the FUTURE and produced a negative age
    (source_track_record read -1 day). Normalize the suffix, then convert any
    offset-aware value to local before dropping the tzinfo. Note fromisoformat
    on py3.10 (the deploy box) accepts "+00:00" but not "Z".
    """
    txt = raw.strip().replace(" ", "T")
    if txt.endswith(("Z", "z")):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        try:
            dt = datetime.fromisoformat(txt[:10])   # bare date prefix
        except ValueError:
            return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def _artifact_date(p: Path):
    """The artifact's self-declared production date, or None."""
    try:
        if p.suffix != ".json" or p.stat().st_size > _MAX_STAMP_PARSE_BYTES:
            return None
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    for key in _GENERATED_AT_KEYS:
        raw = doc.get(key)
        if isinstance(raw, str) and raw[:4].isdigit():
            got = _parse_stamp(raw)
            if got is not None:
                return got
    return None


def freshness(reg: dict | None = None) -> dict[str, dict]:
    """{model_id: {artifact_age_days, stale, age_source, age_is_evidence}}.

    Age comes from the artifact's own `generated_at` where it has one, else the
    file mtime.

    `age_is_evidence` IS THE POINT OF THIS FUNCTION AND WAS MISSING (2026-08-14).
    An mtime-sourced age is NOT evidence about how old a measurement is. The
    deploy box runs `git checkout -- .` nightly, which rewrites the mtime of
    every tracked file to the moment of checkout, so on the machine that SERVES
    THE SITE these rows report an age of roughly zero and `stale: False` no
    matter how old the measurement really is. Measured 2026-08-14: 33 of 217
    rows, behind 28 distinct artifacts, take this path.

    So the number was not merely imprecise, it was confidently wrong in exactly
    the one place a stale eval would matter, and the freshness map presented it
    beside genuinely-stamped ages with nothing to tell them apart. Consumers
    MUST branch on `age_is_evidence` and render an unknown age as unknown
    rather than as fresh.

    `stale` is left False for these rows deliberately rather than flipped True:
    an unknown age is not a finding either, and asserting staleness we cannot
    demonstrate would be the same defect with the sign reversed. The honest
    state is "unknown", which is what `age_is_evidence: False` says.

    The durable fix is a `generated_at` in the artifact. The 28 undated files
    are NOT retro-stamped: their true production dates are not recoverable, and
    inventing one, or borrowing git's first-commit date and calling it a
    production date, is falsifying provenance. `test_no_new_undated_eval_artifact`
    stops the set from growing.
    """
    reg = reg or load()
    out = {}
    today = datetime.now()
    for m in reg.get("models", []):
        art = m.get("eval_artifact")
        if not art:
            continue
        p = Path(__file__).parent / art
        if not p.exists():
            continue
        stamped = _artifact_date(p)
        when = stamped or datetime.fromtimestamp(p.stat().st_mtime)
        age = (today - when).days
        out[m["model_id"]] = {
            "artifact_age_days": age,
            "stale": bool(stamped) and age > STALE_DAYS,
            "age_source": "artifact" if stamped else "mtime",
            "age_is_evidence": bool(stamped),
        }
    return out


def refresh_stamps() -> dict:
    """run_monthly hook: re-derive derived cards, re-validate, restamp
    freshness, rewrite the registry's `checked_at` + per-model
    `last_checked`/`stale` fields. Never changes verdicts: those are
    hand-committed with their evals. A derived card's numbers are not a
    verdict: they are read from the artifact, which run_monthly regenerates
    earlier in the same run (run_source_backtest precedes this hook)."""
    reg = load()
    _rederive_cards(reg)
    problems = validate(reg)
    if problems:
        log.warning("model registry problems: %s", problems)
    fresh = freshness(reg)
    today = date.today().isoformat()
    reg["checked_at"] = today
    reg["problems"] = problems
    for m in reg.get("models", []):
        f = fresh.get(m["model_id"])
        if f:
            m["last_checked"] = today
            m["stale"] = f["stale"]
            m["artifact_age_days"] = f["artifact_age_days"]
    REGISTRY_PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    log.info("model registry: %d models, %d problems", len(reg.get("models", [])),
             len(problems))
    return reg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    reg = refresh_stamps()
    by_v: dict[str, int] = {}
    for m in reg["models"]:
        by_v[m["verdict"]] = by_v.get(m["verdict"], 0) + 1
    print({k: by_v[k] for k in sorted(by_v)})
    if reg["problems"]:
        print("PROBLEMS:", reg["problems"])
