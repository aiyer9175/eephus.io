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

PROVIDER CONTRACT (eWAR epoch, owner decision 2026-09-03; fWAR label epoch,
owner decisions 2026-09-17 and EPOCH-Q4 2026-09-30, flipped 2026-10-03).

  'fwar'     THE DEFAULT since the fWAR label epoch's step D + U (2026-10-03):
             the TRAINING LABEL and every anchor, refit, backtest, eval and
             gate statistic read it through this default. It is NOT the
             displayed WAR: the owner kept eWAR v2 on every surface a visitor
             sees (EPOCH-Q4 "Keep eWAR v2 shown"), so every display door
             (the player pages and WAR tables, the mlbstats boards' side WAR
             and WAR-rate columns through bullpen_export.served_war_basis, the
             PAL history, the trade lookup, the Earned board, F-DEF's input
             file, the identity helpers, the FA Archive, the timeseries
             `career_war` block) passes provider=DISPLAY_PROVIDER explicitly.
             Its contract is further down this list.
  'ewar_v2'  THE DISPLAYED WAR (explicit on every display door) and, until
             2026-10-03, the default and label series site-wide. eWAR v2
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
  'fwar'     PUBLISHED fWAR, the fWAR label epoch's label (owner O1 and O2,
             2026-09-17; docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md),
             servable through every door and THE DEFAULT since the epoch's
             step D + U (2026-10-03, one commit with the epoch bump and the
             label= fingerprint term fwar@<vintage id>). It reads ONLY the frozen
             vintage data/fwar_vintage.json (fwar_vintage.py; written once by
             tools/build_fwar_vintage.py at EPOCH_D9_FREEZE), never the live
             sabermetrics feed, and it is built ON the incumbent: every door
             first computes the 'ewar_v2' answer, then replaces it with fWAR
             where the vintage has the (mlbam, season) in an fwar season
             (both groups frozen) and keeps the incumbent value elsewhere,
             recorded, never silent. So the eWAR v2 series stays
             reconstructible beside it (gate part 4.1 note 2): the aggregate
             carries `seasons_ewar_v2` beside `seasons_bwar`, the frames carry
             `WAR_ewar_v2` beside `WAR_bwar`. A player-season's fWAR is the
             hitting group's war plus the pitching group's war (the bWAR
             aggregate's two-frame summing rule). On the frames the side
             total is split across a player-season's stints exactly as
             _ewar_frame splits eWAR v2 (the bWAR stint plus a share of the
             delta in proportion to PA or IPouts, equal shares without that
             column; _exposure_split is the one implementation); a stint whose
             bWAR is blank counts as 0.0 there, so a side the feed prices and
             B-Ref left blank still lands on the frame. DataUnavailable when
             the vintage is absent (it is absent until EPOCH_D9_FREEZE) or
             when the incumbent's artifact is.
  'ewar_v3'  eWAR v3, THE DISPLAYED WAR once EWAR_V3_LIVE is on (owner answers
             EBR-Q5 and EW3-19; docs/ebr-2026-09-30/EBR_GATE.md 11.10): the
             'fwar' series plus the named, zero-sum departures of
             data/ewar_v3.json (ewar_v3.py; tools/build_ewar_v3.py). Every door
             first computes the 'fwar' answer, then adds the departure of each
             (mlbam, season, side) the artifact lists; anything not listed is
             fWAR. Two series share the artifact: the headline eWAR (the
             default) and eWAR realized (side_war_by_season(series="realized"),
             the frames' WAR_realized column, row_on_provider's
             seasons_ewar_realized). Never DEFAULT_PROVIDER and never a training
             label; refused on the arb_spine door (refuse_on_door).
             DataUnavailable when the vintage, the incumbent's artifact or
             data/ewar_v3.json is absent.

THE BASIS DECISION IS NOT AN ACCURACY CLAIM. The eval record
(data/ewar_eval.json) is: gate 1 team wins r 0.8595 vs bWAR 0.8803 (a
descriptive loss, by construction for any FIP WAR); gate 2 pitcher
persistence 0.3617 vs 0.1768 (2.0x). The eFV label swap (R3a, 2026-08-04)
moved the margin over consensus by -0.0011 hit / -0.0115 pit, a floor-sized
effect that is UNEXCLUDED. Copy must say the flip is a basis choice.

THE RE-ENTRANCY TRAP AND THE FRAME PIN. Label readers (fa_projection.py,
proj_backtest.py, arb_dataset.py, the labs, ...) call stint_frame(side) on the
DEFAULT provider, which now means fWAR; display readers (mlb_player_export.py,
fa_ident.py, proj_export.py, pal_export.py, war_board_export.py, ...) name
provider="ewar_v2". Two transforms in this module need the
raw bWAR frame underneath either kind of reader: career_war_bulk (the aggregate it
transforms must be bWAR so `seasons_bwar` is bWAR) and side_war_by_season
(the map it fills from must be bWAR). They wrap the call in
_frames_pinned('bwar'), a process-global pin that every stint_frame /
condensed_frame call inside the window honours, whatever provider it names.
The pin is visible to worker threads on purpose (stats fetches both sides on
a ThreadPoolExecutor) and is not safe against two providers pinned
concurrently; the pipeline is a single writer.

FRESHNESS. Covered player-seasons are pinned to the ARTIFACT (its ewp/ewb
side totals), so the served WAR of a covered pitcher-season moves only when
data/ewar.json is rebuilt. ewar_frame_diagnostics() counts the player-seasons
whose frame bWAR sum no longer matches the artifact's bwp/bwb (a B-Ref revision
or an in-season update since the build), per season.

THE NIGHTLY CADENCE (owner decision D11, 2026-09-11: NIGHTLY). run_daily runs
EWAR_NIGHTLY_CMD before the timeseries rebuild (and the monthly runs it before
its first WAR reader). It rebuilds ONLY the live season and carries every
completed season forward byte for byte, so:
  - a season is COMPLETE from EWAR_FREEZE_MONTH_DAY of its own year; the first
    nightly on or after that date prices it one last time and FREEZES it. A
    hand build froze only the seasons that were complete on the day it was
    BUILT (ewar_complete_at_build), so a season it priced in progress is
    re-priced by the next nightly, never frozen at the in-progress numbers;
  - a frozen season's blocks are never rewritten by the nightly (each carries
    a sha256 in meta.cadence.frozen_digests and ewar_cadence_status fails on a
    mismatch); only a hand full build (EWAR_BUILD_CMD) re-prices one, and that
    is the runbook cascade;
  - `generated_at` is the build identity of the FROZEN series and does not
    move nightly, which is what storage.board_basis_fingerprint's label term
    reads, so the board basis does not churn with the live season;
    `live_built_at` is the live season's build time, and ewar_vintage reports it
    as the served numerator's build;
  - the box restores the COMMITTED data/ewar.json before every run
    (deploy/nightly-build.sh `git checkout -- .`), so the nightly keeps its own
    state in an untracked copy (tools/build_ewar.CARRY_PATH, under .cache) and
    starts from it whenever it descends from the committed build.
The fitted artifacts the runbook rebuilds after step B (the pooled outcome
curve, the empirical anchors, the draft slot curve, the war_rate_plus vintages,
the eFV matrices and floors, the career_war rebase) read completed seasons, which
the nightly never moves, so none of them rebuilds nightly.

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
#: stays first: it is the INPUT frame the others are built on.
PROVIDERS: tuple[str, ...] = ("bwar", "ewar_v2", "ewar_merged", "fwar", "ewar_v3")

#: The LABEL WAR site-wide: published fWAR from the frozen vintage (owner
#: decisions O1 and O2 of 2026-09-17; docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md,
#: flipped at the epoch's step D + U on 2026-10-03). Every reader that feeds a
#: training label, a label corpus, a refit, a backtest, an eval artifact or a
#: gate statistic follows this default. The DISPLAYED WAR stays eWAR v2 (owner
#: answer EPOCH-Q4, "Keep eWAR v2 shown", 2026-09-30; orchestrator ruling
#: EPOCH-Q4-IMPL R1a): every display door names provider="ewar_v2" explicitly
#: and never reads this default (test_epoch_display_doors.py pins each one).
DEFAULT_PROVIDER: str = "fwar"

#: eWAR v3 serves as THE displayed WAR, plain "eWAR", on every display door,
#: player pages included (owner answers EBR-Q5 and EW3-19; EBR_GATE.md 11.10.5),
#: with eWAR v2, fWAR and bWAR as reference columns. Off: the doors show eWAR v2.
EWAR_V3_LIVE: bool = True

#: The WAR a visitor SEES. Display doors pass this explicitly
#: (test_epoch_display_doors.py pins each door to it).
DISPLAY_PROVIDER: str = "ewar_v3" if EWAR_V3_LIVE else "ewar_v2"

#: How to (re)build the artifact 'ewar_v3' serves from.
EWAR_V3_BUILD_CMD: str = "python tools/build_ewar_v3.py --write"

#: Doors a provider is refused on: the arbitration model's WAR spine is a fitted
#: consumer's input, which eWAR v3 never is (EBR_GATE.md part 9.1, kept by 11.10).
REFUSED_DOORS: dict[str, tuple[str, ...]] = {"ewar_v3": ("arb_spine",)}

#: How to write the frozen vintage 'fwar' serves from (EPOCH_D9_FREEZE runs it
#: once; equal to fwar_vintage.BUILD_CMD, pinned by test).
FWAR_BUILD_CMD: str = "python tools/build_fwar_vintage.py --freeze 2000-2026 --write"

#: How to (re)build the artifact 'ewar_v2' serves from. The 2011 floor is the
#: first season the eFV first-6yr label pool reaches; the FIP corpus prices
#: 2011-2015 in full (707/707 .. 808/810 pitcher rows, tools/build_ewar.py).
EWAR_BUILD_CMD: str = "python tools/build_ewar.py --first 2011 --last 2026 --write"

#: The daily step (run_monthly run_daily, before d9): the live season only.
EWAR_NIGHTLY_CMD: str = "python tools/build_ewar.py --nightly --write"

#: A season is complete, and freezes, on this (month, day) of its own year: the
#: regular season and the postseason are over and Baseball-Reference's
#: end-of-season revisions have landed. The same rule fg_leaderboards uses.
EWAR_FREEZE_MONTH_DAY: tuple[int, int] = (11, 1)

#: The oldest a live-season input may be when the nightly prices on it, in
#: hours before the build (the StatsAPI season stats behind the live FIP, the
#: standings blob behind the replacement level). Their shared scraper cache
#: refetches the current season after 24 hours, so a healthy night reads inputs
#: under a day old; 36 leaves room for a late cron. A POLICY number.
EWAR_LIVE_INPUT_MAX_AGE_HOURS: float = 36.0

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


def _fwar_available() -> bool:
    """True when 'fwar' can serve: a memoised vintage (fwar_vintage._CACHE, the
    test seam) or data/fwar_vintage.json on disk."""
    import fwar_vintage
    return fwar_vintage.available()


def _fwar_missing_message() -> str:
    import fwar_vintage
    return (
        f"WAR provider 'fwar' is declared but its frozen vintage is missing: "
        f"{fwar_vintage.VINTAGE_PATH} (data/fwar_vintage.json, written once by "
        f"tools/build_fwar_vintage.py at EPOCH_D9_FREEZE). Build it: "
        f"{FWAR_BUILD_CMD}. 'fwar' never reads the live sabermetrics feed, and "
        f"nothing falls back to another provider on its own."
    )


def _require(provider: str) -> None:
    """Validate a provider id. ValueError on an unknown id; DataUnavailable
    (with the missing input named) on a declared-but-absent one. 'fwar' needs
    its frozen vintage AND the incumbent's artifact it is built on."""
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown WAR provider {provider!r}; known providers: {PROVIDERS}")
    if provider == "ewar_merged":
        raise DataUnavailable(_UNAVAILABLE[provider])
    if provider == "fwar":
        if not _fwar_available():
            raise DataUnavailable(_fwar_missing_message())
        if not _ewar_available():
            raise DataUnavailable(
                "WAR provider 'fwar' keeps the incumbent eWAR v2 series beside "
                "it, and that series' artifact is missing. " + _ewar_missing_message())
    if provider == "ewar_v2" and not _ewar_available():
        raise DataUnavailable(_ewar_missing_message())
    if provider == "ewar_v3":
        _require("fwar")
        import ewar_v3
        if not ewar_v3.available():
            raise DataUnavailable(
                f"WAR provider 'ewar_v3' is declared but its artifact is missing: "
                f"{ewar_v3.OUT} (data/ewar_v3.json). Build it: {EWAR_V3_BUILD_CMD} "
                f"(with EWAR_V3_LIVE on). Nothing falls back to another provider on its own.")


def refuse_on_door(provider: str, door: str) -> None:
    """ValueError when `provider` may not serve `door` (REFUSED_DOORS): eWAR v3
    on the arbitration spine, a fitted consumer's input."""
    if door in REFUSED_DOORS.get(str(provider), ()):
        raise ValueError(f"WAR provider {provider!r} is refused on the {door!r} door: eWAR v3 is never "
                         "an input to a fitted consumer (docs/ebr-2026-09-30/EBR_GATE.md part 9.1)")


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
    if provider in ("fwar", "ewar_v3"):
        idx = fwar_index()
        out = {key: _fwar_aggregate(_ewar_aggregate(agg, mlbam_by_key.get(key), blob),
                                    mlbam_by_key.get(key), idx)
               for key, agg in base.items()}
        if provider == "ewar_v3":
            out = {key: row_on_provider(row, "ewar_v3") for key, row in out.items()}
        return out
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


# --- the fwar transform (the funnel and the rebase tool share it) -----------

def fwar_index(vintage: dict | None = None) -> dict:
    """What the fwar transform reads from the frozen vintage, built once per
    call site: {"totals": {(mlbam, season): hitting war + pitching war},
    "fwar_years": {seasons whose every group is frozen}, "vintage_id": id}."""
    import fwar_vintage
    blob = fwar_vintage.load() if vintage is None else vintage
    return {"totals": fwar_vintage.season_totals(blob),
            "fwar_years": set(fwar_vintage.fwar_seasons(blob)),
            "vintage_id": blob.get("vintage_id")}


def fwar_seasons_from_incumbent(incumbent: dict, mlbam, idx: dict
                                ) -> tuple[dict[str, float], dict]:
    """THE SHARED FWAR TRANSFORM CONTRACT (war_source's 'fwar' funnel and
    tools/rebase_career_war.py --provider fwar call this one function, so the
    two agree bit for bit by construction):

        for season, inc in incumbent.items():
            if mlbam and int(season) in fwar_years and (mlbam, season) in totals:
                seasons[season] = round(totals[(mlbam, season)], 2)
            else:
                seasons[season] = inc                 # the eWAR v2 value, kept

    The season SET is the incumbent's: the transform moves values, it never adds
    or drops a season. Returns (seasons, receipt) where the receipt counts
    n_fwar, n_fallback_pre (a season the vintage does not serve as fwar: before
    its window, or recorded mixed or absent, which is the pre-2011 rule) and
    n_fallback_post (an fwar season with no feed row for this mlbam), with the
    years of each, and `war_basis` ('fwar' only when every season came from the
    vintage, else 'mixed'; gate part 4.1 note 3)."""
    totals = idx["totals"]
    years = idx["fwar_years"]
    seasons: dict[str, float] = {}
    pre: list[int] = []
    post: list[int] = []
    for yr_s, inc in sorted(incumbent.items(), key=lambda kv: int(kv[0])):
        yr = int(yr_s)
        tot = totals.get((int(mlbam), yr)) if (mlbam and yr in years) else None
        if tot is None:
            seasons[str(yr_s)] = inc
            (post if (mlbam and yr in years) else pre).append(yr)
        else:
            seasons[str(yr_s)] = round(float(tot), 2)
    n = len(seasons)
    receipt = {"n_seasons": n, "n_fwar": n - len(pre) - len(post),
               "n_fallback_pre": len(pre), "n_fallback_post": len(post),
               "fallback_pre_years": pre, "fallback_post_years": post,
               "war_basis": "fwar" if not (pre or post) else "mixed"}
    return seasons, receipt


def _fwar_aggregate(inc: dict, mlbam, idx: dict) -> dict:
    """One eWAR v2 aggregate (the incumbent) -> its fwar payload: the served
    `seasons` move to fWAR, `seasons_ewar_v2` keeps the incumbent, and
    `seasons_bwar` and `ewar_coverage` ride along from the incumbent."""
    inc_seasons = dict(inc.get("seasons") or {})
    seasons, rec = fwar_seasons_from_incumbent(inc_seasons, mlbam, idx)
    career = round(sum(seasons.values()), 2)
    n = len(seasons)
    out = dict(inc)
    out.update({
        "seasons": seasons,
        "career_war": career,
        "war_per_yr": round(career / n, 2) if n else 0.0,
        "war_seasons_count": n,
        "source": "fwar",
        "seasons_ewar_v2": inc_seasons,
        "fwar_coverage": {"vintage_id": idx.get("vintage_id"),
                          "mlbam": int(mlbam) if mlbam else None,
                          "incumbent_source": inc.get("source"), **rec},
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
    totals it. Re-transforming here would hide that state behind a read.

    Provider 'fwar' follows the same rule: the table as stored. The epoch's step
    C (tools/rebase_career_war.py --provider fwar) is what writes fwar rows, each
    carrying `seasons_ewar_v2` and `seasons_bwar` beside the served `seasons`."""
    _require(provider)
    import storage
    return storage.load_career_war()


def row_on_provider(row: dict | None, provider: str = DISPLAY_PROVIDER) -> dict:
    """One stored career_war row RE-EXPRESSED on `provider`'s series, for a
    reader that wants a series other than the one the row serves.

    The table serves the LABEL series (`seasons`, fwar since the epoch's step C)
    and keeps the incumbents beside it, so a display door (EPOCH-Q4: the WAR a
    visitor sees is eWAR v2) asks for its series here instead of reading
    `seasons` raw:

      'fwar'     the row as stored (an fwar row), or as stored when the vintage
                 never reached the row (an ewar_v2 or bbref row: nothing to
                 re-express, the receipt says so per row).
      'ewar_v2'  an fwar row re-derived from its kept `seasons_ewar_v2`: seasons,
                 career_war (2dp sum), war_per_yr (2dp), war_seasons_count and
                 source "ewar_v2", with `seasons_bwar` and `ewar_coverage` carried
                 and `fwar_coverage` dropped; stamped `incumbent_of: "fwar"`. Any
                 other row is returned as stored (it IS the eWAR v2 or bWAR row).
      'bwar'     a row carrying `seasons_bwar` re-derived from it (source "bbref",
                 `incumbent_of` the row's source); else as stored.
      'ewar_v3'  an fwar row with each season the vintage served moved by the
                 eWAR v3 artifact's headline departure (both sides summed, 2dp),
                 source "ewar_v3", `seasons_fwar` keeping the stored series and
                 `seasons_ewar_realized` the realized series beside it; a season
                 the vintage did not serve (fwar_coverage fallback years) keeps
                 its stored value. Any other row is returned as stored.

    Exposure maps (`seasons_pa`, `seasons_ip`) and every other key ride along
    unchanged: they describe the same stints whatever the series. The input is
    never mutated; {} in, {} out."""
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown WAR provider {provider!r}; known providers: {PROVIDERS}")
    row = dict(row or {})
    if not row:
        return row
    src = str(row.get("source") or "")
    if provider == "fwar" or provider == "ewar_merged":
        return row
    if provider == "ewar_v3":
        return _ewar_v3_row(row, src)
    if provider == "ewar_v2":
        if src != "fwar" or not isinstance(row.get("seasons_ewar_v2"), dict):
            return row
        series = dict(row["seasons_ewar_v2"])
    else:  # bwar
        if not isinstance(row.get("seasons_bwar"), dict):
            return row
        series = dict(row["seasons_bwar"])
    vals = [float(v) for v in series.values()]
    career = round(sum(vals), 2)
    n = len(vals)
    out = {k: v for k, v in row.items() if k != "fwar_coverage"}
    out.update({
        "seasons": series,
        "career_war": career,
        "war_per_yr": round(career / n, 2) if n else 0.0,
        "war_seasons_count": n,
        "source": "ewar_v2" if provider == "ewar_v2" else "bbref",
        "incumbent_of": src,
    })
    if provider == "bwar":
        out.pop("seasons_ewar_v2", None)
        out.pop("ewar_coverage", None)
    return out


def career_war_view(*, provider: str = DISPLAY_PROVIDER,
                    table: dict[str, dict] | None = None) -> dict[str, dict]:
    """The whole career_war table re-expressed on `provider` through
    row_on_provider (the table as stored when `provider` is the label series)."""
    if table is None:
        table = career_war_table()
    return {k: row_on_provider(v, provider) for k, v in table.items()}


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
    covered_fwar = 0
    vintage_ids: Counter = Counter()
    for row in table.values():
        by_source[str(row.get("source") or "unknown")] += 1
        total += len(row.get("seasons") or {})
        cov = row.get("ewar_coverage") or {}
        covered += int(cov.get("covered") or 0)
        for yr in cov.get("fallback_years") or []:
            fallback[int(yr)] += 1
        fcov = row.get("fwar_coverage") or {}
        if fcov:
            covered_fwar += int(fcov.get("n_fwar") or 0)
            vintage_ids[str(fcov.get("vintage_id"))] += 1
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
        # fWAR label epoch (step D + U): cells served from the frozen vintage, summed
        # over the fwar rows' fwar_coverage.n_fwar, and the vintage ids they name
        "season_values_fwar": covered_fwar,
        "share_fwar": round(covered_fwar / total, 4) if total else None,
        "fwar_vintage_ids": dict(sorted(vintage_ids.items())),
    }


def side_war_by_season(*, provider: str = DEFAULT_PROVIDER, series: str = "headline"
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
    stores 2dp sums, the map sums raw stints).

    THE RECEIPT. The overlay records, per side, a receipt of the same shape
    _ewar_frame writes (door "side_map"; see ewar_frame_diagnostics), so a
    process that builds a board from this map alone (the reliever, starter
    and hitter boards read nothing else) still reports a measured `stale` in
    ewar_vintage() instead of null. Covered = a pre-overlay bWAR cell with an
    artifact block carrying the side; revised = a covered cell whose bWAR
    differs from the block's bwar_bat / bwar_pit by more than 0.005 (the
    frame receipt's rule on the same stint sums). A frame receipt already
    recorded in the process against the SAME artifact build stays; one taken
    on another build (the nightly rewrote the file since) or an earlier
    side-map receipt is replaced, so the stamp always names the artifact the
    served map was overlaid with. A side whose bWAR frame was not read (the map
    has no cell for it) records a receipt marked `measured: False` instead of a
    count, and ewar_vintage then reports `stale` None with a reason naming that
    side: absent, never a clean zero. Provider 'bwar' records nothing.

    Provider 'fwar' starts from the 'ewar_v2' map (the incumbent, built and
    receipted exactly as above) and overlays the frozen vintage per side:
    "bat" := the hitting group's war and "pit" := the pitching group's war for
    every (mlbam, fwar season) the vintage carries, under the same blank-row
    rule (a 0.0 side the incumbent map lacks is not added). Every other cell
    keeps the incumbent value. Its receipt is fwar_frame_diagnostics()
    (door "side_map").

    Provider 'ewar_v3' starts from the 'fwar' map and adds each listed
    departure of data/ewar_v3.json to the side cell it belongs to; `series`
    picks the headline eWAR (default) or eWAR realized. A departure whose side
    cell the 'fwar' map lacks (the blank-row rule) is not added and is counted
    in ewar_v3_frame_diagnostics()["side_map"]. `series` is ignored by every
    other provider."""
    _require(provider)
    if provider == "fwar":
        return _fwar_side_map()
    if provider == "ewar_v3":
        return _ewar_v3_side_map(series)
    import mlb_player_export
    # pinned for both providers: _war_daily reads stint_frame on the default
    with _frames_pinned("bwar"):
        out = mlb_player_export._war_daily()
    if provider == "bwar":
        return out
    import ewar
    blob = _payload()
    cells = {s: sum(1 for by in out.values() for c in by.values() if s in c)
             for s in _SIDES}
    rec_ = {s: {"covered": 0, "artifact": 0, "revised": {}, "delta": 0.0}
            for s in _SIDES}
    for mid_s, seasons in (blob.get("players") or {}).items():
        mid = int(mid_s)
        for season_s in seasons:
            season = int(season_s)
            rec = ewar.ewar_for(mid, season, payload=blob)
            if rec is None:
                continue
            cell = out.setdefault(mid, {}).setdefault(season, {})
            for key, val, bw in (("bat", rec.get("ewar_bat"), rec.get("bwar_bat")),
                                 ("pit", rec.get("ewar_pit"), rec.get("bwar_pit"))):
                if val is None:
                    continue
                r = rec_[key]
                r["artifact"] += 1
                pre = cell.get(key)
                if pre is not None:   # covered: the bWAR cell this block replaces
                    r["covered"] += 1
                    r["delta"] += float(val) - pre
                    if bw is not None and abs(pre - float(bw)) > 0.005:
                        r["revised"][season] = r["revised"].get(season, 0) + 1
                if key not in cell and float(val) == 0.0:
                    continue          # the blank-row rule (docstring)
                cell[key] = float(val)
            if not cell:              # nothing landed, nothing was there
                out[mid].pop(season, None)
                if not out[mid]:
                    out.pop(mid, None)
    # the served numerator's build and the frozen series' build (_ewar_frame's)
    label = blob.get("generated_at")
    gen = blob.get("live_built_at") or label
    for side in _SIDES:
        prev = _EWAR_FRAME_DIAG.get(side) or {}
        frame_here = (prev.get("door") not in (None, "side_map")
                      and prev.get("artifact_generated_at") == gen
                      and prev.get("artifact_label_build_at") == label)
        if not cells[side]:
            # that side's bWAR frame was not read, so there is nothing to
            # measure on it. A receipt taken on an earlier build must not keep
            # printing a measured-looking flag: it is replaced by a marker that
            # says the side is unmeasured (absent, never a clean zero).
            if frame_here:
                continue              # a frame on this build did measure it
            _EWAR_FRAME_DIAG[side] = {
                "door": "side_map", "measured": False, "rows": 0,
                "reason": (f"the {side} bWAR frame was not read, so this side's "
                           "drift against the artifact is unmeasured"),
                "artifact_generated_at": gen,
                "artifact_label_build_at": label,
            }
            continue
        if frame_here:
            continue                  # a frame receipt on this same build stays
        r = rec_[side]
        _EWAR_FRAME_DIAG[side] = {
            "door": "side_map", "rows": cells[side], "covered_rows": r["covered"],
            "covered_player_seasons": r["covered"],
            "artifact_player_seasons": r["artifact"],
            "bwar_revised": sum(r["revised"].values()),
            "bwar_revised_by_season": {str(k): r["revised"][k]
                                       for k in sorted(r["revised"])},
            "delta_sum": float(r["delta"]),
            "artifact_generated_at": gen,
            "artifact_label_build_at": label,
        }
    return out


def _fwar_side_map() -> dict[int, dict[int, dict[str, float]]]:
    """side_war_by_season for provider 'fwar' (see its docstring)."""
    import fwar_vintage
    out = side_war_by_season(provider="ewar_v2")
    blob = fwar_vintage.load()
    for side in _SIDES:
        rec = {"door": "side_map", "covered_player_seasons": 0, "added": 0,
               "skipped_blank": 0, "delta_sum": 0.0,
               "vintage_player_seasons": 0, "vintage_id": blob.get("vintage_id")}
        targets = fwar_vintage.side_targets(blob, side)
        rec["vintage_player_seasons"] = len(targets)
        for (mid, season), val in targets.items():
            cell = out.get(mid, {}).get(season, {})
            pre = cell.get(side)
            if pre is None and float(val) == 0.0:
                rec["skipped_blank"] += 1      # the blank-row rule
                continue
            if pre is None:
                rec["added"] += 1
            else:
                rec["covered_player_seasons"] += 1
                rec["delta_sum"] += float(val) - float(pre)
            out.setdefault(mid, {}).setdefault(season, {})[side] = float(val)
        rec["rows"] = sum(1 for by in out.values() for c in by.values() if side in c)
        _FWAR_FRAME_DIAG[side] = rec
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
    fp = _frame_provider(provider)
    if fp == "bwar":
        return raw
    if fp == "fwar":
        return _fwar_frame(raw, side, door="condensed")
    if fp == "ewar_v3":
        return _ewar_v3_frame(raw, side, door="condensed")
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

    Provider 'fwar' is the 'ewar_v2' frame plus WAR_ewar_v2 (the incumbent's
    WAR), with WAR replaced on every row whose (mlbam, fwar season) the frozen
    vintage carries, by the same exposure split (_fwar_frame).

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
    fp = _frame_provider(provider)
    if fp == "bwar":
        return raw
    if fp == "fwar":
        return _fwar_frame(raw, side, door="stint")
    if fp == "ewar_v3":
        return _ewar_v3_frame(raw, side, door="stint")
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


# --- the cadence (nightly live season, frozen completed seasons) -------------

def ewar_season_complete(season: int, today=None) -> bool:
    """True from EWAR_FREEZE_MONTH_DAY of `season`'s own year onward."""
    import datetime as _dt
    today = today or _dt.date.today()
    m, d = EWAR_FREEZE_MONTH_DAY
    return (today.year, today.month, today.day) >= (int(season), m, d)


def ewar_build_date(payload: dict | None):
    """The calendar date of the artifact's build (`generated_at`), or None."""
    import datetime as _dt
    g = str((payload or {}).get("generated_at") or "")[:10]
    try:
        return _dt.date.fromisoformat(g)
    except ValueError:
        return None


def ewar_complete_at_build(payload: dict | None) -> list[int]:
    """The seasons of the artifact's window that were COMPLETE on the day it was
    built. On a hand build these are the seasons it priced final; a season it
    priced in progress is not among them however late the file is read, which is
    what stops a restored hand build from freezing a season at in-progress
    numbers (the box restores the committed file before every nightly)."""
    built = ewar_build_date(payload)
    lo, hi = ((payload or {}).get("seasons") or [None, None])[:2]
    if built is None or lo is None or hi is None:
        return []
    return [s for s in range(int(lo), int(hi) + 1) if ewar_season_complete(s, built)]


def ewar_season_digest(payload: dict, season: int) -> str:
    """sha256 over one season's blocks in canonical JSON (keys sorted, compact):
    {mlbam: block} for every player with that season. Two artifacts carry the
    same WAR for a season exactly when this digest agrees, whatever order the
    file lays players out in."""
    import hashlib
    import json
    s = str(int(season))
    blocks = {mid: by[s] for mid, by in (payload.get("players") or {}).items() if s in by}
    blob = json.dumps(blocks, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


def ewar_cadence(payload: dict | None = None) -> dict:
    """The artifact's cadence block (meta.cadence), or {} for a hand-built one."""
    if payload is None:
        try:
            payload = _payload()
        except Exception:   # noqa: BLE001 - absence is a reportable state
            return {}
    return dict(((payload or {}).get("meta") or {}).get("cadence") or {})


def _hours_between(earlier, later):
    """Hours from one ISO stamp to another (naive local stamps, as the nightly
    writes them), or None when either is missing or unparseable."""
    import datetime as _dt
    try:
        a = _dt.datetime.fromisoformat(str(earlier))
        b = _dt.datetime.fromisoformat(str(later))
    except (TypeError, ValueError):
        return None
    if (a.tzinfo is None) != (b.tzinfo is None):
        a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
    return (b - a).total_seconds() / 3600.0


def ewar_cadence_status(payload: dict | None = None, today=None) -> dict:
    """The nightly's FRESHNESS ASSERTION, as a report (never raises).

    ok is True only when all of these hold:
      - the artifact is a nightly build (meta.cadence.mode == "nightly");
      - the live season, if there is one and it is not complete, was built today;
      - the live season was priced on that night's inputs: war_daily came off
        the wire (not the last-good cache), and the StatsAPI season stats behind
        its FIP and the standings behind its replacement level were at most
        EWAR_LIVE_INPUT_MAX_AGE_HOURS old at the build;
      - every frozen season's blocks still hash to the digest recorded when it
        froze (the byte-identical promise, checked on the file itself);
      - every season of the window that is complete is frozen.
    `problems` names each failure. run_monthly logs it and records a heartbeat;
    the tests carry the loudness."""
    import datetime as _dt
    today = today or _dt.date.today()
    out = {"ok": None, "problems": [], "mode": None, "live_season": None,
           "live_built_at": None, "frozen_seasons": [], "label_build_at": None,
           "as_of": today.isoformat()}
    if payload is None:
        try:
            payload = _payload()
        except Exception as exc:   # noqa: BLE001
            out["ok"] = False
            out["problems"].append(f"data/ewar.json unreadable ({type(exc).__name__})")
            return out
    cad = ewar_cadence(payload)
    out.update(mode=cad.get("mode") or "hand", live_season=cad.get("live_season"),
               live_built_at=cad.get("live_built_at"),
               frozen_seasons=list(cad.get("frozen_seasons") or []),
               label_build_at=payload.get("generated_at"))
    if cad.get("mode") != "nightly":
        out["problems"].append("the artifact is hand-built: the nightly eWAR step has not run "
                               f"({EWAR_NIGHTLY_CMD})")
    live = cad.get("live_season")
    if live is not None and not ewar_season_complete(live, today):
        built = str(cad.get("live_built_at") or "")[:10]
        if built != today.isoformat():
            out["problems"].append(f"live season {live} last built {built or 'never'}, "
                                   f"not {today.isoformat()}")
        frames = cad.get("frames") or {}
        if frames.get("served_stale"):
            out["problems"].append("live season priced on the last-good war_daily cache "
                                   f"({sorted(frames['served_stale'])})")
        for key, what in (("fip_source_at", "StatsAPI season stats behind the live FIP"),
                          ("standings_at", "standings behind the live replacement level")):
            age = _hours_between(frames.get(key), cad.get("live_built_at"))
            if age is None:
                out["problems"].append(f"the {what} carry no vintage")
            elif age > EWAR_LIVE_INPUT_MAX_AGE_HOURS:
                out["problems"].append(f"the {what} were {age:.0f} hours old at the build "
                                       f"(limit {EWAR_LIVE_INPUT_MAX_AGE_HOURS:.0f})")
    digests = cad.get("frozen_digests") or {}
    for s in out["frozen_seasons"]:
        want = digests.get(str(s))
        if want is None:
            out["problems"].append(f"frozen season {s} has no recorded digest")
        elif ewar_season_digest(payload, s) != want:
            out["problems"].append(f"frozen season {s} no longer matches the digest it froze with")
    lo, hi = (payload.get("seasons") or [None, None])[:2]
    if lo is not None and hi is not None and cad.get("mode") == "nightly":
        for s in range(int(lo), int(hi) + 1):
            if ewar_season_complete(s, today) and s not in out["frozen_seasons"]:
                out["problems"].append(f"season {s} is complete but not frozen")
    out["ok"] = not out["problems"]
    return out


def ewar_vintage(as_of: str | None = None) -> dict:
    """What build the served eWAR numbers come from, and whether it has fallen
    behind the frame underneath them.

    WHY THIS EXISTS (audit F10-02 / F11-01, 2026-09-10). `data/ewar.json` was
    HAND-BUILT: nothing in the pipeline ran tools/build_ewar.py, so the served WAR
    numerator sat at the artifact's own generated_at while innings, ERA and the
    bWAR input on the same served row refreshed nightly. Measured on the
    2026-09-03 build: 422 of 773 pitcher cards carried a stale numerator, 71 of
    them off by a full display step.

    THE CADENCE (owner decision D11, 2026-09-11: nightly). Once the pipeline's
    eWAR step has written the artifact, `rebuilds_on_a_schedule` is True,
    `artifact_generated_at` is the live season's build (the served numerator's
    vintage, the date the boards print when `stale` fires) and `label_build_at`
    is the frozen series' build (`generated_at`, which the board fingerprint
    reads and which the nightly never moves). On a hand build the two are one
    stamp and the block says the artifact is hand-built. Both states are read
    from the artifact, never assumed: from the frame receipts first (the
    artifact the served frames, or the side map, were transformed with in this
    process), from the file when neither has been read.

    The staleness is CURRENT-SEASON ONLY, and that distinction is the useful
    part: 0 of 855 2024 and 0 of 873 2025 pitcher-seasons drift against the
    artifact, and a full rebuild on 2026-09-11 reproduced every 2011-2025 block
    byte for byte. `bwar_revised_live` and `bwar_revised_frozen` split the drift
    so a frozen-season revision (a B-Ref restatement; re-pricing it is a hand
    run with the cascade) is not mistaken for a missed nightly.

    This REPORTS and never raises: taking the boards down over a disclosure
    trades one outage for another, so the export stays up and a test fails on
    the drift instead. `bwar_revised` is empty until a frame or the side map
    (side_war_by_season, the boards' only WAR read) has been read on provider
    'ewar_v2' in this process, which is stated rather than faked."""
    diag = ewar_frame_diagnostics()
    blob = None
    try:
        import ewar as _ewar   # noqa: PLC0415 - optional, artifact may be absent
        blob = _ewar.load() or {}
    except Exception:   # noqa: BLE001 - absence is a reportable state
        blob = None
    cad = ewar_cadence(blob) if blob is not None else {}
    nightly = cad.get("mode") == "nightly"
    gen = label = None
    for side in _SIDES:
        g = (diag.get(side) or {}).get("artifact_generated_at")
        if g:
            gen = g
            label = (diag.get(side) or {}).get("artifact_label_build_at") or g
            break
    if gen is None and blob is not None:
        label = blob.get("generated_at")
        gen = (blob.get("live_built_at") or label) if nightly else label
    live = cad.get("live_season") if nightly else None
    if not nightly and blob:
        # a hand build has no cadence block: its live season is the last season
        # of its window that was still in progress on the day it was built
        hi = (blob.get("seasons") or [None, None])[-1]
        if hi is not None and int(hi) not in ewar_complete_at_build(blob):
            live = int(hi)
    # a side is MEASURED when a receipt for it counted coverage; a side map that
    # found no cell for it leaves a marker instead (side_war_by_season), and an
    # unmeasured side reports None rather than a zero it never measured
    measured = {s: bool(diag.get(s)) and (diag[s].get("measured") is not False)
                for s in _SIDES}
    revised = {s: (int((diag.get(s) or {}).get("bwar_revised") or 0)
                   if measured[s] else None) for s in _SIDES}
    covered = {s: (int((diag.get(s) or {}).get("covered_player_seasons") or 0)
                   if measured[s] else None) for s in _SIDES}
    by_season: dict[int, int] = {}
    for s in _SIDES:
        if not measured[s]:
            continue
        for yr, n in ((diag.get(s) or {}).get("bwar_revised_by_season") or {}).items():
            by_season[int(yr)] = by_season.get(int(yr), 0) + int(n)
    # absent, not zero, when no frame has been read (the same rule as `stale`)
    live_rev = by_season.get(int(live), 0) if (diag and live is not None) else None
    frozen_rev = (sum(n for yr, n in by_season.items() if live is None or yr != int(live))
                  if diag else None)
    _counts = [n for n in revised.values() if n is not None]
    worst = max(_counts) if _counts else 0
    out = {
        "artifact_generated_at": gen,
        "label_build_at": label,
        "as_of": as_of,
        "bwar_revised": revised,
        "bwar_revised_live": live_rev,
        "bwar_revised_frozen": frozen_rev,
        "covered_player_seasons": covered,
        "threshold": EWAR_STALE_REVISED_MAX,
        "frames_read": any(measured.values()),
        "build_command": EWAR_NIGHTLY_CMD if nightly else EWAR_BUILD_CMD,
        "rebuilds_on_a_schedule": nightly,
        "cadence": {"mode": cad.get("mode") or "hand", "live_season": live,
                    "frozen_through": max(cad.get("frozen_seasons") or [0]) or None},
        "note": (("data/ewar.json rebuilds its live season nightly; completed seasons are "
                  "frozen byte for byte and re-priced only by a hand build with the runbook "
                  "cascade.") if nightly else
                 ("data/ewar.json is hand-built; nothing in the pipeline has rebuilt it. "
                  "Completed seasons do not drift, so a gap here is a current-season "
                  "staleness in the WAR numerator while the denominator on the same row "
                  "is current.")),
    }
    unmeasured = [s for s in _SIDES if not measured[s]]
    if not diag:
        out["stale"] = None
        out["reason"] = ("no eWAR frame has been read in this process, so the "
                         "drift count is unavailable rather than zero")
    elif unmeasured and worst <= EWAR_STALE_REVISED_MAX:
        # one side measured clean is not the board's answer while the other side
        # was never read: say which side is missing rather than serve a bool for
        # it. Measured drift past the threshold still fires below.
        out["stale"] = None
        out["reason"] = ("no eWAR frame has been read for the "
                         + " and ".join(unmeasured)
                         + " side in this process, so its drift count is "
                           "unavailable rather than zero")
    else:
        out["stale"] = worst > EWAR_STALE_REVISED_MAX
        if out["stale"]:
            out["warning"] = (
                f"{worst} covered player-seasons no longer match the eWAR artifact "
                f"built {out['artifact_generated_at']}; the served WAR numerator is "
                f"behind its own frame (rebuild: {out['build_command']}"
                + ("" if nightly else ", then the runbook cascade") + ")")
            log.warning(out["warning"])
    return out


def _ewar_v3_vintage(v2: dict) -> dict:
    """ewar_vintage while the displayed eWAR is eWAR v3 (EBR_GATE.md 11.10.5): the
    served numbers are data/ewar_v3.json's, built on the FROZEN fWAR vintage, so the
    build stamp names that artifact and nothing drifts under it night to night
    (no frame revision can move a frozen published value). The eWAR v2 block the
    receipts measured rides along under `ewar_v2`, as the reference column's."""
    import ewar_v3
    try:
        blob = ewar_v3.load()
    except Exception as e:   # noqa: BLE001 - absence is a reportable state
        out = dict(v2)
        out.update({"series": "ewar_v3", "stale": None,
                    "reason": f"data/ewar_v3.json unreadable ({type(e).__name__})"})
        return out
    gen = blob.get("generated_at")
    return {
        "series": "ewar_v3",
        "artifact_generated_at": gen,
        "label_build_at": gen,
        "as_of": v2.get("as_of"),
        "fwar_vintage_id": blob.get("fwar_vintage_id"),
        "frames_read": v2.get("frames_read"),
        "build_command": EWAR_V3_BUILD_CMD,
        "rebuilds_on_a_schedule": False,
        "cadence": {"mode": "hand", "live_season": None,
                    "frozen_through": (blob.get("seasons") or [None, None])[-1]},
        "stale": False,
        "note": ("data/ewar_v3.json is FanGraphs' published WAR from the frozen vintage plus the site's "
                 "named departures; it moves only when it is rebuilt by hand."),
        "ewar_v2": {k: v2.get(k) for k in ("artifact_generated_at", "label_build_at", "stale",
                                           "bwar_revised", "build_command")},
    }


def safe_ewar_vintage(as_of: str | None = None) -> dict:
    """ewar_vintage for a served board: the served eWAR build stamp, or a stated
    absence. Never raises: a board that cannot report its vintage must still
    render (audit F10-02). `as_of` is the payload's own as_of, so the block
    dates the drift it measured. The six player and eWAR boards import this
    as their module-level _war_source_vintage (tests patch it there)."""
    try:
        out = ewar_vintage(as_of=as_of)
        # the displayed eWAR's own build stamp (EBR_GATE.md 11.10.5): eWAR v3's
        # artifact while it is the displayed series; ewar_vintage itself keeps
        # reporting the eWAR v2 artifact its receipts measure
        return _ewar_v3_vintage(out) if DISPLAY_PROVIDER == "ewar_v3" else out
    except Exception as e:   # noqa: BLE001 - reporting must not take a board down
        return {"artifact_generated_at": None, "stale": None,
                "reason": f"war_source.ewar_vintage unavailable ({type(e).__name__})"}


#: {side: receipt} for the last eWAR read per side in this process: an
#: _ewar_frame call (door "stint" / "condensed") or side_war_by_season's
#: overlay (door "side_map"), which yields to a frame receipt on the same build.
_EWAR_FRAME_DIAG: dict[str, dict] = {}


def ewar_frame_diagnostics() -> dict[str, dict]:
    """Receipts from the last ewar_v2 frame transform per side:
      door                     "stint" / "condensed" (a frame transform) or
                               "side_map" (side_war_by_season's overlay, which
                               yields to a frame receipt on the same build)
      rows                     frame rows (side_map: the bWAR map's cells
                               carrying the side, one per player-season)
      covered_rows             rows whose (mlb_ID, year_ID) has an artifact
                               block with this side: frame rows at the frame
                               doors (a player-season can hold several stints),
                               player-seasons at the side_map door, where the
                               map's unit is already the player-season
      covered_player_seasons   distinct such (mlb_ID, year_ID)
      artifact_player_seasons  blocks with this side in the artifact
      bwar_revised             covered player-seasons whose frame bWAR sum
                               differs from the artifact's bwp/bwb by more
                               than 0.005: B-Ref revised the row, or the
                               season advanced since generated_at. The
                               artifact's eWAR is served either way.
      bwar_revised_by_season   the same count per season ({"2026": n})
      delta_sum                sum over covered rows of (WAR - WAR_bwar):
                               the league-level move this transform made
      artifact_generated_at    the served numerator's build: live_built_at on
                               a nightly artifact, generated_at on a hand one
      artifact_label_build_at  generated_at (the frozen series' build)
      measured                 present and False only on the side_map marker
                               for a side whose bWAR frame was not read: that
                               side carries no counts and ewar_vintage reports
                               `stale` None with a reason naming it
    Empty until a frame or the side map has been read on provider 'ewar_v2'."""
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


def _exposure_split(out, side: str, war, targets: dict):
    """THE STINT SPLIT, one implementation for 'ewar_v2' and 'fwar'.

    `war` is the per-row base series (bWAR on both providers), `targets` maps
    (mlbam, season) to a tuple (side total, B-Ref side total or None). For every
    row with an mlbam, a season and a base value whose player-season has a
    target, the new value is

        base + (side total - sum of the player-season's bases) * weight

    with weight the row's share of the player-season's PA (bat) or IPouts
    (pit), or an equal share when that column is absent or sums to zero. So the
    stints of a covered player-season sum to its side total. Returns None when
    no row is covered, else (cov_idx, w, grp, new_war): the covered index, the
    per-row frame (war, expo, g, tgt, bart), its groupby on g and the new
    values in cov_idx order."""
    import numpy as np
    import pandas as pd

    mid = pd.to_numeric(out["mlb_ID"], errors="coerce")
    yr = pd.to_numeric(out["year_ID"], errors="coerce")
    ok = mid.notna() & yr.notna() & war.notna()
    ok_idx = ok[ok].index
    keys = list(zip(mid[ok_idx].astype("int64").tolist(),
                    yr[ok_idx].astype("int64").tolist()))
    hit = [targets.get(k) for k in keys]
    cov_pos = [i for i, h in enumerate(hit) if h is not None]
    if not cov_pos:
        return None
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
    return cov_idx, w, grp, new_war


#: {side: receipt} for the last 'fwar' read per side in this process: a frame
#: transform (door "stint" / "condensed") or the side map (door "side_map").
_FWAR_FRAME_DIAG: dict[str, dict] = {}


def fwar_frame_diagnostics() -> dict[str, dict]:
    """Receipts from the last 'fwar' read per side:
      door                     "stint" / "condensed" / "side_map"
      rows                     frame rows (side_map: cells carrying the side)
      covered_rows             frame rows that took an fWAR value
      covered_player_seasons   distinct (mlbam, season) that took one
      vintage_player_seasons   (mlbam, fwar season) the vintage carries for the side
      vintage_unplaced         of those, how many have no row on this frame
                               (the frames cannot carry a player-season B-Ref
                               has no stint for; the aggregate can)
      added / skipped_blank    side_map only: cells the incumbent map lacked
                               that fWAR added, and 0.0 sides not added
      delta_sum                sum over covered rows of (fWAR - incumbent)
      vintage_id               the frozen vintage's id
    Empty until a frame or the side map has been read on provider 'fwar'."""
    return {k: dict(v) for k, v in _FWAR_FRAME_DIAG.items()}


def _fwar_frame(df, side: str, *, door: str):
    """A war_daily frame on provider 'fwar' (module docstring, 'fwar'): the
    'ewar_v2' frame (WAR = eWAR v2, WAR_bwar added) plus WAR_ewar_v2 := that
    incumbent WAR, then WAR := the bWAR stint plus a PA / IPouts share of
    (fWAR side total - the player-season's bWAR sum) on every row whose
    (mlbam, fwar season) the vintage carries. A blank bWAR stint counts as
    0.0 in that split. Rows the vintage does not reach keep the incumbent."""
    import numpy as np
    import pandas as pd
    import fwar_vintage

    out = _ewar_frame(df, side, door=door)
    out["WAR_ewar_v2"] = out["WAR"]
    blob = fwar_vintage.load()
    side_t = fwar_vintage.side_targets(blob, side)
    receipt = {"door": door, "rows": int(len(out)), "covered_rows": 0,
               "covered_player_seasons": 0, "vintage_player_seasons": len(side_t),
               "vintage_unplaced": len(side_t), "delta_sum": 0.0,
               "vintage_id": blob.get("vintage_id")}
    if not len(out) or not side_t:
        _FWAR_FRAME_DIAG[side] = receipt
        return out
    base = pd.to_numeric(out["WAR_bwar"], errors="coerce").fillna(0.0)
    targets = {k: (v, None) for k, v in side_t.items()}
    split = _exposure_split(out, side, base, targets)
    if split is None:
        _FWAR_FRAME_DIAG[side] = receipt
        return out
    cov_idx, w, grp, new_war = split
    inc = pd.to_numeric(out.loc[cov_idx, "WAR_ewar_v2"], errors="coerce").fillna(0.0)
    out.loc[cov_idx, "WAR"] = new_war
    n_ps = int(w["g"].nunique())
    receipt.update({"covered_rows": int(len(cov_idx)), "covered_player_seasons": n_ps,
                    "vintage_unplaced": len(side_t) - n_ps,
                    "delta_sum": float(np.sum(new_war - inc.values))})
    _FWAR_FRAME_DIAG[side] = receipt
    return out


# --- the eWAR v3 transforms (provider 'ewar_v3', EBR_GATE.md 11.10) -----------

#: {door: receipt} for the last 'ewar_v3' read per door and side in this process.
_EWAR_V3_DIAG: dict[str, dict] = {}


def ewar_v3_frame_diagnostics() -> dict[str, dict]:
    """Receipts from the last 'ewar_v3' reads: per "<door>:<side>" the rows
    that took a departure, the listed departures with no cell or row to land on,
    the departure sum, and the artifact's build and vintage id."""
    return {k: dict(v) for k, v in _EWAR_V3_DIAG.items()}


def _ewar_v3_side_map(series: str = "headline") -> dict[int, dict[int, dict[str, float]]]:
    """side_war_by_season for provider 'ewar_v3' (see its docstring)."""
    import ewar_v3
    base = _fwar_side_map()
    out = {mid: {s: dict(c) for s, c in by.items()} for mid, by in base.items()}
    blob = ewar_v3.load()
    rec = {"door": "side_map", "series": series, "applied": 0, "absent_cell": 0, "delta_sum": 0.0,
           "generated_at": blob.get("generated_at"), "vintage_id": blob.get("fwar_vintage_id")}
    for (mid, season), cell_d in ewar_v3.departures(series=series).items():
        cell = (out.get(mid) or {}).get(season)
        for side, d in cell_d.items():
            if cell is None or side not in cell:
                rec["absent_cell"] += 1
                continue
            cell[side] = float(cell[side]) + float(d)
            rec["applied"] += 1
            rec["delta_sum"] += float(d)
    _EWAR_V3_DIAG["side_map:" + series] = rec
    return out


def _ewar_v3_row(row: dict, src: str) -> dict:
    """row_on_provider(row, 'ewar_v3'): see its docstring."""
    if src != "fwar" or not isinstance(row.get("seasons"), dict):
        return row
    import ewar_v3
    if not ewar_v3.available():
        return row
    fcov = row.get("fwar_coverage") or {}
    mid = fcov.get("mlbam")
    keep = {int(y) for y in (fcov.get("fallback_pre_years") or [])} | {
        int(y) for y in (fcov.get("fallback_post_years") or [])}
    stored = dict(row["seasons"])

    def _series(name: str) -> dict:
        deps = ewar_v3.departures(series=name)
        out_s = {}
        for yr_s, v in stored.items():
            d = deps.get((int(mid), int(yr_s))) if (mid and int(yr_s) not in keep) else None
            out_s[yr_s] = round(float(v) + sum(d.values()), 2) if d else v
        return out_s

    head, real = _series("headline"), _series("realized")
    vals = [float(v) for v in head.values()]
    career = round(sum(vals), 2)
    n = len(vals)
    out = dict(row)
    out.update({
        "seasons": head,
        "career_war": career,
        "war_per_yr": round(career / n, 2) if n else 0.0,
        "war_seasons_count": n,
        "source": "ewar_v3",
        "incumbent_of": src,
        "seasons_fwar": stored,
        "seasons_ewar_realized": real,
    })
    return out


def _ewar_v3_frame(df, side: str, *, door: str):
    """A war_daily frame on provider 'ewar_v3': the 'fwar' frame (WAR = fWAR,
    WAR_ewar_v2 and WAR_bwar beside it) plus WAR_fwar := that fWAR, then WAR :=
    WAR_fwar plus the headline departure and WAR_realized := WAR_fwar plus the
    realized departure, each spread over the player-season's stints in
    proportion to PA or IPouts (_exposure_split, equal shares without the
    column). Refused on the arb_spine door."""
    import pandas as pd
    import ewar_v3

    refuse_on_door("ewar_v3", door)
    out = _fwar_frame(df, side, door=door)
    out["WAR_fwar"] = out["WAR"]
    out["WAR_realized"] = out["WAR"]
    blob = ewar_v3.load()
    for series, col in (("headline", "WAR"), ("realized", "WAR_realized")):
        deps = {k: (float(v[side]), None) for k, v in ewar_v3.departures(series=series).items() if side in v}
        rec = {"door": door, "side": side, "series": series, "rows": int(len(out)), "covered_rows": 0,
               "listed": len(deps), "unplaced": len(deps), "delta_sum": 0.0,
               "generated_at": blob.get("generated_at"), "vintage_id": blob.get("fwar_vintage_id")}
        if len(out) and deps:
            zero = pd.Series(0.0, index=out.index)
            split = _exposure_split(out, side, zero, deps)
            if split is not None:
                cov_idx, w, grp, new = split
                base = pd.to_numeric(out.loc[cov_idx, col], errors="coerce").fillna(0.0)
                out.loc[cov_idx, col] = base.values + new
                n_ps = int(w["g"].nunique())
                rec.update({"covered_rows": int(len(cov_idx)), "unplaced": len(deps) - n_ps,
                            "delta_sum": float(new.sum())})
        _EWAR_V3_DIAG[f"{door}:{side}:{series}"] = rec
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
        "bwar_revised": 0, "bwar_revised_by_season": {}, "delta_sum": 0.0,
        # the served numerator's build (the live season's, on a nightly artifact)
        # and the frozen series' build; one stamp on a hand build
        "artifact_generated_at": blob.get("live_built_at") or blob.get("generated_at"),
        "artifact_label_build_at": blob.get("generated_at"),
    }
    if not len(out) or not targets:
        _EWAR_FRAME_DIAG[side] = receipt
        return out

    war = pd.to_numeric(out["WAR"], errors="coerce")
    split = _exposure_split(out, side, war, targets)
    if split is None:
        _EWAR_FRAME_DIAG[side] = receipt
        return out
    cov_idx, w, grp, new_war = split
    out.loc[cov_idx, "WAR"] = new_war

    per = grp.agg(fsum=("war", "sum"), bart=("bart", "first"))
    revised = per["bart"].notna() & ((per["fsum"] - per["bart"]).abs() > 0.005)
    # the group id is mlbam * 10000 + season, so the season is its last 4 digits
    rev_years = (per.index[revised.values] % 10000).tolist()
    by_season: dict[int, int] = {}
    for yr_ in rev_years:
        by_season[int(yr_)] = by_season.get(int(yr_), 0) + 1
    receipt.update({
        "covered_rows": int(len(cov_idx)),
        "covered_player_seasons": int(len(per)),
        "bwar_revised": int(revised.sum()),
        "bwar_revised_by_season": {str(k): by_season[k] for k in sorted(by_season)},
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
