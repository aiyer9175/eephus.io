# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4, non-roster spring invitations as a timing-head column (EFV4_NRI_ASOF; owner
decisions EW2-8 to EW2-12, 2026-10-08: new sources only, read on the development frames,
and once more on the spent reserved frames, labelled as such, choosing nothing).

WHAT THIS BUILDS. Two pre-declared columns, each offered to the V2 TIMING head of each
side (never the skill head: the D4 pattern of the pick re-test and of nov_add), four
arms in all, admitted or refused inside every fold by V2's own DS-06 rule:

    nri_pre        1.0 when the player was on a major league club's spring non-roster
                   invitee list for any spring known as of the read, else 0.0
    nri_count_pre  the number of distinct springs he was on such a list, known as of
                   the read

An NRI is a club decision dated before or inside the list window, like nov_add (the
Rule 5 protection add), the one timing driver whose removal costs on lv_dev.

SOURCE. statsapi.mlb.com /api/v1/teams/{id}/roster?rosterType=nonRosterInvitees&season=S
for the 30 clubs of each season 2009 to 2025, cached one file per (season, club) under
.cache/efv4_nri (fetch(): resumable, sequential, PAUSE_S between calls, backoff on 429
and 5xx, refused between 06:00 and 11:00 UTC). The endpoint IGNORES its date parameter
(probed 2026-10-08: team 147 returns the same 22 ids for 2016 at 01-10, 03-01 and
09-01; 2020 at 02-01, 03-01 and 07-20), so a list is a SEASON list: in 2020 it holds
the summer-camp invitations of June to September as well (809 ids against 375 to 453
in other seasons).

DATING (the as-of rule). Because the list carries no date, each (season S, person)
entry is dated by the league transaction feed already on disk (.cache/mlb_transactions,
read through efv_drivers.load_league_transactions, never written): the earliest
transaction for that person whose description names an invitation to spring training,
announced from 1 September of S - 1 through 30 September of S. An entry with no such
transaction is known only once the season is over (31 December of S). A read at date d
counts an entry only when its known date is on or before d, so every value is dated on
or before the read: the list date on the list-vintage frame (the frame row's asof_date,
the latest board point inside the V preseason window), the matrix row's own asof_date
for a vintage-matched training row and the pinned preseason read for a vintage-matched
test row (efv_v2_model.pinned_inputs). The feed dates 89 to 98 percent of the entries
of 2010 to 2021 (1 percent of 2009, whose feed is sparse; 77 to 86 percent of 2022 to
2025). A read before FIRST_READ (2010-01-01) carries no value.

KEYS. The person id is the row's OUTCOME-BLIND id on the list-vintage frame (`mlbam_id`
from efv_identity, never `record_mlbam_id`) and the matrix id on the vintage-matched
frame, as the base V2 and every wave-2 column read it there. A row with no id is None
and the fit imputes the observed training mean (no absence flag enters any head); the
nri_absent indicator is checked by the lab's DS-03 balance probe on lv_dev. Matrix ids
are partly a debut proxy (bug B4: protection never enters a matrix fit for that reason),
so the vm reads are disclosed as such in the artifact.

THE READS. Development (EW2-10): lv_dev through the screening lab's own Frame and
measure_arm (DS-06 refit per fold, the zero-information twin, the balance probe), and
vm_dev at vm2 through tools/efv_v3_backtest's Inputs (the DS-16 rows, base parity bit
for bit), each against the V2 base and PROSPX consensus with E_cond CI95. Spent
(EW2-10): R-LV (list vintages 2020 and 2021) and R-VM (the 2025 debut cohort) through
efv_v3_backtest.build_reserved on the committed gate sha the 10-08 confirmation read
used (copied from its artifact), every row labelled SPENT_NOTE; they choose and tune
nothing and land no progress-ledger row (efv_progress takes development rows only).
Development reads load no roster season after DEV_SEASON_CAP and no entry known on or
after DEV_DATE_CAP; only the spent read's look_index (gate sha) reaches the 2025 window.

BANS. No served number moves: nothing served imports this module and no flag exists to
flip. Nothing here groups, counts or averages anything by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md); the only summaries are counts by (side, year). No
column builder reads a label, a WAR series or a debut.

Run:  python efv_w2_nri.py --fetch            (fill .cache/efv4_nri)
      python efv_w2_nri.py --check            (coverage receipt only, no statistic)
      python efv_w2_nri.py --read             (development and spent reads; artifact)
      python efv_w2_nri.py --ledger           (this module's development ledger rows)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "efv4_nri"
OUT_PATH = DATA_DIR / "_labs" / "efv_w2" / "efv_w2_nri.json"
CONFIRM_PATH = DATA_DIR / "_labs" / "efv_v3" / "efv_v3_confirm.json"
TOOL = "efv_w2_nri.py"
ITEM = "EFV4_NRI_ASOF"
WAVE = 2
MODEL_PREFIX = "efv_v2_screen:wave2:"
FROZEN_PROVIDER = "fwar"

API = "https://statsapi.mlb.com/api/v1"
USER_AGENT = ("BaseballR prospect-tracker eFV research fetch (non-roster invitee lists; "
              "cached, resumable, one request at a time)")
#: Seasons cached: the first season the league feed dates (2009) through the R-VM cohort.
SEASONS: tuple[int, ...] = tuple(range(2009, F.R_VM_FIRST_DEBUT_YEAR + 1))
PAUSE_S = 0.3
#: UTC hours in which no fetch runs (EW2-11).
FETCH_BLOCK_UTC = (6, 11)
#: Development reads: no roster season after this, no entry known on or after this date.
DEV_SEASON_CAP = F.R_VM_FIRST_DEBUT_YEAR - 1
DEV_DATE_CAP = f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01"
#: A read before this date carries no value (the 2009 lists are mostly undated).
FIRST_READ = "2010-01-01"
#: The transaction text that dates an entry, and the dating range around season S.
INVITE_TEXT = "spring training"
DATING_OPEN_MMDD = "-09-01"     # of S - 1
DATING_CLOSE_MMDD = "-09-30"    # of S
UNDATED_KNOWN_MMDD = "-12-31"   # of S: the season list is complete
SPENT_NOTE = "spent frame, read after the 10-08 confirmation"
NOTE = ("eFV v4 (EFV4_NRI_ASOF), development read only: selects and adjudicates "
        "nothing")

STATS: dict[str, str] = {
    "nri_pre": ("1.0 when on a major league spring non-roster invitee list for any "
                "spring known as of the read, else 0.0"),
    "nri_count_pre": "distinct springs on such a list, known as of the read",
}
#: The arms: each column offered to the timing head of each side (D4: never a skill
#: rank feature).
ARMS: tuple[dict, ...] = tuple(
    {"name": f"w2n_{stat}_{side}", "stat": stat, "side": side, "head": "timing",
     "kind": "column", "retest": False,
     "column": {"source": "module", "module": "efv_w2_nri", "attr": "screen_column",
                "arg": stat}}
    for stat in STATS for side in F.SIDES)


# ---------------------------------------------------------------------------
# the cache: one roster file per (season, club)
# ---------------------------------------------------------------------------

def fetch_window_open(now: datetime | None = None) -> bool:
    """False between 06:00 and 11:00 UTC (EW2-11)."""
    h = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).hour
    return not (FETCH_BLOCK_UTC[0] <= h < FETCH_BLOCK_UTC[1])


def _get(url: str, *, tries: int = 6) -> dict:
    for attempt in range(tries):
        if not fetch_window_open():
            raise RuntimeError("fetch window closed (06:00 to 11:00 UTC)")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and exc.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(5 * (2 ** attempt))
    raise RuntimeError(f"no answer after {tries} tries: {url}")


def _roster_path(season: int, club: int) -> Path:
    return CACHE_DIR / f"nri_{int(season)}_{int(club)}.json"


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(path)


def clubs(season: int, *, fetch: bool = False) -> list[int]:
    """The major league club ids of a season (cached teams file)."""
    p = CACHE_DIR / f"teams_{int(season)}.json"
    if not p.exists():
        if not fetch:
            return []
        _write(p, _get(f"{API}/teams?sportId=1&season={int(season)}"))
        time.sleep(PAUSE_S)
    return sorted(int(t["id"]) for t in json.loads(p.read_text(encoding="utf-8"))["teams"])


def fetch(seasons=SEASONS, *, log=print) -> dict:
    """Fill the cache; a cached file is never fetched again (a past season is final)."""
    out = {"calls": 0, "cached": 0}
    for season in seasons:
        for club in clubs(season, fetch=True):
            p = _roster_path(season, club)
            if p.exists():
                out["cached"] += 1
                continue
            url = (f"{API}/teams/{club}/roster?rosterType=nonRosterInvitees"
                   f"&season={int(season)}&date={int(season)}-03-01")
            doc = _get(url)
            doc["_fetched_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            doc["_url"] = url
            _write(p, doc)
            out["calls"] += 1
            time.sleep(PAUSE_S)
        log(f"  season {season}: cached")
    return out


def load_rosters(season_cap: int) -> dict[int, dict[int, list[int]]]:
    """{season: {person id: [club ids]}} for the cached seasons up to season_cap."""
    out: dict[int, dict[int, list[int]]] = {}
    for season in SEASONS:
        if season > int(season_cap):
            continue
        for p in sorted(CACHE_DIR.glob(f"nri_{season}_*.json")):
            club = int(p.stem.split("_")[2])
            for e in json.loads(p.read_text(encoding="utf-8")).get("roster") or []:
                pid = (e.get("person") or {}).get("id")
                if pid:
                    out.setdefault(season, {}).setdefault(int(pid), []).append(club)
    return out


def cache_receipt() -> dict:
    by = {}
    for season in SEASONS:
        files = sorted(CACHE_DIR.glob(f"nri_{season}_*.json")) if CACHE_DIR.exists() else []
        ids, entries = set(), 0
        for p in files:
            for e in json.loads(p.read_text(encoding="utf-8")).get("roster") or []:
                pid = (e.get("person") or {}).get("id")
                if pid:
                    ids.add(int(pid))
                    entries += 1
        by[str(season)] = {"club_files": len(files), "entries": entries,
                           "persons": len(ids)}
    return {"dir": ".cache/efv4_nri", "seasons": [min(SEASONS), max(SEASONS)],
            "endpoint": "statsapi.mlb.com/api/v1/teams/{id}/roster rosterType=nonRosterInvitees",
            "date_parameter_honoured": False, "by_season": by}


# ---------------------------------------------------------------------------
# dating and the as-of index
# ---------------------------------------------------------------------------

class NriIndex:
    """{person id: [(known date, season, dated)]}, every entry known before date_cap."""

    def __init__(self, entries: dict[int, list[tuple[str, int, bool]]], *,
                 season_cap: int, date_cap: str, receipt: dict | None = None):
        self.entries = entries
        self.season_cap = int(season_cap)
        self.date_cap = str(date_cap)
        self.receipt = receipt or {}

    @classmethod
    def build(cls, *, season_cap: int, date_cap: str, rosters: dict | None = None,
              tx: dict | None = None) -> "NriIndex":
        """Date every roster entry by its earliest invitation transaction announced
        from 1 September of S - 1 through 30 September of S, else 31 December of S;
        entries known on or after date_cap are not loaded."""
        rosters = load_rosters(season_cap) if rosters is None else rosters
        if tx is None:
            import efv_drivers as DRV
            tx = DRV.load_league_transactions(int(season_cap))
        entries: dict[int, list[tuple[str, int, bool]]] = {}
        receipt: dict = {}
        for season, people in sorted(rosters.items()):
            if int(season) > int(season_cap):
                continue
            lo = f"{int(season) - 1}{DATING_OPEN_MMDD}"
            hi = f"{int(season)}{DATING_CLOSE_MMDD}"
            rc = receipt.setdefault(str(season), {"entries": 0, "dated": 0,
                                                  "past_cap": 0})
            for pid in people:
                days = [d for d, _code, desc in tx.get(int(pid), ())
                        if INVITE_TEXT in str(desc).lower() and lo <= d <= hi]
                if days:
                    known, dated = min(days), True
                else:
                    known, dated = f"{int(season)}{UNDATED_KNOWN_MMDD}", False
                rc["entries"] += 1
                rc["dated"] += int(dated)
                if known >= str(date_cap):
                    rc["past_cap"] += 1
                    continue
                entries.setdefault(int(pid), []).append((known, int(season), dated))
        for v in entries.values():
            v.sort()
        return cls(entries, season_cap=season_cap, date_cap=date_cap, receipt=receipt)


_DEV_INDEX: NriIndex | None = None


def default_index() -> NriIndex:
    """The development index: seasons through DEV_SEASON_CAP, entries known before
    DEV_DATE_CAP."""
    global _DEV_INDEX
    if _DEV_INDEX is None:
        _DEV_INDEX = NriIndex.build(season_cap=DEV_SEASON_CAP, date_cap=DEV_DATE_CAP)
    return _DEV_INDEX


def look_cap() -> str:
    """The end of the first R-VM cohort's preseason window (source_backtest)."""
    import source_backtest as SB
    return f"{F.R_VM_FIRST_DEBUT_YEAR}{SB._WINDOW_END_MMDD}"


def look_index(gate_sha: str | None) -> NriIndex:
    """The spent read's index (seasons through the R-VM cohort, entries known before
    look_cap()), opened only on the committed gate sha."""
    if not F.gate_sha_committed(gate_sha):
        raise F.ReservedFrameError(f"the NRI look index opens only on the committed gate "
                                   f"sha, got {gate_sha!r}")
    return NriIndex.build(season_cap=F.R_VM_FIRST_DEBUT_YEAR, date_cap=look_cap())


def nri_values(person_id, asof, index: NriIndex) -> dict:
    """{stat: value | None} for one person read at `asof`: only entries whose known date
    is on or before the read count. None everywhere without an id, without a read date,
    before FIRST_READ, or for a read on or after the index's date cap."""
    out = {s: None for s in STATS}
    try:
        pid = int(person_id) if person_id is not None else None
    except (TypeError, ValueError):
        pid = None
    d = str(asof or "")[:10]
    if pid is None or len(d) < 10 or d < FIRST_READ or d >= index.date_cap:
        return out
    seasons = {s for known, s, _dated in index.entries.get(pid, ()) if known <= d}
    out["nri_pre"] = 1.0 if seasons else 0.0
    out["nri_count_pre"] = float(len(seasons))
    return out


# ---------------------------------------------------------------------------
# the list-vintage column (the screening lab's hook)
# ---------------------------------------------------------------------------

def lv_values(side: str, frames: dict, index: NriIndex | None = None) -> dict:
    """{(V, player_key): {stat: value}} on the side's list-vintage frame rows, each read
    on its outcome-blind id at its own list date (asof_date)."""
    idx = default_index() if index is None else index
    out = {}
    for V in sorted((frames.get(side) or {})):
        F.guard_score_request(int(V), purpose="w2 nri column")
        for r in frames[side][V][0]:
            out[(int(V), r["player_key"])] = nri_values(r.get("mlbam_id"),
                                                        r.get("asof_date"), idx)
    return out


_LV_MEMO: dict = {}


def screen_column(stat: str, side: str, frames: dict) -> dict:
    """The screening lab's builder hook (column source "module", arg = statistic):
    {(V, player_key): value | None} on the side's list-vintage frame rows."""
    if stat not in STATS:
        raise ValueError(f"unknown statistic {stat!r}")
    key = (side, id(frames))
    if key not in _LV_MEMO:
        _LV_MEMO.clear()
        _LV_MEMO[key] = lv_values(side, frames)
    return {slot: v.get(stat) for slot, v in _LV_MEMO[key].items()}


def coverage(values: dict, stat: str) -> dict:
    """{str(year): {"rows", "with_value", "positive"}} of {(year, ...): {stat: v}}."""
    out: dict = {}
    for k, v in values.items():
        c = out.setdefault(str(k[0]), {"rows": 0, "with_value": 0, "positive": 0})
        x = (v or {}).get(stat)
        c["rows"] += 1
        c["with_value"] += int(x is not None)
        c["positive"] += int(bool(x))
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# helpers shared by the reads
# ---------------------------------------------------------------------------

def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _key(arm: dict) -> str:
    import efv_v2_model as H
    return f"{H.V2_SCREEN_PREFIX}{arm['name']}"


@contextmanager
def registered_columns():
    """The four arms as efv_v3 W2_COLUMNS entries for the duration of one read (the
    Inputs path validates an added column against that table); removed afterwards, so
    the v3 selection menu is never widened."""
    import efv_v3 as V3
    added = []
    for arm in ARMS:
        if arm["name"] in V3.W2_COLUMNS:
            continue
        V3.W2_COLUMNS[arm["name"]] = {"side": arm["side"], "head": "timing",
                                      "module": "efv_w2_nri", "arg": arm["stat"],
                                      "key": _key(arm)}
        added.append(arm["name"])
    try:
        yield
    finally:
        for n in added:
            V3.W2_COLUMNS.pop(n, None)


@contextmanager
def _frames_fixed(frames_lv: dict | None):
    """efv_v2_assemble.build_frames answers `frames_lv` (built once per run)."""
    _tools()
    import efv_v2_assemble as ASM
    orig = ASM.build_frames
    if frames_lv is not None:
        ASM.build_frames = lambda *a, **k: frames_lv
    try:
        yield
    finally:
        ASM.build_frames = orig


def _cand(arm: dict) -> dict:
    out = {k: arm[k] for k in ("name", "side", "head", "kind", "retest", "column")}
    out["what"] = f"{arm['stat']}: {STATS[arm['stat']]} (efv_w2_nri, timing head)"
    return out


# ---------------------------------------------------------------------------
# lv_dev: the screening lab's own Frame and measure_arm
# ---------------------------------------------------------------------------

def lv_read(arms, *, B: int, log=print) -> tuple[dict, dict]:
    """Every arm on lv_dev (list vintages 2017 to 2019) through the lab's Frame and
    measure_arm: DS-06 refit inside every fold with the column offered to the timing
    head, the zero-information twin, the DS-03 balance probe on the nri_absent
    indicator, and the consensus leg. No floor and no permutation null: a development
    read forms no verdict. Returns (block, the frames it built)."""
    _tools()
    import efv_screen_lab as LAB
    t0 = time.time()
    frame, frames = LAB.real_frame()
    log(f"lv_dev frame built in {time.time() - t0:.0f} s")
    base_vs_cons = {}
    for s in F.SIDES:
        order = {}
        for V in frame.folds:
            for pk, idx in frame.base(s, V)["order"].items():
                order[(V, pk)] = idx
        base_vs_cons[s] = LAB._vs_consensus(frame, (s,), order, B=B)
    out = {"frame": {"id": "lv_dev", "folds": list(frame.folds), "counts": frame.counts,
                     "w_star_dev": frame.w_star, "label": frame.label},
           "coverage": {}, "arms": {}}
    for s in F.SIDES:
        vals = lv_values(s, frames)
        out["coverage"][s] = {st: coverage(vals, st) for st in STATS}
    for arm in arms:
        t1 = time.time()
        values = screen_column(arm["stat"], arm["side"], frames)
        a = LAB.measure_arm(frame, _cand(arm), values, {}, B=B, n_perm=0,
                            base_vs_cons=base_vs_cons)
        a.pop("_order", None)
        a.pop("permutation_null", None)
        a["tag"] = f"SCREEN-W{WAVE}:{arm['side']}.timing.{arm['name']}"
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["frame"]["note"] = NOTE
        a["nri_absent_balance"] = a.get("balance")
        out["arms"][arm["name"]] = a
        w = a["within"]
        vc = a["frame"]["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  lv_dev {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, within "
            f"vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
            f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out, frames


# ---------------------------------------------------------------------------
# the Inputs path (vm_dev, and the spent R-LV and R-VM frames)
# ---------------------------------------------------------------------------

COMPARISONS = (("candidate_vs_efv_v2_base", "efv_v3", "efv_v2"),
               ("candidate_vs_prospx_consensus", "efv_v3", "prospx_consensus"),
               ("efv_v2_base_vs_prospx_consensus", "efv_v2", "prospx_consensus"))
_RATER_NAMES = {"efv_v3": "efv_v2_candidate", "efv_v2": "efv_v2_base"}


def frame_block(rows: list[dict], *, B: int, frame_version: str, note: str) -> dict:
    """Raters and the within / pooled / AUC deltas of the candidate against the V2 base
    and against consensus, paired on identical rows (E_cond, player-clustered), in the
    screening ledger's shape."""
    _tools()
    import efv_v2_stat as S
    import efv_v3_backtest as BT
    blk = BT.frame_block(rows, B=B, stats=("within", "pooled", "auc"),
                         comparisons=COMPARISONS, scopes=("both",))
    raters = {_RATER_NAMES.get(k, k): v for k, v in blk["raters"].items()}
    years = sorted({int(str(g).split("|")[1]) for g in blk["groups"]})
    deltas = blk["deltas"]
    return {"frame_version": frame_version,
            "window": [min(years), max(years)] if years else None,
            "n": blk["n"], "n_by_side": blk["n_by_side"], "n_players": blk["n_players"],
            "groups": blk["groups"], "statistic": S.STAT_LABEL[S.PRIMARY],
            "raters": raters, "deltas": deltas,
            "secondary": {"statistic": S.STAT_LABEL["pooled"],
                          "raters": {n: r.get("pooled") for n, r in raters.items()},
                          "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                                         "ci95": (d.get("pooled") or {}).get("ci95"),
                                         "mde95": (d.get("pooled") or {}).get("mde95"),
                                         "reading": (d.get("pooled") or {}).get("reading")}
                                     for n, d in deltas.items()}},
            "verdict": None, "note": note}


def _vm_asof(side: str) -> tuple[dict, dict]:
    """(raw matrix rows by player_key, pinned preseason read date by player_key)."""
    import efv_v2_model as H
    raw = {r["player_key"]: r for r in json.loads(
        H._matrix_path(side).read_text(encoding="utf-8"))}
    mine: dict = {}
    H.pinned_inputs(side, H.matrix_training_rows(side), mine)
    return raw, {pk: rec.get("asof_date") for pk, rec in mine.items()}


def inputs_columns(inp, fid: str, kind: str, index: NriIndex, *, lv_rows: dict | None = None
                   ) -> tuple[dict, dict]:
    """({side: {arm name: {(year, player_key, train|test): value}}}, coverage) on one
    Inputs frame. lv: each row at its frame row's list date on its outcome-blind id
    (lv_rows {(side, V, player_key): frame row}); vm: a training row at its matrix
    asof_date, a test row at its pinned preseason read, on the matrix id."""
    cols: dict = {s: {} for s in F.SIDES}
    cov: dict = {s: {} for s in F.SIDES}
    for side in F.SIDES:
        raw = pinned = None
        if kind == "vm":
            raw, pinned = _vm_asof(side)
        vals: dict = {}
        for fold, blk in inp.frames[fid]["by_side"][side].items():
            for part in ("train", "test"):
                for r in blk[part]:
                    y, pk = int(r["decision_year"]), r["player_key"]
                    if kind == "lv":
                        fr = (lv_rows or {}).get((side, y, pk))
                        if fr is None:
                            raise KeyError(f"{fid} {side} {y} {pk}: no frame row")
                        v = nri_values(fr.get("mlbam_id"), fr.get("asof_date"), index)
                    else:
                        rw = raw.get(pk) or {}
                        asof = rw.get("asof_date") if part == "train" else pinned.get(pk)
                        v = nri_values(rw.get("mlbam_id"), asof, index)
                    vals[(y, pk, part)] = v
        for arm in ARMS:
            if arm["side"] == side:
                cols[side][arm["name"]] = {k: v[arm["stat"]] for k, v in vals.items()}
        cov[side] = {st: coverage(vals, st) for st in STATS}
    return cols, cov


def read_inputs_arm(inp, fid: str, arm: dict, *, B: int, frame_version: str,
                    note: str) -> dict:
    """One arm on one Inputs frame: the V2 base with the column offered to the side's
    timing head under DS-06 in every fold, scored on the frame's rows."""
    import efv_v3 as V3
    cfg = V3.base_config()
    cfg["add"][arm["side"]]["timing"].append(arm["name"])
    V3.validate_config(cfg)
    orders, rec = inp.orders(fid, cfg, sides=(arm["side"],))
    rows = inp.rows_with(fid, orders, sides=(arm["side"],))
    key = _key(arm)
    folds = {}
    for fold in inp.frames[fid]["by_side"][arm["side"]]:
        m = inp.fold_fit(fid, arm["side"], fold, cfg)["model"]
        t = m.get("timing") or {}
        adm = (t.get("admission") or {}).get(key) or {}
        beta = None
        if key in (t.get("keys") or []):
            beta = round(float(t["beta"][list(t["keys"]).index(key)]), 5)
        folds[str(fold)] = {"offered": m.get("timing") is not None,
                            "admitted": key in (t.get("keys") or []),
                            "reason": adm.get("reason") or m.get("consensus_only_reason"),
                            "per_vintage_signs": adm.get("per_vintage_signs"),
                            "mean_abs_t": adm.get("mean_abs_t"),
                            "beta_std": beta, "w_time": m.get("w_time"),
                            "timing_keys": list(t.get("keys") or [])}
    return {"name": arm["name"], "side": arm["side"], "head": "timing", "folds": folds,
            "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
            "n_folds": len(folds),
            "frame": frame_block(rows, B=B, frame_version=frame_version, note=note)}


def vm_read(arms, frames_lv: dict, *, B: int, log=print) -> dict:
    """Every arm on vm_dev (frame version vm2, the DS-16 rows) through efv_v3_backtest's
    development Inputs: base parity with DS-16 and v3-at-base parity are asserted there
    before any arm is read. The wave-2 columns of the v3 menu are not built."""
    _tools()
    import efv_v3_backtest as BT
    t0 = time.time()
    orig = BT.w2_values_dev
    BT.w2_values_dev = lambda inputs, fl, log=print: {fid: {s: {} for s in F.SIDES}
                                                       for fid in BT.FRAMES_DEV}
    try:
        with _frames_fixed(frames_lv):
            inp = BT.build_dev(log=log)
    finally:
        BT.w2_values_dev = orig
    years = list(inp.frames["vm_dev"]["folds"]) if "folds" in inp.frames["vm_dev"] else sorted(
        inp.frames["vm_dev"]["by_side"]["hit"])
    if any(int(y) >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm years reach R-VM: {years}")
    log(f"vm_dev inputs built in {time.time() - t0:.0f} s")
    index = default_index()
    cols, cov = inputs_columns(inp, "vm_dev", "vm", index)
    inp.cols = {"vm_dev": cols}
    out = {"frame": {"id": "vm_dev", "frame_version": "vm2", "fold_years": years,
                     "n_scored": len(inp.scored("vm_dev")),
                     "base_parity": inp.meta.get("base_parity", {}).get("reproduces"),
                     "v3_base_parity": inp.meta.get("v3_base_parity")},
           "coverage": cov, "arms": {},
           "id_note": ("matrix ids, partly a debut proxy (B4); a row without one is None "
                       "and imputed at the fold's observed training mean")}
    with registered_columns():
        for arm in arms:
            t1 = time.time()
            a = read_inputs_arm(inp, "vm_dev", arm, B=B, frame_version="vm2", note=NOTE)
            out["arms"][arm["name"]] = a
            d = a["frame"]["deltas"]
            w, vc = d["candidate_vs_efv_v2_base"]["spearman"], \
                d["candidate_vs_prospx_consensus"]["spearman"]
            log(f"  vm_dev {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, "
                f"within vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus "
                f"{vc.get('delta')} {vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def gate_sha_from_confirm(path: Path = CONFIRM_PATH) -> str:
    """The committed gate sha the 10-08 confirmation read opened the reserved frames on,
    copied from its artifact and checked again here."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    sha = ((doc.get("gate") or {}).get("sha"))
    if not F.gate_sha_committed(sha):
        raise F.ReservedFrameError(f"the confirmation artifact's gate sha {sha!r} is not "
                                   "the committed registration")
    return sha


def spent_read(arms, frames_lv: dict, *, B: int, log=print) -> dict:
    """Every arm on the SPENT reserved frames, R-LV (list vintages 2020 and 2021, W3)
    and R-VM (the 2025 debut cohort, vm2 rule), through efv_v3_backtest.build_reserved
    on the confirmation's gate sha; v3-at-base parity with the V2 base is asserted
    first. Every block is labelled SPENT_NOTE. It chooses and tunes nothing."""
    _tools()
    import efv_v3 as V3
    import efv_v3_backtest as BT
    gate_sha = gate_sha_from_confirm()
    t0 = time.time()
    with _frames_fixed(frames_lv):
        inp = BT.build_reserved(V3.base_config(), gate_sha=gate_sha, log=log)
    parity = BT.assert_v3_base_parity(inp, BT.FRAMES_RES)
    log(f"spent inputs built in {time.time() - t0:.0f} s; v3 base parity {parity}")
    index = look_index(gate_sha)
    lv_rows = {}
    for side in F.SIDES:
        for V, (rows, _labs) in frames_lv[side].items():
            for r in rows:
                lv_rows[(side, int(V), r["player_key"])] = r
        for V, blk in inp.frames["lv_res"]["by_side"][side].items():
            for pk, r in blk["frame_rows"].items():
                lv_rows[(side, int(V), pk)] = r
    cols_lv, cov_lv = inputs_columns(inp, "lv_res", "lv", index, lv_rows=lv_rows)
    cols_vm, cov_vm = inputs_columns(inp, "vm_pros", "vm", index)
    inp.cols = {"lv_res": cols_lv, "vm_pros": cols_vm}
    out = {"note": SPENT_NOTE, "gate_sha": gate_sha, "v3_base_parity": parity,
           "guards": inp.guards, "frames": {}}
    names = {"lv_res": ("R-LV", "lv1_v2", cov_lv), "vm_pros": ("R-VM", "vm2", cov_vm)}
    with registered_columns():
        for fid, (label, fv, cov) in names.items():
            blk = {"frame": {"id": fid, "label": label, "frame_version": fv,
                             "folds": sorted(int(y) for y in
                                             inp.frames[fid]["by_side"]["hit"]),
                             "n_scored": len(inp.scored(fid)), "note": SPENT_NOTE},
                   "coverage": cov, "arms": {}}
            for arm in arms:
                t1 = time.time()
                a = read_inputs_arm(inp, fid, arm, B=B, frame_version=fv, note=SPENT_NOTE)
                blk["arms"][arm["name"]] = a
                d = a["frame"]["deltas"]
                w, vc = d["candidate_vs_efv_v2_base"]["spearman"], \
                    d["candidate_vs_prospx_consensus"]["spearman"]
                log(f"  {label} (spent) {arm['name']}: admitted {a['admitted_folds']}/"
                    f"{a['n_folds']}, within vs V2 {w.get('delta')} {w.get('ci95')}, vs "
                    f"consensus {vc.get('delta')} {vc.get('ci95')} "
                    f"({time.time() - t1:.0f} s)")
            out["frames"][fid] = blk
    return out


# ---------------------------------------------------------------------------
# the artifact, the summary and the ledger rows
# ---------------------------------------------------------------------------

def _leg(blk: dict, comp: str) -> list:
    d = ((blk.get("deltas") or {}).get(comp) or {}).get("spearman") or {}
    return [d.get("delta"), d.get("ci95")]


def summary(doc: dict) -> list[dict]:
    """One line per arm: rows, admitted folds, within delta vs V2 and vs consensus with
    CI95 on every frame read. Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        n = arm["name"]
        row = {"arm": n, "side": arm["side"], "stat": arm["stat"]}
        blocks = [("lv_dev", (doc.get("lv_dev") or {}).get("arms")),
                  ("vm_dev", (doc.get("vm_dev") or {}).get("arms"))]
        for fid, b in ((doc.get("spent") or {}).get("frames") or {}).items():
            blocks.append((fid, b.get("arms")))
        for fid, arms in blocks:
            a = (arms or {}).get(n)
            if not a:
                continue
            row[fid] = {"n": a["frame"]["n"],
                        "admitted_folds": f"{a['admitted_folds']}/{a['n_folds']}",
                        "vs_v2": _leg(a["frame"], "candidate_vs_efv_v2_base"),
                        "vs_consensus": _leg(a["frame"], "candidate_vs_prospx_consensus")}
            if fid in ("lv_res", "vm_pros"):
                row[fid]["note"] = SPENT_NOTE
        out.append(row)
    return out


def ledger_docs(doc: dict) -> list[dict]:
    """One development document per (arm, development frame) in the shape
    efv_progress.build_dev_rows reads. The spent frames land no row. Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        for fid in ("lv_dev", "vm_dev"):
            a = ((doc.get(fid) or {}).get("arms") or {}).get(arm["name"])
            if not a:
                continue
            out.append({"role": "development",
                        "model_id": f"{MODEL_PREFIX}{arm['name']}:{arm['side']}",
                        "generated_at": doc.get("generated_at"),
                        "label": doc.get("label") or {}, "code": doc.get("code") or {},
                        "screening": {"wave": f"{WAVE} ({fid})", "exploratory": False,
                                      "development_only": True, "adjudicates": False,
                                      "selects": False, "head": "timing",
                                      "statistic_column": arm["stat"],
                                      "admitted_folds": a["admitted_folds"],
                                      "n_folds": a["n_folds"]},
                        "frames": {fid: a["frame"]}})
    return out


def update_ledger(doc: dict | None = None, *, path: Path = OUT_PATH, ledger_path=None,
                  out_path=None, trigger: str = "efv_change") -> dict:
    """Append this module's development rows (and only them) to data/efv_progress.json
    through efv_progress.build_dev_rows and commit_rows. Idempotent."""
    import efv_progress as P
    doc = doc if doc is not None else json.loads(Path(path).read_text(encoding="utf-8"))
    now_dt = datetime.now(timezone.utc)
    now_iso = P._now_iso(now_dt)
    src = [{"path": P._rel(Path(path)), "generated_at": doc.get("generated_at"),
            "sha256": _sha(path)}]
    cands = []
    for d in ledger_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now_dt.date().isoformat(),
                                  trigger=trigger, now_iso=now_iso,
                                  frames=tuple(d["frames"]), raters=P.SCREEN_RATERS,
                                  deltas=P.SCREEN_DELTAS, statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no development rows"}
    res = P.commit_rows(cands, out_path=out_path, ledger_path=ledger_path,
                        sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


def check(*, log=print) -> dict:
    """The coverage receipt alone (cache and dating), no frame and no statistic."""
    idx = default_index()
    return {"source": cache_receipt(), "dating": idx.receipt,
            "persons_indexed": len(idx.entries)}


def read(*, B: int | None = None, out: Path = OUT_PATH, spent: bool = True,
         log=print) -> dict:
    """The development read of every arm on lv_dev and vm_dev, then the spent read on
    R-LV and R-VM; writes the artifact."""
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    _tools()
    import efv_screen_lab as LAB
    if L.provider() != FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not the frozen "
                           f"{FROZEN_PROVIDER!r}")
    B = S.B_DEFAULT if B is None else int(B)
    LAB.guards()
    t0 = time.time()
    dev_idx = default_index()
    doc = {"schema": 1, "item": ITEM,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "produced_by": TOOL, "wave": WAVE, "role": "development",
           "adjudicates": False, "selects": False, "exploratory": False, "note": NOTE,
           "owner_decision": ("EW2-8 to EW2-12 (2026-10-08): new sources only; choose on "
                              "the development frames; the reserved frames are spent"),
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": LAB.label_id()},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                    "module_sha256": _sha(Path(__file__)),
                    "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
           "assembly_sha256": _sha(H.ASSEMBLY_PATH),
           "estimator": {"name": "E_cond", "B": B, "seed": S.SEED_DEFAULT,
                         "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
           "construction": {"stats": STATS, "head": "timing",
                            "dating": ("earliest league-feed transaction naming an "
                                       "invitation to spring training, 1 September of "
                                       "S - 1 to 30 September of S; else 31 December "
                                       "of S"),
                            "as_of": ("an entry counts when its known date is on or "
                                      "before the row's read date"),
                            "first_read": FIRST_READ, "dev_season_cap": DEV_SEASON_CAP,
                            "dev_date_cap": DEV_DATE_CAP},
           "source": cache_receipt(), "dating": dev_idx.receipt,
           "arms_declared": [{k: a[k] for k in ("name", "stat", "side", "head")}
                             for a in ARMS],
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "lv_folds": list(LAB.FOLDS), "anchor_gate_grouping": False}}
    doc["lv_dev"], frames_lv = lv_read(ARMS, B=B, log=log)
    doc["vm_dev"] = vm_read(ARMS, frames_lv, B=B, log=log)
    if spent:
        doc["spent"] = spent_read(ARMS, frames_lv, B=B, log=log)
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(out)
    log(f"wrote {out} in {doc['elapsed_s']} s")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fetch", action="store_true", help="fill .cache/efv4_nri")
    ap.add_argument("--check", action="store_true", help="coverage receipt only")
    ap.add_argument("--read", action="store_true",
                    help="the development and spent reads; writes the artifact")
    ap.add_argument("--no-spent", action="store_true", help="skip the spent read")
    ap.add_argument("--ledger", action="store_true",
                    help="append this module's development rows from the artifact")
    ap.add_argument("--ledger-path", default=None,
                    help="durable ledger path (default: efv_progress's own)")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args(argv)
    if not (a.fetch or a.check or a.read or a.ledger):
        a.read = a.ledger = True

    def log(msg):
        print(msg, flush=True)
    if a.fetch:
        log(json.dumps(fetch(log=log), indent=1))
    if a.check:
        log(json.dumps(check(log=log), indent=1))
    if a.read:
        res = read(B=a.B, out=Path(a.out), spent=not a.no_spent, log=log)
        log(json.dumps(res["summary"], indent=1))
    if a.ledger:
        log(json.dumps(update_ledger(path=Path(a.out), ledger_path=a.ledger_path),
                       indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
