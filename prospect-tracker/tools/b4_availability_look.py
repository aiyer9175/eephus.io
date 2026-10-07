"""The B4 availability looks: 5c-B `lineup_strength` and 5c-C `star_out`.

docs/diamond-betting.md sections 5c-B and 5c-C register one look each, first
day 2026-10-05, last day 2026-10-31, moved after the fWAR label epoch's step Z
by the owner's E5 waiver (EPOCH-Q1, FWAR_LABEL_EPOCH_GATE.md part 3). Every
item below is named in those sections; nothing here is a choice made at the
look. Nothing served imports this file and it adds no serve flag.

THE PARTS, in the sections' own words
  * the store: prospect-tracker/.cache/leaderboard_vintages/ on host NOAH-PC,
    hashed as SHA-256 over the sorted (file name, file SHA-256) pairs;
  * the pinned incumbent: betting_model.py and leaderboard_vintages.py at
    INCUMBENT_COMMIT, loaded from git into this process, never HEAD's pricer;
    the vintage-mode parameters re-solved inline on the anchored window
    (every vintage-gradable game dated before 2026-08-01) with a parity check
    against the artifact's vintage block at that commit;
  * one seam that prices both arms: the incumbent's per-side lambdas plus the
    candidate's terms, clamped to [1.5, 9.5], priced through `_score_joint`
    (Poisson) and `split_tie_atom`, Platt at identity; the incumbent arm is the
    same seam at zero, checked against `game_probabilities` to 5 places;
  * the row builder: one row per scoring side carrying game_pk, date, side,
    scoring org, opposing org, bucket, lambda and runs, counting what it skips;
  * the buckets, checked in the section's order, and the split date
    M = F + floor((L - F) / 2) from dates and buckets alone;
  * the residual fit (5c-B: one term c; 5c-C: c_own and c_opp together, no
    intercept), the written paired statistic with the n-1 divisor, criteria 1
    to 4, both twins (200 replicates each, seeds k and 200 + k, the 190-of-200
    bar), the reported-only offense arm, and leg 1, the contaminated-forward
    screen (5c-C's reads the step A PINNED bundle, never the bundle on disk);
  * the date refusal (before 2026-10-05, after 2026-10-31, and the registered
    look dates named in REFUSED_DATES) and the outcome-field refusal, in the
    form of tools/ph_gate.check_look_date and refuse_outcome_fields.

COMMANDS
  counts    counts only: nights, buckets, F, L, M, the store hash, the anchored
            window's game_pk set. Reads no outcome and no column value (only
            whether a club's cell is null). Admissible before the look.
  identity  the c = 0 identity check on every window game at the pinned
            artifact's parameters. Reads no outcome.
  checks    step 0: the identity check at the re-solved parameters, both parity
            checks and the _paired_delta fixture check. Reads incumbent outcomes
            only (the anchored window and the contaminated forward fit), never a
            candidate column beside one.
  look      the one look for one column: date refusal, one-look guard, the
            note match, step 1 counts, M written before any fit, step 2 fit,
            step 3 everything, the verdict. Writes the record under
            data/_labs/b4_look/ (data/_labs ships in neither deploy consumer).
  probe     5c-C leg 1's endpoint probe: reads two clubs' dated 40-man rosters,
            joins no outcome and no price.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import random
import socket
import subprocess
import sys
import types
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # prospect-tracker/
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# pins, every one of them named in 5c-B or 5c-C
# ---------------------------------------------------------------------------
HARNESS_PATH = "prospect-tracker/tools/b4_availability_look.py"
STORE = ROOT / ".cache" / "leaderboard_vintages"
STORE_HOST = "NOAH-PC"
GAME_CACHE = ROOT / ".cache" / "betting" / "completed_games.json"
EVAL_ARTIFACT = ROOT / "data" / "betting_model_eval.json"
RECORD_DIR = ROOT / "data" / "_labs" / "b4_look"
#: The served pricer at the commit that landed the 2026-09-11 corrections. No
#: 5c B3/B4 look was recorded on or before 2026-10-04 (5c-A closed without
#: look code at 239ef253), so 5c-B's second branch binds and 5c-C chains to it.
INCUMBENT_COMMIT = "6e82acd5"
PINNED_MODULES = ("betting_model", "leaderboard_vintages")
ANCHOR_SPLIT = "2026-08-01"
SEASON = "2026"
SEASON_END = "2026-09-27"
WINDOW_GAMES_BEFORE = "2026-10-05"
STAMP_DUE = "2026-09-19"
LOOK_FIRST_DAY = date(2026, 10, 5)
LOOK_LAST_DAY = date(2026, 10, 31)
#: Registered look dates on which no other look may run (the 5d / RE family's
#: earliest day and the PROJ ARM A look). The orchestrator's calendar rule.
REFUSED_DATES = (date(2026, 10, 7), date(2026, 10, 23))
CLOCK_NIGHTS = 28
NIGHT_FLOOR = 14
MIN_FIT_GAMES = 100            # betting_model.VINTAGE_MIN_FIT_GAMES
MIN_EVAL_GAMES = 50            # betting_model.VINTAGE_MIN_EVAL_GAMES
ID_MIN_CLUB_GAMES = 30         # 5c-C's identification precondition (POLICY)
N_TWIN = 200
TWIN_BAR = 190                 # strictly greater than the 190th smallest
TWIN_B_SEED_OFFSET = 200
Z95 = 1.645
LOGLOSS_EPS = 1e-9
LAM_LO, LAM_HI = 1.5, 9.5
#: Step A's pins for 5c-C leg 1 (FWAR_LABEL_EPOCH_GATE.md part 3, E5 waiver).
PINNED_BUNDLE_DIR = REPO / "_pre_epoch_fwar_2026-10"
PINNED_BUNDLE = PINNED_BUNDLE_DIR / "mlb_projections.json"
PINNED_MANIFEST = PINNED_BUNDLE_DIR / "MANIFEST.json"
LEG1_ROSTER_URL = ("https://statsapi.mlb.com/api/v1/teams/{tid}/roster"
                   "?rosterType=40Man&date={d}")
LEG1_COVERAGE_CLUBS = 28
LEG1_COVERAGE_DATE_SHARE = 0.90

#: The construction audits, pinned. A vintage CAPTURED after an event goes to
#: that event's bucket. 5c-B: no X9 event between 7cd5f572 and the harness
#: (hem_plus.build_batting_order's d4a76a62 hunk is comment text; membership is
#: still the top nine by PA); step M is its post-retrain event. 5c-C: 809902c6
#: re-keyed the corpus label by side (a construction-class change on the label
#: path), step D flipped the provider, and d11ed73f changed the vet team rule.
COLUMN_SPECS: dict[str, dict] = {
    "lineup_strength": {
        "section": "5c-B", "terms": 1, "record": "5cB",
        "nights": ("2026-09-07", "2026-10-04"),
        "window": ("2026-09-07", "2026-10-04"),
        "post_retrain": (
            ("a4bd70e8", "2026-10-03T22:15:02+00:00",
             "fWAR epoch step M retrains the projections bundle (woba[0])"),),
        "x9": (),
        "flag_unrecorded": ("2026-09-07", "2026-09-09", "2026-09-10"),
        "stamp_late": ("2026-09-12", "2026-09-18"),
        "pre_change": ("2026-08-20", "2026-09-06"),
        "serve_flag": "SERVE_LINEUP_STRENGTH",
    },
    "star_out": {
        "section": "5c-C", "terms": 2, "record": "5cC",
        "nights": ("2026-09-05", "2026-10-02"),
        "window": ("2026-09-05", "2026-10-04"),
        "post_retrain": (
            ("809902c6", "2026-09-23T16:54:04+00:00",
             "the corpus label is keyed by side (fa_projection._side_war_age_maps)"),
            ("8232729f", "2026-10-03T16:04:26+00:00",
             "fWAR epoch step D flips war_source.DEFAULT_PROVIDER to fwar")),
        "x9": (
            ("d11ed73f", "2026-09-25T03:09:01+00:00",
             "the vet team rule: the club that holds him today, not the Spotrac club"),),
        "basis_unconfirmed": ("2026-09-04",),
        "pre_change": ("2026-08-20", "2026-09-03"),
        "cadence_commit": ("419811bb", "2026-09-11T22:44:20+00:00"),
        "serve_flag": "SERVE_STAR_OUT",
    },
}
#: The roster-filter stamp (5c-B) and the build stamp (5c-C) were promised for
#: the 2026-09-19 vintage and never built. A record carrying either token is a
#: stamp this harness cannot read, and the run stops rather than guess.
RECORD_STAMP_TOKENS = {"lineup_strength": ("roster_filter.applied",),
                       "star_out": ("bundle_sha256", "war_provider", "fit_key")}

ALLOWED_FEATURE_KEYS = frozenset({"game_pk", "date", "home_org", "away_org",
                                  "home_sp", "away_sp", "season"})


class LookRefused(RuntimeError):
    """The look may not run (date, store, one-look guard, note mismatch)."""


class OutcomeJoinRefused(RuntimeError):
    """A pre-look path was handed a row carrying an outcome."""


class StoreRefused(RuntimeError):
    """The store is not the registered one, or a record cannot be read."""


# ---------------------------------------------------------------------------
# the two refusals, in tools/ph_gate form
# ---------------------------------------------------------------------------
def _as_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def check_b4_look_date(today) -> None:
    """Raise LookRefused unless `today` is a day the B4 look may run: on or
    after 2026-10-05, on or before 2026-10-31, and not a registered look date
    of another family. Fixed dates; ph_gate.check_look_date itself refuses
    every date before 2027 and cannot be reused (5c-B, 'To be built')."""
    t = _as_date(today)
    if t is None:
        raise LookRefused("no run date; the look date rule cannot be checked")
    if t < LOOK_FIRST_DAY:
        raise LookRefused(f"{t.isoformat()} is before the first look day "
                          f"{LOOK_FIRST_DAY.isoformat()}; nothing on the column is "
                          "computed before it (5c-B, 5c-C)")
    if t > LOOK_LAST_DAY:
        raise LookRefused(f"{t.isoformat()} is after the last look day "
                          f"{LOOK_LAST_DAY.isoformat()}; the look records "
                          "INDETERMINATE and 2026 closes for the column")
    if t in REFUSED_DATES:
        raise LookRefused(f"{t.isoformat()} is another registered look's date")


def refuse_outcome_fields(rows) -> None:
    """Raise OutcomeJoinRefused if any row carries a key outside the
    feature-only allowlist. The counts path and the identity check read their
    games through this, so a run before the look cannot put a column value
    beside a run, a win or a price."""
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            raise OutcomeJoinRefused(f"row {i} is not a mapping")
        extra = set(r) - ALLOWED_FEATURE_KEYS
        if extra:
            raise OutcomeJoinRefused(
                f"row {i} carries {sorted(extra)}; this path reads features only, "
                "never an outcome")


def feature_rows(games) -> list[dict]:
    """The completed-game rows with every outcome field removed."""
    out = [{k: g.get(k) for k in ALLOWED_FEATURE_KEYS if k in g} for g in games or []]
    refuse_outcome_fields(out)
    return out


# ---------------------------------------------------------------------------
# the pinned incumbent
# ---------------------------------------------------------------------------
def _git(*args, cwd: Path = REPO) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True,
                          encoding="utf-8").stdout


def _git_bytes(*args, cwd: Path = REPO) -> bytes:
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          capture_output=True).stdout


def pinned_source(commit: str, module: str) -> tuple[str, str]:
    """(source text, blob id) of prospect-tracker/<module>.py at `commit`."""
    spec = f"{commit}:prospect-tracker/{module}.py"
    blob = _git("rev-parse", spec).strip()
    return _git_bytes("show", spec).decode("utf-8"), blob


def _module_from_source(name: str, src: str, file_path: Path) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__file__ = str(file_path)
    exec(compile(src, str(file_path), "exec"), mod.__dict__)
    return mod


@contextlib.contextmanager
def pinned_incumbent(commit: str = INCUMBENT_COMMIT, sources: dict | None = None):
    """Yield (bm, lv, blobs): betting_model and leaderboard_vintages at
    `commit`, loaded into this process. The pinned leaderboard_vintages is
    installed under its import name for the duration, because the pinned
    pricer imports it lazily by name; the previous entry is restored after.
    `sources` ({module: (src, blob)}) replaces the git read, for tests."""
    got = {}
    for m in PINNED_MODULES:
        got[m] = (sources or {}).get(m) or pinned_source(commit, m)
    prev = sys.modules.get("leaderboard_vintages", None)
    had_prev = "leaderboard_vintages" in sys.modules
    lv = _module_from_source("leaderboard_vintages", got["leaderboard_vintages"][0],
                             ROOT / "leaderboard_vintages.py")
    sys.modules["leaderboard_vintages"] = lv
    try:
        bm = _module_from_source("_b4_pinned_betting_model", got["betting_model"][0],
                                 ROOT / "betting_model.py")
        yield bm, lv, {m: got[m][1] for m in PINNED_MODULES}
    finally:
        if had_prev:
            sys.modules["leaderboard_vintages"] = prev
        else:
            sys.modules.pop("leaderboard_vintages", None)


SERVE_FLAG_NAMES = ("SERVE_ATH_PARK", "SERVE_RUNLINE_TIE_SPLIT", "SERVE_RUN_DISPERSION",
                    "SERVE_PROB_CALIBRATION", "SERVE_TOTAL_LEVEL",
                    "SERVE_TOTAL_DISPERSION", "SERVE_TOTAL_CALIBRATION",
                    "SERVE_RIDGE_FIT", "SERVE_LINEUP_STRENGTH", "SERVE_STAR_OUT")


def serve_flags(bm) -> dict:
    """Every serve flag the pricer module defines, by name (absent -> None)."""
    return {n: getattr(bm, n, None) for n in SERVE_FLAG_NAMES}


def assert_incumbent_form(bm) -> None:
    """The seam's Poisson / identity-Platt reading holds only while these
    flags are off; a pinned commit with them on is not the registered form."""
    if getattr(bm, "SERVE_RUN_DISPERSION", False):
        raise LookRefused("SERVE_RUN_DISPERSION is True at the pinned commit")
    if getattr(bm, "SERVE_PROB_CALIBRATION", False):
        raise LookRefused("SERVE_PROB_CALIBRATION is True at the pinned commit")


# ---------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------
def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store_files(store: Path = STORE) -> list[Path]:
    return sorted(p for p in Path(store).glob("*.json") if p.is_file())


def store_hash(store: Path = STORE) -> dict:
    """SHA-256 over the sorted (file name, file SHA-256) pairs of every file
    the run may read (the reader indexes every record in the directory)."""
    pairs = [(p.name, _sha256_file(p)) for p in store_files(store)]
    h = hashlib.sha256()
    for name, digest in pairs:
        h.update(f"{name}\t{digest}\n".encode("utf-8"))
    return {"sha256": h.hexdigest(), "n_files": len(pairs),
            "files": {n: d for n, d in pairs}}


def check_store(lv, store: Path = STORE, *, host: str | None = None,
                require_host: bool = True) -> dict:
    """The registered store or a StoreRefused. The pinned reader's own
    VINTAGE_DIR must be this directory, so the resolver and the counts read
    one store; the host must be NOAH-PC."""
    h = host if host is not None else socket.gethostname()
    if require_host and str(h).upper() != STORE_HOST:
        raise StoreRefused(f"host {h!r} is not {STORE_HOST}; the box's store is "
                           "never read for this look")
    if Path(lv.VINTAGE_DIR).resolve() != Path(store).resolve():
        raise StoreRefused(f"the pinned reader's VINTAGE_DIR {lv.VINTAGE_DIR} is not "
                           f"the registered store {store}")
    return {"host": str(h), "path": str(Path(store).resolve())}


def _utc(ts) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def is_present_night(night: str, rec: dict | None, lv) -> bool:
    """2026-09-11b point 3: <D>.json exists, its provenance is live, and its
    captured_at UTC date is D or D+1."""
    if not isinstance(rec, dict):
        return False
    if lv.provenance_source(rec) != "live":
        return False
    cap = _utc(rec.get("captured_at"))
    if cap is None:
        return False
    d = date.fromisoformat(night)
    return cap.date() in (d, d + timedelta(days=1))


def _dates(first: str, last: str) -> list[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def night_inventory(lv, first: str, last: str, store: Path = STORE) -> dict:
    present, missing, why = [], [], {}
    for d in _dates(first, last):
        rec = lv.load_vintage(d, vintage_dir=store)
        if is_present_night(d, rec, lv):
            present.append(d)
        else:
            missing.append(d)
            why[d] = ("no file" if rec is None else
                      f"provenance {lv.provenance_source(rec)}, captured_at "
                      f"{rec.get('captured_at')}")
    return {"first": first, "last": last, "n_nights": len(present) + len(missing),
            "present": present, "missing": missing, "missing_why": why,
            "n_present": len(present), "floor": NIGHT_FLOOR,
            "floor_met": len(present) >= NIGHT_FLOOR}


def vintage_meta(rec: dict, col: str) -> dict:
    fb = (rec.get("feature_basis") or {}).get(col) or {}
    src = (rec.get("sources") or {}).get("hitter_leaderboards.json")
    return {"schema": rec.get("schema"), "vintage_date": rec.get("vintage_date"),
            "captured_at": rec.get("captured_at"),
            "covers_through": rec.get("covers_through"),
            "provenance": (rec.get("provenance") or {}).get("source"),
            "hitter_as_of": src.get("as_of") if isinstance(src, dict) else None,
            "parks_short_window": isinstance(rec.get("parks_short_window"), dict),
            "basis": fb.get("basis"), "basis_n": fb.get("n")}


def _mtime_lag_hours(store: Path, vd: str, rec: dict) -> float | None:
    """Hours from the record's captured_at to its file's mtime. A file copied
    in from another host carries a write time well after its capture; the
    look reports the lag of every window night so a copy cannot pass unseen."""
    cap = _utc(rec.get("captured_at"))
    try:
        mt = datetime.fromtimestamp((Path(store) / f"{vd}.json").stat().st_mtime,
                                    tz=timezone.utc)
    except OSError:
        return None
    return round((mt - cap).total_seconds() / 3600.0, 2) if cap else None


def record_stamp(rec: dict, col: str) -> bool:
    basis = str(((rec.get("feature_basis") or {}).get(col) or {}).get("basis") or "")
    return any(tok in basis for tok in RECORD_STAMP_TOKENS[col])


# ---------------------------------------------------------------------------
# the committed-board stamp (5c-B), read from git
# ---------------------------------------------------------------------------
def git_board_stamps(*, path: str = "prospect-tracker/data/hitter_leaderboards.json",
                     since: str = "2026-08-15") -> dict:
    """{board as_of: [{commit, committed_at, applied, skipped, n_dropped}]}
    for every commit of the hitter board since `since`."""
    out: dict[str, list] = {}
    log = _git("log", "--all", f"--since={since}", "--format=%H %cI", "--", path)
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, ts = line.split()
        try:
            blob = json.loads(_git_bytes("show", f"{sha}:{path}").decode("utf-8"))
        except (subprocess.CalledProcessError, ValueError):
            continue
        rf = blob.get("roster_filter")
        if not isinstance(rf, dict):
            continue
        skipped = sorted(str(t.get("team")) for t in blob.get("teams") or []
                         if isinstance(t, dict) and t.get("roster_filter_skipped"))
        out.setdefault(str(blob.get("as_of")), []).append({
            "commit": sha[:8], "committed_at": ts,
            "applied": bool(rf.get("applied")),
            "n_dropped_from_constructions": rf.get("n_dropped_from_constructions"),
            "skipped": skipped,
            "unreadable_mlbam_kept": rf.get("n_unreadable_mlbam_kept")})
    return out


# ---------------------------------------------------------------------------
# games, pricing vintages and buckets (no outcome, no value)
# ---------------------------------------------------------------------------
def load_games(bm) -> list[dict]:
    """The completed regular-season games, offline (refresh=False never
    touches the network). gameType R is the cache's fetch-time filter."""
    games = bm.completed_games(SEASON, refresh=False)
    return sorted(games, key=lambda g: (g.get("date") or "", g.get("game_pk") or 0))


def _event_after(rec: dict, events) -> list[str]:
    cap = _utc(rec.get("captured_at"))
    hits = []
    for sha, ts, _why in events or ():
        if cap is not None and cap > _utc(ts):
            hits.append(sha)
    return hits


def classify_games(bm, lv, col: str, games: list[dict], *, store: Path = STORE,
                   board_stamps: dict | None = None) -> dict:
    """Every completed game into exactly one bucket for `col`, in the
    section's order, from the pricing vintage, the stamps and whether each
    club's cell is NULL. Reads no outcome (feature rows only) and keeps no
    column value. Returns {"games": [...], "vintages": {...}}."""
    spec = COLUMN_SPECS[col]
    rows = feature_rows(games)
    w0, w1 = spec["window"]
    resolve, _rstats = bm._vintage_resolver()
    vmeta: dict[str, dict] = {}
    out = []
    for g in rows:
        d = g.get("date") or ""
        rec = lv.as_of(d, vintage_dir=store) if d else None
        base = {"game_pk": g.get("game_pk"), "date": d,
                "home_org": g.get("home_org"), "away_org": g.get("away_org")}
        if not rec:
            out.append({**base, "vintage": None, "bucket": "no_vintage", "in_window": False})
            continue
        vd = str(rec.get("vintage_date"))
        if vd not in vmeta:
            m = vintage_meta(rec, col)
            m["file_mtime_minus_capture_h"] = _mtime_lag_hours(store, vd, rec)
            m["present"] = is_present_night(vd, rec, lv)
            m["post_retrain"] = _event_after(rec, spec["post_retrain"])
            m["x9"] = _event_after(rec, spec["x9"])
            m["record_stamp"] = record_stamp(rec, col)
            m["git_stamp"] = (list((board_stamps or {}).get(str(m["hitter_as_of"])) or [])
                              if col == "lineup_strength" else [])
            if m["record_stamp"]:
                raise StoreRefused(f"the {vd} record carries a {col} stamp this harness "
                                   "does not read; stop rather than guess its form")
            vmeta[vd] = m
        m = vmeta[vd]
        cov = str(rec.get("covers_through") or vd)
        age = (date.fromisoformat(d) - date.fromisoformat(cov)).days
        base.update({"vintage": vd, "vintage_age_days": age,
                     "parks_short_window": m["parks_short_window"]})
        in_window = (w0 <= vd <= w1) and d < WINDOW_GAMES_BEFORE
        if not in_window:
            out.append({**base, "bucket": _outside_bucket(col, vd, rec), "in_window": False})
            continue
        got = resolve({"date": d, "home_org": base["home_org"],
                       "away_org": base["away_org"]})
        teams = got[0] if got else {}
        h, a = teams.get(base["home_org"]), teams.get(base["away_org"])
        if not h or not a:
            out.append({**base, "bucket": "incumbent_cannot_price", "in_window": True})
            continue
        bucket, sub = _window_bucket(col, vd, m, base, h, a)
        out.append({**base, "bucket": bucket, "sub": sub, "in_window": True})
    return {"games": out, "vintages": vmeta}


def _outside_bucket(col: str, vd: str, rec: dict) -> str:
    spec = COLUMN_SPECS[col]
    if vd >= spec["window"][0]:
        return "outside_window_later"
    if vd in spec.get("basis_unconfirmed", ()):
        return "basis_unconfirmed"
    p0, p1 = spec["pre_change"]
    if p0 <= vd <= p1:
        return "pre_change_ranking_basis" if col == "star_out" else "pre_change_membership"
    return "predates_column"


def _window_bucket(col: str, vd: str, m: dict, g: dict, h: dict, a: dict):
    spec = COLUMN_SPECS[col]
    if not m["present"]:
        return "not_present_night", None
    if m["post_retrain"]:
        return "post_retrain", None
    if m["x9"]:
        return "x9", None
    if col == "lineup_strength":
        stamps = m["git_stamp"]
        if stamps:
            if not all(s["applied"] for s in stamps):
                return "pre_change_membership", ["board_applied_false"]
            skipped = {c for s in stamps for c in s["skipped"]}
            if g["home_org"] in skipped or g["away_org"] in skipped:
                return "pre_change_membership", ["skipped_club"]
        if vd >= STAMP_DUE and not stamps:
            return "stamp_missing", None
    elif vd >= STAMP_DUE:
        return "stamp_missing", None
    if h.get(col) is None or a.get(col) is None:
        return "stated_null", None
    sub = []
    if col == "lineup_strength":
        if vd in spec["flag_unrecorded"]:
            sub.append("filter_flag_unrecorded")
        elif spec["stamp_late"][0] <= vd <= spec["stamp_late"][1] and not m["git_stamp"]:
            sub.append("stamp_late")
        if m["git_stamp"]:
            sub.append("stamped_from_git")
    else:
        sub.append("basis_unrecorded")
    return "dated_value", sub


def split_date(dated_value_dates) -> dict:
    """M = F + floor((L - F) / 2) calendar days, from dates alone."""
    ds = sorted(set(dated_value_dates))
    if not ds:
        return {"F": None, "L": None, "M": None}
    f, l_ = date.fromisoformat(ds[0]), date.fromisoformat(ds[-1])
    m = f + timedelta(days=(l_ - f).days // 2)
    return {"F": f.isoformat(), "L": l_.isoformat(), "M": m.isoformat()}


def counts_report(bm, lv, col: str, games: list[dict], *, store: Path = STORE,
                  board_stamps: dict | None = None) -> dict:
    """Step 1's counts and every count-only report item, with M."""
    spec = COLUMN_SPECS[col]
    cl = classify_games(bm, lv, col, games, store=store, board_stamps=board_stamps)
    gs = cl["games"]
    nights = night_inventory(lv, *spec["nights"], store=store)
    dv = [g for g in gs if g["bucket"] == "dated_value"]
    sp = split_date(g["date"] for g in dv)
    fit = [g for g in dv if sp["M"] and g["date"] < sp["M"]]
    graded = [g for g in dv if sp["M"] and g["date"] >= sp["M"]]
    by_bucket = Counter(g["bucket"] for g in gs)
    window_by_vintage: dict = {}
    for g in gs:
        if not g.get("in_window"):
            continue
        b = window_by_vintage.setdefault(g["vintage"], Counter())
        b[g["bucket"]] += 1
        for s in g.get("sub") or ():
            b[g["bucket"] + ":" + s] += 1
    old = [g for g in dv if (g.get("vintage_age_days") or 0) >= 2]
    rep = {
        "column": col, "section": spec["section"],
        "clock": {"start": spec["nights"][0], "floor": (
            date.fromisoformat(spec["nights"][0]) + timedelta(days=CLOCK_NIGHTS)).isoformat(),
            "nights": nights},
        "n_games": len(gs),
        "by_bucket": dict(sorted(by_bucket.items())),
        "window_by_vintage": {k: dict(sorted(v.items()))
                              for k, v in sorted(window_by_vintage.items())},
        "split": sp,
        "n_fit": len(fit), "n_graded": len(graded),
        "fit_by_date": dict(sorted(Counter(g["date"] for g in fit).items())),
        "graded_by_date": dict(sorted(Counter(g["date"] for g in graded).items())),
        "parks_short_window": {
            "fit_with": sum(1 for g in fit if g["parks_short_window"]),
            "fit_without": sum(1 for g in fit if not g["parks_short_window"]),
            "graded_with": sum(1 for g in graded if g["parks_short_window"]),
            "graded_without": sum(1 for g in graded if not g["parks_short_window"])},
        "dated_value_sub": dict(sorted(Counter(
            s for g in dv for s in (g.get("sub") or ())).items())),
        "pre_change_sub": dict(sorted(Counter(
            s for g in gs if g["bucket"] == "pre_change_membership" and g.get("in_window")
            for s in (g.get("sub") or ())).items())),
        "vintage_age": {"n_dated_value": len(dv), "n_age_2_plus": len(old),
                        "game_weighted_mean_age": (round(sum(
                            g["vintage_age_days"] for g in dv) / len(dv), 3) if dv else None)},
        "vintages": {k: {kk: vv for kk, vv in v.items() if kk != "basis"}
                     for k, v in sorted(cl["vintages"].items())
                     if spec["window"][0] <= k <= spec["window"][1]},
        "bases": sorted({v.get("basis") or "" for k, v in cl["vintages"].items()
                         if spec["window"][0] <= k <= spec["window"][1]}),
        "floors": {"nights": nights["floor_met"],
                   "fit": len(fit) >= MIN_FIT_GAMES,
                   "graded": len(graded) >= MIN_EVAL_GAMES},
    }
    if col == "star_out":
        cad = _utc(spec["cadence_commit"][1])
        rep["cadence_419811bb"] = {
            "dated_value_before": sum(1 for g in dv if _utc(
                cl["vintages"][g["vintage"]]["captured_at"]) < cad),
            "dated_value_after": sum(1 for g in dv if _utc(
                cl["vintages"][g["vintage"]]["captured_at"]) >= cad)}
    rep["step1_counts_pass"] = all(rep["floors"].values())
    rep["_games"] = gs
    return rep


def anchored_window(bm, games: list[dict]) -> dict:
    """Every vintage-gradable game dated before 2026-08-01, as its game_pk set,
    plus _vintage_cut_index's own cut at this run (printed beside it)."""
    rows = feature_rows(games)
    resolve, _ = bm._vintage_resolver()
    gradable = [g for g in rows if resolve(g)]
    dates = sorted({g["date"] for g in gradable if g.get("date")})
    cut = dates[bm._vintage_cut_index(gradable, dates)] if len(dates) > 1 else None
    pks = sorted(int(g["game_pk"]) for g in gradable if (g.get("date") or "") < ANCHOR_SPLIT)
    return {"split_governs": ANCHOR_SPLIT, "cut_index_at_run": cut,
            "n_games": len(pks), "game_pks": pks,
            "game_pks_sha256": hashlib.sha256(
                ",".join(map(str, pks)).encode()).hexdigest()}


# ---------------------------------------------------------------------------
# the incumbent's parameters, re-solved inline as backtest._grade does
# ---------------------------------------------------------------------------
def solve_params(bm, fit_games, *, resolve=None, teams=None, parks=None,
                 starters=None) -> dict:
    """`backtest._grade`'s fit block, verbatim in order: coefficients, tie
    rate, the fit window's home rate, alpha None, the differential shrink,
    the home adjustment, and the lab runline split."""
    teams = {} if teams is None else teams
    parks = {} if parks is None else parks
    starters = {} if starters is None else starters
    coeffs = (bm.fit_coefficients(fit_games, teams=teams, parks=parks,
                                  starters=starters, resolve=resolve)
              or dict(bm.LITERATURE_COEFFS))
    tie = bm._fit_tie_home(fit_games)
    home_rate = (sum(1 for g in fit_games if g["home_runs"] > g["away_runs"])
                 / max(1, len(fit_games)))
    shrink, _ = bm._solve_diff_shrink(fit_games, teams, parks, starters, coeffs, tie,
                                      0.0, resolve, None)
    adj = bm._solve_home_adj(fit_games, teams, parks, starters, coeffs, tie,
                             home_rate, shrink, resolve, None)
    return {"coeffs": coeffs, "tie_home": tie, "diff_shrink": shrink,
            "home_adj": adj, "runline_split": bm._lab_runline_split(fit_games),
            "n_fit": len(fit_games)}


def params_from_artifact(block: dict) -> dict:
    """The incumbent's parameters as an artifact block stores them (the
    identity check's counts-only form: no outcome is read)."""
    c = block["coefficients"]
    return {"coeffs": {k: float(c[k]) for k in ("b0", "b1", "b2", "b3", "b4")},
            "tie_home": float(block["extra_inning_home_rate"]),
            "diff_shrink": float(block["diff_shrink"]),
            "home_adj": float(block["home_field_runs_adj"]),
            "runline_split": None, "n_fit": block.get("n_fit_games")}


def pinned_artifact(commit: str = INCUMBENT_COMMIT) -> dict:
    return json.loads(_git_bytes(
        "show", f"{commit}:prospect-tracker/data/betting_model_eval.json").decode("utf-8"))


def parity(solved: dict, block: dict, *, split: str | None, block_split: str | None,
           n_key: str = "n_fit", block_n=None) -> dict:
    """Each parameter against the artifact block, to the artifact's rounding:
    coefficients to 6 places, diff_shrink and the home adjustment and the tie
    rate to 4, the split date and the count exactly."""
    c = block.get("coefficients") or {}
    rows = []
    for k in ("b0", "b1", "b2", "b3", "b4"):
        rows.append((k, round(solved["coeffs"][k], 6),
                     round(float(c[k]), 6) if k in c else None))
    rows.append(("diff_shrink", round(solved["diff_shrink"], 4),
                 round(float(block.get("diff_shrink")), 4)
                 if block.get("diff_shrink") is not None else None))
    rows.append(("home_field_runs_adj", round(solved["home_adj"], 4),
                 round(float(block.get("home_field_runs_adj")), 4)
                 if block.get("home_field_runs_adj") is not None else None))
    rows.append(("extra_inning_home_rate", round(solved["tie_home"], 4),
                 round(float(block.get("extra_inning_home_rate")), 4)
                 if block.get("extra_inning_home_rate") is not None else None))
    rows.append(("split_date", split, block_split))
    rows.append((n_key, solved.get(n_key), block_n))
    checks = [{"item": k, "solved": s, "artifact": a, "equal": s == a} for k, s, a in rows]
    return {"pass": all(r["equal"] for r in checks), "items": checks}


# ---------------------------------------------------------------------------
# the seam, and the rows
# ---------------------------------------------------------------------------
def _clamp(x: float) -> float:
    return max(LAM_LO, min(LAM_HI, x))


def seam(bm, lam_home: float, lam_away: float, tie_home: float, rl_split,
         d_home: float = 0.0, d_away: float = 0.0) -> dict:
    """One seam prices both arms: shifted, clamped lambdas through
    `_score_joint` (Poisson, r None) and `split_tie_atom`; Platt identity.
    Unrounded. The incumbent arm is d_home = d_away = 0."""
    lh, la = _clamp(lam_home + d_home), _clamp(lam_away + d_away)
    dist, _tot = bm._score_joint(lh, la, None)
    atom = bm.split_tie_atom(dist, tie_home, rl_split)
    return {"lam_home": lh, "lam_away": la, "p_home": atom["p_home"],
            "p_home_minus_1_5": atom["p_home_minus_1_5"],
            "p_away_minus_1_5": atom["p_away_minus_1_5"]}


def game_lambdas(bm, g: dict, got, params: dict) -> dict | None:
    """The incumbent's unrounded per-side lambdas for one game, or None when
    it cannot price it."""
    gt, gs, gpk = got
    er = bm.expected_runs(g["home_org"], g["away_org"],
                          home_sp=gs.get(g.get("home_sp")),
                          away_sp=gs.get(g.get("away_sp")),
                          teams=gt, parks=gpk, coeffs=params["coeffs"],
                          home_adj=params["home_adj"], diff_shrink=params["diff_shrink"])
    if not er:
        return None
    return {"lam_home": er["lam_home"], "lam_away": er["lam_away"]}


def identity_check(bm, games: list[dict], params: dict, *, resolve) -> dict:
    """At zero the seam's p_home equals game_probabilities' p_home to its 5
    published places on every game passed. Reads no outcome."""
    rows = feature_rows(games)
    n = bad = skipped = 0
    first_bad = None
    for g in rows:
        got = resolve(g)
        if not got:
            skipped += 1
            continue
        gt, gs, gpk = got
        gp = bm.game_probabilities(g["home_org"], g["away_org"],
                                   home_sp=gs.get(g.get("home_sp")),
                                   away_sp=gs.get(g.get("away_sp")),
                                   teams=gt, parks=gpk, coeffs=params["coeffs"],
                                   tie_home=params["tie_home"], home_adj=params["home_adj"],
                                   diff_shrink=params["diff_shrink"], run_alpha=None,
                                   runline_tie_split=params["runline_split"])
        lam = game_lambdas(bm, g, got, params)
        if not gp or not lam:
            skipped += 1
            continue
        s = seam(bm, lam["lam_home"], lam["lam_away"], params["tie_home"],
                 params["runline_split"])
        n += 1
        if round(s["p_home"], 5) != gp["p_home"]:
            bad += 1
            if first_bad is None:
                first_bad = {"game_pk": g.get("game_pk"), "seam": round(s["p_home"], 5),
                             "game_probabilities": gp["p_home"]}
    return {"pass": n > 0 and bad == 0, "n_checked": n, "n_mismatch": bad,
            "n_skipped": skipped, "first_mismatch": first_bad}


def build_game_records(bm, lv, col: str, games: list[dict], buckets: list[dict],
                       params: dict, *, resolve) -> tuple[list[dict], dict]:
    """Per dated-value game: the incumbent's lambdas and the features each arm
    reads (z of the column, z_off and z_prev for both clubs, the stored count
    for 5c-C's distribution), keyed by game_pk; outcomes joined in by the
    caller. Counts what it skips."""
    by_pk = {g.get("game_pk"): g for g in games}
    out, skipped = [], Counter()
    zc = "z_" + col
    for b in buckets:
        if b["bucket"] != "dated_value":
            continue
        g = by_pk.get(b["game_pk"])
        got = resolve(feature_rows([g])[0]) if g else None
        if not got:
            skipped["no_vintage_at_score"] += 1
            continue
        lam = game_lambdas(bm, g, got, params)
        if not lam:
            skipped["incumbent_cannot_price"] += 1
            continue
        h, a = got[0][g["home_org"]], got[0][g["away_org"]]
        out.append({"game_pk": g["game_pk"], "date": g["date"],
                    "home_org": g["home_org"], "away_org": g["away_org"],
                    "vintage": b["vintage"], "vintage_age_days": b["vintage_age_days"],
                    "bucket": b["bucket"], **lam,
                    "z_home": h.get(zc), "z_away": a.get(zc),
                    "v_home": h.get(col), "v_away": a.get(col),
                    "z_off_home": h.get("z_off"), "z_off_away": a.get("z_off"),
                    "z_prev_home": h.get("z_prev"), "z_prev_away": a.get("z_prev"),
                    "home_runs": int(g["home_runs"]), "away_runs": int(g["away_runs"])})
    return out, dict(skipped)


def side_rows(recs: list[dict], zkey: tuple[str, str] = ("z_home", "z_away")) -> list[dict]:
    """The row builder: one row per scoring side, carrying the org and the
    bucket. z_s is the scoring club's value, z_o the opposing club's."""
    rows = []
    for r in recs:
        zh, za = r[zkey[0]], r[zkey[1]]
        rows.append({"game_pk": r["game_pk"], "date": r["date"], "side": "home",
                     "org": r["home_org"], "opp_org": r["away_org"], "bucket": r["bucket"],
                     "lam": r["lam_home"], "runs": r["home_runs"], "z_s": zh, "z_o": za})
        rows.append({"game_pk": r["game_pk"], "date": r["date"], "side": "away",
                     "org": r["away_org"], "opp_org": r["home_org"], "bucket": r["bucket"],
                     "lam": r["lam_away"], "runs": r["away_runs"], "z_s": za, "z_o": zh})
    return rows


# ---------------------------------------------------------------------------
# the fit
# ---------------------------------------------------------------------------
def fit_terms(rows: list[dict], terms: int) -> dict:
    """The residual least squares, no intercept. terms 1: c over x = z_s -
    xbar. terms 2: (c_own, c_opp) over x_own = z_s - zbar, x_opp = z_o - zbar.
    {"ok": False, "why": ...} when it cannot run."""
    if not rows:
        return {"ok": False, "why": "no fit rows"}
    if any(r["z_s"] is None or r["z_o"] is None for r in rows):
        return {"ok": False, "why": "a fit row carries no z (a pricing vintage had "
                                    "fewer than 2 clubs with a value)"}
    zbar = sum(r["z_s"] for r in rows) / len(rows)
    res = [r["runs"] - r["lam"] for r in rows]
    if terms == 1:
        xs = [r["z_s"] - zbar for r in rows]
        sxx = sum(x * x for x in xs)
        if sxx <= 0.0:
            return {"ok": False, "why": "sum of x squared is 0"}
        c = sum(x * e for x, e in zip(xs, res)) / sxx
        n = len(rows)
        s2 = sum((e - c * x) ** 2 for x, e in zip(xs, res)) / max(1, n - 1)
        return {"ok": True, "zbar": zbar, "c": c, "se_c": math.sqrt(s2 / sxx), "n_rows": n}
    xo = [r["z_s"] - zbar for r in rows]
    xp = [r["z_o"] - zbar for r in rows]
    a11 = sum(x * x for x in xo)
    a22 = sum(x * x for x in xp)
    a12 = sum(x * y for x, y in zip(xo, xp))
    if a11 <= 0.0 or a22 <= 0.0:
        return {"ok": False, "why": "a column's sum of squares is 0"}
    det = a11 * a22 - a12 * a12
    if abs(det) <= 1e-12 * a11 * a22:
        return {"ok": False, "why": "the design matrix is singular"}
    b1 = sum(x * e for x, e in zip(xo, res))
    b2 = sum(x * e for x, e in zip(xp, res))
    c_own = (a22 * b1 - a12 * b2) / det
    c_opp = (a11 * b2 - a12 * b1) / det
    n = len(rows)
    s2 = sum((e - c_own * x - c_opp * y) ** 2
             for x, y, e in zip(xo, xp, res)) / max(1, n - 2)
    return {"ok": True, "zbar": zbar, "c_own": c_own, "c_opp": c_opp,
            "se_c_own": math.sqrt(s2 * a22 / det), "se_c_opp": math.sqrt(s2 * a11 / det),
            "n_rows": n}


def shifts(rec: dict, fit: dict, terms: int, zh: float, za: float) -> tuple[float, float]:
    """(d_home, d_away) the candidate adds to the incumbent's lambdas."""
    zb = fit["zbar"]
    if terms == 1:
        return fit["c"] * (zh - zb), fit["c"] * (za - zb)
    xh, xa = zh - zb, za - zb
    return (fit["c_own"] * xh + fit["c_opp"] * xa,
            fit["c_own"] * xa + fit["c_opp"] * xh)


# ---------------------------------------------------------------------------
# the statistic, written out
# ---------------------------------------------------------------------------
def paired_stat(d: list[float]) -> dict:
    """mean, the n-1 sd, se, t and lb95 of incumbent-minus-candidate losses.
    sd = 0 cannot run; nothing escapes to se = 0."""
    n = len(d)
    if n < 2:
        return {"n": n, "mean": None, "sd": None, "se": None, "t": None, "lb95": None,
                "runnable": False, "why": "fewer than 2 graded games"}
    mean = sum(d) / n
    # Identical differences are sd = 0 exactly; the float mean of identical
    # values can carry an ulp of drift that would fake a nonzero sd.
    sd = 0.0 if max(d) == min(d) else math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
    if sd == 0.0:
        return {"n": n, "mean": mean, "sd": 0.0, "se": None, "t": None, "lb95": None,
                "runnable": False, "why": "sd = 0"}
    se = sd / math.sqrt(n)
    return {"n": n, "mean": mean, "sd": sd, "se": se, "t": mean / se,
            "lb95": mean - Z95 * se, "runnable": True}


def paired_delta_fixture_check(bm) -> dict:
    """The pinned `_paired_delta` against the written form on a fixture. The
    helper divides by n; when it differs the record says so and the inline
    n-1 form is the one that ran."""
    inc = [0.25, 0.16, 0.09, 0.36, 0.30, 0.12]
    ch = [0.20, 0.18, 0.05, 0.30, 0.31, 0.10]
    helper = bm._paired_delta(inc, ch)
    mine = paired_stat([a - b for a, b in zip(inc, ch)])
    agree = {
        "delta": helper.get("delta") == round(mine["mean"], 6),
        "sd": helper.get("sd") == round(mine["sd"], 6),
        "t": helper.get("t") == round(mine["t"], 3),
        "lb95": helper.get("lb95") == round(mine["lb95"], 6)}
    return {"helper": helper, "inline": {k: mine[k] for k in ("mean", "sd", "t", "lb95")},
            "agree": agree, "helper_agrees": all(agree.values()),
            "note": ("the helper agrees to its rounding" if all(agree.values()) else
                     "the helper differs (n divisor); the inline n-1 form ran")}


def _ll(p: float, y: int) -> float:
    return -(y * math.log(max(p, LOGLOSS_EPS)) + (1 - y) * math.log(max(1 - p, LOGLOSS_EPS)))


def game_losses(r: dict, s: dict) -> dict:
    """Every per-game loss one arm takes on one game. y is home runs greater
    than away runs, as _grade scores it."""
    hr, ar = r["home_runs"], r["away_runs"]
    y = 1 if hr > ar else 0
    y1 = 1 if hr - ar >= 2 else 0
    y2 = 1 if ar - hr >= 2 else 0
    p1, p2 = s["p_home_minus_1_5"], s["p_away_minus_1_5"]
    return {"brier": (s["p_home"] - y) ** 2, "logloss": _ll(s["p_home"], y),
            "total_abs": abs(hr + ar - (s["lam_home"] + s["lam_away"])),
            "rl_logloss": _ll(p1, y1) + _ll(p2, y2),
            "rl_brier_home": (p1 - y1) ** 2, "rl_brier_away": (p2 - y2) ** 2}


def score_graded(bm, recs: list[dict], fit: dict, terms: int, params: dict,
                 inc_cache: dict | None = None, zget=None) -> dict:
    """Paired losses on the graded games. `zget(rec) -> (z_home, z_away)`
    lets a twin pass permuted values."""
    zget = zget or (lambda r: (r["z_home"], r["z_away"]))
    deltas = {k: [] for k in ("brier", "logloss", "total_abs", "rl_logloss",
                              "rl_brier_home", "rl_brier_away")}
    dp = []
    for r in recs:
        key = r["game_pk"]
        if inc_cache is not None and key in inc_cache:
            inc_s, inc_l = inc_cache[key]
        else:
            inc_s = seam(bm, r["lam_home"], r["lam_away"], params["tie_home"],
                         params["runline_split"])
            inc_l = game_losses(r, inc_s)
            if inc_cache is not None:
                inc_cache[key] = (inc_s, inc_l)
        zh, za = zget(r)
        dh, da = shifts(r, fit, terms, zh, za)
        cs = seam(bm, r["lam_home"], r["lam_away"], params["tie_home"],
                  params["runline_split"], dh, da)
        cl = game_losses(r, cs)
        for k in deltas:
            deltas[k].append(inc_l[k] - cl[k])
        dp.append(cs["p_home"] - inc_s["p_home"])
    return {"deltas": deltas, "dp": dp}


# ---------------------------------------------------------------------------
# the twins
# ---------------------------------------------------------------------------
def _vintage_z_map(recs: list[dict]) -> dict:
    """{vintage: {org: z}} over the dated-value records (both halves)."""
    out: dict = {}
    for r in recs:
        m = out.setdefault(r["vintage"], {})
        m[r["home_org"]] = r["z_home"]
        m[r["away_org"]] = r["z_away"]
    return out


def twin_a_maps(recs: list[dict], vintage_clubs: dict, k: int) -> dict:
    """Replicate k of twin A: random.Random(k), advanced across the pricing
    vintages in ascending order; in each, the stored values (so the z-scores)
    are shuffled among the clubs carrying one, in canonical org-code order."""
    rng = random.Random(k)
    out = {}
    for vd in sorted(vintage_clubs):
        clubs = sorted(o for o, z in vintage_clubs[vd].items() if z is not None)
        vals = [vintage_clubs[vd][o] for o in clubs]
        rng.shuffle(vals)
        out[vd] = dict(zip(clubs, vals))
    return out


def twin_b_maps(fit_recs: list[dict], graded_recs: list[dict], k: int) -> dict:
    """Replicate k of twin B: random.Random(200 + k); within each half (fit,
    then graded), for each club in canonical order, its z shuffled across its
    own dated-value club-games in (date, game_pk) order. {(game_pk, org): z}."""
    rng = random.Random(TWIN_B_SEED_OFFSET + k)
    out = {}
    for half in (fit_recs, graded_recs):
        games_of: dict[str, list] = {}
        for r in half:
            games_of.setdefault(r["home_org"], []).append((r["date"], r["game_pk"], r["z_home"]))
            games_of.setdefault(r["away_org"], []).append((r["date"], r["game_pk"], r["z_away"]))
        for org in sorted(games_of):
            lst = sorted(games_of[org], key=lambda t: (t[0], t[1]))
            vals = [t[2] for t in lst]
            rng.shuffle(vals)
            for (d, pk, _z), v in zip(lst, vals):
                out[(pk, org)] = v
    return out


def constant_z_clubs(recs: list[dict]) -> list[str]:
    zs: dict[str, set] = {}
    for r in recs:
        zs.setdefault(r["home_org"], set()).add(r["z_home"])
        zs.setdefault(r["away_org"], set()).add(r["z_away"])
    return sorted(o for o, s in zs.items() if len(s) <= 1)


def _fit_with(recs, terms, zget) -> dict:
    rows = []
    for r in recs:
        zh, za = zget(r)
        rows.append({"lam": r["lam_home"], "runs": r["home_runs"], "z_s": zh, "z_o": za})
        rows.append({"lam": r["lam_away"], "runs": r["away_runs"], "z_s": za, "z_o": zh})
    return fit_terms(rows, terms)


def run_twin(bm, kind: str, fit_recs, graded_recs, terms, params, inc_cache,
             cand_mean: float | None) -> dict:
    """200 replicates; each refits (its own zbar) on the fit side and grades
    the graded side. The bar: the candidate's criterion-1 mean strictly greater
    than the 190th smallest twin mean."""
    means = []
    vclubs = _vintage_z_map(fit_recs + graded_recs) if kind == "A" else None
    for k in range(N_TWIN):
        if kind == "A":
            pm = twin_a_maps(fit_recs + graded_recs, vclubs, k)

            def zget(r, pm=pm):
                return pm[r["vintage"]][r["home_org"]], pm[r["vintage"]][r["away_org"]]
        else:
            pm = twin_b_maps(fit_recs, graded_recs, k)

            def zget(r, pm=pm):
                return pm[(r["game_pk"], r["home_org"])], pm[(r["game_pk"], r["away_org"])]
        f = _fit_with(fit_recs, terms, zget)
        if not f["ok"]:
            return {"runnable": False, "why": f"replicate {k}: {f['why']}",
                    "means": means}
        sc = score_graded(bm, graded_recs, f, terms, params, inc_cache, zget)
        st = paired_stat(sc["deltas"]["brier"])
        if st["mean"] is None:
            return {"runnable": False, "why": f"replicate {k}: no graded mean",
                    "means": means}
        means.append(st["mean"])
    srt = sorted(means)
    bar = srt[TWIN_BAR - 1]
    out = {"runnable": True, "n": len(means), "means": means,
           "bar_190th_smallest": bar}
    if cand_mean is not None:
        out["candidate_rank"] = sum(1 for m in means if m < cand_mean)
        out["beaten"] = cand_mean > bar
    return out


# ---------------------------------------------------------------------------
# reported-only reads
# ---------------------------------------------------------------------------
def corr(xs, ys) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pairs) / math.sqrt(sxx * syy)


def vif(y, x1, x2) -> float | None:
    """1 / (1 - R^2) of y on (x1, x2) with an intercept."""
    pts = [(a, b, c) for a, b, c in zip(y, x1, x2) if None not in (a, b, c)]
    n = len(pts)
    if n < 4:
        return None
    my = sum(p[0] for p in pts) / n
    m1 = sum(p[1] for p in pts) / n
    m2 = sum(p[2] for p in pts) / n
    s11 = sum((p[1] - m1) ** 2 for p in pts)
    s22 = sum((p[2] - m2) ** 2 for p in pts)
    s12 = sum((p[1] - m1) * (p[2] - m2) for p in pts)
    s1y = sum((p[1] - m1) * (p[0] - my) for p in pts)
    s2y = sum((p[2] - m2) * (p[0] - my) for p in pts)
    syy = sum((p[0] - my) ** 2 for p in pts)
    det = s11 * s22 - s12 * s12
    if det <= 0 or syy <= 0:
        return None
    b1 = (s22 * s1y - s12 * s2y) / det
    b2 = (s11 * s2y - s12 * s1y) / det
    r2 = (b1 * s1y + b2 * s2y) / syy
    return None if r2 >= 1 else 1.0 / (1.0 - r2)


def date_clustered_t(recs, d) -> float | None:
    """t over per-date mean differences (n-1 divisor over dates)."""
    by: dict[str, list] = {}
    for r, x in zip(recs, d):
        by.setdefault(r["date"], []).append(x)
    ms = [sum(v) / len(v) for v in by.values()]
    st = paired_stat(ms)
    return st["t"]


# ---------------------------------------------------------------------------
# leg 1, the contaminated-forward screen
# ---------------------------------------------------------------------------
def forward_split(games: list[dict]) -> dict:
    dates = sorted({g["date"] for g in games if g.get("date")})
    sd = dates[int(len(dates) * 0.7)] if len(dates) > 20 else None
    fit_g = [g for g in games if sd and (g.get("date") or "") < sd]
    ev_g = [g for g in games if sd and (g.get("date") or "") >= sd]
    ok = len(fit_g) > 200 and len(ev_g) > 50
    return {"split_date": sd if ok else None, "fit": fit_g, "eval": ev_g, "ok": ok}


def forward_incumbent(bm, games: list[dict]) -> dict:
    """backtest()'s contaminated `forward` fit at the pinned commit, re-solved
    inline on the live season-to-date inputs, and its eval-half n."""
    teams, parks, starters = bm.team_inputs(), bm.park_index(), bm.starter_inputs()
    fs = forward_split(games)
    if not fs["ok"]:
        return {"ok": False, "why": "the forward split leaves too few games"}
    p = solve_params(bm, fs["fit"], teams=teams, parks=parks, starters=starters)
    n_eval = 0
    for g in fs["eval"]:
        if bm.expected_runs(g["home_org"], g["away_org"], teams=teams, parks=parks,
                            coeffs=p["coeffs"], home_adj=p["home_adj"],
                            diff_shrink=p["diff_shrink"]):
            n_eval += 1
    p["n"] = n_eval
    return {"ok": True, "params": p, "split_date": fs["split_date"],
            "fit": fs["fit"], "eval": fs["eval"],
            "inputs": (teams, starters, parks)}


def vintage_meta_all(lv, col: str, board_stamps: dict | None, first: str, last: str,
                     store: Path = STORE) -> dict:
    """vintage_meta plus the bucket facts for EVERY store record dated first
    to last, whether or not it prices a game."""
    spec = COLUMN_SPECS[col]
    out = {}
    for d in _dates(first, last):
        rec = lv.load_vintage(d, vintage_dir=store)
        if not isinstance(rec, dict):
            continue
        m = vintage_meta(rec, col)
        m["present"] = is_present_night(d, rec, lv)
        m["post_retrain"] = _event_after(rec, spec["post_retrain"])
        m["x9"] = _event_after(rec, spec["x9"])
        m["git_stamp"] = (list((board_stamps or {}).get(str(m["hitter_as_of"])) or [])
                          if col == "lineup_strength" else [])
        out[d] = m
    return out


def season_end_lineup_values(lv, spec_col: str, vmeta: dict, store: Path = STORE) -> dict:
    """5c-B leg 1's column: each club's value from the newest present vintage
    dated on or before the season end where it carries a value outside every
    ungraded bucket. {org: (value, vintage)}; clubs with none are absent."""
    out: dict = {}
    for vd in sorted(vmeta, reverse=True):
        m = vmeta[vd]
        if vd > SEASON_END or not m.get("in_scope", True):
            continue
        if not m["present"] or m["post_retrain"] or m["x9"]:
            continue
        stamps = m.get("git_stamp") or []
        if vd >= STAMP_DUE and not stamps:
            continue
        if stamps and not all(s["applied"] for s in stamps):
            continue
        skipped = {c for s in stamps for c in s["skipped"]}
        rec = lv.load_vintage(vd, vintage_dir=store)
        for org in sorted((rec or {}).get("teams") or {}):
            if org in out or org in skipped:
                continue
            row = lv.team_row(rec, org) or {}
            v = row.get(spec_col)
            if v is not None:
                out[org] = (float(v), vd)
    return out


def standardize(values: dict, bm) -> dict:
    """z over the clubs' values, population sd, sd 0 read as 1.0 (_mean_sd)."""
    orgs = sorted(values)
    mu, sd = bm._mean_sd([values[o] for o in orgs])
    return {o: (values[o] - mu) / sd for o in orgs}


def leg1_run(bm, fwd: dict, zfun, terms: int) -> dict:
    """The residual fit on the forward fit half and the forward-eval paired
    Brier mean. `zfun(game, org) -> z | None`; a game with either club's z
    None is excluded and counted."""
    teams, starters, parks = fwd["inputs"]
    p = fwd["params"]

    def recs(gs):
        out, excl = [], Counter()
        for g in gs:
            zh, za = zfun(g, g["home_org"]), zfun(g, g["away_org"])
            if zh is None or za is None:
                excl["no_value"] += 1
                continue
            er = bm.expected_runs(g["home_org"], g["away_org"],
                                  home_sp=starters.get(g.get("home_sp")),
                                  away_sp=starters.get(g.get("away_sp")),
                                  teams=teams, parks=parks, coeffs=p["coeffs"],
                                  home_adj=p["home_adj"], diff_shrink=p["diff_shrink"])
            if not er:
                excl["incumbent_cannot_price"] += 1
                continue
            out.append({"game_pk": g["game_pk"], "date": g["date"],
                        "home_org": g["home_org"], "away_org": g["away_org"],
                        "lam_home": er["lam_home"], "lam_away": er["lam_away"],
                        "z_home": zh, "z_away": za,
                        "home_runs": int(g["home_runs"]), "away_runs": int(g["away_runs"]),
                        "vintage": None, "bucket": "contaminated"})
        return out, dict(excl)

    fit_recs, fit_excl = recs(fwd["fit"])
    ev_recs, ev_excl = recs(fwd["eval"])
    f = _fit_with(fit_recs, terms, lambda r: (r["z_home"], r["z_away"]))
    if not f["ok"]:
        return {"runnable": False, "why": f["why"], "excluded_fit": fit_excl,
                "excluded_eval": ev_excl}
    sc = score_graded(bm, ev_recs, f, terms, p)
    st = paired_stat(sc["deltas"]["brier"])
    if terms == 1:
        sign_bad = f["c"] <= 0
    else:
        sign_bad = (f["c_own"] - f["c_opp"]) >= 0
    fires = (st["mean"] is not None and st["mean"] <= 0) or sign_bad
    return {"runnable": st["mean"] is not None, "fit": f, "brier": st,
            "fires": bool(fires), "n_fit_games": len(fit_recs), "n_eval_games": len(ev_recs),
            "excluded_fit": fit_excl, "excluded_eval": ev_excl,
            "label": "CONTAMINATED: season-to-date features; can only fail the candidate"}


def pinned_bundle_check() -> dict:
    """5c-C leg 1's ranking bundle: the step A snapshot, verified against the
    step A manifest's pins. Never the bundle on disk."""
    if not PINNED_BUNDLE.exists() or not PINNED_MANIFEST.exists():
        return {"ok": False, "why": "no step A pinned bundle on disk"}
    man = json.loads(PINNED_MANIFEST.read_text(encoding="utf-8"))
    pins = man.get("e5_waiver_pins") or {}
    sha = _sha256_file(PINNED_BUNDLE)
    ok = (sha == pins.get("mlb_projections_sha256")
          and pins.get("corpus_war_provider") == "ewar_v2")
    return {"ok": ok, "path": str(PINNED_BUNDLE), "sha256": sha,
            "mtime": datetime.fromtimestamp(PINNED_BUNDLE.stat().st_mtime).isoformat(),
            "manifest_sha256": pins.get("mlb_projections_sha256"),
            "war_provider": pins.get("corpus_war_provider"),
            "champion_fit_key": pins.get("champion_fit_key_corpus_sig"),
            "why": None if ok else "the bundle's hash or provider does not match step A"}


def star_top5(vets: list, lv) -> dict:
    """{org: [mlbam of its top five by warY1Champ]}, star_out_from_projections'
    ranking (descending, ties by mlbam; orgs with fewer than five dropped)."""
    ranked: dict[str, list] = {}
    for v in vets or []:
        if not isinstance(v, dict) or not v.get("mlbam"):
            continue
        org = lv._org(v.get("team"))
        w = v.get("warY1Champ")
        if not org or not isinstance(w, (int, float)):
            continue
        ranked.setdefault(org, []).append((float(w), int(v["mlbam"])))
    out = {}
    for org, rows in ranked.items():
        if len(rows) < lv.STAR_OUT_TOP_N:
            continue
        rows.sort(key=lambda r: (-r[0], r[1]))
        out[org] = [mid for _, mid in rows[:lv.STAR_OUT_TOP_N]]
    return out


def dated_star_out(top5: dict, roster_status, team_ids: dict, game_dates) -> dict:
    """{date: {org: count}} of each club's top five carrying a D code on the
    40-man roster as of the day before the game date. `roster_status(tid, d)`
    returns {mlbam: code} or None when no dated status could be read."""
    out: dict = {}
    for gd in sorted(set(game_dates)):
        prev = (date.fromisoformat(gd) - timedelta(days=1)).isoformat()
        day = {}
        for org, mids in sorted(top5.items()):
            tid = team_ids.get(org)
            st = roster_status(tid, prev) if tid else None
            if st is None:
                continue
            day[org] = sum(1 for m in mids if str(st.get(m, "")).startswith("D"))
        out[gd] = day
    return out


def leg1_coverage(dated: dict) -> dict:
    n = len(dated)
    good = sum(1 for d in dated.values() if len(d) >= LEG1_COVERAGE_CLUBS)
    return {"n_dates": n, "n_dates_28_clubs": good,
            "ok": n > 0 and good >= LEG1_COVERAGE_DATE_SHARE * n}


def statsapi_roster_status(tid, d, *, fetch=None) -> dict | None:
    """The dated 40-man roster's status codes, through scrapers._fetch's cache."""
    if fetch is None:
        import scrapers
        fetch = scrapers._fetch
    fr = fetch(LEG1_ROSTER_URL.format(tid=tid, d=d), f"b4look_roster40_{tid}_{d}",
               accept_json=True)
    if getattr(fr, "status", 0) != 200 or not getattr(fr, "body", ""):
        return None
    try:
        blob = json.loads(fr.body)
    except ValueError:
        return None
    out = {}
    for p in blob.get("roster") or []:
        mid = ((p or {}).get("person") or {}).get("id")
        code = (((p or {}).get("status") or {}).get("code"))
        if mid and code:
            out[int(mid)] = str(code)
    return out or None


def team_id_map(lv) -> dict:
    blob = json.loads((ROOT / ".cache" / f"statsapi_teams_{SEASON}.json").read_text(
        encoding="utf-8"))
    out = {}
    for t in blob.get("teams") or []:
        org = lv._org(t.get("name") or "")
        if org and len(org) <= 3 and t.get("id"):
            out[org] = int(t["id"])
    return out


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------
def verdict(col: str, *, ran_in_span: bool, note_ok: bool, checks_ok: bool,
            step1_ok: bool, step2_ok: bool, criteria: dict | None, twins: dict | None,
            leg1: dict | None) -> dict:
    """The first matching row wins (5c-B and 5c-C, 'The verdict')."""
    why = []
    if not ran_in_span:
        return {"verdict": "INDETERMINATE", "row": 1, "why": ["not run by 2026-10-31"]}
    if col == "star_out" and not note_ok:
        return {"verdict": "INDETERMINATE", "row": 1,
                "why": ["the dated note was not filed before the first B3/B4 outcome join"]}
    if col == "star_out" and not checks_ok:
        return {"verdict": "INDETERMINATE", "row": 1,
                "why": ["a parity or identity check failed"]}
    if not step1_ok:
        return {"verdict": "INDETERMINATE", "row": 1, "why": ["step 1 counts failed"]}
    if not step2_ok:
        return {"verdict": "INDETERMINATE", "row": 1, "why": ["step 2 fit cannot run"]}
    failed, unrun = [], []
    for k, v in (criteria or {}).items():
        if v.get("runnable") is False:
            unrun.append(k)
        elif v.get("pass") is False:
            failed.append(k)
    for k, v in (twins or {}).items():
        if not v.get("runnable"):
            unrun.append(f"twin {k}")
        elif not v.get("beaten"):
            failed.append(f"twin {k} not beaten")
    if not leg1 or not leg1.get("runnable"):
        unrun.append("leg 1")
    elif leg1.get("fires"):
        failed.append("leg 1 fires")
    if failed:
        return {"verdict": "FAIL", "row": 2, "why": failed, "could_not_run": unrun}
    if unrun:
        return {"verdict": "INDETERMINATE", "row": 3, "why": unrun}
    why.append("every floor met, criteria 1 to 4 hold, both twins beaten, leg 1 silent")
    return {"verdict": "PASS", "row": 4, "why": why}


def criteria_block(col: str, sc: dict, fit: dict) -> dict:
    b = paired_stat(sc["deltas"]["brier"])
    ll = paired_stat(sc["deltas"]["logloss"])
    tot = paired_stat(sc["deltas"]["total_abs"])
    if col == "lineup_strength":
        sign = {"value": fit["c"], "rule": "c > 0", "pass": fit["c"] > 0, "runnable": True}
    else:
        net = fit["c_own"] - fit["c_opp"]
        sign = {"value": net, "rule": "c_own - c_opp < 0", "pass": net < 0,
                "runnable": True, "c_own": fit["c_own"], "c_opp": fit["c_opp"]}

    def _pt(st, rule_ok):
        if st["mean"] is None:
            return {**st, "pass": None, "runnable": False}
        return {**st, "pass": rule_ok(st), "runnable": True}

    c1 = ({**b, "pass": None, "runnable": False} if not b["runnable"] else
          {**b, "pass": bool(b["mean"] > 0 and b["t"] >= Z95), "runnable": True})
    return {"1_moneyline_brier": c1,
            "2_moneyline_logloss": _pt(ll, lambda s: s["mean"] >= 0),
            "3_sign": sign,
            "4_total_not_worse": _pt(tot, lambda s: s["mean"] >= 0)}


# ---------------------------------------------------------------------------
# the look
# ---------------------------------------------------------------------------
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _say(msg: str) -> None:
    print(msg, flush=True)


def note_matches(note: dict, col: str, counts: dict, sh: dict, anchor: dict) -> list[str]:
    """Everything the dated note pinned must hold at the look run. Files the
    nightly added after the note are allowed (they cannot price a window
    game); a file the note hashed must be byte-equal."""
    bad = []
    cn = (note.get("columns") or {}).get(col) or {}
    if cn.get("split", {}).get("M") != counts["split"]["M"]:
        bad.append(f"M {counts['split']['M']} != note {cn.get('split', {}).get('M')}")
    for k in ("n_fit", "n_graded"):
        if cn.get(k) != counts[k]:
            bad.append(f"{k} {counts[k]} != note {cn.get(k)}")
    for name, digest in (note.get("store", {}).get("files") or {}).items():
        if sh["files"].get(name) != digest:
            bad.append(f"store file {name} changed since the note")
    if note.get("anchored_window", {}).get("game_pks_sha256") != anchor["game_pks_sha256"]:
        bad.append("the anchored window's game_pk set differs from the note")
    return bad


def step0_checks(bm, games: list[dict], resolve, anchor: dict, window_pks: set, *,
                 commit: str = INCUMBENT_COMMIT) -> dict:
    """Order of operations 0, before any number on either column: the
    incumbent re-solved inline on the anchored window and its parity with the
    artifact's vintage block at the pinned commit; the c = 0 identity check on
    every window game; leg 1's forward incumbent and its parity with the
    artifact on disk; the _paired_delta fixture check. Reads the incumbent's
    own outcomes only; no candidate column enters."""
    by_pk = {g["game_pk"]: g for g in games}
    anchor_games = [by_pk[pk] for pk in anchor["game_pks"]]
    params = solve_params(bm, anchor_games, resolve=resolve)
    art = pinned_artifact(commit)
    vpar = parity(params, art["vintage"], split=ANCHOR_SPLIT,
                  block_split=art["vintage"].get("split_date"),
                  block_n=art["vintage"].get("n_fit_games"))
    window_games = [by_pk[pk] for pk in sorted(window_pks) if pk in by_pk]
    ident = identity_check(bm, window_games, params, resolve=resolve)
    fwd = forward_incumbent(bm, games)
    cur_art = json.loads(EVAL_ARTIFACT.read_text(encoding="utf-8"))
    fpar = (parity(fwd["params"], cur_art.get("forward") or {}, split=fwd["split_date"],
                   block_split=cur_art.get("split_date"), n_key="n",
                   block_n=(cur_art.get("forward") or {}).get("n"))
            if fwd["ok"] else {"pass": False, "items": [], "why": fwd.get("why")})
    return {
        "identity": ident, "vintage_parity": vpar, "forward_parity": fpar,
        "forward_artifact_generated_at": cur_art.get("generated_at"),
        "forward_split_at_run": fwd.get("split_date"),
        "paired_delta_fixture": paired_delta_fixture_check(bm),
        "cut_index_at_run": anchor["cut_index_at_run"],
        "split_governs": ANCHOR_SPLIT,
        "runline_split": params["runline_split"],
        "runline_construction": ("lab split of the anchored fit window"
                                 if params["runline_split"] else "whole atom"),
        "incumbent_params": {"coeffs": {k: params["coeffs"][k] for k in
                                        ("b0", "b1", "b2", "b3", "b4")},
                             "diff_shrink": params["diff_shrink"],
                             "home_adj": params["home_adj"],
                             "tie_home": params["tie_home"], "n_fit": params["n_fit"]},
        "_params": params, "_fwd": fwd}


def run_checks(out_path: Path, *, commit: str = INCUMBENT_COMMIT) -> dict:
    """Step 0 on its own, before the dated note: the note pins the harness
    commit only after this passes."""
    with pinned_incumbent(commit) as (bm, lv, blobs):
        assert_incumbent_form(bm)
        check_store(lv)
        games = load_games(bm)
        resolve, _ = bm._vintage_resolver()
        anchor = anchored_window(bm, games)
        pks = set()
        for col in COLUMN_SPECS:
            cl = classify_games(bm, lv, col, games,
                                board_stamps={} if col == "star_out" else git_board_stamps())
            pks |= {g["game_pk"] for g in cl["games"] if g.get("in_window")}
        s0 = step0_checks(bm, games, resolve, anchor, pks, commit=commit)
        s0.pop("_params")
        s0.pop("_fwd")
        out = {"run_date": date.today().isoformat(),
               "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "incumbent_commit": commit, "incumbent_blobs": blobs,
               "model_version": bm.MODEL_VERSION, "serve_flags": serve_flags(bm),
               "n_window_games": len(pks), **s0}
    out_path.write_text(json.dumps(_jsonable(out), indent=1), encoding="utf-8")
    return out


def run_look(col: str, *, note_path: Path, out_dir: Path, today: date | None = None,
             commit: str = INCUMBENT_COMMIT) -> dict:
    """The one look for `col`. Order of operations: the date refusal and the
    one-look guard, step 0 (identity, both parities, fixture; the note match),
    step 1 counts (nothing else if any fails), M written before any fit, step
    2 the fit, step 3 criteria, both twins, the reported arms and leg 1."""
    spec = COLUMN_SPECS[col]
    today = today or date.today()
    check_b4_look_date(today)
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = RECORD_DIR / f"{spec['record']}_look_record.json"
    marker = RECORD_DIR / f"{spec['record']}_SCORING_BEGAN"
    if rec_path.exists() or marker.exists():
        raise LookRefused(f"{rec_path.name} or its marker exists: there is no second "
                          "read on 2026 data")
    note = json.loads(Path(note_path).read_text(encoding="utf-8"))
    head_blob = _git("hash-object", str(ROOT / "tools" / "b4_availability_look.py")).strip()
    note_blob = _git("rev-parse", f"{note['harness_commit']}:{HARNESS_PATH}").strip()
    if head_blob != note_blob:
        raise LookRefused("the harness on disk is not the one the dated note pinned")
    record: dict = {"column": col, "section": spec["section"], "run_date": today.isoformat(),
                    "run_started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "harness_commit": note["harness_commit"], "harness_blob": head_blob,
                    "note_commit": note.get("note_commit"), "incumbent_commit": commit}
    with pinned_incumbent(commit) as (bm, lv, blobs):
        assert_incumbent_form(bm)
        record["incumbent"] = {"blobs": blobs, "model_version": bm.MODEL_VERSION,
                               "serve_flags": serve_flags(bm)}
        record["store"] = check_store(lv)
        sh = store_hash()
        record["store"].update({"sha256": sh["sha256"], "n_files": sh["n_files"]})
        games = load_games(bm)
        resolve, _ = bm._vintage_resolver()
        anchor = anchored_window(bm, games)
        stamps = git_board_stamps() if col == "lineup_strength" else {}
        counts = counts_report(bm, lv, col, games, board_stamps=stamps)
        mism = note_matches(note, col, counts, sh, anchor)
        if mism:
            raise LookRefused("the run does not match the dated note: " + "; ".join(mism))
        # ---- step 0 -------------------------------------------------------
        window_pks = {g["game_pk"] for g in counts["_games"] if g.get("in_window")}
        s0 = step0_checks(bm, games, resolve, anchor, window_pks, commit=commit)
        params, fwd = s0.pop("_params"), s0.pop("_fwd")
        record["step0"] = s0
        ident, vpar, fpar = s0["identity"], s0["vintage_parity"], s0["forward_parity"]
        checks_ok = bool(ident["pass"] and vpar["pass"])
        _say(f"[{spec['section']}] step 0: identity {ident['pass']} "
             f"({ident['n_checked']} games), vintage parity {vpar['pass']}, forward parity "
             f"{fpar['pass']}, _paired_delta: {s0['paired_delta_fixture']['note']}")
        # 5c-C row 1 reads "a parity or identity check fails" (both parities);
        # 5c-B pins its note only after identity and both parities pass, and
        # reads a forward-parity failure as leg 1 unable to run (row 3).
        stop = not (ident["pass"] and vpar["pass"]) or (
            col == "star_out" and not fpar["pass"])
        if stop:
            record["verdict"] = verdict(col, ran_in_span=True, note_ok=True, checks_ok=False,
                                        step1_ok=False, step2_ok=False, criteria=None,
                                        twins=None, leg1=None)
            if col == "lineup_strength":
                record["verdict"]["why"] = ["identity or vintage parity failed before any "
                                            "number; the look cannot run"]
            return _finish(record, counts, rec_path)
        look_core(bm, lv, col, games, counts, params, resolve=resolve, fwd=fwd,
                  fpar=fpar, checks_ok=checks_ok, record=record, out_dir=out_dir,
                  marker=marker, anchor=anchor)
        return _finish(record, counts, rec_path)


def look_core(bm, lv, col: str, games: list[dict], counts: dict, params: dict, *,
              resolve, fwd: dict, fpar: dict, checks_ok: bool, record: dict,
              out_dir: Path, marker: Path, anchor: dict | None = None) -> dict:
    """Steps 1 to 3 and the verdict, after step 0 passed and the note matched.
    Fills `record` and returns it; the marker is written when scoring begins,
    so a crash after it can never be rerun."""
    spec = COLUMN_SPECS[col]
    # ---- step 1 -------------------------------------------------------
    record["counts"] = counts
    if anchor:
        record["anchored_window"] = {k: anchor[k] for k in
                                     ("split_governs", "cut_index_at_run", "n_games",
                                      "game_pks_sha256")}
    _say(f"[{spec['section']}] step 1: nights {counts['clock']['nights']['n_present']}"
         f"/{CLOCK_NIGHTS}, F {counts['split']['F']} L {counts['split']['L']} "
         f"M {counts['split']['M']}, fit n {counts['n_fit']}, graded n "
         f"{counts['n_graded']}")
    rec_partial = dict(record)
    rec_partial["split_written_before_fit"] = counts["split"]
    (out_dir / f"{spec['record']}_M_before_fit.json").write_text(
        json.dumps(_jsonable(rec_partial), indent=1), encoding="utf-8")
    step1_ok = counts["step1_counts_pass"]
    M = counts["split"]["M"]
    recs, skipped = (build_game_records(bm, lv, col, games, counts["_games"], params,
                                        resolve=resolve) if step1_ok else ([], {}))
    record["row_builder_skipped"] = skipped
    fit_recs = [r for r in recs if r["date"] < M] if M else []
    graded_recs = [r for r in recs if r["date"] >= M] if M else []
    if step1_ok and col == "star_out":
        n_pos = sum((1 if r["v_home"] >= 1 else 0) + (1 if r["v_away"] >= 1 else 0)
                    for r in fit_recs)
        n_zero = sum((1 if r["v_home"] == 0 else 0) + (1 if r["v_away"] == 0 else 0)
                     for r in fit_recs)
        record["identification"] = {"fit_club_games_count_ge_1": n_pos,
                                    "fit_club_games_count_0": n_zero,
                                    "min": ID_MIN_CLUB_GAMES}
        step1_ok = n_pos >= ID_MIN_CLUB_GAMES and n_zero >= ID_MIN_CLUB_GAMES
    if not step1_ok:
        record["verdict"] = verdict(col, ran_in_span=True, note_ok=True,
                                    checks_ok=checks_ok, step1_ok=False, step2_ok=False,
                                    criteria=None, twins=None, leg1=None)
        return record
    marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    # ---- step 2 -------------------------------------------------------
    fit = fit_terms(side_rows(fit_recs), spec["terms"])
    record["fit"] = fit
    if not fit["ok"]:
        record["verdict"] = verdict(col, ran_in_span=True, note_ok=True,
                                    checks_ok=checks_ok, step1_ok=True, step2_ok=False,
                                    criteria=None, twins=None, leg1=None)
        return record
    # ---- step 3 -------------------------------------------------------
    inc_cache: dict = {}
    sc = score_graded(bm, graded_recs, fit, spec["terms"], params, inc_cache)
    crit = criteria_block(col, sc, fit)
    record["criteria"] = crit
    record["runline_reported"] = {
        "logloss_sum_two_tails": paired_stat(sc["deltas"]["rl_logloss"]),
        "brier_home_minus_1_5": paired_stat(sc["deltas"]["rl_brier_home"]),
        "brier_away_minus_1_5": paired_stat(sc["deltas"]["rl_brier_away"])}
    n_g = len(sc["dp"])
    rms = math.sqrt(sum(x * x for x in sc["dp"]) / n_g) if n_g else None
    record["power_reported"] = {"rms_p_home_shift": rms,
                                "sqrt_n_rms": (math.sqrt(n_g) * rms) if rms else None}
    cmean = crit["1_moneyline_brier"].get("mean")
    twins = {}
    for kind in ("A", "B"):
        tw = run_twin(bm, kind, fit_recs, graded_recs, spec["terms"], params,
                      inc_cache, cmean)
        twins[kind] = tw
        _say(f"[{spec['section']}] twin {kind}: runnable {tw.get('runnable')}, "
             f"bar {tw.get('bar_190th_smallest')}, rank {tw.get('candidate_rank')}")
    twins["B"]["constant_z_clubs"] = {"fit": constant_z_clubs(fit_recs),
                                      "graded": constant_z_clubs(graded_recs)}
    record["twins"] = twins
    # reported-only: the offense arm and the feature correlations
    off_fit = _fit_with(fit_recs, spec["terms"],
                        lambda r: (r["z_off_home"], r["z_off_away"]))
    arm = {"fit": off_fit}
    if off_fit["ok"]:
        osc = score_graded(bm, graded_recs, off_fit, spec["terms"], params, inc_cache,
                           lambda r: (r["z_off_home"], r["z_off_away"]))
        arm["brier"] = paired_stat(osc["deltas"]["brier"])
    record["offense_arm_reported"] = arm
    feats = {}
    for half, rs in (("fit", fit_recs), ("graded", graded_recs)):
        sr = side_rows(rs)
        zz = [r["z_s"] for r in sr]
        zo = [x for r in rs for x in (r["z_off_home"], r["z_off_away"])]
        zp = [x for r in rs for x in (r["z_prev_home"], r["z_prev_away"])]
        feats[half] = {"corr_with_z_off": corr(zz, zo)}
        if col == "star_out":
            feats[half]["corr_with_z_prev"] = corr(zz, zp)
            feats[half]["vif_on_z_off_z_prev"] = vif(zz, zo, zp)
            feats[half]["stored_count_distribution"] = dict(sorted(Counter(
                x for r in rs for x in (r["v_home"], r["v_away"])).items()))
    record["features_reported"] = feats
    if col == "star_out":
        age1 = [i for i, r in enumerate(graded_recs) if r["vintage_age_days"] == 1]
        record["age1_reported"] = {
            "brier": paired_stat([sc["deltas"]["brier"][i] for i in age1]),
            "logloss": paired_stat([sc["deltas"]["logloss"][i] for i in age1])}
        record["date_clustered_t_reported"] = date_clustered_t(
            graded_recs, sc["deltas"]["brier"])
    # leg 1
    leg1 = _leg1(bm, lv, col, fwd, fpar, counts, games)
    record["leg1"] = leg1
    record["verdict"] = verdict(col, ran_in_span=True, note_ok=True,
                                checks_ok=checks_ok and fpar["pass"], step1_ok=True,
                                step2_ok=True, criteria=crit, twins=twins, leg1=leg1)
    return record


def _leg1(bm, lv, col, fwd, fpar, counts, games) -> dict:
    if not fwd["ok"]:
        return {"runnable": False, "why": fwd.get("why")}
    if not fpar["pass"]:
        return {"runnable": False, "why": "the forward parity check failed",
                "forward_split_at_run": fwd["split_date"]}
    clubs = sorted({o for g in games for o in (g["home_org"], g["away_org"])})
    if col == "lineup_strength":
        vmeta = vintage_meta_all(lv, col, git_board_stamps(),
                                 COLUMN_SPECS[col]["window"][0], SEASON_END)
        vals = season_end_lineup_values(lv, col, vmeta)
        if not vals:
            return {"runnable": False, "why": "no club has a season-end value"}
        z = standardize({o: v for o, (v, _vd) in vals.items()}, bm)
        out = leg1_run(bm, fwd, lambda g, org: z.get(org), 1)
        out["season_end_vintage_by_club"] = {o: vd for o, (_v, vd) in sorted(vals.items())}
        out["excluded_clubs"] = sorted(set(clubs) - set(vals))
        out["forward_split"] = fwd["split_date"]
        return out
    pb = pinned_bundle_check()
    if not pb["ok"]:
        return {"runnable": False, "why": pb["why"], "pinned_bundle": pb}
    vets = json.loads(PINNED_BUNDLE.read_text(encoding="utf-8")).get("vets") or []
    top5 = star_top5(vets, lv)
    tids = team_id_map(lv)
    gd = [g["date"] for g in fwd["fit"] + fwd["eval"]]
    dated = dated_star_out(top5, statsapi_roster_status, tids, gd)
    cov = leg1_coverage(dated)
    if not cov["ok"]:
        return {"runnable": False, "why": "no dated 40-man status for 28 of 30 clubs on "
                                          "90% of dates (leg 1 unbuildable)",
                "coverage": cov, "pinned_bundle": pb}
    zday = {}
    for d0, day in dated.items():
        if len(day) >= 2:
            zday[d0] = standardize(day, bm)
    out = leg1_run(bm, fwd, lambda g, org: (zday.get(g["date"]) or {}).get(org), 2)
    out.update({"pinned_bundle": pb, "coverage": cov, "forward_split": fwd["split_date"]})
    return out


def _finish(record: dict, counts: dict, rec_path: Path) -> dict:
    record.setdefault("counts", counts)
    record["run_finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec_path.write_text(json.dumps(_jsonable(record), indent=1), encoding="utf-8")
    _say(f"[{record['section']}] VERDICT {record['verdict']['verdict']} "
         f"(row {record['verdict']['row']}): {'; '.join(record['verdict']['why'])}")
    _say(f"[{record['section']}] record: {rec_path}")
    return record


# ---------------------------------------------------------------------------
# the counts-only and check commands
# ---------------------------------------------------------------------------
def run_counts(out_path: Path, *, commit: str = INCUMBENT_COMMIT) -> dict:
    """Counts only: no outcome, no column value. The dated note's numbers."""
    with pinned_incumbent(commit) as (bm, lv, blobs):
        store = check_store(lv)
        sh = store_hash()
        games = load_games(bm)
        anchor = anchored_window(bm, games)
        stamps = git_board_stamps()
        out = {"kind": "counts only: no outcome and no column value was read",
               "run_date": date.today().isoformat(),
               "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "incumbent_commit": commit, "incumbent_blobs": blobs,
               "model_version": bm.MODEL_VERSION, "serve_flags": serve_flags(bm),
               "store": {**store, "sha256": sh["sha256"], "n_files": sh["n_files"],
                         "files": sh["files"]},
               "anchored_window": anchor,
               "board_stamps": {k: v for k, v in sorted(stamps.items())
                                if k >= "2026-09-01"},
               "games": {"n": len(games), "first": games[0]["date"] if games else None,
                         "last": games[-1]["date"] if games else None},
               "columns": {}}
        for col in COLUMN_SPECS:
            rep = counts_report(bm, lv, col, games, board_stamps=stamps)
            rep.pop("_games", None)
            out["columns"][col] = rep
    out_path.write_text(json.dumps(_jsonable(out), indent=1), encoding="utf-8")
    return out


def run_identity_artifact(*, commit: str = INCUMBENT_COMMIT) -> dict:
    """The c = 0 identity check at the pinned artifact's parameters, on every
    window game of both columns. Reads no outcome."""
    with pinned_incumbent(commit) as (bm, lv, _blobs):
        check_store(lv)
        games = load_games(bm)
        params = params_from_artifact(pinned_artifact(commit)["vintage"])
        resolve, _ = bm._vintage_resolver()
        out = {}
        for col in COLUMN_SPECS:
            cl = classify_games(bm, lv, col, games,
                                board_stamps={} if col == "star_out" else None)
            pks = {g["game_pk"] for g in cl["games"] if g.get("in_window")}
            wg = [g for g in games if g["game_pk"] in pks]
            out[col] = identity_check(bm, wg, params, resolve=resolve)
        return out


def probe(out_path: Path, *, commit: str = INCUMBENT_COMMIT) -> dict:
    """5c-C leg 1's endpoint probe: two clubs, two dates, status codes only."""
    with pinned_incumbent(commit) as (_bm, lv, _blobs):
        tids = team_id_map(lv)
        res = {}
        for org in sorted(tids)[:2]:
            for d in ("2026-07-01", "2026-09-01"):
                st = statsapi_roster_status(tids[org], d)
                res[f"{org} {d}"] = {"n": len(st or {}), "n_D": sum(
                    1 for c in (st or {}).values() if c.startswith("D"))}
    out = {"probe_date": date.today().isoformat(), "reads": "roster status codes only",
           "results": res}
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("counts")
    c.add_argument("--out", required=True)
    sub.add_parser("identity")
    ck = sub.add_parser("checks")
    ck.add_argument("--out", required=True)
    k = sub.add_parser("look")
    k.add_argument("--column", required=True, choices=sorted(COLUMN_SPECS))
    k.add_argument("--note", required=True)
    k.add_argument("--out-dir", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "counts":
        o = run_counts(Path(a.out))
        for col, rep in o["columns"].items():
            print(col, json.dumps({k2: rep[k2] for k2 in ("split", "n_fit", "n_graded",
                                                          "floors", "by_bucket")}))
        print("store", o["store"]["sha256"], o["store"]["n_files"])
        return 0
    if a.cmd == "identity":
        print(json.dumps(run_identity_artifact(), indent=1))
        return 0
    if a.cmd == "checks":
        o = run_checks(Path(a.out))
        print(json.dumps({k2: o[k2] for k2 in ("identity", "vintage_parity",
                                                "forward_parity", "paired_delta_fixture",
                                                "cut_index_at_run")}, indent=1))
        return 0
    if a.cmd == "look":
        out_dir = Path(a.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        run_look(a.column, note_path=Path(a.note), out_dir=out_dir)
        return 0
    if a.cmd == "probe":
        print(json.dumps(probe(Path(a.out)), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
