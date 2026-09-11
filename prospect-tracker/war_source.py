# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pluggable WAR facade (the D0 spec from
docs/master-plan-2026-08-03-eight-asks.md, built 2026-08-04d lane B1; eWAR
epoch 2026-09-03, wave 1 lane L2).

One module wraps every WAR read the sites make, behind a provider id:

  * per-season WAR by player_key - the career_war sqlite table, written by
    the funnel run_monthly -> career_war_bulk -> storage.upsert_career_war
    (career_war_bulk / career_war_table / coverage_report)
  * the stint frame - Baseball-Reference war_daily rows via pybaseball
    (stint_frame), one row per player-stint-season
  * the run-value decomposition - WAR_def / runs_position / runs_bat etc.,
    columns that ride the stint frame (run_value_frame)
  * the condensed frame - pybaseball's narrow default column set
    (condensed_frame)
  * the name index - normalized name -> {mlb_ID: {years, war}}
    (name_index, delegating to fa_ident.war_daily_index)
  * the per-season side split - {mlbam: {season: {"bat": w, "pit": w}}}
    (side_war_by_season)

PROVIDER CONTRACT (eWAR epoch, owner decision 2026-09-03, locked).

  'ewar_v2'  THE DEFAULT and the served/label series site-wide. eWAR v2
             (ewar.py) is the Baseball-Reference run frame with ONE component
             replaced: pitching re-priced on FIP, centred per season x role so
             role totals match B-Ref. Fielding swap weight is 0.0 (measured,
             see ewar.build), offense/baserunning/positional untouched. So:
               - position players: eWAR == bWAR exactly, season by season,
                 until the SDR defense drop lands (0 of the batting-side
                 numbers move);
               - pitchers: runs are redistributed WITHIN role; league sum per
                 season is preserved by the re-derived replacement scale.
             Servable whenever data/ewar.json exists; it is read through
             ewar.load / ewar.ewar_for and never re-derived here. Where the
             artifact has no block for a (mlbam, season) the bWAR value is
             served and the fallback is RECORDED (ewar_coverage on the
             aggregate, ewar_frame_diagnostics() on the frames), never
             silent. DataUnavailable only when the artifact is missing,
             naming the build command (EWAR_BUILD_CMD).
  'bwar'     The INPUT frame. Still servable on explicit request and still a
             pure delegation over stats.py / fa_ident.py / mlb_player_export.py
             (pinned byte-exact by test_war_source.py). bWAR is what eWAR is
             built on (war_daily via pybaseball); what changed is the SERVED
             and LABEL series, not the input.
  'ewar_merged'  Declared, not servable (Will's pitcher eWAR + SDR fielding);
             raises DataUnavailable naming the missing handoff.

THE BASIS DECISION IS NOT AN ACCURACY CLAIM. The eval record
(data/ewar_eval.json) is: gate 1 team wins r 0.8595 vs bWAR 0.8803 (a
descriptive loss, by construction for any FIP WAR); gate 2 pitcher
persistence 0.3617 vs 0.1768 (2.0x). The eFV label swap (R3a, 2026-08-04)
moved the margin over consensus by -0.0011 hit / -0.0115 pit, a floor-sized
effect that is UNEXCLUDED. Copy must say the flip is a basis choice.

THE RE-ENTRANCY TRAP AND THE FRAME PIN. Legacy readers (stats.py,
mlb_player_export.py, fa_ident.py, fa_projection.py, proj_export.py, ...)
call stint_frame(side) on the DEFAULT provider, which now means eWAR. That is
the intent for served numbers, but two transforms in this module need the
raw bWAR frame underneath a legacy reader: career_war_bulk (the aggregate it
transforms must be bWAR so `seasons_bwar` is bWAR) and side_war_by_season
(the map it fills from must be bWAR). They wrap the call in
_frames_pinned('bwar'), a process-global pin that every stint_frame /
condensed_frame call inside the window honours, whatever provider it names.
The pin is visible to worker threads on purpose (stats fetches both sides on
a ThreadPoolExecutor) and is not safe against two providers pinned
concurrently; the pipeline is a single writer.

FRESHNESS. Covered player-seasons are pinned to the ARTIFACT (its ewp/ewb
side totals), so the served WAR of a covered pitcher-season moves only when
data/ewar.json is rebuilt. In season, war_daily advances daily while the
artifact holds its generated_at. Rebuild the artifact (EWAR_BUILD_CMD, add
--force-fetch to bypass ewar.bwar_frames' 7-day cache) before the monthly WAR
reads, or the pitcher side serves the build date. ewar_frame_diagnostics()
counts the player-seasons whose frame bWAR sum no longer matches the
artifact's bwp/bwb (a B-Ref revision or an in-season update since the build).

THE RE-ANCHOR CASCADE IS A LATER WAVE. Flipping this default lands eWAR in
every default reader; the bWAR-pinned artifacts (empirical FV outcome curve,
FV_EXPECTED_WAR / survivor anchors, draft slot curve, war_rate_plus vintages,
eFV matrices / evals / floors, fingerprint label term, projections retrain)
are rebuilt by the wave that owns them. Until it runs, a not-yet-rebased
career_war table serves bWAR under source 'bbref' and career_war_table()
says so (it does not re-transform; read its docstring).
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class DataUnavailable(RuntimeError):
    """A declared WAR provider whose input data does not exist.

    Deliberately loud: callers must never catch this to fall back silently
    to another provider - the caller that wants bwar asks for bwar."""


#: Every provider id this facade recognises. Declared != servable. 'bwar'
#: stays first: it is the INPUT frame the other two are built on.
PROVIDERS: tuple[str, ...] = ("bwar", "ewar_v2", "ewar_merged")

#: The served and label WAR site-wide (owner decision 2026-09-03).
DEFAULT_PROVIDER: str = "ewar_v2"

#: How to (re)build the artifact 'ewar_v2' serves from. The 2011 floor is the
#: first season the eFV first-6yr label pool reaches; the FIP corpus prices
#: 2011-2015 in full (707/707 .. 808/810 pitcher rows, tools/build_ewar.py).
EWAR_BUILD_CMD: str = "python tools/build_ewar.py --first 2011 --last 2026 --write"

_SIDES = ("bat", "pit")

#: Exposure column the pitching/batting delta is spread over within a
#: player-season, per side. Absent (the condensed frame) -> equal split.
_EXPOSURE_COL = {"bat": "PA", "pit": "IPouts"}

# Why the non-servable provider refuses, naming the missing input. Kept as
# module data so test_war_source.py can pin the wording without duplicating it.
_UNAVAILABLE: dict[str, str] = {
    "ewar_merged": (
        "WAR provider 'ewar_merged' is declared but not servable: the merged "
        "series is Will's pitcher eWAR plus SDR-bearing fielding on the "
        "ewar.py frame, and the pitcher eWAR parquet handoff "
        "(milb-projections/manifests/BENCHMARK_MANIFEST.yaml, "
        "mlb_pitcher_ewar_champion) has not been delivered; no hitter eWAR "
        "exists anywhere. Missing input: the private export bundle (a queued "
        "owner action)."
    ),
}


def _ewar_artifact_path() -> Path:
    import ewar
    return ewar.OUT


def _ewar_available() -> bool:
    """True when 'ewar_v2' can serve: an in-memory payload (ewar._CACHE, which
    is also how tests inject a synthetic artifact) or data/ewar.json on disk."""
    import ewar
    return ewar._CACHE is not None or Path(ewar.OUT).exists()


def _ewar_missing_message() -> str:
    return (
        f"WAR provider 'ewar_v2' is the default but its artifact is missing: "
        f"{_ewar_artifact_path()} (data/ewar.json, written by ewar.export_payload). "
        f"Build it: {EWAR_BUILD_CMD}. Nothing falls back to bWAR on its own; a "
        f"caller that wants bWAR passes provider='bwar'."
    )


def _require(provider: str) -> None:
    """Validate a provider id. ValueError on an unknown id; DataUnavailable
    (with the missing input named) on a declared-but-absent one."""
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown WAR provider {provider!r}; known providers: {PROVIDERS}")
    if provider == "ewar_merged":
        raise DataUnavailable(_UNAVAILABLE[provider])
    if provider == "ewar_v2" and not _ewar_available():
        raise DataUnavailable(_ewar_missing_message())


def _check_side(side: str, what: str = "frame") -> None:
    if side not in _SIDES:
        raise ValueError(f"unknown {what} side {side!r}; use one of {_SIDES}")


def _payload() -> dict:
    """The eWAR artifact, through ewar.load (memoised there)."""
    import ewar
    return ewar.load()


# ---------------------------------------------------------------------------
# the frame pin (see the module docstring, THE RE-ENTRANCY TRAP)
# ---------------------------------------------------------------------------

_FRAME_PIN: str | None = None


@contextlib.contextmanager
def _frames_pinned(provider: str):
    """Force every stint_frame / condensed_frame read inside the window onto
    ``provider``, regardless of the provider those calls name. Restores the
    previous pin on exit (nesting is fine). Process-global by design: the
    legacy readers this exists for run their fetches on worker threads."""
    global _FRAME_PIN
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown WAR provider {provider!r}; known providers: {PROVIDERS}")
    prev = _FRAME_PIN
    _FRAME_PIN = provider
    try:
        yield
    finally:
        _FRAME_PIN = prev


def _frame_provider(provider: str) -> str:
    return _FRAME_PIN if _FRAME_PIN is not None else provider


# ---------------------------------------------------------------------------
# per-season WAR by player (the career_war funnel)
# ---------------------------------------------------------------------------

def career_war_bulk(targets: list[tuple[str, int, bool]],
                    start_year: int, end_year: int,
                    *, provider: str = DEFAULT_PROVIDER) -> dict[str, dict]:
    """Per-player {seasons, career_war, war_per_yr, war_seasons_count, source,
    ...} aggregates for a (player_key, mlbam_id, is_pitcher) cohort. This is
    the payload storage.upsert_career_war stores and every label / WAG /
    anchor / surplus reader prices off.

    Provider 'bwar' delegates verbatim to stats.fetch_career_war_bulk over the
    raw bWAR frames (byte-exact; test_war_source.py).

    Provider 'ewar_v2' fetches the SAME bWAR aggregate (stats, with the frames
    pinned to bwar so the aggregate really is bWAR), then transforms each row:

        seasons[year]     := ewar_for(mlbam, year)["ewar"] where the artifact
                             has the block, else the bWAR value (recorded)
        seasons_bwar      := the untouched bWAR seasons
        career_war        := round(sum(seasons), 2)
        war_per_yr        := round(career_war / n, 2)
        war_seasons_count := n
        source            := "ewar_v2"
        ewar_coverage     := {"covered": k, "total": n,
                              "fallback_years": [years served as bWAR]}

    Rounding is 2dp like the incumbent (the artifact's `ew` is already 2dp).
    A row whose target mlbam is missing or unknown to the artifact is served
    as bWAR in full, with every year in fallback_years: identity, not the
    model, is the binding constraint (69 debuted players have no id anywhere,
    2026-09-03 census).
    """
    _require(provider)
    import stats
    # Both providers fetch the aggregate over the RAW bWAR frames: stats reads
    # stint_frame on the default provider, so without the pin a 'bwar' request
    # would sum eWAR-replaced stints and 'seasons_bwar' would not be bWAR.
    with _frames_pinned("bwar"):
        base = stats.fetch_career_war_bulk(targets, start_year, end_year)
    if provider == "bwar" or not base:
        return base
    # last target wins per key, mirroring stats' result[player_key] overwrite
    mlbam_by_key = {key: mid for key, mid, _ in targets}
    blob = _payload()
    return {key: _ewar_aggregate(agg, mlbam_by_key.get(key), blob)
            for key, agg in base.items()}


def _ewar_aggregate(agg: dict, mlbam, blob: dict) -> dict:
    """One bWAR aggregate -> its eWAR v2 payload (see career_war_bulk)."""
    import ewar
    seasons_bwar = dict(agg.get("seasons") or {})
    seasons: dict[str, float] = {}
    fallback: list[int] = []
    for yr_s, bw in seasons_bwar.items():
        yr = int(yr_s)
        rec = ewar.ewar_for(int(mlbam), yr, payload=blob) if mlbam else None
        ew = rec.get("ewar") if rec else None
        if ew is None:
            seasons[yr_s] = bw
            fallback.append(yr)
        else:
            seasons[yr_s] = round(float(ew), 2)
    career = round(sum(seasons.values()), 2)
    n = len(seasons)
    out = dict(agg)
    out.update({
        "seasons": seasons,
        "career_war": career,
        "war_per_yr": round(career / n, 2) if n else 0.0,
        "war_seasons_count": n,
        "source": "ewar_v2",
        "seasons_bwar": seasons_bwar,
        "ewar_coverage": {"covered": n - len(fallback), "total": n,
                          "fallback_years": fallback},
    })
    return out


def career_war_table(*, provider: str = DEFAULT_PROVIDER) -> dict[str, dict]:
    """The persisted per-player aggregate the sites read:
    {player_key: aggregate} from the career_war sqlite table
    (storage.load_career_war). {} when the table is absent.

    Both servable providers return the table AS STORED. This function does not
    re-transform: the funnel (run_monthly -> career_war_bulk on the default
    provider -> storage.upsert_career_war) and tools/rebase_career_war_to_ewar
    write ewar_v2 payloads, and each row's `source` field says which basis it
    carries ('ewar_v2' with `seasons_bwar` beside it, or 'bbref' = bWAR on a
    row the rebase has not reached). A not-yet-rebased table therefore serves
    bWAR under provider 'ewar_v2' and SAYS SO per row; coverage_report()
    totals it. Re-transforming here would hide that state behind a read."""
    _require(provider)
    import storage
    return storage.load_career_war()


def coverage_report(table: dict[str, dict] | None = None) -> dict:
    """What basis the stored career_war table actually carries.

    Reads the table (or the one passed in) and returns
      rows               row count
      by_source          {source: rows}  ('bbref' = bWAR, 'ewar_v2', ...)
      season_values      total (player, season) cells across all rows
      season_values_ewar cells served from the eWAR artifact (the sum of the
                         rows' ewar_coverage.covered; a row without the
                         receipt contributes 0, whatever its source says)
      share_ewar         season_values_ewar / season_values (4dp; None if 0)
      fallback_years     {year: rows served as bWAR for that year} over the
                         ewar_v2 rows' fallback_years
      artifact           {model, generated_at, seasons} of data/ewar.json,
                         or None when it is not available
    """
    from collections import Counter
    if table is None:
        import storage
        table = storage.load_career_war()
    by_source: Counter = Counter()
    fallback: Counter = Counter()
    total = 0
    covered = 0
    for row in table.values():
        by_source[str(row.get("source") or "unknown")] += 1
        total += len(row.get("seasons") or {})
        cov = row.get("ewar_coverage") or {}
        covered += int(cov.get("covered") or 0)
        for yr in cov.get("fallback_years") or []:
            fallback[int(yr)] += 1
    artifact = None
    if _ewar_available():
        try:
            blob = _payload()
            artifact = {"model": blob.get("model"),
                        "generated_at": blob.get("generated_at"),
                        "seasons": blob.get("seasons")}
        except (OSError, ValueError):
            artifact = None
    return {
        "rows": len(table),
        "by_source": dict(sorted(by_source.items())),
        "season_values": total,
        "season_values_ewar": covered,
        "share_ewar": round(covered / total, 4) if total else None,
        "fallback_years": {k: fallback[k] for k in sorted(fallback)},
        "artifact": artifact,
    }


def side_war_by_season(*, provider: str = DEFAULT_PROVIDER
                       ) -> dict[int, dict[int, dict[str, float]]]:
    """{mlbam: {season: {"bat": WAR, "pit": WAR}}} with batting and pitching
    kept on SEPARATE keys (two-way players; position-player pitching cameos).

    Provider 'bwar' delegates to mlb_player_export._war_daily over the raw
    bWAR frames.

    Provider 'ewar_v2' starts from that bWAR map (frames pinned to bwar) and
    overlays the artifact: for every (mlbam, season) block, "bat" := ewb when
    the block carries a batting side and "pit" := ewp when it carries a
    pitching side. Blocks carry a side only where a war_daily row of that
    side exists (ewar.export_payload): 11,801 blocks both sides, 9,653
    bat-only, 706 pit-only in the 2026-09-03T12:35 build (22,160 blocks,
    2011-2026). Seasons absent from the artifact keep the bWAR cell, so
    coverage never shrinks.

    ONE EXCEPTION, so the key structure mirrors bWAR's. A side B-Ref left
    BLANK (WAR NaN: 12,023 batting rows and 196 pitching rows in the
    2026-09-03 frames, mostly pitchers' batting lines) is 0.0 in the artifact
    (ewar._num coerces blank to 0; 4,617 batting blocks in the current build,
    every one of them 0.0) and absent from the bWAR map, which drops NaN
    rows. A zero-valued side the map lacks is NOT added, so a pitcher's blank
    batting line does not become a 0.0 batting WAR on a hitter surface.

    Batting-side values equal bWAR by construction today (fielding swap
    weight 0.0); only their float representation changes (the artifact
    stores 2dp sums, the map sums raw stints)."""
    _require(provider)
    import mlb_player_export
    # pinned for both providers: _war_daily reads stint_frame on the default
    with _frames_pinned("bwar"):
        out = mlb_player_export._war_daily()
    if provider == "bwar":
        return out
    import ewar
    blob = _payload()
    for mid_s, seasons in (blob.get("players") or {}).items():
        mid = int(mid_s)
        for season_s in seasons:
            season = int(season_s)
            rec = ewar.ewar_for(mid, season, payload=blob)
            if rec is None:
                continue
            cell = out.setdefault(mid, {}).setdefault(season, {})
            for key, val in (("bat", rec.get("ewar_bat")),
                             ("pit", rec.get("ewar_pit"))):
                if val is None:
                    continue
                if key not in cell and float(val) == 0.0:
                    continue          # the blank-row rule (docstring)
                cell[key] = float(val)
            if not cell:              # nothing landed, nothing was there
                out[mid].pop(season, None)
                if not out[mid]:
                    out.pop(mid, None)
    return out


# ---------------------------------------------------------------------------
# the stint frame + run-value decomposition
# ---------------------------------------------------------------------------

def condensed_frame(side: str, *, provider: str = DEFAULT_PROVIDER):
    """The CONDENSED war_daily frame: pybaseball's default call, WITHOUT
    return_all=True, so it carries the narrow public column set rather than the
    full decomposition. A different shape from stint_frame(), which is why
    mlb_trade_lookup's name-to-WAR backfill reads through this door instead.

    Kept separate on purpose: a caller written against one column set will
    KeyError on the other, so the two frames must never be silently swapped.
    Provider semantics match stint_frame(): 'bwar' is the raw pybaseball
    frame; 'ewar_v2' is that frame with WAR replaced per (mlb_ID, year_ID)
    (see _ewar_frame) plus a WAR_bwar column. The condensed pitching frame has
    no IPouts and the batting one keeps PA, so a multi-stint pitcher-season's
    delta is split EQUALLY across its stints here (the exposure-weighted split
    needs the stint frame)."""
    _require(provider)
    _check_side(side)
    import pybaseball as pyb
    fn = pyb.bwar_bat if side == "bat" else pyb.bwar_pitch
    raw = fn()
    if _frame_provider(provider) == "bwar":
        return raw
    return _ewar_frame(raw, side, door="condensed")


def stint_frame(side: str, *, provider: str = DEFAULT_PROVIDER,
                allow_stale: bool = True):
    """The raw war_daily stint frame: one row per player-stint-season, with
    mlb_ID / year_ID / WAR / name_common / age / team_ID / exposure columns.
    ``side`` is 'bat' or 'pit'.

    Provider 'bwar' is pybaseball.bwar_bat / bwar_pitch with return_all=True,
    two static Baseball-Reference CSV downloads (the body below, unchanged).

    Provider 'ewar_v2' is the SAME frame (fetched and cached exactly as bwar:
    the last-good cache always holds the raw bWAR download) with the WAR
    column replaced so that, per (mlb_ID, year_ID), the stint WARs sum to the
    artifact's side total (ewp on the pitching frame, ewb on the batting
    frame). The (side total - frame sum) delta is spread across that
    player-season's stints in proportion to IPouts (pit) or PA (bat); rows
    with no artifact block keep bWAR. Every other column (salary, the runs
    decomposition, WAA, WAR_rep, ...) is untouched and WAR_bwar carries the
    original. Batting values do not move today (ewb == bwb at fielding swap
    weight 0.0) but the same distribution runs so the frame stays correct if
    fielding ever does. Note the decomposition columns still describe the
    bWAR row: WAR is FIP-repriced, WAA / runs_above_avg are not.

    THE ASYMMETRY THIS GUARDS (2026-08-04, root-caused 2026-08-06). The
    docstring here used to say both calls were "cached by pybaseball". Only one
    is. `pybaseball.bwar_bat` resolves into pybaseball/cache/cache.py, so it is
    wrapped by the disk cache; `pybaseball.bwar_pitch` resolves to its own
    module carrying NO decorator at all. Batting serves from a local parquet
    for a week at a time while pitching is a live download on every process
    that builds an index.

    That is why the outage was always the pitching side, and why it looked
    random. One failed download blanked 79 of 228 free agents on the 2027
    board, and nothing raised, because the caller swallowed the per-side error
    and returned a batting-only index that was structurally perfect.

    So this keeps its own last-good copy per side. A successful download is
    written to .cache/war_daily/<side>.parquet; a failed one falls back to that
    copy rather than propagating. The fallback is LOUD and it is RECORDED:
    served_stale() names any side currently being served from disk, with the
    age, so a caller can refuse to publish off it. Pass allow_stale=False to
    opt out and get the raw exception.

    What this does NOT do is mask a permanent break. With no cached copy the
    original exception propagates untouched, which is the first-run and
    fresh-checkout behaviour, and the per-site try/except policy stays where it
    always lived, at the call sites."""
    _require(provider)
    _check_side(side, "stint-frame")
    raw = _bwar_stint_frame(side, allow_stale)
    if _frame_provider(provider) == "bwar":
        return raw
    return _ewar_frame(raw, side, door="stint")


def _bwar_stint_frame(side: str, allow_stale: bool):
    """Provider 'bwar' body of stint_frame, verbatim from lane B1."""
    import pybaseball as pyb
    fn = pyb.bwar_bat if side == "bat" else pyb.bwar_pitch
    try:
        df = fn(return_all=True)
    except Exception as exc:
        if not allow_stale:
            raise
        cached = _load_last_good(side)
        if cached is None:
            log.error(
                "war_daily %s frame failed and there is no cached copy to fall "
                "back to: %s. Every %s-only player will fail to resolve.",
                side, exc, side)
            raise
        age = _last_good_age_days(side)
        log.error(
            "war_daily %s frame failed (%s); SERVING A CACHED COPY %s days old "
            "with %d rows. This is degraded, not healthy: check "
            "war_source.served_stale() before publishing off it.",
            side, exc, "unknown" if age is None else f"{age:.1f}", len(cached))
        _SERVED_STALE[side] = {"age_days": age, "rows": len(cached),
                               "error": f"{type(exc).__name__}: {exc}"}
        return cached
    _SERVED_STALE.pop(side, None)
    _store_last_good(side, df)
    return df


# --- the eWAR frame transform ----------------------------------------------

#: Covered player-seasons whose frame bWAR no longer matches the artifact before
#: a board is called stale. Not zero: B-Ref revises single rows all the time and
#: one revision is not a staleness signal. It is a POLICY number, not a fitted
#: one, and it is here rather than in a caller so the three boards cannot drift.
EWAR_STALE_REVISED_MAX: int = 25


def ewar_vintage(as_of: str | None = None) -> dict:
    """What build the served eWAR numbers come from, and whether it has fallen
    behind the frame underneath them.

    WHY THIS EXISTS (audit F10-02 / F11-01, 2026-09-10). `data/ewar.json` is
    HAND-BUILT: nothing in run_monthly, build_site or deploy runs
    tools/build_ewar.py, so the served WAR numerator sits at the artifact's own
    generated_at while innings, ERA and the bWAR input on the same served row
    refresh nightly. Measured on the 2026-09-03 build: 422 of 773 pitcher cards
    carried a stale numerator, 71 of them off by a full display step.

    The staleness is CURRENT-SEASON ONLY, and that distinction is the useful
    part: 0 of 855 2024 and 0 of 873 2025 pitcher-seasons drift against the
    artifact, so career totals, WAG inputs and the eFV labels carry one stale
    cell rather than a stale series.

    This REPORTS and never raises. A scheduled rebuild is an owner decision about
    the whole re-anchor cascade (WAR_BASIS_RUNBOOK step B ends "INVALIDATES:
    everything below", and below it sit the career_war rebase, the pooled outcome
    curve, the empirical anchors, the slot curve and the projections retrain), so
    a nightly rebuild with none of that would drift the label out from under
    artifacts fitted on a named build, which is a worse defect than this one. The
    board therefore publishes its vintage and a test fails on the drift; the
    export stays up, because taking the boards down over a disclosure problem
    trades one outage for another.

    `bwar_revised` is the direct evidence and is already computed by the frame
    transform, so no new pass over the data is needed. It is empty until a frame
    has been read on provider 'ewar_v2' in this process, which is stated rather
    than faked."""
    diag = ewar_frame_diagnostics()
    gen = None
    for side in _SIDES:
        g = (diag.get(side) or {}).get("artifact_generated_at")
        if g:
            gen = g
            break
    if gen is None:
        try:
            import ewar as _ewar   # noqa: PLC0415 - optional, artifact may be absent
            gen = (_ewar.load() or {}).get("generated_at")
        except Exception:   # noqa: BLE001 - absence is a reportable state
            gen = None
    revised = {s: int((diag.get(s) or {}).get("bwar_revised") or 0) for s in _SIDES}
    covered = {s: int((diag.get(s) or {}).get("covered_player_seasons") or 0)
               for s in _SIDES}
    worst = max(revised.values()) if revised else 0
    out = {
        "artifact_generated_at": gen,
        "as_of": as_of,
        "bwar_revised": revised,
        "covered_player_seasons": covered,
        "threshold": EWAR_STALE_REVISED_MAX,
        "frames_read": bool(diag),
        "build_command": EWAR_BUILD_CMD,
        "rebuilds_on_a_schedule": False,
        "note": ("data/ewar.json is hand-built; nothing in the pipeline rebuilds "
                 "it. Completed seasons do not drift, so a gap here is a "
                 "current-season staleness in the WAR numerator while the "
                 "denominator on the same row is current."),
    }
    if not diag:
        out["stale"] = None
        out["reason"] = ("no eWAR frame has been read in this process, so the "
                         "drift count is unavailable rather than zero")
    else:
        out["stale"] = worst > EWAR_STALE_REVISED_MAX
        if out["stale"]:
            out["warning"] = (
                f"{worst} covered player-seasons no longer match the eWAR artifact "
                f"built {gen}; the served WAR numerator is behind its own frame "
                f"(rebuild: {EWAR_BUILD_CMD}, then the runbook cascade)")
            log.warning(out["warning"])
    return out


#: {side: receipt} for the last _ewar_frame call per side in this process.
_EWAR_FRAME_DIAG: dict[str, dict] = {}


def ewar_frame_diagnostics() -> dict[str, dict]:
    """Receipts from the last ewar_v2 frame transform per side:
      rows                     frame rows
      covered_rows             rows whose (mlb_ID, year_ID) has an artifact
                               block with this side
      covered_player_seasons   distinct such (mlb_ID, year_ID)
      artifact_player_seasons  blocks with this side in the artifact
      bwar_revised             covered player-seasons whose frame bWAR sum
                               differs from the artifact's bwp/bwb by more
                               than 0.005: B-Ref revised the row, or the
                               season advanced since generated_at. The
                               artifact's eWAR is served either way.
      delta_sum                sum over covered rows of (WAR - WAR_bwar):
                               the league-level move this transform made
      artifact_generated_at
    Empty until a frame has been read on provider 'ewar_v2'."""
    return {k: dict(v) for k, v in _EWAR_FRAME_DIAG.items()}


def _artifact_side_targets(blob: dict, side: str
                           ) -> dict[tuple[int, int], tuple[float, float | None]]:
    """{(mlbam, season): (ewar_side, bwar_side)} for every block carrying the
    side, read through ewar.ewar_for so the field semantics live in one place."""
    import ewar
    ek, bk = (("ewar_bat", "bwar_bat") if side == "bat"
              else ("ewar_pit", "bwar_pit"))
    out: dict[tuple[int, int], tuple[float, float | None]] = {}
    for mid_s, seasons in (blob.get("players") or {}).items():
        mid = int(mid_s)
        for season_s in seasons:
            rec = ewar.ewar_for(mid, int(season_s), payload=blob)
            if rec is None or rec.get(ek) is None:
                continue
            bw = rec.get(bk)
            out[(mid, int(season_s))] = (float(rec[ek]),
                                         None if bw is None else float(bw))
    return out


def _ewar_frame(df, side: str, *, door: str):
    """Replace WAR on a war_daily frame with the eWAR v2 series (stint_frame
    docstring). Adds WAR_bwar (the original). Keeps every other column and
    the row order. Rows without an artifact block keep bWAR."""
    import numpy as np
    import pandas as pd

    blob = _payload()
    targets = _artifact_side_targets(blob, side)
    out = df.copy()
    out["WAR_bwar"] = out["WAR"]
    receipt = {
        "door": door, "rows": int(len(out)), "covered_rows": 0,
        "covered_player_seasons": 0, "artifact_player_seasons": len(targets),
        "bwar_revised": 0, "delta_sum": 0.0,
        "artifact_generated_at": blob.get("generated_at"),
    }
    if not len(out) or not targets:
        _EWAR_FRAME_DIAG[side] = receipt
        return out

    mid = pd.to_numeric(out["mlb_ID"], errors="coerce")
    yr = pd.to_numeric(out["year_ID"], errors="coerce")
    war = pd.to_numeric(out["WAR"], errors="coerce")
    ok = mid.notna() & yr.notna() & war.notna()
    ok_idx = ok[ok].index
    keys = list(zip(mid[ok_idx].astype("int64").tolist(),
                    yr[ok_idx].astype("int64").tolist()))
    hit = [targets.get(k) for k in keys]
    cov_pos = [i for i, h in enumerate(hit) if h is not None]
    if not cov_pos:
        _EWAR_FRAME_DIAG[side] = receipt
        return out
    cov_idx = ok_idx[cov_pos]
    expo_col = _EXPOSURE_COL[side]
    if expo_col in out.columns:
        expo = pd.to_numeric(out.loc[cov_idx, expo_col], errors="coerce")
        expo = expo.fillna(0.0).clip(lower=0.0).astype("float64")
    else:
        expo = pd.Series(1.0, index=cov_idx)
    w = pd.DataFrame({
        "war": war[cov_idx].astype("float64"),
        "expo": expo,
        # one int64 group id per (mlbam, season); mlbams are < 10**6
        "g": np.asarray([keys[i][0] * 10000 + keys[i][1] for i in cov_pos],
                        dtype="int64"),
        "tgt": np.asarray([hit[i][0] for i in cov_pos], dtype="float64"),
        "bart": np.asarray([np.nan if hit[i][1] is None else hit[i][1]
                            for i in cov_pos], dtype="float64"),
    }, index=cov_idx)
    grp = w.groupby("g", sort=False)
    fsum = grp["war"].transform("sum")
    esum = grp["expo"].transform("sum")
    n = grp["war"].transform("count").astype("float64")   # no NaN here: == size
    weight = np.where(esum.values > 0,
                      w["expo"].values / np.where(esum.values > 0, esum.values, 1.0),
                      1.0 / n.values)
    new_war = w["war"].values + (w["tgt"].values - fsum.values) * weight
    out.loc[cov_idx, "WAR"] = new_war

    per = grp.agg(fsum=("war", "sum"), bart=("bart", "first"))
    revised = per["bart"].notna() & ((per["fsum"] - per["bart"]).abs() > 0.005)
    receipt.update({
        "covered_rows": int(len(cov_idx)),
        "covered_player_seasons": int(len(per)),
        "bwar_revised": int(revised.sum()),
        "delta_sum": float(np.sum(new_war - w["war"].values)),
    })
    _EWAR_FRAME_DIAG[side] = receipt
    if receipt["bwar_revised"]:
        log.info("war_source: %s %s frame: %d of %d covered player-seasons have "
                 "a bWAR sum that no longer matches the artifact (built %s); "
                 "serving the artifact's eWAR. Rebuild: %s",
                 side, door, receipt["bwar_revised"], len(per),
                 blob.get("generated_at"), EWAR_BUILD_CMD)
    return out


# --- last-good cache -------------------------------------------------------
# Deliberately this module's own cache rather than a patch to pybaseball's:
# the failure it covers is a network read, and we want a copy we control, in a
# format we can date, with a record of when we fell back to it. It always
# holds the RAW bWAR download; the eWAR transform runs on top of it.

#: {side: {"age_days": float|None, "rows": int, "error": str}} for any side
#: currently being served from disk. Empty when everything is live.
_SERVED_STALE: dict[str, dict] = {}


def served_stale() -> dict[str, dict]:
    """Sides currently served from the last-good cache, with age and cause.

    Empty dict means every frame this process read came off the wire. A caller
    that publishes a board should treat a non-empty result the way it treats
    fa_ident.index_sides_missing(): as a reason to refuse to overwrite a good
    artifact with a degraded one."""
    return dict(_SERVED_STALE)


def _cache_dir():
    d = Path(__file__).resolve().parent / ".cache" / "war_daily"
    return d


def _cache_path(side: str):
    return _cache_dir() / f"{side}.parquet"


def _last_good_age_days(side: str):
    import time
    p = _cache_path(side)
    try:
        return (time.time() - p.stat().st_mtime) / 86400.0
    except OSError:
        return None


def _load_last_good(side: str):
    p = _cache_path(side)
    if not p.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
    except Exception:
        log.exception("war_source: unreadable last-good %s frame at %s", side, p)
        return None
    return df if len(df) else None


def _store_last_good(side: str, df) -> None:
    """Best effort, and never fatal: a cache write failing must not take down a
    read that already succeeded.

    Written to a SIBLING temp then os.replace'd, so a reader concurrent with
    the write sees the old copy or the new one, never a half file. Same rule as
    storage._dump, and for the same reason: a truncated artifact that still
    parses is the worst outcome available."""
    if df is None or not len(df):
        return
    import os
    p = _cache_path(side)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    except Exception:
        log.warning("war_source: could not cache the %s frame (continuing)",
                    side, exc_info=True)
        try:
            tmp.unlink()
        except OSError:
            pass


def run_value_frame(side: str = "bat", *, provider: str = DEFAULT_PROVIDER):
    """The run-value decomposition read: the stint frame selected for its
    component columns (WAR_def, runs_position, runs_bat, runs_br, runs_dp,
    PA, pitcher, ...). Defaults to the batting frame, which carries the
    fielding/positional decomposition tools/build_def_history.py consumes.
    Under 'ewar_v2' the decomposition columns are the bWAR row's (only WAR is
    replaced, WAR_bwar added); on the batting frame WAR itself does not move
    today (fielding swap weight 0.0)."""
    return stint_frame(side, provider=provider)


# ---------------------------------------------------------------------------
# the name index
# ---------------------------------------------------------------------------

def name_index(*, provider: str = DEFAULT_PROVIDER) -> dict[str, dict[int, dict]]:
    """{normalized_name: {mlb_ID: {"years": set[int], "war": {year: WAR}}}}
    across both war_daily sides - the veteran identity index. Delegates to
    fa_ident.war_daily_index (lru-cached there; use fa_ident.resolve for
    windowed disambiguation, never guess here).

    PROVIDER-INVARIANT ON PURPOSE. This index is identity (names, ids, the
    seasons a player appeared), not a served WAR: the facade applies no
    transform here and every servable provider returns the same object. Its
    "war" values ride whatever frame the process default serves (fa_ident
    reads stint_frame on the default provider), which is eWAR on covered
    pitcher-seasons and bWAR elsewhere; nothing prices off them, and the
    seasons a row exists in are the same under either series. Served WAR
    comes from career_war_table / side_war_by_season / stint_frame, never
    from here."""
    _require(provider)
    import fa_ident
    return fa_ident.war_daily_index()


# ---------------------------------------------------------------------------
# player_key -> mlbam (the join the artifact needs)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent

#: Fallback bindings after the canonical table, in resolution order.
MLBAM_OVERRIDE_FILES: tuple[Path, ...] = (
    _ROOT / "data" / "sources" / "mlbam_id_overrides.json",
    _ROOT / "data" / "sources" / "mlbam_id_overrides_busts.json",
)

_MLBAM_INDEX: dict[str, int] | None = None


def mlbam_index(refresh: bool = False) -> dict[str, int]:
    """{player_key: mlbam}, memoised per process. Not a fourth resolver: a
    router over the bindings the repo already keeps, in this order, and a key
    already bound is never re-pointed by a later source:

      1. storage.load_mlbam_player_keys() inverted - player_photos, the
         canonical durable mlbam <-> player_key table (storage.bind_player_ids
         guards it in both directions). 7,763 bindings, 0 keys on two ids,
         2026-09-03.
      2. data/sources/mlbam_id_overrides.json (735 keys, the old-cohort
         resolve, tools/efv_oldcohort_id_resolve.py).
      3. data/sources/mlbam_id_overrides_busts.json (283 keys).

    Measured 2026-09-03: 38 override keys are also in player_photos and 3 of
    them disagree (tyler_wilson, jose_alvarez, kyle_mcpherson: two humans per
    slug), which is why the binding table wins. Merged 8,460 keys; 2,524 of
    2,666 career_war rows resolve. The 142 that do not are the identity gap
    the rebase tool must report, not guess."""
    global _MLBAM_INDEX
    if _MLBAM_INDEX is not None and not refresh:
        return _MLBAM_INDEX
    import json
    out: dict[str, int] = {}
    try:
        import storage
        for mid_s, key in storage.load_mlbam_player_keys().items():
            try:
                out.setdefault(key, int(mid_s))
            except (TypeError, ValueError):
                continue
    except Exception:
        log.warning("war_source.mlbam_index: player_photos unreadable; "
                    "falling through to the override files", exc_info=True)
    for path in MLBAM_OVERRIDE_FILES:
        try:
            blob = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, mid in (blob or {}).items():
            try:
                out.setdefault(str(key), int(mid))
            except (TypeError, ValueError):
                continue
    _MLBAM_INDEX = out
    return out


def mlbam_for(player_key: str) -> int | None:
    """The mlbam a player_key resolves to under mlbam_index(), or None."""
    if not player_key:
        return None
    return mlbam_index().get(str(player_key))
