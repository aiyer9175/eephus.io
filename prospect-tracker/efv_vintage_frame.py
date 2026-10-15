# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v2 list-vintage frame F-LV (docs/efv-v2/PROGRAM.md s2.2, s2.4, item EV-04).

WHAT A ROW IS. One (player, list vintage V) pair: every prospect with a real-grader
preseason read in V who had not yet debuted when that read was taken. Every input the
row carries is dated inside the V preseason window:

    window      [V-01-01, end), end = min(V-05-01, the player's debut date). The window
                is source_backtest's own preseason window (_WINDOW_START_MMDD,
                _WINDOW_END_MMDD), cut short at the debut for an April debut so no read
                taken after he reached MLB can enter his row.
    grades      source_backtest._rater_grades_for_year on the points inside the window:
                each SCORED_SOURCES grade (max across the window) and the consensus of
                the latest in-window point, i.e. the board as it stood.
    prior       efv_dataset._prior_features on that same latest in-window point.
    milb        efv_dataset._milb_features(person, V, birth, side, cutoff=V-01-01), so
                the last MiLB season read is V - 1 (its season ended before the window).
                The walk reaches back to MILB_FLOOR_LV (2005, the cache's first season)
                on THIS frame only (lane B M1, E3-Q22), on the sides where the DS-03
                re-run stayed BALANCED (MILB_FLOOR_LV_WITHHELD names the rest): the
                served matrices and the live board keep efv_dataset.MILB_FLOOR_DEFAULT.
                Every row carries the floor it was read at as `milb_floor`.
                `person` is the OUTCOME-BLIND id from efv_identity (DS-03, bug B4): the
                printed name matched against the people in affiliated minor league ball
                before V, never the id the record carries (records gained ids mostly on
                reaching the majors, so a block keyed on them is a debut proxy). The
                record's own id stays on the row as `record_mlbam_id`, for audit only.
    sidecars    IL stints strictly before V-01-01; acquisition fields only when the
                acquisition year is before V (a July draft in V is after the window).

The frame is FEATURES AND GRADES ONLY. It reads no WAR and imports no label module;
labels live in efv_labels.py and are joined by a caller. Membership uses only facts
known at the read: a published debut date before the window, or a MLB (sport-1) stat
line in a season before V, removes the row. Side routing uses efv_dataset._side_match,
the same identity rule the v1 matrices use; it is routing, not a model input.

RESERVED FRAMES (PROGRAM.md s2.4). List vintages 2020 and 2021 are R-LV, read once after
docs/efv-v2/EFV_V2_GATE.md commits. guard_score_request() RAISES for a reserved vintage
unless it is handed the sha of a commit that is an ancestor of HEAD and carries the gate
document marked REGISTERED (a DRAFT of the gate, committed so its text is dated, never
opens the guard; see GATE_STATUS_REGISTERED); every builder here calls it, and so must
every scorer that reads this frame.
The prospective leg R-VM (the 2025 and later debut cohorts) is pinned by
reserved_vm_pins(): source_backtest.CANDIDATE_YEARS and efv_model.SCORED_YEARS may not
include R_VM_FIRST_DEBUT_YEAR or later until its look record exists. A read of an
R-VM cohort by an explicit year list goes through guard_vm_request(), which opens on
the same committed gate sha and on nothing else (owner EW2-6, 2026-10-08: the one
confirmation read of eFV v3, tools/efv_v3_backtest.py); the pinned constants are
never widened by it.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md). Nothing here groups, counts, averages or
strata rows by consensus-FV level. The only summary this module emits is row counts by
(side, vintage). test_efv_vintage_frame.py scans the source for any such grouping.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import efv_dataset as D
import efv_identity as ID
import milb_history as mh
import source_backtest as SB

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

#: R-LV: list vintages held out for the one registered look (PROGRAM.md s2.4).
RESERVED_LV: frozenset[int] = frozenset({2020, 2021})
#: R-VM: the first debut cohort held out for the prospective vintage-matched looks.
R_VM_FIRST_DEBUT_YEAR: int = 2025
#: Development vintages: spent, readable, adjudicate nothing.
DEV_VINTAGES: tuple[int, ...] = tuple(range(2011, 2020))
#: The registration a reserved read must cite (relative to this directory).
GATE_DOC = "docs/efv-v2/EFV_V2_GATE.md"
#: The status line a FINAL registration carries, alone on its line. A gate document at
#: the named commit opens the reserved guard only when it has this line and no other
#: status line (DS-15: the gate is committed as a DRAFT first, which must not open it).
GATE_STATUS_PREFIX = "Registration status:"
GATE_STATUS_REGISTERED = "Registration status: REGISTERED"
SIDES = ("hit", "pit")
#: The earliest MiLB season a row of THIS frame reads (efv_dataset._milb_features
#: first_season_floor). 2005 is the first season on disk for every sport id. The
#: 2026-07-24 lift on the debuted frame was NO-SHIP (era-distant survivors); its
#: revival condition, symmetric availability, holds here because busts and debuts are
#: resolved by the same outcome-blind name index (DS-03). The v1 matrices never read
#: this constant. Screened as the arm milb_floor_2005 against a frame built with
#: milb_floor=efv_dataset.MILB_FLOOR_DEFAULT (EFV3_PLAN.md s4, wave 1).
MILB_FLOOR_LV: int = 2005
#: Sides whose rows keep efv_dataset.MILB_FLOOR_DEFAULT: the lift is pre-registered to
#: hold only where the DS-03 balance probe stays BALANCED on milb_absent and
#: level_prev_missing after it (EFV3_B3). Re-run 2026-10-02 on the lifted frame, eWAR
#: v2 label, same inputs both ways (data/efv_milb_floor_coverage.json, ds03_rerun):
#: hitters milb_absent BALANCED at both floors (partial -0.0113 then -0.0441, CI95
#: -0.1097 to +0.0158 lifted); pitchers milb_absent BALANCED at the default floor
#: (-0.0604, CI95 -0.1314 to +0.0086) and IMBALANCED lifted (-0.1156, CI95 -0.1723 to
#: -0.0565; 243 of the 320 absent rows are id_unresolved, itself IMBALANCED on
#: pitchers at either floor). So the pitcher side is withheld; a lab may still build
#: it with milb_floor=MILB_FLOOR_LV, and admission criterion (f) then reads this row.
MILB_FLOOR_LV_WITHHELD: frozenset[str] = frozenset({"pit"})

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
#: (repository root, sha) -> the committed-gate answer, memoized per process: a sha
#: names immutable content, and the guard is asked once per fit on a reserved read.
_GATE_SHA_MEMO: dict[tuple[str, str], bool] = {}


def lv_milb_floor(side: str) -> int:
    """The MiLB floor a row of (side) reads at when the caller names none: MILB_FLOOR_LV,
    or the served default on a withheld side."""
    return int(D.MILB_FLOOR_DEFAULT if side in MILB_FLOOR_LV_WITHHELD else MILB_FLOOR_LV)


class ReservedFrameError(RuntimeError):
    """A read on a reserved frame without the committed gate's sha."""


# ---------------------------------------------------------------------------
# the reserved guard
# ---------------------------------------------------------------------------

def _git_ok(*args: str) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def gate_doc_registered(text: str | None) -> bool:
    """True when the gate text carries GATE_STATUS_REGISTERED alone on a line and no
    other status line. A DRAFT (or a document with no status line) is False."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    status = [ln for ln in lines if ln.startswith(GATE_STATUS_PREFIX)]
    return status == [GATE_STATUS_REGISTERED]


def _git_show(spec: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", spec], capture_output=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def gate_sha_committed(gate_sha: str | None) -> bool:
    """True only for a full 40-hex commit sha that is an ancestor of HEAD and whose
    tree carries GATE_DOC marked REGISTERED (gate_doc_registered). Anything else (None,
    a short sha, an uncommitted gate, a committed DRAFT, a commit on another line of
    history) is False."""
    if not isinstance(gate_sha, str) or not _SHA_RE.match(gate_sha):
        return False
    memo_key = (str(ROOT), gate_sha)
    if memo_key in _GATE_SHA_MEMO:
        return _GATE_SHA_MEMO[memo_key]
    ok = False
    if (_git_ok("cat-file", "-e", f"{gate_sha}^{{commit}}")
            and _git_ok("cat-file", "-e", f"{gate_sha}:./{GATE_DOC}")
            and gate_doc_registered(_git_show(f"{gate_sha}:./{GATE_DOC}"))):
        ok = _git_ok("merge-base", "--is-ancestor", gate_sha, "HEAD")
    _GATE_SHA_MEMO[memo_key] = bool(ok)
    return bool(ok)


def guard_score_request(vintage: int, *, gate_sha: str | None = None,
                        purpose: str = "score") -> None:
    """Raise ReservedFrameError for any read of a reserved list vintage unless
    `gate_sha` names the committed registration. Development vintages pass."""
    v = int(vintage)
    if v not in RESERVED_LV:
        return
    if gate_sha_committed(gate_sha):
        return
    raise ReservedFrameError(
        f"list vintage {v} is reserved (R-LV, RESERVED_LV={sorted(RESERVED_LV)}); "
        f"a {purpose} request needs the sha of the commit carrying {GATE_DOC}, "
        f"got {gate_sha!r}. See docs/efv-v2/PROGRAM.md s2.4.")


def guard_vm_request(years, *, gate_sha: str | None = None,
                     purpose: str = "score") -> None:
    """Raise ReservedFrameError for any read of a reserved R-VM debut cohort (a year
    at or after R_VM_FIRST_DEBUT_YEAR) unless `gate_sha` names the committed
    registration, exactly as guard_score_request opens R-LV. Development years pass.
    The constants reserved_vm_pins() checks are not widened by a read that passes
    here; the caller hands the years in explicitly."""
    bad = sorted({int(y) for y in years if int(y) >= R_VM_FIRST_DEBUT_YEAR})
    if not bad:
        return
    if gate_sha_committed(gate_sha):
        return
    raise ReservedFrameError(
        f"debut cohorts {bad} are reserved (R-VM, from {R_VM_FIRST_DEBUT_YEAR}); a "
        f"{purpose} request needs the sha of the commit carrying {GATE_DOC}, got "
        f"{gate_sha!r}. See docs/efv-v2/PROGRAM.md s2.4.")


def reserved_vm_pins() -> list[str]:
    """Violations of the R-VM pin: CANDIDATE_YEARS and SCORED_YEARS may not reach the
    first reserved debut cohort. [] when clean."""
    import efv_model
    bad = []
    for name, years in (("source_backtest.CANDIDATE_YEARS", SB.CANDIDATE_YEARS),
                        ("efv_model.SCORED_YEARS", efv_model.SCORED_YEARS)):
        hit = sorted(y for y in years if int(y) >= R_VM_FIRST_DEBUT_YEAR)
        if hit:
            bad.append(f"{name} includes reserved R-VM years {hit}")
    return bad


# ---------------------------------------------------------------------------
# the training window (EFV_2026_FOLD_TRAINING, docs/efv-v2/EFV_2026_TRAINING.md)
# ---------------------------------------------------------------------------

#: THE TRAINING SWITCH (owner EW3-13, 2026-10-15; registration
#: docs/efv-v2/EFV_2026_TRAINING.md). False: every fit stops before R_VM_FIRST_DEBUT_YEAR,
#: exactly as before. True: a FIT (production or development selection) may read decision
#: years and debut cohorts through TRAIN_THROUGH_SEASON, from the training-only fold
#: matrices (fold_matrix_path), once label_window_closed holds for that season. It never
#: opens a look, a score on a reserved frame, CANDIDATE_YEARS or SCORED_YEARS. Stays False
#: until EFV_X3 or a successor model is registered with it.
EFV_TRAIN_THROUGH_2026: bool = False
#: The last season the flag lets a fit read (the 2026 holdout frame is SPENT; a model fitted
#: with the flag on is claimed only on the 2027 season).
TRAIN_THROUGH_SEASON: int = 2026
TRAINING_DOC = "docs/efv-v2/EFV_2026_TRAINING.md"
#: (season, resolved_through, vintage mtime) -> (closed, reason), memoized per process.
_CLOSED_MEMO: dict[tuple, tuple[bool, str]] = {}


def label_window_closed(season: int, *, resolved_through: int | None = None,
                        vintage: dict | None = None) -> tuple[bool, str]:
    """(closed, reason) for season `season` of the label: closed only when the season is at
    or before efv_dataset.RESOLVED_THROUGH and the frozen fWAR vintage holds it with both
    groups frozen, each fetched after the season was complete
    (fwar_vintage.season_complete on the fetch date). The registration, section 3."""
    import fwar_vintage as FV
    from datetime import date as _date
    s = int(season)
    rt = int(D.RESOLVED_THROUGH if resolved_through is None else resolved_through)
    if s > rt:
        return False, f"season {s} is after the label's RESOLVED_THROUGH {rt}"
    if vintage is None:
        try:
            blob = FV.load()
        except (OSError, ValueError) as e:
            return False, f"the fWAR vintage is unreadable ({type(e).__name__})"
    else:
        blob = vintage
    blk = (blob.get("seasons") or {}).get(str(s)) or {}
    for g in ("hitting", "pitching"):
        gb = blk.get(g) or {}
        if gb.get("status") != "frozen":
            return False, f"season {s} {g} is not frozen in the fWAR vintage"
        try:
            fetched = _date.fromisoformat(str(gb.get("fetched_at") or "")[:10])
        except ValueError:
            return False, f"season {s} {g} carries no fetch date"
        ok, why = FV.season_complete(s, fetched)
        if not ok:
            return False, f"season {s} {g} was fetched before it was complete: {why}"
    return True, f"season {s} closed (RESOLVED_THROUGH {rt}, fWAR vintage frozen after its end)"


def _closed_memoized(season: int) -> tuple[bool, str]:
    import fwar_vintage as FV
    try:
        mt = FV.VINTAGE_PATH.stat().st_mtime_ns
    except OSError:
        mt = None
    key = (int(season), int(D.RESOLVED_THROUGH), mt, id(FV._CACHE))
    if key not in _CLOSED_MEMO:
        _CLOSED_MEMO[key] = label_window_closed(season)
    return _CLOSED_MEMO[key]


def train_end_year(*, flag: bool | None = None) -> int:
    """The first decision year (debut cohort) a FIT may not read: R_VM_FIRST_DEBUT_YEAR with
    EFV_TRAIN_THROUGH_2026 off, TRAIN_THROUGH_SEASON + 1 with it on. With the flag on and the
    label window of TRAIN_THROUGH_SEASON not closed, raises ReservedFrameError (no fit reads
    an open label). Never a scoring or claim bound."""
    on = EFV_TRAIN_THROUGH_2026 if flag is None else bool(flag)
    if not on:
        return int(R_VM_FIRST_DEBUT_YEAR)
    ok, why = _closed_memoized(TRAIN_THROUGH_SEASON)
    if not ok:
        raise ReservedFrameError(
            f"EFV_TRAIN_THROUGH_2026 is on but the label window of {TRAIN_THROUGH_SEASON} is "
            f"not closed: {why}. See {TRAINING_DOC} s3.")
    return int(TRAIN_THROUGH_SEASON) + 1


def fold_matrix_path(side: str) -> Path:
    """The training-only fold matrix of the side (efv_2026_fold.py --build writes it)."""
    return DATA_DIR / "_labs" / "efv2026" / f"train_matrix_{side}_through{TRAIN_THROUGH_SEASON}.json"


def training_matrix_path(side: str) -> Path:
    """The fold matrix a fit reads with EFV_TRAIN_THROUGH_2026 on, after the closed-window
    check; raises when the window is open or the fold matrix was never built. Callers read
    efv_dataset.matrix_path with the flag off."""
    train_end_year(flag=True)
    p = fold_matrix_path(side)
    if not p.exists():
        raise ReservedFrameError(
            f"EFV_TRAIN_THROUGH_2026 is on but {p.name} does not exist; build it with "
            f"python efv_2026_fold.py --build ({TRAINING_DOC} s1).")
    return p


# ---------------------------------------------------------------------------
# universe
# ---------------------------------------------------------------------------

_UNIVERSE_MEMO: dict[str, dict[str, dict]] = {}


def load_universe(data_dir: Path = DATA_DIR) -> dict[str, dict]:
    """{player_key: record} over debuts.json, inactive.json and timeseries.json, first
    file wins on a duplicate key. Busts (inactive.json) belong to this frame: it is the
    population the industry publishes on, every prospect every preseason."""
    key = str(Path(data_dir).resolve())
    if key in _UNIVERSE_MEMO:
        return _UNIVERSE_MEMO[key]
    out: dict[str, dict] = {}
    for fn in ("debuts.json", "inactive.json", "timeseries.json"):
        p = Path(data_dir) / fn
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        recs = doc if isinstance(doc, list) else (doc.get("players") or [])
        for r in recs:
            pk = r.get("player_key")
            if pk and pk not in out:
                out[pk] = r
    _UNIVERSE_MEMO[key] = out
    return out


_MLB_BY_SEASON: dict[int, frozenset[int]] = {}


def _mlb_ids(season: int) -> frozenset[int]:
    """mlbam ids with a MLB (sport-1) line in `season`, cache only (offline safe)."""
    if season not in _MLB_BY_SEASON:
        ids: set[int] = set()
        for group in ("hitting", "pitching"):
            for r in mh.season_splits(1, season, group, fetch=False):
                if r.get("mlbam"):
                    ids.add(int(r["mlbam"]))
        _MLB_BY_SEASON[season] = frozenset(ids)
    return _MLB_BY_SEASON[season]


def _real_sources() -> tuple[frozenset[str], frozenset[str]]:
    return SB._NON_RATER_SOURCES, D._constant_anchor_sources()


def _is_real_grader(src: str, ps: dict | None, excl: frozenset[str]) -> bool:
    if src in excl or src.endswith("_statcast_by_age"):
        return False
    return (ps or {}).get("fv_published") is not None


def window_bounds(vintage: int, debut_date: str | None) -> tuple[str, str]:
    """[start, end) of the V preseason window for one player (see module docstring)."""
    lo = f"{int(vintage)}{SB._WINDOW_START_MMDD}"
    hi = f"{int(vintage)}{SB._WINDOW_END_MMDD}"
    if debut_date and str(debut_date)[:10] < hi:
        hi = str(debut_date)[:10]
    return lo, hi


# ---------------------------------------------------------------------------
# one row
# ---------------------------------------------------------------------------

def frame_row(rec: dict, side: str, vintage: int, *, excl: frozenset[str] | None = None,
              milb: bool = True, index: ID.NameIndex | None = None,
              milb_floor: int | None = None) -> dict | None:
    """The F-LV row for one record at vintage V, or None when he is not in the frame.
    Callers go through build_frame, which applies the reserved guard first.

    Membership reads facts dated before the window (a published debut before it, a
    major league line before V) off the record. The id every INPUT is keyed on is the
    outcome-blind efv_identity resolution (`index` is the name index through V - 1;
    `side` is the routing the tiebreaks read, applied above before any resolution).
    `milb_floor` is the earliest MiLB season the block walks back to; None means
    lv_milb_floor(side) (MILB_FLOOR_LV, or the served default on a withheld side), and
    the screening lab passes efv_dataset.MILB_FLOOR_DEFAULT for the base arm. The row
    records it as `milb_floor` whether or not a block was read."""
    V = int(vintage)
    floor = lv_milb_floor(side) if milb_floor is None else int(milb_floor)
    if not D._side_match(rec, side):
        return None
    if excl is None:
        non_rater, constant = _real_sources()
        excl = frozenset(non_rater | constant)
    # DS-12: a placeholder debut day is never read as one (efv_dataset).
    dd = D.debut_day_for_cutoff(rec)[0]
    lo, hi = window_bounds(V, dd)
    if dd and str(dd)[:10] < lo:
        return None                          # debuted before the window opened
    mlbam = rec.get("mlbam_id")
    if mlbam:
        try:
            mid = int(mlbam)
        except (TypeError, ValueError):
            mid = None
        if mid and any(mid in _mlb_ids(s) for s in range(2014, V)):
            return None                      # a MLB line before V: not a prospect at V
    pts = [p for p in (rec.get("points") or [])
           if p.get("snapshot_date") and lo <= p["snapshot_date"][:10] < hi]
    if not pts:
        return None
    # A real grader must have PUBLISHED inside the window. A point can carry a source's
    # grade forward from an earlier board (per-source snapshot_date before the window);
    # that grade is known at V and stays in `grades`, but it is not a read in V, so it
    # cannot put the player in the frame on its own.
    real, carried = set(), set()
    for p in pts:
        for s, ps in (p.get("per_source") or {}).items():
            if not _is_real_grader(s, ps, excl):
                continue
            sd = str((ps or {}).get("snapshot_date") or p["snapshot_date"])[:10]
            (real if lo <= sd < hi else carried).add(s)
    if not real:
        return None
    grades = SB._rater_grades_for_year(dict(rec, points=pts), V)
    pts.sort(key=lambda p: p["snapshot_date"])
    asof = pts[-1]
    # every date an in-window input carries: the point dates and each per-source
    # publication date the grades were read from
    src_dates = sorted({str(ps.get("snapshot_date"))[:10]
                        for p in pts for s, ps in (p.get("per_source") or {}).items()
                        if (ps or {}).get("snapshot_date") and _is_real_grader(s, ps, excl)})
    if index is None:
        index = ID.build_index(V - 1)
    ident = ID.resolve_record(rec, V, index, side)
    row = {
        "player_key": rec.get("player_key"),
        # the outcome-blind id (DS-03); every input below is keyed on it
        "mlbam_id": ident.person_id,
        "id_how": ident.how,
        "id_candidates": ident.n_candidates,
        # the record's stored id: audit only, never an input (see the module docstring)
        "record_mlbam_id": mlbam,
        "side": side,
        "vintage": V,
        "window": [lo, hi],
        "debut_date": dd,
        "birth_date": rec.get("birth_date"),
        "position": rec.get("position"),
        "real_sources": sorted(real),
        "carried_sources": sorted(carried - real),
        "grades": grades,
        "asof_date": asof["snapshot_date"][:10],
        "point_dates": [p["snapshot_date"][:10] for p in pts],
        "source_dates": src_dates,
        "prior": D._prior_features(rec, asof, side),
        "milb": None,
        "milb_last_season": None,
        "milb_floor": floor,
    }
    if milb:
        feats = D._milb_features(ident.person_id, V, rec.get("birth_date"), side,
                                 cutoff=lo, first_season_floor=floor)
        row["milb"] = feats
        row["milb_last_season"] = (feats or {}).get("milb_season")
    return row


def _attach_sidecars(rows: list[dict]) -> None:
    """IL stints before the window and acquisition fields known before V."""
    keys = {r["player_key"] for r in rows if r.get("player_key")}
    if not keys:
        return
    acq, il = D._load_sidecars(keys)
    for r in rows:
        lo = r["window"][0]
        r.update(D._injury_features(il.get(r["player_key"]), lo))
        r["il_cutoff"] = lo
        a = acq.get(r["player_key"]) or {}
        ay = a.get("year")
        known = ay is not None and int(ay) < r["vintage"]
        r["acq_year"] = int(ay) if ay is not None else None
        r["acq_known_at_v"] = bool(known)
        if known:
            r["pick_overall"] = a.get("pick_overall")
            r["bonus_usd"] = a.get("bonus_usd")
            r["is_ifa"], r["is_college"] = D._cohort_flags(a.get("method"), ay,
                                                           r.get("birth_date"))
        else:
            r["pick_overall"] = r["bonus_usd"] = None
            r["is_ifa"], r["is_college"] = 0.0, 0.0


def build_frame(side: str, vintage: int, *, gate_sha: str | None = None,
                universe: dict[str, dict] | None = None, milb: bool = True,
                sidecars: bool = True, milb_floor: int | None = None) -> list[dict]:
    """Every F-LV row for (side, V). Reserved vintages raise without the gate sha.
    `milb_floor` as in frame_row (None: MILB_FLOOR_LV)."""
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")
    guard_score_request(vintage, gate_sha=gate_sha, purpose="frame")
    if universe is None:
        universe = load_universe()
    non_rater, constant = _real_sources()
    excl = frozenset(non_rater | constant)
    index = ID.build_index(int(vintage) - 1)
    rows = []
    for rec in universe.values():
        r = frame_row(rec, side, vintage, excl=excl, milb=milb, index=index,
                      milb_floor=milb_floor)
        if r is not None:
            rows.append(r)
    rows.sort(key=lambda r: r["player_key"])
    if sidecars:
        _attach_sidecars(rows)
    return rows


def row_input_dates(row: dict) -> list[str]:
    """Every date a point read on the row carries, for the timing test. Each is inside
    [window start, window end). Per-source publication dates are in `source_dates`;
    those can precede the window (a carried-forward grade) and never follow it."""
    out = list(row.get("point_dates") or [])
    if row.get("asof_date"):
        out.append(row["asof_date"])
    if (row.get("prior") or {}).get("asof_date"):
        out.append(str(row["prior"]["asof_date"])[:10])
    return out


def frame_counts(vintages=DEV_VINTAGES, *, gate_sha: str | None = None,
                 universe: dict[str, dict] | None = None) -> dict:
    """Row counts per (side, vintage), and nothing else: no grade, label or score."""
    universe = universe if universe is not None else load_universe()
    out: dict = {}
    for side in SIDES:
        for v in vintages:
            rows = build_frame(side, v, gate_sha=gate_sha, universe=universe)
            out.setdefault(side, {})[int(v)] = {
                "rows": len(rows),
                "with_consensus": sum(1 for r in rows
                                      if r["grades"].get(SB.CONSENSUS_KEY) is not None),
                "with_milb": sum(1 for r in rows if r.get("milb")),
            }
    return out
