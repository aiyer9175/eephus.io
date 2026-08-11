# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball America board ingest. Owner-pasted markdown, NOT a scraper.

BA boards are licensed subscription material. Paywall circumvention was asked
about and DECLINED (plan Lane K4); the sanctioned acquisition paths are an
owner paste into data/baseballamerica_imports/inbox/ and a licensing email.
Nothing in this module fetches anything. It reads files a human put on disk.

The material is used ONLY as eFV / consensus TRAINING input and is never
displayed. The drop tree is gitignored and, because deploy/nightly-build.sh
rsyncs only data/*.json at depth 1, it cannot reach the public webroot either.

WHAT BA PUBLISHES, verified against two real boards (2026 preseason Orioles
and Blue Jays, 30 players each, 60 rows total):

    30 players
    Expand all
    Headshot of Trey Yesavage          <- OPTIONAL, see below
    1\\. Trey Yesavage                  <- the anchor. markdown-escaped dot.
    RHP
    Ht: 6'4" | Wt: 225 | B-T: R-R
    Age: 22
    BA Grade/Risk: 60/Mild
    Adjusted Grade: 55
    Previous Rank: 2                   <- OPTIONAL, see below
    Track Record: ...
    Scouting Report: ...
    The Future: ...
    Scouting Grades: Fastball: 60 | Slider: 55 | Split: 70 | Control: 50

ANCHOR ON THE RANK LINE, NOT THE HEADSHOT LINE. 3 of 30 Orioles and 4 of 30
Blue Jays rows have no "Headshot of" line at all, so anchoring there silently
drops rows. The rank line is present on 60 of 60. It is matched only at the
start of a line, which is what keeps prose like "the Blue Jays at pick No.
20\\." from registering as a rank.

FIELDS THAT LOOK REQUIRED AND ARE NOT. Previous Rank is on all 30 Orioles rows
and absent from all 30 Blue Jays rows. Age is missing on 1-2 per board.
Scouting Report and The Future are missing on some. Requiring any of them
rejects a valid board.

THE FILENAME IS LOAD-BEARING, not cosmetic. The Blue Jays file carries no
season, board or team header anywhere in its body, so season / board / team
come from the name and nowhere else. See the inbox README for the spec.

ADJUSTED GRADE IS A COMPUTED FIELD. Deterministic on both boards with zero
exceptions in 60 rows:

    adjusted = raw - penalty(risk),  Low 0, Mild 5, Average 10, High 15, Extreme 20

Owner instruction stands: `fv` takes the Adjusted Grade, never the raw grade.
But raw and risk are BOTH stored under _extras, for two reasons. The pair
resolves 11 distinct cells against adjusted's 4-5, so it is strictly finer.
And adjusted is a FUNCTION OF RANK (monotone non-increasing in rank on both
boards, perfect contiguous tiers) while raw is not, so adjusted alone would
feed a model something close to a re-encoding of the rank column.

This module RECOMPUTES adjusted from raw and risk and reports every row where
the identity fails, rather than trusting it. A board that stops obeying the
identity is a format change, and finding out from a silent drift later is the
expensive version.

===========================================================================
AMATEUR DRAFT BOARDS ARE A SECOND FORMAT AND A SECOND TABLE
===========================================================================

BA also publishes DRAFT boards, and they are not the format above. Measured on
five real files (2027 Top 100, 2027 College Top 100, 2027 HS Top 150, 2028
College Top 50, 2028 HS Top 100; 500 rows):

    1\\. Dylan Seward
    SS
    Ht: 6'0" | Wt: 175 | B-T: B-R
    School: Norco (Calif.) HS
    Committed: Tennessee
    Age At Draft: 18.8
    <one unlabelled prose paragraph>

THEY CARRY NO GRADES AT ALL. BA Grade/Risk, Adjusted Grade and Scouting Grades
each appear on 0 of 500 rows. These are RANK-ONLY boards, so `fv`, `risk` and
`tools` are absent, and absent is what gets recorded. That also makes the
era rule above MOOT here rather than merely inapplicable: fv_basis(2027) picks
"adjusted" and fv_basis(2025) would pick "raw", and BOTH are None on a draft
board because neither field is published, so there is no reading under which a
grade gets fabricated. parse_draft_board never consults fv_basis and REFUSES a
draft board that starts publishing grades, because that is a format change that
deserves a decision rather than a silent new column.

THE FILENAME MEANS SOMETHING DIFFERENT FROM AN ORG BOARD:

    ba__{class_year}__draft__{scope}__{publication_date}.md

The first field is the DRAFT CLASS YEAR, not the list season, and the trailing
date is the PUBLICATION date, which is what snapshot_date takes. On an org board
the first field is the list season and the date is optional because a season
convention exists. There is NO defensible convention date for a draft board (a
class is ranked continuously from two years out), so the date is REQUIRED and a
draft file without one is refused rather than dated by guess.

THE FIELDS ARE OPTIONAL AND A PARSER THAT REQUIRES THEM DROPS ROWS SILENTLY.
Measured per board, rows carrying the field over rows total:

    Ht:            100/100  100/100  150/150  50/50  100/100   always
    School:        100/100  100/100  150/150  50/50  100/100   always
    Age At Draft:   96/100   89/100  150/150  47/50  100/100   OPTIONAL
    commit-ish:    100/100  100/100  150/150  50/50  100/100   always, 3 spellings
    Headshot of:        16       25        0     23        0   sporadic

THE COMMIT FIELD HAS THREE SPELLINGS AND TWO MEANINGS, and this is the trap.

    College boards write   "Drafted: Never Drafted" / "Drafted: Reds '25 (19)"
    HS boards write        "Committed: Tennessee"   / "Committed: Uncommitted"
    The mixed board writes "Committed/Drafted: ..." carrying EITHER

So the label does not tell you which quantity you have; only the VALUE does. A
draft-history value ("Never Drafted", or a club, a two-digit year and a round in
parentheses) is NOT a college commitment, and writing it into `college_commit`
would put "Never Drafted" in a column every consumer reads as a school. The
value is classified, `college_commit` takes only a real commitment, and the
untouched published string is kept at _extras.ba_commit_raw either way.

That classification is also the best HS-vs-college discriminator available, and
it is better than the two obvious ones. On the mixed 2027 Top 100 it is defined
on 100 of 100 rows and agrees with Age At Draft on 100 of 100 where age exists
(HS tops out at 19.2, college starts at 20.8). The SCHOOL string disagrees with
both on 9 of those 100, because BA does not tag every high school with an "HS"
token ("Metrolina Christian Academy, Indian Trail, N.C."), and school is exactly
what draft_export._canon_player_type falls back on when it is handed no
player_type. Across the two HS boards that fallback would mistype 40 more rows
as college. Hence the board-level pool is passed IN rather than left to be
inferred, which is what the "board wins" rule below is protecting.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from scrapers import (
    HITTER_TOOL_KEYS as _HITTER_TOOL_KEYS,
    PITCHER_TOOL_KEYS as _PITCHER_TOOL_KEYS,
    Snapshot,
    fix_mojibake,
    normalize_key,
    strip_name_markers,
)

log = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
DROP_DIR = _BASE / "data" / "baseballamerica_imports"
INBOX_DIR = DROP_DIR / "inbox"
PROCESSED_DIR = DROP_DIR / "processed"

# The source string already in prospects.db. Do NOT mint a variant: the tree
# carries 100 rows under exactly this name (Baseball America 2026-06-03 Top
# 100, snapshot_date 2026-06-03) plus 41 under baseballamerica_statcast_by_age,
# and a second spelling would read as a second outlet to consensus and to
# source_backtest.
SOURCE = "baseballamerica"

BOARDS = ("preseason", "midseason", "offseason")

# A SECOND SOURCE STRING, deliberately not a variant of the first.
#
# Amateur draft rows land in `draft_snapshots`, keyed on draft_{year}_{slug},
# and pro rows land in `snapshots`, keyed on the MiLB-style slug. They are
# different tables, different key namespaces and different populations, and a
# shared source string would let a mistake in either path read as the other
# outlet's data to consensus and to source_backtest. Matches the shape the other
# draft feeds already use (espn_draft, mlb_pipeline_draft).
DRAFT_SOURCE = "baseballamerica_draft"

DRAFT_BOARD = "draft"

# THE SCOPE REGISTRY. slug -> (label fragment, published extent, pool).
#
# `pool` is the load-bearing field and it is NOT cosmetic. None means the board
# mixes high schoolers and college players, so its rank orders the whole draft
# class. "HS" or "COL" means the board ranks a SUBSET, so its rank orders that
# subset only and is NOT comparable with a whole-class rank. See
# scope_rank_is_global for what that costs and why it is enforced.
#
# The extent is carried here rather than derived from the parsed row count, for
# the same reason the org path labels by published extent: a Top 150 that parsed
# 100 rows must not relabel itself a Top 100. That is the label-collision class
# of bug, and on this side it would silently fuse two different boards onto one
# upsert key.
DRAFT_SCOPES: dict[str, tuple[str, int, str | None]] = {
    "top-100":         ("Top 100", 100, None),
    "top100":          ("Top 100", 100, None),
    "top-250":         ("Top 250", 250, None),
    "top250":          ("Top 250", 250, None),
    "college-top-100": ("College Top 100", 100, "COL"),
    "college-top-50":  ("College Top 50", 50, "COL"),
    "hs-top-150":      ("HS Top 150", 150, "HS"),
    "hs-top-100":      ("HS Top 100", 100, "HS"),
}


def scope_rank_is_global(pool: str | None) -> bool:
    """True when this board's rank orders the whole draft class.

    THE HAZARD, and it is the draft-side twin of the org-list guard above.
    draft_export._consensus(snaps, "rank") averages the latest rank per SOURCE,
    and _latest_per_source collapses by source string alone, so every BA draft
    board votes into one number as though its ranks were the same quantity. They
    are not. On a College Top 50 and an HS Top 100 there are TWO players ranked
    1, and neither of them is the first pick of the class.

    consensus_rank drives consensus_pick, projected_round and draft_stock_plus,
    so a scope-local rank entering it is exactly the Bryan Sanchez failure on the
    amateur side: a rank that means "best in his subset" read as "best overall",
    silently and board-wide.

    There is no arithmetic that converts one into the other, because BA never
    published the interleaving. So a scoped board's rank does not enter the
    `rank` column at all; it is preserved verbatim at _extras.ba_scope_rank
    beside the scope it belongs to, which loses nothing and can be re-derived if
    a gated within-scope model is ever fitted.
    """
    return pool is None

# Known slug collisions where a BA board's own org identifies the NEWCOMER of a
# two-human key: (slug, board_org) -> the discriminated key the newcomer lives
# under. Consulted in resolve_identities before the plain slug can reach the
# incumbent. Mirrors fangraphs_csv._FG_ORG_SPLIT_KEYS and pairs with
# scrapers._SPLIT_KEYS, which routes the same humans by MLBAM id.
_BA_ORG_SPLIT_KEYS: dict[tuple[str, str], str] = {
    # The Angels C Garrett Wright (mlbam 835226, Tennessee, drafted 2026 rd 8)
    # vs the White Sox RHP Garrett Wright (mlbam 695057, b. 2002-02-11). The
    # 2026-08-09 verification caught the merge; the age check in
    # screen_identity would now quarantine it, but a pin routes the row to the
    # RIGHT human instead of merely refusing the wrong one.
    ("garrett_wright", "LAA"): "garrett_wright_laa",
}

# WHICH PUBLISHED NUMBER IS THE FV, and it depends on the season.
#
# Baseball America introduced the Grade/Risk-to-Adjusted-Grade system for the
# 2026 boards (owner-sourced:
# baseballamerica.com/stories/explaining-baseball-americas-updated-mlb-prospect-grades-risk-system/).
# Measured in this tree, the data agrees exactly: an "Adjusted Grade" line
# appears on 390 of 390 rows in 2026 and on 0 of 1,140 rows in 2023-2025.
#
# So there are two eras and each has exactly one FV-equivalent:
#   2026 and later:  the Adjusted Grade. BA does the risk discount for you.
#   2025 and earlier: the BA Grade. There was no adjustment to apply, so the
#                     published grade IS the grade, and using it is not a
#                     fallback.
#
# This is NOT the "never fall back to the raw grade" case the module docstring
# warns about. That rule exists for a row whose Adjusted Grade is MISSING while
# its siblings have one, where a raw grade in an FV column would be a silent
# scale error. Here the whole era has no adjusted grade because the concept did
# not exist yet, and the two numbers are not competing measurements of the same
# thing.
#
# THE CONSEQUENCE, stated rather than buried: this puts a scale break in BA's
# own series at 2026, because a 2026 FV is discounted by 0 to 20 points and a
# 2025 FV is not. grade_normalization keys its correction by (source, role,
# cycle-year) and therefore fits a SEPARATE offset per year, which absorbs the
# level part of the break automatically. What it cannot absorb is the
# risk-dependent spread, since the discount varies per player. Both eras keep
# raw and risk under _extras so the break stays measurable and the decision
# stays reversible.
ADJUSTED_GRADE_FIRST_SEASON = 2026


def fv_basis(season: int) -> str:
    """Which published field is the FV for this season: 'adjusted' or 'raw'."""
    return "adjusted" if season >= ADJUSTED_GRADE_FIRST_SEASON else "raw"

_REPORT_MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Risk -> adjusted-grade penalty
# ---------------------------------------------------------------------------

# Measured on 60 of 60 rows across two boards, zero exceptions. Ordered so the
# report can print the ladder. "Extreme" was not observed on either board and
# is carried from BA's published risk vocabulary; a row that uses it will be
# checked by the same identity as every other row, so a wrong guess here shows
# up as an identity failure rather than as a silently wrong FV.
RISK_PENALTY: dict[str, float] = {
    "low": 0.0,
    "mild": 5.0,
    "average": 10.0,
    "high": 15.0,
    "extreme": 20.0,
}

# BA CHANGED ITS RISK VOCABULARY, measured across 2023-2026 (1,530 rows, 52 org
# boards). The 2023 and 2025 boards use a DIFFERENT five-level ladder:
#
#   2023 / 2025:  Low, Medium, High, Very High, Extreme
#   2026:         Low, Mild,   Average, High,   Extreme
#
# The 2026 ladder above is verified exactly: 390 of 390 rows satisfy
# adjusted = raw - penalty(risk), zero exceptions.
#
# The older ladder CANNOT be verified and no penalty is guessed for it, because
# those seasons publish NO Adjusted Grade at all (0 of 750 rows), so there is
# nothing to solve the penalty against. Inventing one would put a fabricated
# number in the FV column of 750 rows with no way for any downstream layer to
# detect it. These labels are recognised so the risk value is STORED as data
# and so an unknown-vocabulary warning can tell a genuine format change apart
# from a known older format.
KNOWN_RISK_LABELS: frozenset[str] = frozenset(
    set(RISK_PENALTY) | {"medium", "very high"}
)


def canonical_risk(risk: str | None) -> str | None:
    """The risk label as a canonical token, or the stripped original when the
    vocabulary is unknown.

    BA's own pages are not case-consistent: the 2026-08-10 midseason drop
    published "HIgh" on 2 of 370 High rows. Storing the raw string made those
    two a SEPARATE CATEGORY to every downstream consumer, which is how a
    5-level ordinal silently becomes 6 and a per-risk aggregate gets a bucket
    of n=2. Canonicalising on the way in costs nothing and cannot be undone
    wrongly, because an unrecognised label is passed through untouched rather
    than guessed at.
    """
    if not risk:
        return None
    token = risk.strip()
    return token.title() if token.lower() in KNOWN_RISK_LABELS else token


def risk_penalty(risk: str | None) -> float | None:
    """Penalty in FV points, or None when it is not derivable for this label.

    None means "not checkable", which is a different fact from a wrong answer,
    and the adjusted-grade identity check distinguishes them on purpose.
    """
    if not risk:
        return None
    return RISK_PENALTY.get(risk.strip().lower())


# ---------------------------------------------------------------------------
# Tool vocabulary
# ---------------------------------------------------------------------------

# BA's Scouting Grades labels -> this repo's canonical tool keys
# (scrapers.HITTER_TOOL_KEYS / PITCHER_TOOL_KEYS).
#
# The two genuinely ambiguous labels are Split and Sweeper, and the tree has
# ALREADY DECIDED BOTH for another source: scrapers.JB_TOOL_KEY:1639 maps
# splitter onto the changeup slot and :1635 maps sweeper onto the slider slot,
# with the reasoning written at :1611-1613 ("variants of those pitch
# families"). Following that precedent is what makes a BA splitter grade
# comparable with a Just Baseball splitter grade inside the consensus, which
# is the entire purpose of a canonical vocabulary. The audit plan proposed
# minting a new `sw` key instead; that was written without sight of
# JB_TOOL_KEY and is not followed here. See the SPLIT/SWEEPER note in
# _map_tools for what is preserved so the decision stays reversible.
#
# KNOWN INCONSISTENCY, reported not silently inherited: tjstats writes a
# distinct `sp` key on 210 rows and `ct` on 279, so splitter currently lands in
# `ch` from Just Baseball and in `sp` from tjstats. `sp` is not in
# PITCHER_TOOL_KEYS, so consumers iterating the canonical tuple skip it. That
# is a pre-existing defect in the tool taxonomy, it is not created here, and it
# is worth an owner decision separately from this ingest.
# LABEL VOCABULARY ALSO DRIFTS BY SEASON. Measured across 2023-2026:
#   2023 writes Hitting / Fielding / Speed / Throw beside Hit / Field / Run / Arm,
#        and contains two genuine BA typos, "Comtrol" and "FIeld".
#   2025 adds the abbreviations CH and CUT.
#   2026 settles on Hit / Power / Run / Field / Arm and the pitch names.
# All variants map onto the same canonical keys. The typos are included
# deliberately: they are in the source data, a human wrote them, and dropping
# those rows' command grades to protect a tidy table would be the wrong trade.
BA_TOOL_KEY: dict[str, str] = {
    # hitters
    "hit": "hit",
    "hitting": "hit",
    "power": "game_pwr",       # BA publishes ONE power grade; FG splits raw/game
    "run": "speed",
    "speed": "speed",
    "field": "field",
    "fielding": "field",
    "fieid": "field",
    "arm": "throw",
    "throw": "throw",
    "throwing": "throw",
    # pitchers
    "fastball": "fb",
    "fb": "fb",
    "slider": "sl",
    "sweeper": "sl",           # sweeper = slider variant (JB precedent)
    "sl": "sl",
    "curveball": "cb",
    "curve": "cb",
    "cb": "cb",
    "changeup": "ch",
    "change": "ch",
    "ch": "ch",
    "split": "ch",             # splitter = changeup variant (JB precedent)
    "splitter": "ch",
    "cutter": "ct",
    "cut": "ct",
    "control": "cmd",
    "comtrol": "cmd",          # BA typo, present in the 2023 boards
    "command": "cmd",
    "cmd": "cmd",
}

# Labels that appear inside a Scouting Grades line but are NOT tools. Listed so
# they are skipped silently instead of being reported as unmapped every row.
_NON_TOOL_LABELS: frozenset[str] = frozenset({"ba grade", "adjusted grade", "risk"})

# THE LABELS THAT FOLD ONTO ANOTHER PITCH'S SLOT. Everything else in BA_TOOL_KEY
# is either the canonical name of its own slot or a spelling of it ("fb" for
# fastball, "comtrol" for control), so it is the slot's rightful owner.
#
# These three are different: BA grades Slider and Sweeper as DISTINCT pitches and
# both land on `sl`, and Changeup and Split both land on `ch`. When a pitcher is
# graded for both, one of them has to yield the canonical slot, and WHICH one
# must not depend on the order BA happened to print them in. See _slot_claim.
BA_FOLDED_LABELS: frozenset[str] = frozenset({"sweeper", "split", "splitter"})


def _slot_claim(label: str, grade: float) -> tuple[int, str, float]:
    """Sort key deciding which BA label KEEPS a canonical tool slot. Lowest wins.

    Rank 0 is the pitch that legitimately owns the slot (a real slider owns `sl`,
    a real changeup owns `ch`); rank 1 is a variant folded onto it. The label
    string and then the negated grade break the remaining ties, so the winner is
    a pure function of the SET of (label, grade) pairs on the row and never of
    their order in the file.

    That order-independence is the actual fix. Measured on this drop, all 35
    collisions already put the native pitch in the slot, but only because BA
    printed Slider before Sweeper on all 35 rows. Under the previous first-wins
    rule a board that printed them the other way round would have silently
    evicted the real slider, and nothing downstream could have detected it.
    """
    return (1 if label in BA_FOLDED_LABELS else 0, label, -grade)

# BA's single `Power` maps onto game_pwr rather than raw_pwr. Recorded because
# it is a real modelling choice and not an obvious one: BA's power grade is a
# projection of production, which is what game power means here, whereas
# raw_pwr is the physical ceiling. A future re-read of BA power as raw_pwr
# would change what tool_hit-style features see, so it needs its own gate.
BA_POWER_TARGET = "game_pwr"


# ---------------------------------------------------------------------------
# Filename
# ---------------------------------------------------------------------------

# ba__{season}__{board}__{team}[__{YYYY-MM-DD}].md
# Double underscores so a team slug containing a hyphen ("blue-jays",
# "red-sox", "white-sox", "d-backs") can never be mistaken for a boundary.
_FILENAME_RE = re.compile(
    r"^ba__(?P<season>\d{4})__(?P<board>[a-z]+)__(?P<team>[a-z0-9-]+?)"
    r"(?:__(?P<pubdate>\d{4}-\d{2}-\d{2}))?\.md$"
)


def _org_lookup() -> tuple[dict[str, str], dict[str, str]]:
    """(team_slug -> org code, org code -> nickname).

    Derived from build_site.ORG_NAMES so there is exactly one club table in
    the tree. A second hardcoded copy here would drift the first time a club
    renames, which has already happened once (Athletics dropped "Oakland"
    mid-2024 and spotrac.py:266-268 carries the scar).
    """
    from build_site import ORG_NAMES
    slug_to_org = {}
    for code, nickname in ORG_NAMES.items():
        slug = nickname.lower().replace(" ", "-")
        slug_to_org[slug] = code
    # BA and casual usage both shorten Diamondbacks. Accept it rather than
    # bounce a correctly-named file.
    if "diamondbacks" in slug_to_org:
        slug_to_org.setdefault("d-backs", slug_to_org["diamondbacks"])
        slug_to_org.setdefault("dbacks", slug_to_org["diamondbacks"])
    return slug_to_org, dict(ORG_NAMES)


def _club_to_org(club: str | None) -> str | None:
    """A club line printed on a GLOBAL board -> this repo's org code.

    BA prints the full club ("Milwaukee Brewers", "Boston Red Sox") where
    ORG_NAMES stores the nickname ("Brewers", "Red Sox"), and prints bare
    "Athletics" for the club that dropped its city. Matching on the nickname as
    a whole-word suffix covers all three shapes and cannot confuse Red Sox with
    White Sox, because the nickname carries the qualifier. Measured on the 2026
    midseason Top 100: 100 of 100 rows map, across all 30 clubs.

    Returns None rather than guessing. An unmapped club is reported by the
    caller, because a new spelling is a format change and a silently org-less
    pro row is worse than useless on the board.
    """
    if not club:
        return None
    text = fix_mojibake(club).strip()
    _, org_names = _org_lookup()
    for code, nickname in org_names.items():
        if text == nickname or text.endswith(" " + nickname):
            return code
    return None


# GLOBAL (non-team) boards, keyed by the slug that sits in the team position of
# the filename. A global board has NO org of its own: every row carries its own
# club, which BA prints on these lists, so `org` is None and the per-row value is
# authoritative.
#
# THE LABEL IS THE LOAD-BEARING PART. consensus._ORG_LIST_LABEL_RE is
# r"\bTop\s+(?:10|20|25|30)\b\s*$" and it is what stops a team Top 30 from
# feeding implied_fv_from_rank, where a number-one ORG prospect would otherwise
# become a rank-implied FV 70. A GLOBAL list is the case that guard exists to let
# through: on a Top 100, rank 1 really is the best prospect in baseball, so
# rank-implied FV is meaningful. "Top 100" does not match that regex (the \b
# after 10 fails against the second 0), so the distinction falls out correctly
# from the label alone. Do not "fix" the regex to catch 100.
GLOBAL_BOARDS: dict[str, str] = {
    "top-100": "Top 100",
    "top100": "Top 100",
    "top-250": "Top 250",
    "top250": "Top 250",
}


def parse_filename(name: str) -> dict | None:
    """Parse a drop filename into its board identity, or None if malformed."""
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    board = m.group("board")
    team_slug = m.group("team")

    # A DRAFT board. The first field is the draft CLASS YEAR, not a list season,
    # and the third is a scope rather than a club. Kept as its own branch rather
    # than folded into the org path, because every field downstream means
    # something different: the target table, the key namespace, the label shape
    # and the date convention.
    if board == DRAFT_BOARD:
        scope = DRAFT_SCOPES.get(team_slug)
        if scope is None:
            return None
        scope_label, extent, pool = scope
        return {
            "season": int(m.group("season")),
            "class_year": int(m.group("season")),
            "board": board,
            "team_slug": team_slug,
            "pubdate": m.group("pubdate"),
            "org": None,
            "team_name": None,
            "scope": scope_label,
            "scope_extent": extent,
            "pool": pool,
            "rank_is_global": scope_rank_is_global(pool),
            "is_global": False,
            "is_draft": True,
        }

    if board not in BOARDS:
        return None
    common = {
        "season": int(m.group("season")),
        "board": board,
        "team_slug": team_slug,
        "pubdate": m.group("pubdate"),
    }
    scope = GLOBAL_BOARDS.get(team_slug)
    if scope is not None:
        return {**common, "org": None, "team_name": None,
                "scope": scope, "is_global": True}
    slug_to_org, org_names = _org_lookup()
    org = slug_to_org.get(team_slug)
    if org is None:
        return None
    return {**common, "org": org, "team_name": org_names[org],
            "scope": None, "is_global": False}


# ---------------------------------------------------------------------------
# Content dating. Boards are dated by CONTENT, never by label.
# ---------------------------------------------------------------------------

# THE HAZARD THIS EXISTS FOR, caught on a real file. The first board pasted
# during this program was named for "Preseason 2026" and carried mid-season
# content: 2 of 30 rows said "through mid-May", 4 said "this year", 12
# referenced 2026 in-season. The owner spotted it independently and replaced
# the file. The Blue Jays board is genuinely preseason (0 and 0).
#
# WHY THIS IS NOT A MONTH SCANNER. A naive "find a month name, find a year"
# rule refuses the GOOD board: the Blue Jays lead row says Yesavage "made his
# major league debut on Sept. 15" (a 2025 fact) two paragraphs from "Yesavage
# enters 2026" (a forward-looking one), and pairing those yields a phantom
# 2026-09-15. The discriminator that actually separated the two files was
# in-season PHRASING, so that is what is matched here.
_IN_SEASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bthrough (?:mid-|early |late )?(?:January|February|March|April|May|June|July|"
     r"August|September|October|Jan\.|Feb\.|Mar\.|Apr\.|Jun\.|Jul\.|Aug\.|Sept\.|Oct\.)",
     "through-a-month"),
    (r"\bthis (?:year|season)\b", "this-year"),
    (r"\bso far this (?:year|season)\b", "so-far-this-season"),
    (r"\bentering play\b", "entering-play"),
    (r"\bthus far\b", "thus-far"),
    (r"\bhas (?:hit|posted|struck out|thrown|pitched)[^.]{0,60}\bthis (?:year|season)\b",
     "production-this-season"),
)

_EXPLICIT_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan\.|Feb\.|Mar\.|Apr\.|Jun\.|Jul\.|Aug\.|Sept\.|Sep\.|Oct\.|Nov\.|Dec\.)"
    r"\s+(\d{1,2})(?:\\?\.)?,?\s+(\d{4})\b"
)

_MONTH_NUM = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def scan_content_dates(text: str, season: int) -> dict:
    """Report every in-content signal about when a board was actually written.

    Returns the evidence; it does not decide. The caller pairs this with the
    board label, because the failure mode is a MISMATCH between the two and
    neither one alone can show it.
    """
    in_season: list[dict] = []
    for pattern, tag in _IN_SEASON_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = text[line_start:line_end if line_end != -1 else len(text)]
            in_season.append({
                "tag": tag,
                "match": m.group(0),
                "excerpt": line.strip()[:200],
            })

    explicit: list[dict] = []
    for m in _EXPLICIT_DATE_RE.finditer(text):
        mon = _MONTH_NUM.get(m.group(1).lower().rstrip("."))
        if not mon:
            continue
        try:
            d = date(int(m.group(3)), mon, int(m.group(2)))
        except ValueError:
            continue
        explicit.append({"iso": d.isoformat(), "match": m.group(0)})

    season_refs = sorted({int(y) for y in re.findall(r"\b(20\d{2})\b", text)})

    return {
        "in_season_markers": in_season,
        "in_season_count": len(in_season),
        "explicit_dates": explicit,
        "latest_explicit_date": max((e["iso"] for e in explicit), default=None),
        "years_referenced": season_refs,
        "max_year_referenced": max(season_refs) if season_refs else None,
        "season_labelled": season,
    }


def resolve_snapshot_date(meta: dict, evidence: dict) -> tuple[str | None, list[str]]:
    """(snapshot_date, refusals). A non-empty refusal list means DO NOT INGEST.

    snapshot_date is what the whole as-of chain keys on: consensus picks the
    latest point strictly before a player's decision date and the eFV training
    matrix inherits that, so a wrong date does not merely mislabel a row, it
    can move the row across a decision boundary. There is a recorded failure of
    exactly this kind in this repo (the MLB Pipeline org backfill hardcoded
    {y}-01-22 for every season, which froze 829 prospects on January grades
    until 2026-07-24), which is why a season-level convention is a FALLBACK
    that gets RECORDED as a convention, never a measurement.
    """
    refusals: list[str] = []
    warnings: list[str] = []
    season = meta["season"]
    board = meta["board"]

    # A DRAFT BOARD HAS NO DEFENSIBLE CONVENTION DATE, so it does not get one.
    #
    # The org conventions below work because a preseason list is published in a
    # narrow window every February. A draft class is ranked continuously from
    # roughly two years out to the draft itself, and the five real boards span
    # 2026-05-20 to 2026-07-31 for two different classes. Any fixed date would be
    # wrong by months, and snapshot_date is what the as-of chain keys on, which
    # is precisely the MLB Pipeline {y}-01-22 failure that froze 829 prospects on
    # January grades. Refusing costs the operator one filename edit.
    if board == DRAFT_BOARD:
        if not meta.get("pubdate"):
            refusals.append(
                "a draft board filename must carry its publication date "
                "(ba__{class_year}__draft__{scope}__YYYY-MM-DD.md). There is no "
                "convention date for a draft board: a class is ranked "
                "continuously, so any fixed date would be wrong by months and "
                "snapshot_date is what the whole as-of chain keys on.")
            return None, refusals, warnings
        latest = evidence["latest_explicit_date"]
        if latest and latest > meta["pubdate"]:
            refusals.append(
                f"snapshot_date {meta['pubdate']} (filename) is EARLIER than an "
                f"explicit date in the board's own text ({latest}).")
        return meta["pubdate"], refusals, warnings

    # Convention fallbacks. Recorded as conventions in the artifact.
    convention = {
        "preseason": f"{season}-02-15",
        "midseason": f"{season}-07-01",
        "offseason": f"{season - 1}-11-15",
    }[board]
    snapshot_date = meta.get("pubdate") or convention
    basis = "filename" if meta.get("pubdate") else "convention"

    # IN-SEASON PROSE IS A WARNING, NOT A REFUSAL. Demoting it is a correction
    # to this module, not a concession, and the measurement is worth recording.
    #
    # It shipped as a refusal on the strength of ONE known-bad file: a board
    # labelled Preseason 2026 that carried mid-season content. Run against 52
    # genuinely-preseason org boards it refused 39 of them, and every hit that
    # could be read by hand was legitimate prose:
    #
    #   "Through April and May, he produced an OPS of .621"  2023 board, 2022 season
    #   "in the Dominican Summer League later this year"     forward-looking
    #   "one of the top pitchers available this year"        forward-looking, draft class
    #   "at an astounding 78% clip through August"           the completed season
    #
    # Describing the season just finished and projecting the season about to
    # start are the two things a preseason board is FOR, so phrasing alone
    # cannot separate them from a mis-dated file. Requiring the board's own
    # season year near the marker does not fix it either (tested: 9 of 52 still
    # flag, all false). Density does not separate it: the known-bad file carried
    # 6 markers and a genuine 2023 board carries 5.
    #
    # A guard that blocks three quarters of good data to catch a hazard it
    # cannot reliably identify is worse than no guard, because it trains the
    # operator to bypass it. So this reports and does not block. The unambiguous
    # half of the check, the explicit-date contradiction below, still refuses:
    # it had zero false positives across all 52 boards.
    if board == "preseason" and evidence["in_season_count"] > 0:
        tags = sorted({m["tag"] for m in evidence["in_season_markers"]})
        warnings.append(
            f"{evidence['in_season_count']} in-season prose marker(s) "
            f"({', '.join(tags)}) on a board labelled preseason. Usually this is "
            f"the board describing the season just finished, which is normal. "
            f"Worth a look only if several rows read as written mid-season."
        )

    # No snapshot_date may precede a date the content itself states.
    latest = evidence["latest_explicit_date"]
    if latest and latest > snapshot_date:
        refusals.append(
            f"snapshot_date {snapshot_date} ({basis}) is EARLIER than an explicit "
            f"date in the board's own text ({latest}). Add the real publication "
            f"date to the filename."
        )

    # A LATER YEAR IS NOT EVIDENCE OF ANYTHING, and refusing on it cost 17 of
    # the 52 boards. Scouting prose names future years constantly: Rule 5
    # eligibility, free agency, club control, "should reach Double-A in 2027".
    # One board legitimately mentions 2034. The rule is removed rather than
    # softened, because there is no version of it that is right.
    return snapshot_date, refusals, warnings


# ---------------------------------------------------------------------------
# Board parsing
# ---------------------------------------------------------------------------

# Markdown escapes the rank dot: "1\. Trey Yesavage". Anchored at line start,
# which is what keeps "at pick No. 20\." inside a Track Record paragraph from
# matching. The name is captured loosely and cleaned afterwards.
_RANK_LINE_RE = re.compile(r"^(\d{1,3})\\?\.\s+(\S.*?)\s*$")
_HEADER_COUNT_RE = re.compile(r"^(\d{1,3})\s+players\s*$", re.IGNORECASE)
# The risk label can be TWO WORDS. "Very High" is real BA vocabulary on the
# 2023 and 2025 boards, and a single-word capture silently truncated it to
# "Very", which then failed the known-vocabulary check on 11 of 52 boards.
# Anchored to end of line so it cannot run past the field.
_GRADE_RISK_RE = re.compile(
    r"^BA Grade(?:\s*/\s*Risk)?:\s*(\d{2})\s*/\s*([A-Za-z][A-Za-z ]*?)\s*\\?\.?\s*$",
    re.MULTILINE)
_ADJUSTED_RE = re.compile(r"Adjusted Grade:\s*(\d{2})")
_PREV_RANK_RE = re.compile(r"Previous Rank:\s*(\d{1,3})")
_AGE_RE = re.compile(r"^Age:\s*(\d{1,2})\s*$", re.MULTILINE)
_PHYS_RE = re.compile(
    r"Ht:\s*([0-9]'[0-9]{1,2}\")\s*\|\s*Wt:\s*(\d{2,3})\s*\|\s*B-T:\s*([A-Z])-([A-Z])")
# THE COLON IS OPTIONAL, and requiring it lost 11 of 13 2026 boards. Measured:
# only blue-jays and yankees write "Scouting Grades:"; the other eleven write
# "Scouting Grades Hit: 45 | Power: 65 | ...". Same field, same season, same
# publisher. This is why the README says paste it raw.
_SCOUT_GRADES_RE = re.compile(r"Scouting Grades:?\s*(.+?)\s*$", re.MULTILINE)
_PROSE_RE = {
    "track_record": re.compile(r"^Track Record:\s*(.+?)\s*$", re.MULTILINE),
    "report": re.compile(r"^Scouting Report:\s*(.+?)\s*$", re.MULTILINE),
    "future": re.compile(r"^The Future:\s*(.+?)\s*$", re.MULTILINE),
}
# "RHP", "SS", "OF / C", "1B / 3B". The position line is the first short,
# all-caps-ish line after the rank line.
_POSITION_RE = re.compile(r"^([A-Z0-9]{1,3}(?:\s*/\s*[A-Z0-9]{1,3})*)\s*$")


class BoardFormatError(ValueError):
    """The file is not a board this parser will ingest. Never partial."""


def _clean_name(raw: str) -> str:
    """BA names are clean UTF-8 on both probed boards, but the same defences
    the FanGraphs path needs are cheap and this is an untrusted paste."""
    return strip_name_markers(fix_mojibake(raw)).strip()


# A trailing personal suffix, which is a legitimate reason for a player's name
# to end in a period. Anchored to the end so it cannot match mid-sentence, and
# kept to the forms BA actually prints.
_NAME_SUFFIX_RE = re.compile(r"\b(?:Jr|Sr|II|III|IV|V)\.$", re.IGNORECASE)


def _split_blocks(text: str) -> list[tuple[int, str, str]]:
    """[(rank, raw_name, block_text)] in file order."""
    lines = text.splitlines()
    anchors: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = _RANK_LINE_RE.match(line)
        if not m:
            continue
        name = m.group(2)
        # A rank line's name is a person, not a sentence. Prose lines that
        # begin with a number are excluded by length and by punctuation.
        #
        # EXCEPT A PERSONAL SUFFIX IS A LEGITIMATE TRAILING PERIOD. The blanket
        # punctuation rule dropped "18. Robert Perez Jr." from the 2023 Mariners
        # board, which then failed its own 30-vs-29 count check and refused the
        # whole board. Loud, but wrong: the player is real and the paste was
        # fine. Every BA board carries several "Jr." names, so this is a
        # recurring silent-drop-turned-refusal, not a one-off.
        #
        # The exemption is deliberately narrow - a closed set of suffixes and
        # a length bound - because the guard it relaxes is what keeps a prose
        # sentence beginning with a number from being read as a player. A
        # sentence does not end in "Jr." in under 60 characters.
        if len(name) > 60:
            continue
        if name.endswith((",", ":", ";")):
            continue
        if name.endswith(".") and not _NAME_SUFFIX_RE.search(name):
            continue
        anchors.append((i, int(m.group(1)), name))
    out = []
    for idx, (line_no, rank, name) in enumerate(anchors):
        end = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(lines)
        # Drop a trailing "Headshot of X" line: it belongs to the NEXT player.
        block_lines = lines[line_no + 1:end]
        while block_lines and block_lines[-1].strip().startswith("Headshot of "):
            block_lines.pop()
        out.append((rank, name, "\n".join(block_lines)))
    return out


def _map_tools(raw_grades: str) -> tuple[dict, dict, list[dict], dict]:
    """(canonical tools, raw BA labels, collisions, displaced variants).

    SPLIT / SWEEPER: both fold onto an existing canonical slot per the Just
    Baseball precedent, and the untouched BA label is ALWAYS kept in
    _extras.ba_tools_raw. That is what keeps the decision reversible: if the
    owner later rules that a splitter deserves its own key, every ingested row
    can be re-derived from the raw block without re-pasting a single board.
    Discarding the label and keeping only the folded value is the version that
    cannot be undone, so it is not done.

    WHEN BOTH PITCHES ARE GRADED, NOTHING IS DROPPED (2026-08-09). BA lists
    Slider and Sweeper as distinct pitches and grades both, and the same for
    Changeup and Split. Two things are fixed here:

      1. SLOT OWNERSHIP IS NOW ORDER-INDEPENDENT. It used to be first-wins in
         file order. On the 2026 midseason drop that happened to be right on 35
         of 35 rows, because BA printed the native pitch first on every one of
         them, but it was right by luck: a board that printed Sweeper first would
         have put the sweeper's grade in `sl` and evicted the real slider, board
         wide and undetectably. _slot_claim decides it from the labels instead.

      2. THE DISPLACED GRADE IS RETURNED, not discarded. It rides
         _extras.ba_tool_variants keyed by the slot it was displaced FROM, which
         is strictly more than ba_tools_raw carries: that dict is keyed by BA
         label alone and does not record which canonical slot the label lost.

    NO NEW TOP-LEVEL tools_json SLOT is minted for the variant, deliberately.
    Every consumer that walks a tools blob numerically (consensus.py:1017,
    draft_export.py:715, overseas_export.py:765, mock_draft.py:152) skips exactly
    the key `_extras` and treats everything else as a grade, and this module's own
    role inference at parse_board tests `set(tools) <= set(PITCHER_TOOL_KEYS)`, so
    an `sw` key would break role inference for every 2023 pitcher and enter tool
    aggregation as if it were a sixth pitch. `_extras` is the channel that already
    carries ba_raw_grade and ba_tools_raw past all of them.

    Collisions are still surfaced, never silently resolved.
    """
    tools: dict[str, float] = {}
    raw: dict[str, float] = {}
    collisions: list[dict] = []
    variants: dict[str, dict[str, float]] = {}
    by_slot: dict[str, list[tuple[str, float]]] = {}
    # SEPARATOR VARIES BY SEASON and splitting on one of them silently drops a
    # whole season's tools. 2025 and 2026 use " | "; 2023 uses a markdown-escaped
    # period, "Hitting: 60\. Power: 60\. Speed: 55\.". Rather than split, pull
    # the (label, grade) pairs out directly, which is separator-agnostic and
    # therefore does not need updating the next time BA changes punctuation.
    # Safe against prose because this only ever runs on a Scouting Grades line.
    for label, value in re.findall(r"([A-Za-z][A-Za-z ]*?)\s*:\s*(\d{2})\b", raw_grades):
        label = label.strip().lower()
        if label in _NON_TOOL_LABELS:
            continue
        grade = float(value)
        raw[label] = grade
        key = BA_TOOL_KEY.get(label)
        if key is None:
            collisions.append({"kind": "unmapped_label", "label": label, "grade": grade})
            continue
        by_slot.setdefault(key, []).append((label, grade))

    # Resolve every slot from the collected SET, so the outcome cannot depend on
    # the order the pairs were read in. sorted() over slots and over the losing
    # entries keeps the emitted issue list deterministic too.
    for key in sorted(by_slot):
        entries = by_slot[key]
        winner_label, winner_grade = min(
            entries, key=lambda e: _slot_claim(e[0], e[1]))
        tools[key] = winner_grade
        for label, grade in sorted(entries):
            if label == winner_label:
                continue
            variants.setdefault(key, {})[label] = grade
            if grade == winner_grade:
                # Same number under two names loses no information, so it is
                # kept but is not reported as a collision.
                continue
            collisions.append({
                "kind": "slot_collision", "label": label, "canonical": key,
                "kept": winner_grade, "kept_label": winner_label,
                "dropped": grade,
                "preserved_at": f"_extras.ba_tool_variants.{key}.{label}",
            })
    return tools, raw, collisions, variants


def parse_board(text: str, meta: dict) -> dict:
    """Parse one pasted board. Raises BoardFormatError rather than ingest a
    partial board: a board missing rows is a board whose ranks mean something
    different, and rank is the quantity this ingest exists to capture."""
    declared = None
    for line in text.splitlines()[:20]:
        m = _HEADER_COUNT_RE.match(line.strip())
        if m:
            declared = int(m.group(1))
            break

    blocks = _split_blocks(text)
    if not blocks:
        raise BoardFormatError(
            "no rank lines found. The anchor is a line starting with a number "
            "and an escaped dot, e.g. '1\\. Trey Yesavage'. Was the file tidied "
            "before pasting? Paste it raw.")

    ranks = [b[0] for b in blocks]
    dupes = sorted({r for r in ranks if ranks.count(r) > 1})
    # A DUPLICATE RANK IS TWO DIFFERENT FAILURES AND THEY NEED DIFFERENT ANSWERS.
    #
    # The hazard this guard was built for is ONE PLAYER reaching the board
    # TWICE, which is the Jack Natili incident (ranks 155 and 320, surplus double
    # counted at $16.7M plus $3.8M). That still refuses, unconditionally.
    #
    # What it also caught, and should not have, is BA printing one rank number on
    # TWO DIFFERENT PLAYERS. Real case, the 2025 Braves board: 31 blocks, header
    # "31 players", ranks 1..30 with 26 on both Trent Harris and Carter Holton.
    # Two distinct humans, no double count, a publisher numbering typo. Refusing
    # it threw away 31 real players over a label.
    #
    # We do NOT renumber. Which of the two is "really" 27 is not recoverable from
    # the file, and inventing an order would be fabricating the one field the
    # board exists to publish. Both keep the rank BA printed, and the defect is
    # named in the artifact so a reader can see it.
    duplicate_rank_note = None
    if dupes:
        by_rank: dict[int, set[str]] = {}
        for rank, name, _ in blocks:
            by_rank.setdefault(rank, set()).add(normalize_key(name))
        same_player = sorted(r for r in dupes if len(by_rank[r]) == 1)
        if same_player:
            raise BoardFormatError(
                f"rank(s) {same_player} carry the SAME player twice. That is how "
                f"a player reaches the board twice and has his surplus double "
                f"counted; fix the paste.")
        _detail = []
        for r in dupes:
            names = [nm for rk, nm, _ in blocks if rk == r]
            _detail.append(f"{r}: {', '.join(names)}")
        duplicate_rank_note = (
            f"duplicate_rank_distinct_players: {'; '.join(_detail)}. Both are "
            f"kept at the rank BA printed; no renumbering is inferred.")
    if ranks != sorted(ranks):
        raise BoardFormatError(f"ranks are not in ascending order: {ranks[:15]}")
    if ranks[0] != 1:
        raise BoardFormatError(f"board does not start at rank 1 (starts at {ranks[0]})")
    # A HEADER CLAIMING ZERO IS AN UNPOPULATED COUNTER, NOT A DISAGREEMENT.
    #
    # Real case, the 2026 midseason Padres board: line 1 reads "0 players" where
    # all 29 sibling boards read "30 players", and the file below it carries 30
    # contiguous rank lines with full grades. BA's page renders that counter from
    # a script, so a paste taken before it populated captures the zero. There is
    # no reading of "0" under which the 30 parsed rows are a partial board: zero
    # is not a count that 30 rows could be a truncation of.
    #
    # That is categorically different from "claims 25 but 30 parsed", where the
    # two numbers are both real and disagree, and one of them is wrong about the
    # board. Those still refuse, unchanged.
    #
    # The carve-out is deliberately narrow. It requires BOTH the claim to be
    # exactly 0 AND the parsed ranks to be contiguous 1..N, because contiguity is
    # the independent evidence that nothing is missing: duplicates, gaps, a wrong
    # start and non-ascending order are all rejected above, so reaching here with
    # ranks[-1] == len(ranks) means the board is complete on its own terms. The
    # source file is NOT edited to fix this. The README rule is "paste it raw",
    # and tidying the .md would hide the artifact from the next drop.
    header_count_unpopulated = False
    # Contiguity is a statement about the RANK SLOTS, so it is measured on the
    # distinct ranks. A board carrying 1..30 with one number printed twice is
    # still complete on its own terms; it just has 31 players in 30 slots.
    _slots = sorted(set(ranks))
    contiguous = _slots == list(range(1, len(_slots) + 1))
    if declared == 0 and contiguous:
        header_count_unpopulated = True
    elif declared is not None and declared != len(blocks):
        raise BoardFormatError(
            f"board header claims {declared} players but {len(blocks)} rank "
            f"lines parsed. Refusing a partial board.")

    # A GAP IS NOT A PARTIAL PASTE, and the difference is worth getting right.
    #
    # Real case: the 2023 Twins board runs 1..17, 19..30. There is no rank 18
    # and no rank 31 anywhere in the file, in any format, and BA's own header
    # says "29 players" where every other board says 30. So BA published 29
    # players across a Top 30, with slot 18 vacated, almost certainly an entry
    # deleted from their CMS.
    #
    # The published ranks are kept VERBATIM. Renumbering 19..30 down to 18..29
    # would close the gap, but it would also invent ranks BA never published:
    # that player was BA's 19th, not its 18th. Rank is precisely the quantity
    # this ingest exists to capture (it is the only thing that orders the 30
    # players BA sorts onto four or five distinct grades), so fabricating it is
    # the worst available option.
    #
    # The board is labelled by its published EXTENT rather than its row count,
    # so a Top 30 with one hole is still a Top 30 and still trips the org-list
    # guard. Labelling it "Top 29" would leave the guard unmatched and drop its
    # ranks into implied_fv_from_rank, which is the Bryan Sanchez failure.
    max_rank = ranks[-1]
    missing = sorted(set(range(1, max_rank + 1)) - set(ranks))
    # SELF-ADDED BAR, disclosed: refuse above 10 percent missing. One hole in
    # thirty (3.3 percent) is a publishing quirk; a third of the board absent is
    # a truncated paste, and the two need different answers. No board in the
    # 2023-2026 corpus exceeds 3.3 percent.
    if missing and len(missing) > 0.10 * max_rank:
        raise BoardFormatError(
            f"{len(missing)} of {max_rank} ranks are missing ({missing[:12]}). "
            f"That is too many to be a publishing gap; it reads as a truncated "
            f"paste. Re-copy the board.")

    rows: list[dict] = []
    for rank, raw_name, block in blocks:
        name = _clean_name(raw_name)
        if not name:
            raise BoardFormatError(f"rank {rank} has an empty name")

        # THE CLUB LINE SHADOWS THE POSITION LINE ON A GLOBAL BOARD, and the
        # previous rule lost the position on 75 of 100 rows (measured on the
        # 2026 midseason Top 100). An ORG board opens a block with the position:
        #
        #     1\. Trey Yesavage / RHP / Ht: ...
        #
        # A GLOBAL board carries the player's club first, because that is how a
        # non-team list says who he belongs to:
        #
        #     1\. Jesus Made / Milwaukee Brewers / SS / Ht: ...
        #
        # The old loop read the FIRST non-blank line and broke unconditionally,
        # so "Milwaukee Brewers" failed _POSITION_RE and position stayed None.
        # It looked survivable only because the tool-based role inference below
        # then rebuilt RHP/LHP for the 25 pitchers from their pitch grades. The
        # 75 hitters simply lost SS / OF / C / 3B outright.
        #
        # That is not cosmetic, and it breaks two things at once:
        #   * grade_normalization splits paired cells by role through
        #     _is_pitcher(position), and a null position reads as HITTER. That is
        #     the exact mechanism written up for the 2023 boards below, where a
        #     43.4% role error pooled an offset ACROSS ERAS and cost 5.0 FV.
        #   * screen_identity's side-of-ball check compares BA's position against
        #     the stored one, and side_of_ball(None) is None, so the check
        #     silently no-ops. On 75 of 100 rows the guard that caught the
        #     Garrett Wright merge was not running at all.
        #
        # So scan the block's leading lines for the position instead of reading
        # exactly one, and stop at the physical line, which is present on every
        # board in the corpus and always sits after the position. Bounding the
        # scan is what keeps a short all-caps token inside prose from being read
        # as a position. On an org board the first line still matches on the
        # first pass, so that path is unchanged.
        position = None
        club_line = None
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("Ht:") or s.startswith("Age:"):
                break
            pm = _POSITION_RE.match(s)
            if pm:
                position = pm.group(1)
                break
            # A non-position line ahead of the position is the club name, which
            # only a global board prints. Kept as the per-row org: on a global
            # list the club is a per-row fact and meta["org"] is None, so
            # without this every row would be ingested org-less.
            if club_line is None:
                club_line = s
        row_org = _club_to_org(club_line) if club_line else None


        gr = _GRADE_RISK_RE.search(block)
        adj = _ADJUSTED_RE.search(block)
        prev = _PREV_RANK_RE.search(block)
        age = _AGE_RE.search(block)
        phys = _PHYS_RE.search(block)
        grades = _SCOUT_GRADES_RE.search(block)

        raw_grade = float(gr.group(1)) if gr else None
        risk = gr.group(2) if gr else None
        adjusted = float(adj.group(1)) if adj else None

        tools, ba_tools_raw, tool_issues, tool_variants = ({}, {}, [], {})
        if grades:
            tools, ba_tools_raw, tool_issues, tool_variants = _map_tools(
                grades.group(1))

        # THE 2023 BOARDS CARRY NO POSITION LINE AT ALL (22 of 389 rows have
        # one, against 390 of 390 in every later season), and that is not
        # cosmetic. grade_normalization splits its paired cells by ROLE through
        # _is_pitcher(position), and a null position reads as HITTER. Measured
        # consequence before this fix: a 43.4 percent role error, which left the
        # (baseballamerica, pitcher, 2023) cell with ZERO cycle pairs, tripped
        # the _MIN_N fallback at grade_normalization.py:121, and pooled an
        # offset ACROSS ERAS out of 2024+2025+2026. That gave +1.920 against a
        # true within-2023 pitcher offset of +6.955, a 5.0 FV error, and a
        # cross-year pooled cell is leak D1 of the audit plan reproduced on a
        # brand new source.
        #
        # Role is recoverable EXACTLY from data already parsed. BA publishes
        # tool sets by role and the two vocabularies are disjoint: measured on
        # the 2023 corpus, 222 rows carry hitter-only tools, 162 carry
        # pitcher-only tools, and ZERO are mixed. Handedness comes from the B-T
        # field, populated on 389 of 389.
        #
        # Only the PITCHER side is emitted, because RHP and LHP are exactly what
        # the data says. A hitter's fielding position is NOT inferable from a
        # tool set, so it stays null rather than invented, which is also the
        # correct role split since _is_pitcher(None) is False.
        role_inferred = False
        if position is None and tools:
            keys = set(tools)
            if keys and keys <= set(_PITCHER_TOOL_KEYS):
                throws = phys.group(4) if phys else None
                position = {"R": "RHP", "L": "LHP"}.get(throws or "", "P")
                role_inferred = True
            elif keys and keys <= set(_HITTER_TOOL_KEYS):
                role_inferred = True   # hitter, position deliberately left null

        # Recompute rather than trust. See the module docstring.
        # Three states, and collapsing them loses the distinction that matters.
        #   True  = published an Adjusted Grade and it satisfies the identity
        #   False = published one and it does NOT (a format change, investigate)
        #   None  = nothing to check, because this season publishes no Adjusted
        #           Grade at all (2023-2025) or the risk label has no derivable
        #           penalty. NOT a failure.
        # Treating None as False reported 927 phantom failures on the 2023-2025
        # boards, which publish raw grade and risk but no adjusted grade.
        expected_adj = None
        identity_ok = None
        pen = risk_penalty(risk)
        if raw_grade is not None and pen is not None:
            expected_adj = raw_grade - pen
            if adjusted is not None:
                identity_ok = (adjusted == expected_adj)

        prose = {}
        for field, rx in _PROSE_RE.items():
            pm = rx.search(block)
            if pm:
                prose[field] = pm.group(1).strip()[:_REPORT_MAX_CHARS]

        basis = fv_basis(meta["season"])
        fv = adjusted if basis == "adjusted" else raw_grade

        rows.append({
            "rank": rank,
            "player_name": name,
            "fv_basis": basis,
            # "OF / C" -> OF. A multi-position line lists the primary first on
            # both probed boards; the full string is preserved beside it so a
            # later positional-fit consumer is not stuck with the truncation.
            "position": position.split("/")[0].strip() if position else None,
            "position_full": position,
            "role_inferred": role_inferred,
            # Per-row club, GLOBAL boards only. None on an org board, where the
            # club is a board-level fact carried in meta["org"].
            "club_line": club_line,
            "row_org": row_org,
            "ba_raw_grade": raw_grade,
            "ba_risk": canonical_risk(risk),
            # Era-dependent, see ADJUSTED_GRADE_FIRST_SEASON. 2026+ takes the
            # Adjusted Grade; 2025 and earlier take the BA Grade, which was the
            # only grade BA published in that era.
            "fv": fv,
            "adjusted_expected": expected_adj,
            "adjusted_identity_ok": identity_ok,
            "previous_rank": int(prev.group(1)) if prev else None,
            "age": int(age.group(1)) if age else None,
            "height": phys.group(1) if phys else None,
            "weight": int(phys.group(2)) if phys else None,
            "bats": phys.group(3) if phys else None,
            "throws": phys.group(4) if phys else None,
            "tools": tools,
            "ba_tools_raw": ba_tools_raw,
            # {canonical slot: {displaced BA label: grade}}. Populated only when
            # BA graded two pitches that fold onto one slot.
            "tool_variants": tool_variants,
            "tool_issues": tool_issues,
            **prose,
        })

    n = len(rows)
    # Label by published EXTENT, not row count, so a Top 30 with a hole in it
    # still reads as a Top 30 to consensus._ORG_LIST_LABEL_RE.
    #
    # A DUPLICATE RANK MUST NOT INFLATE THE LABEL. The 2025 Braves board is 31
    # players in 30 rank slots; taking the row count would label it "Top 31",
    # which _ORG_LIST_LABEL_RE does NOT match, so the board would lose org-list
    # protection and its ranks would feed implied_fv_from_rank - the Bryan
    # Sanchez failure, reached by a route nobody would look for. The extent is
    # the highest rank BA printed, and that is 30.
    board_size = max_rank if (max_rank >= n or duplicate_rank_note) else n
    return {
        "meta": {
            **meta,
            "n_players": n,
            "declared_players": declared,
            "board_size": board_size,
            "missing_ranks": missing,
            # NAMED so it is greppable in the artifact and countable across a
            # drop, rather than a prose sentence a reader has to notice.
            "header_count_unpopulated": header_count_unpopulated,
            "duplicate_rank": duplicate_rank_note,
            "parse_warnings": (
                ([f"header_count_unpopulated: board header claims 0 players and "
                  f"{n} contiguous ranks 1..{n} parsed. Accepted as an unpopulated "
                  f"page counter, not a partial board. Source file left as pasted."]
                 if header_count_unpopulated else [])
                + ([duplicate_rank_note] if duplicate_rank_note else [])),
            "fv_basis": fv_basis(meta["season"]),
            # THE TRAP. consensus._ORG_LIST_LABEL_RE is
            # r"\bTop\s+(?:10|20|25|30)\b\s*$" and it is the only thing keeping
            # an org list out of implied_fv_from_rank. Get this label wrong and
            # every number-one org prospect becomes a rank-implied FV 70. That
            # is the Bryan Sanchez failure: his only signal was rank 30 on a
            # 2021 Nationals Top-30, the legacy check missed the label format,
            # and he sorted 19th overall on zero published FVs. The existing
            # convention this matches is literally
            # "MLB Pipeline 2011 Angels Top 30".
            #
            # THE LABEL IS ALSO THE UPSERT KEY, and that nearly cost the 2026
            # preseason vintage (caught 2026-08-09, before any write).
            # insert_ba_snapshots conflicts on (source, interval_label,
            # player_key) and its DO UPDATE overwrites snapshot_date, rank and
            # fv. A season-only label means the 2026 MIDSEASON board and the
            # 2026 PRESEASON board are the same key, so ingesting the midseason
            # slate would have rewritten the preseason rows IN PLACE instead of
            # adding a vintage beside them. Measured on the real drop: 259 of the
            # 383 stored 2026-02-15 rows, across all 13 boards that exist in both
            # slates, with the FV changing on 99 of them, mean |delta| 2.10 FV
            # and max 15.0 FV. The preseason vintage would have fallen from 383
            # rows to 124 and nothing would have reported it.
            #
            # So a board that is not the preseason one carries its board name.
            # PRESEASON KEEPS THE BARE FORM, deliberately: 52 boards over four
            # vintages are already stored under it, and relabelling them is a
            # migration with its own gate, not a side effect of this ingest. Keep
            # the qualifier BEFORE the size, because the guard's regex is anchored
            # to end of string and anything after "Top 30" unmatches it.
            # A GLOBAL board (Top 100 / Top 250) has no club in its label, and
            # MUST NOT read as an org list: on a global list rank 1 really is
            # the best prospect in baseball, so rank-implied FV is meaningful
            # and the guard is supposed to let it through. "Top 100" already
            # fails _ORG_LIST_LABEL_RE on its own, which is why the size is
            # taken from GLOBAL_BOARDS rather than from board_size: a Top 100
            # that parsed 30 rows would otherwise label itself "Top 30" and
            # silently acquire org-list protection it is not entitled to.
            "interval_label": (
                f"Baseball America {meta['season']} "
                f"{meta['board'].capitalize()} {meta['scope']}"
                if meta.get("is_global") else
                f"Baseball America {meta['season']} {meta['team_name']} "
                f"Top {board_size}"
                if meta["board"] == "preseason" else
                f"Baseball America {meta['season']} {meta['board'].capitalize()} "
                f"{meta['team_name']} Top {board_size}"),
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Draft boards. Rank-only amateur lists -> draft_snapshots, never `snapshots`.
# ---------------------------------------------------------------------------

# One regex per field, all optional, all matched WITHIN a row block. Anchored at
# line start so a "School:" written inside a prose paragraph cannot register.
#
# THE SPACING CLASS IS [^\S\n] AND NOT \s, and that is not pedantry. \s matches a
# NEWLINE, so on a field BA published EMPTY the pattern walks past the end of the
# line and captures the next one. Both shapes exist in the corpus and both were
# caught doing real damage before this was tightened:
#
#   "Committed/Drafted:"  (2027 Top 100 rank 92, Kyle Alivo) swallowed the whole
#       scouting paragraph as the commit value. On the MIXED board the commit
#       value is the pool discriminator, so an Iowa COLLEGE pitcher was typed
#       HSp - the mislabeled-cohort failure this ingest is supposed to prevent.
#   "Committed:  "        (2027 HS Top 150 rank 126, Kam Smith) swallowed the
#       following line, putting the literal string "Age At Draft: 18.7" into
#       college_commit, a column every consumer reads as a school name.
#
# Anchoring the value to its own line makes an empty field parse as empty, which
# is what it is.
_DRAFT_SCHOOL_RE = re.compile(r"^School:[^\S\n]*(.*?)[^\S\n]*$", re.MULTILINE)
_DRAFT_AGE_RE = re.compile(
    r"^Age At Draft:[^\S\n]*(\d{1,2}(?:\.\d)?)[^\S\n]*$", re.MULTILINE)
# The three spellings BA uses for the commit-ish field. They carry two different
# quantities, so the LABEL is captured alongside the value and the value is
# classified separately. See _classify_commit.
_DRAFT_COMMIT_RE = re.compile(
    r"^(Committed/Drafted|Committed|Drafted):[^\S\n]*(.*?)[^\S\n]*$", re.MULTILINE)

# The grade fields an amateur board must NOT have. Presence is a format change.
_DRAFT_FORBIDDEN = (
    ("BA Grade/Risk", _GRADE_RISK_RE),
    ("Adjusted Grade", _ADJUSTED_RE),
    ("Scouting Grades", _SCOUT_GRADES_RE),
)

# A draft-history value, not a college commitment. Two shapes, both measured:
#   "Never Drafted"        191 rows, plus the BA typos "Never Drafred" and
#                          "Never Draftes" (1 each), which a strict equality
#                          test would misclassify as a school named after them.
#   "Reds  25 (19)"        club, apostrophe, two-digit year, round in parens.
#                          Includes BA's own "Natioanls  25 (19)".
# No commitment value in the corpus contains a digit, so the round-in-parens
# test is exact rather than heuristic.
_DRAFT_HISTORY_RE = re.compile(r"(?i)^never\s+draf\w*$|\(\d{1,2}\)\s*$")

# BA writes this where a high schooler has not picked a college. It is a real
# published fact, but it is not a school, and `college_commit` holds school
# names everywhere else in this database (no 'Uncommitted' sentinel exists in
# any of the 4,489 stored draft rows). It maps to NULL and survives verbatim in
# _extras.ba_commit_raw.
_DRAFT_UNCOMMITTED = frozenset({"uncommitted", "undecided", "none", "n/a"})

# The Age At Draft that separates the two pools. Measured on the mixed 2027 Top
# 100, where the commit-value classification puts every HS row at 19.2 or below
# and every college row at 20.8 or above: a 1.6-year gap around this cut, with
# zero rows inside it. Used only to CORROBORATE the commit classification and to
# report disagreements, never as the primary discriminator, because Age At Draft
# is missing on 18 of the 500 rows and the commit field is missing on none.
DRAFT_HS_AGE_CEILING = 20.0


def _classify_commit(label: str | None, value: str | None) -> tuple[str | None, str | None]:
    """(kind, cleaned) for a commit-ish field. kind is 'commit', 'draft_history',
    'uncommitted' or None.

    The LABEL cannot decide this: the mixed board writes "Committed/Drafted" over
    both quantities, 54 rows of draft history and 46 of college commitments. Only
    the value separates them.
    """
    if value is None:
        return None, None
    # BA escapes the ampersand in "Texas A\&M". Markdown escaping is a transport
    # artifact of the paste, not part of the school's name, and leaving it in
    # would split one school into two spellings against every other source.
    cleaned = fix_mojibake(value).replace("\\&", "&").replace("\\.", ".").strip()
    if not cleaned:
        return None, None
    if _DRAFT_HISTORY_RE.search(cleaned):
        return "draft_history", cleaned
    if cleaned.lower() in _DRAFT_UNCOMMITTED:
        return "uncommitted", cleaned
    return "commit", cleaned


def _first(rx: re.Pattern, block: str, group: int = 1):
    """The FIRST match of a field inside one row block, or None.

    Taking the first rather than asserting uniqueness is what survives a paste
    that repeats a block. Real case: rank 94 of the 2027 Top 100 (Noah Franco)
    carries its School / Committed / Age lines TWICE, identically, which is why
    that board greps to 101 School lines over 100 rows. The repeat is BA's page,
    the values agree, and the .md is left exactly as pasted per the README.
    """
    m = rx.search(block)
    return m.group(group) if m else None


def classify_pool(board_pool: str | None, commit_kind: str | None,
                  age_at_draft: float | None,
                  school_pool: str | None = None) -> tuple[str | None, str]:
    """(pool, basis) for one row. 'HS' or 'COL'.

    THE BOARD-LEVEL FACT WINS WHERE IT EXISTS. A College Top 50 is all college
    by construction; that is a stronger statement than anything a single row's
    text can support, and letting a per-row guess override it is how a
    mislabeled cohort gets built. Disagreements are COUNTED and reported by the
    caller rather than silently resolved either way.

    On a MIXED board there is no board-level fact, so the row decides, and the
    commit VALUE is the discriminator: a draft-history value can only belong to
    a college player (a high schooler in this class has not been draftable), and
    a college commitment or an "Uncommitted" can only belong to a high schooler.
    Age At Draft corroborates and is the fallback when the commit field is
    empty, which happens on 2 of 500 rows.
    """
    if board_pool is not None:
        return board_pool, "board"
    if commit_kind == "draft_history":
        return "COL", "commit_value"
    if commit_kind in ("commit", "uncommitted"):
        return "HS", "commit_value"
    if age_at_draft is not None:
        return ("HS" if age_at_draft < DRAFT_HS_AGE_CEILING else "COL"), "age"
    # LAST RESORT, and named as such. This is the same school-token test
    # _canon_player_type falls back on, and it is the WEAKEST signal here: it
    # disagrees with the other two on 49 of the 500 rows because BA does not tag
    # every high school with an "HS" token. It is used only where a mixed board
    # published neither a commit value nor an age (1 of 500 rows), and naming the
    # basis is what keeps that row distinguishable from a confident one.
    if school_pool is not None:
        return school_pool, "school_fallback"
    return None, "unresolved"


def parse_draft_board(text: str, meta: dict) -> dict:
    """Parse one pasted AMATEUR DRAFT board. Rank-only; never fabricates a grade.

    Raises BoardFormatError rather than ingest a partial board, on the same
    reasoning as parse_board: rank is the only quantity these boards carry, so a
    board missing rows is a board whose ranks mean something different.
    """
    from draft_export import _canon_player_type

    declared = None
    for line in text.splitlines()[:20]:
        m = _HEADER_COUNT_RE.match(line.strip())
        if m:
            declared = int(m.group(1))
            break

    blocks = _split_blocks(text)
    if not blocks:
        raise BoardFormatError(
            "no rank lines found. The anchor is a line starting with a number "
            "and an escaped dot, e.g. '1\\. Dylan Seward'. Paste it raw.")

    ranks = [b[0] for b in blocks]
    dupes = sorted({r for r in ranks if ranks.count(r) > 1})
    if dupes:
        raise BoardFormatError(f"duplicated rank(s) {dupes} on a draft board")
    if ranks != sorted(ranks):
        raise BoardFormatError(f"ranks are not ascending: {ranks[:15]}")
    if ranks[0] != 1:
        raise BoardFormatError(f"board does not start at rank 1 (starts at {ranks[0]})")

    # THE GUARD THE ORG PATH ALREADY HAS: parsed rows must equal the declared
    # count. A parser that quietly requires an optional field drops rows, and
    # this is the check that turns that into a refusal instead of a short board.
    if declared is not None and declared != len(blocks):
        raise BoardFormatError(
            f"board header claims {declared} players but {len(blocks)} rank "
            f"lines parsed. Refusing a partial board.")

    # NO GRADES. Verified as an assertion rather than an assumption: if BA starts
    # publishing amateur grades, that is a modelling decision with its own gate
    # (which scale? adjusted or raw? against what reference?) and it must not
    # arrive as a silently-populated column.
    grade_hits = {name: len(rx.findall(text)) for name, rx in _DRAFT_FORBIDDEN}
    grades_found = {k: v for k, v in grade_hits.items() if v}

    rows: list[dict] = []
    pool_disagreements: list[dict] = []
    for rank, raw_name, block in blocks:
        name = _clean_name(raw_name)
        if not name:
            raise BoardFormatError(f"rank {rank} has an empty name")

        position = None
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("Ht:"):
                break
            pm = _POSITION_RE.match(s)
            if pm:
                position = pm.group(1)
            break

        phys = _PHYS_RE.search(block)
        school_raw = _first(_DRAFT_SCHOOL_RE, block)
        school = (fix_mojibake(school_raw).replace("\\&", "&").replace("\\.", ".").strip()
                  if school_raw else None) or None
        age_raw = _first(_DRAFT_AGE_RE, block)
        age_at_draft = float(age_raw) if age_raw else None

        cm = _DRAFT_COMMIT_RE.search(block)
        commit_label = cm.group(1) if cm else None
        commit_kind, commit_value = _classify_commit(
            commit_label, cm.group(2) if cm else None)

        school_pool = None
        if school:
            school_pool = ("HS" if (re.search(r"\bHS\b", school)
                                    or re.search(r"high school", school, re.I))
                           else "COL")

        pool, pool_basis = classify_pool(
            meta.get("pool"), commit_kind, age_at_draft, school_pool)

        # What the row ALONE would have said, so an override of a board-level
        # fact is counted rather than invisible. Both the per-row inference and
        # the school-token fallback that draft_export would otherwise apply are
        # checked, because the second is the one that actually mistypes rows.
        row_pool, _ = classify_pool(None, commit_kind, age_at_draft)
        if pool_basis == "board" and row_pool is not None and row_pool != pool:
            pool_disagreements.append(
                {"rank": rank, "name": name, "board_pool": pool,
                 "row_pool": row_pool, "kind": "row_inference",
                 "school": school, "age_at_draft": age_at_draft,
                 "commit": commit_value})
        if school_pool is not None and school_pool != pool:
            pool_disagreements.append(
                {"rank": rank, "name": name, "board_pool": pool,
                 "row_pool": school_pool, "kind": "school_token",
                 "school": school, "age_at_draft": age_at_draft,
                 "commit": commit_value})

        # Canonicalise through draft_export's own function so this source lands
        # in the same COLh/COLp/HSh/HSp vocabulary as every other draft feed.
        # The POOL is handed in rather than left to be inferred: that argument is
        # resolved before the school fallback inside _canon_player_type, which is
        # exactly what stops the 49 untagged high schools from folding to COL.
        player_type = _canon_player_type(pool, school, position)

        # The unlabelled prose paragraph. There is no "Track Record:" or
        # "Scouting Report:" prefix on a draft board, so it is identified
        # structurally: the longest non-field line in the block.
        prose = None
        for line in block.splitlines():
            s = line.strip()
            if not s or ":" in s[:24] or _POSITION_RE.match(s):
                continue
            if len(s) > len(prose or ""):
                prose = s

        rows.append({
            "rank": rank,
            "player_name": name,
            "position": position.split("/")[0].strip() if position else None,
            "position_full": position,
            "school": school,
            # Only a real commitment reaches college_commit. A draft-history
            # value ("Never Drafted", "Reds  25 (19)") is a different quantity
            # and would read as a school to every consumer of this column.
            "college_commit": commit_value if commit_kind == "commit" else None,
            "commit_label": commit_label,
            "commit_kind": commit_kind,
            "commit_raw": commit_value,
            "pool": pool,
            "pool_basis": pool_basis,
            "player_type": player_type,
            "age_at_draft": age_at_draft,
            "height": phys.group(1) if phys else None,
            "weight": int(phys.group(2)) if phys else None,
            "bats": phys.group(3) if phys else None,
            "throws": phys.group(4) if phys else None,
            # Rank-only. Stated as data rather than left implicit.
            "fv": None,
            "ba_raw_grade": None,
            "ba_risk": None,
            "tools": {},
            "report": (prose or None) and prose[:_REPORT_MAX_CHARS],
        })

    extent = meta["scope_extent"]
    return {
        "meta": {
            **meta,
            "n_players": len(rows),
            "declared_players": declared,
            # From the SCOPE, never the row count. A Top 150 that parsed 100 rows
            # must not relabel itself a Top 100.
            "board_size": extent,
            "missing_ranks": sorted(set(range(1, max(ranks) + 1)) - set(ranks)),
            "fv_basis": "none_published",
            "grades_found": grades_found,
            # "Baseball America 2027 Draft HS Top 150". Matches the shape the
            # other draft feeds are stored under ("ESPN 2026 Draft Top 150",
            # "MLB Pipeline 2026 Draft Top 250") and puts the SCOPE in the label,
            # so the five boards cannot collide on the (source, interval_label,
            # player_key) upsert key.
            "interval_label": (f"Baseball America {meta['class_year']} Draft "
                               f"{meta['scope']}"),
            "parse_warnings": [],
        },
        "rows": rows,
        "pool_disagreements": pool_disagreements,
    }


def validate_org_label(label: str) -> str | None:
    """Return a refusal reason if this label would NOT be seen as an org list.

    Checked against the LIVE regex rather than a copy of the sizes it accepts,
    because a copy is exactly what failed last time. _ORG_LIST_LABEL_RE matches
    only Top 10 / 20 / 25 / 30, so a board that parsed to 29 or 31 rows would
    build a label the guard does not match, its ranks would fall through to
    implied_fv_from_rank, and the number-one org prospect would become FV 70 on
    zero published grades. That failure is silent, board-wide, and has happened:
    Bryan Sanchez sorted 19th overall off rank 30 on a 2021 Nationals Top-30.

    Loud refusal is the whole point. Do not "fix" a refusal by padding the
    label to 30; fix the paste.
    """
    from consensus import _ORG_LIST_LABEL_RE
    if _ORG_LIST_LABEL_RE.search(label):
        return None
    return (
        f"interval_label {label!r} is NOT matched by consensus._ORG_LIST_LABEL_RE, "
        f"so this board's ranks would feed implied_fv_from_rank and its top "
        f"prospect would become a rank-implied FV 70. The guard accepts only "
        f"Top 10, 20, 25 and 30. Check the paste is a complete org board.")


# ---------------------------------------------------------------------------
# Identity. Resolve against what exists; never guess.
# ---------------------------------------------------------------------------

# THE ADMISSION BAR RUNS OVER EVERY RESOLVED ROW, NOT ONLY THE UNRESOLVED ONES.
#
# The first pass of this module held the two-signal bar only against the names
# that did NOT match a key, and let 878 exact-key matches through with no
# identity check at all. That is backwards. An exact key match on a common name
# is exactly where a silent merge hides, and it did: BA's Angels rank 20
# "Garrett Wright" (C/OF, age 20, Tennessee, drafted by the Angels in the 8th
# round) resolved onto `garrett_wright`, which this database holds as a CHW
# PITCHER born 2002-02-11 with a 37.1-inning A+ pitching line. Org, side of the
# ball and age all contradicted, the mismatch was written into the resolution
# string, and the row was ingested anyway.
#
# Two checks, both measured against the real 900-row 2026 midseason drop before
# they were written:
#
#   AGE       BA's age against players.birth_date at a ~June 1 reference. At 2.0
#             years it fires on 8 of the 875 rows that carry both fields (0.91%)
#             against a 95% exact-match base rate at that reference, and it
#             catches Garrett Wright. This is the cheap gate the audit asked for.
#   SIDE      pitcher-versus-hitter, BA's position against `players`. Fires on
#             1 of 896 (Garrett Wright again, C against P), and on 1 of the 38
#             org-mismatch rows. TWP is exempt: a two-way player legitimately
#             reads as either side, and exempting it is what takes this check
#             from 2 hits to 1 (BA lists Jared Grindlinger, a stored TWP, as OF).
#
# An age contradiction says the row and the KEY disagree. It does not say which
# of the two is wrong, so the second stage asks a third party. FanGraphs stores
# its own age on every board row it publishes (tools._extras.age), which makes a
# per-key DERIVED birth date - snapshot_date minus that age - from an outlet that
# never saw either the BA row or players.birth_date:
#
#   * derived dates that disagree with each other by more than a year mean the
#     KEY ITSELF already holds two humans, and BA must not add mass to it. Five
#     of the eight are this shape (luke_williams: FanGraphs 2021 carries a
#     25-year-old PHI 3B and FanGraphs 2026 an 18.6-year-old WSN shortstop).
#   * derived dates that agree with each other AND with BA mean the one outlier
#     is players.birth_date. Two of the eight are this shape (sean_sullivan,
#     wilian_bormie), and their rows are ADMITTED with the discrepancy recorded
#     rather than deleted, because the keying is right and the biography is not.
#
# Everything the bar rejects is reported by rank, name, key and reason. A
# refused row is recoverable from the drop file; a wrong merge is not.
AGE_CONTRADICTION_YEARS = 2.0

# BA prints a SEASON age. Over the 829 rows of the 2026 midseason drop that
# resolved and carry a stored birth_date it is exact on 787 (94.93%) against a
# June 1 reference and on only 644 (77.68%) against the board's own 2026-08-01
# date, so June 1 is the reference the arithmetic uses.
AGE_REFERENCE_MONTH_DAY = (6, 1)

# Two FanGraphs-derived birth dates further apart than this cannot be one human.
FUSED_KEY_DOB_SPREAD_YEARS = 1.0

# How close FanGraphs' own age has to be to BA's for the third party to be read
# as agreeing with the board against players.birth_date. BA's season age runs up
# to a year under a mid-season current age by construction, hence 1.5 and not 1.0.
AGE_CORROBORATION_YEARS = 1.5

_PITCHER_POS_TOKENS = frozenset({
    "P", "SP", "RP", "LHP", "RHP", "LHRP", "RHRP", "SIRP", "MIRP", "LHSP",
    "RHSP", "PITCHER",
})
_HITTER_POS_TOKENS = frozenset({
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "IF", "DH", "INF",
    "UTIL", "UT", "CIF", "MIF", "CATCHER",
})


def side_of_ball(position) -> str | None:
    """"P", "H", or None when the label is unknown, mixed or two-way.

    TWP is deliberately None rather than "P". A two-way player reads as either
    side and is the one shape that would make this check lie: BA lists Jared
    Grindlinger as OF where this database stores TWP, and treating TWP as a
    pitcher turns that correct row into a refusal."""
    kinds = set()
    for tok in str(position or "").replace("/", " ").replace(",", " ").split():
        tok = tok.strip().upper()
        if tok in _PITCHER_POS_TOKENS:
            kinds.add("P")
        elif tok in _HITTER_POS_TOKENS:
            kinds.add("H")
        else:  # TWP, UTL variants, anything new BA starts printing
            return None
    if len(kinds) == 1:
        return kinds.pop()
    return None


def age_reference_date(snapshot_date: str | None) -> date:
    """June 1 of the board's own season. Falls back to today's year."""
    try:
        year = int(str(snapshot_date)[:4])
    except (TypeError, ValueError):
        year = date.today().year
    return date(year, *AGE_REFERENCE_MONTH_DAY)


def implied_age(birth_date, as_of: date) -> float | None:
    try:
        born = date.fromisoformat(str(birth_date)[:10])
    except (TypeError, ValueError):
        return None
    return (as_of - born).days / 365.25


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def screen_identity(row: dict, known: dict, as_of: date,
                    fg_ages: dict | None = None) -> dict | None:
    """The admission bar for ONE already-resolved row.

    Returns None when the row may be ingested, otherwise a dict carrying the
    check that fired, the two values that disagree and the verdict. A verdict of
    "quarantine" means do not ingest; "admit" means ingest and record.

    `known` is {player_key: (player_name, org, birth_date, position)} and
    `fg_ages` is {player_key: [(snapshot_date, age), ...]} from FanGraphs.
    """
    key = row.get("player_key")
    entry = (known or {}).get(key)
    if not key or not entry:
        return None
    db_name, db_org, db_birth, db_pos = entry

    ba_side = side_of_ball(row.get("position_full") or row.get("position"))
    db_side = side_of_ball(db_pos)
    if ba_side and db_side and ba_side != db_side:
        return {"check": "side", "verdict": "quarantine",
                "rank": row.get("rank"), "name": row.get("player_name"),
                "player_key": key, "db_name": db_name,
                "ba_position": row.get("position"), "db_position": db_pos,
                "reason": (f"BA publishes a {ba_side} ({row.get('position')}) where "
                           f"the database stores a {db_side} ({db_pos})")}

    ba_age = _as_float(row.get("age"))
    db_age = implied_age(db_birth, as_of)
    if ba_age is None or db_age is None:
        return None
    delta = ba_age - db_age
    if abs(delta) < AGE_CONTRADICTION_YEARS:
        return None

    out = {"check": "age", "rank": row.get("rank"), "name": row.get("player_name"),
           "player_key": key, "db_name": db_name, "db_org": db_org,
           "ba_age": ba_age, "db_birth_date": db_birth,
           "db_implied_age": round(db_age, 2), "delta_years": round(delta, 2)}

    series = sorted((fg_ages or {}).get(key) or [])
    derived = []
    for snap_date, age in series:
        try:
            d = date.fromisoformat(str(snap_date)[:10])
        except (TypeError, ValueError):
            continue
        derived.append(d.toordinal() - (age or 0) * 365.25)
    if len(derived) >= 2 and (max(derived) - min(derived)) / 365.25 > FUSED_KEY_DOB_SPREAD_YEARS:
        out.update({"verdict": "quarantine", "third_party": "fangraphs_fused_key",
                    "fg_dob_spread_years": round((max(derived) - min(derived)) / 365.25, 2),
                    "reason": ("FanGraphs' own ages on this key derive birth dates "
                               "more than a year apart, so the key already holds "
                               "two humans and BA must not add mass to it")})
        return out
    if series:
        latest_date, latest_age = series[-1]
        fg_at_reference = None
        try:
            d = date.fromisoformat(str(latest_date)[:10])
            fg_at_reference = latest_age - (d - as_of).days / 365.25
        except (TypeError, ValueError):
            fg_at_reference = None
        if (fg_at_reference is not None
                and abs(ba_age - fg_at_reference) <= AGE_CORROBORATION_YEARS):
            out.update({"verdict": "admit", "third_party": "fangraphs_agrees_with_ba",
                        "fg_age_at_reference": round(fg_at_reference, 2),
                        "reason": ("FanGraphs' own age agrees with BA against "
                                   "players.birth_date, so the keying is right and "
                                   "the stored birth date is the outlier")})
            return out
    out.update({"verdict": "quarantine", "third_party": "none",
                "reason": ("BA's age and players.birth_date disagree by "
                           f"{abs(delta):.1f} years with no third party to "
                           "settle which record is the wrong human")})
    return out


def _fangraphs_ages(con, keys) -> dict:
    """{player_key: [(snapshot_date, age), ...]} from FanGraphs' own board rows.

    FanGraphs stores an age on every row it publishes and it reaches this
    database inside tools_json under _extras.age. It is a genuinely independent
    reading: a different outlet, never keyed on BA's spelling and never derived
    from players.birth_date."""
    keys = [k for k in dict.fromkeys(keys) if k]
    out: dict[str, list] = {}
    for i in range(0, len(keys), 400):
        chunk = keys[i:i + 400]
        # The LIKE pattern carries a literal percent, so this string is built by
        # concatenation. Interpolating it would make the pattern a format spec.
        sql = ("SELECT player_key, snapshot_date, tools_json FROM snapshots "
               "WHERE source LIKE 'fangraphs%' AND tools_json IS NOT NULL "
               "AND player_key IN (" + ",".join("?" * len(chunk)) + ")")
        for key, snap_date, tools_json in con.execute(sql, chunk):
            try:
                extras = (json.loads(tools_json) or {}).get("_extras") or {}
            except (TypeError, ValueError):
                continue
            age = _as_float(extras.get("age"))
            if age is not None:
                out.setdefault(key, []).append((snap_date, age))
    return out


def resolve_identities(rows: list[dict], org: str,
                       snapshot_date: str | None = None) -> dict:
    """Attach a player_key to every row this can settle UNAMBIGUOUSLY.

    A confident wrong resolution is worse than a missing row, and this repo has
    three recorded incidents to prove it: joe_jr_gray resolved to Connor Joe,
    william_jr_bergolla to William Contreras, and Jack Natili reached the
    served board twice at ranks 155 and 320 with his surplus double counted.
    So the ladder resolves onto keys that already exist and reports everything
    else for a human. Minting is opt-in and lives in ingest_drops.
    """
    import storage
    # THE ALIAS TABLE IS THE ONLY SANCTIONED PLACE TO SETTLE A SPELLING SPLIT.
    #
    # It lives in consensus.PLAYER_KEY_ALIASES and canonicalises at READ time, so
    # a wrong entry is undone by deleting four lines. The alternative, re-keying
    # prospects.db, is a standing repo prohibition with three recorded incidents
    # behind it (joe_jr_gray resolved to Connor Joe, william_jr_bergolla to
    # William Contreras, and Jack Natili reaching the served board twice with his
    # surplus double counted). The Natili survey also found the DB remap would
    # have thrown on 23 of 30 rows, because both keys held snapshots on the same
    # dates under PK(player_key, snapshot_date).
    #
    # BA prints the SHORT form of a name ("Eric Booth", "Eli Serrano") where this
    # database holds the suffixed or full form ("Eric Booth Jr.", "Eli Serrano
    # III"), so without this step a correctly-parsed row for a player the
    # database already knows is reported unresolved and never ingested at all.
    from consensus import PLAYER_KEY_ALIASES
    with storage.connect() as con:
        known = {r[0]: (r[1], r[2], r[3], r[4]) for r in con.execute(
            "SELECT player_key, player_name, org, birth_date, position FROM players")}

        resolved, unresolved, org_mismatch = [], [], []
        for r in rows:
            # A GLOBAL board has no board-level org and carries the club PER ROW,
            # so the row's own value is the org to compare against and to key the
            # split table with. Passing the board's None instead did two things,
            # both caught on the real 2026 midseason Top 100: it reported all 100
            # rows as an org mismatch ("board None vs db MIL"), burying any
            # genuine one in noise, and it made the _BA_ORG_SPLIT_KEYS pin inert,
            # because that table is keyed on (slug, org) and (slug, None) can
            # never match. That pin is what routes the two Garrett Wrights.
            row_org = r.get("row_org") or org
            key = normalize_key(r["player_name"])
            # Known slug collisions where the BA board's own org identifies the
            # NEWCOMER of a two-human key: route to the discriminated key before
            # the plain slug can reach the incumbent. Mirrors
            # fangraphs_csv._FG_ORG_SPLIT_KEYS; the DB-side repair alone is not
            # enough, because carlos_castillo was repaired once and then
            # RE-MERGED by the next board when nothing pinned the ingest.
            split = _BA_ORG_SPLIT_KEYS.get((key, row_org))
            if split and split in known:
                r["split_from"] = key
                key = split
            alias = PLAYER_KEY_ALIASES.get(key)
            if alias and alias.get("player_key") in known:
                r["alias_from"] = key
                key = alias["player_key"]
            if key in known:
                db_name, db_org = known[key][0], known[key][1]
                r["player_key"] = key
                r["resolution"] = "alias_key" if r.get("alias_from") else "exact_key"
                if db_org and row_org and db_org != row_org:
                    # Not necessarily wrong: a player traded between the board's
                    # publication and today has a different current org. Reported
                    # so a genuine name collision cannot hide inside the noise.
                    r["resolution"] += "_org_mismatch"
                    org_mismatch.append({"rank": r["rank"], "name": r["player_name"],
                                         "player_key": key, "board_org": row_org,
                                         "db_org": db_org, "db_name": db_name})
                resolved.append(r)
            else:
                r["player_key"] = None
                r["resolution"] = "unresolved"
                unresolved.append({"rank": r["rank"], "name": r["player_name"],
                                   "would_be_key": key, "board_org": row_org})

        # THE BAR, over every row that resolved - see the block comment above.
        fg_ages = _fangraphs_ages(con, [r["player_key"] for r in resolved])

    as_of = age_reference_date(snapshot_date)
    quarantined, admitted_with_conflict, kept = [], [], []
    for r in resolved:
        verdict = screen_identity(r, known, as_of, fg_ages)
        if verdict is None:
            kept.append(r)
            continue
        r["identity_screen"] = verdict
        if verdict["verdict"] == "quarantine":
            r["resolution"] = f"quarantined_{verdict['check']}_conflict"
            r["quarantined_key"] = r["player_key"]
            r["player_key"] = None
            quarantined.append(verdict)
        else:
            r["resolution"] += f"_{verdict['check']}_conflict_admitted"
            admitted_with_conflict.append(verdict)
            kept.append(r)

    return {
        "resolved": kept,
        "unresolved": unresolved,
        "org_mismatch": org_mismatch,
        "quarantined": quarantined,
        "admitted_with_conflict": admitted_with_conflict,
        "n_resolved": len(kept),
        "n_unresolved": len(unresolved),
        "n_quarantined": len(quarantined),
    }


def to_snapshots(board: dict) -> list[Snapshot]:
    """Rows with a settled identity -> Snapshot objects."""
    meta = board["meta"]
    out: list[Snapshot] = []
    for r in board["rows"]:
        if not r.get("player_key"):
            continue
        extras = {
            # The pair the owner instruction says to keep beside the FV. This
            # mirrors what consensus already does, where per_source.fv_published
            # keeps the untouched published grade next to fv_adjusted.
            "ba_raw_grade": r["ba_raw_grade"],
            "ba_risk": r["ba_risk"],
            "ba_board": meta["board"],
            "ba_previous_rank": r["previous_rank"],
            "position_full": r["position_full"],
            "age": r["age"],
            "height": r["height"],
            "weight": r["weight"],
            "bats": r["bats"],
            "throws": r["throws"],
            # Untouched BA tool labels, so the split/sweeper folding decision
            # stays reversible without re-pasting the board.
            "ba_tools_raw": r["ba_tools_raw"] or None,
            # The grade of a pitch that FOLDED onto a slot another pitch owns,
            # keyed by that slot. Nothing BA published is discarded, and no new
            # top-level tools_json key is minted to hold it (see _map_tools).
            "ba_tool_variants": r.get("tool_variants") or None,
            "report": r.get("report"),
        }
        extras = {k: v for k, v in extras.items() if v is not None and v != ""}
        tools = dict(r["tools"])
        if extras:
            tools["_extras"] = extras
        out.append(Snapshot(
            source=SOURCE,
            snapshot_date=meta["snapshot_date"],
            interval_label=meta["interval_label"],
            player_key=r["player_key"],
            player_name=r["player_name"],
            position=r["position"],
            # An ORG board's club is a board-level fact; a GLOBAL board prints
            # it per row and meta["org"] is None, so the row value is the only
            # org there is. Falling back to meta["org"] keeps the org path
            # byte-identical.
            org=meta["org"] or r.get("row_org"),
            rank=r["rank"],
            # A row whose Adjusted Grade is missing is ingested RANK-ONLY. It
            # does NOT fall back to the raw grade: a raw grade sitting in an FV
            # column is a scale error no downstream layer can detect.
            fv=r["fv"],
            status="active",
            tools=tools or None,
            fv_plus=False,
        ))
    return out


def resolve_draft_identities(rows: list[dict], class_year: int) -> dict:
    """Attach the canonical amateur key to every draft row.

    AMATEURS DO NOT RESOLVE AGAINST `players`, and that is the whole point of
    the separate namespace. draft_csv.draft_player_key mints
    draft_{class_year}_{name_slug} precisely so a high schooler never collides
    with a pro of the same name until draft_promotion links them deliberately.
    So there is no resolution ladder here and no admission bar: the key is a
    function of the class year and the spelling, and it is the SAME function
    draft_promotion.draft_canonical_keys reads on promotion. A format mismatch
    would orphan every row silently, so this calls the real builder rather than
    formatting the string locally.

    What IS reported is a within-board key collision: two different humans whose
    names normalise to one key would upsert onto each other under the
    (source, interval_label, player_key) conflict target, and the second would
    overwrite the first in place with nothing to show for it.
    """
    from draft_csv import draft_player_key

    seen: dict[str, dict] = {}
    collisions: list[dict] = []
    for r in rows:
        key = draft_player_key(class_year, r["player_name"])
        r["player_key"] = key
        r["resolution"] = "draft_key"
        prior = seen.get(key)
        if prior is not None:
            collisions.append({
                "player_key": key,
                "ranks": [prior["rank"], r["rank"]],
                "names": [prior["player_name"], r["player_name"]],
            })
        else:
            seen[key] = r
    return {
        "resolved": rows,
        "n_resolved": len(rows),
        "n_unresolved": 0,
        "unresolved": [],
        "key_collisions": collisions,
        "n_distinct_keys": len(seen),
    }


def to_draft_rows(board: dict) -> list[dict]:
    """Draft board -> dicts shaped for storage.insert_draft_snapshots.

    Plain dicts rather than Snapshot objects: the writer accepts either, and
    Snapshot has no school / college_commit / player_type / draft_year fields.
    """
    meta = board["meta"]
    rank_is_global = meta["rank_is_global"]
    out: list[dict] = []
    for r in board["rows"]:
        if not r.get("player_key"):
            continue
        extras = {
            "ba_board": DRAFT_BOARD,
            "ba_scope": meta["scope"],
            # THE PUBLISHED RANK, ALWAYS, whatever the column gets. On a scoped
            # board this is the only place it lives, so nothing BA published is
            # discarded and a within-scope model can be fitted later without
            # re-pasting the board. See scope_rank_is_global.
            "ba_scope_rank": r["rank"],
            "ba_rank_is_global": rank_is_global,
            "ba_commit_label": r["commit_label"],
            # The untouched published string, whichever quantity it turned out
            # to be. college_commit above takes only a real commitment.
            "ba_commit_raw": r["commit_raw"],
            "ba_commit_kind": r["commit_kind"],
            "ba_pool_basis": r["pool_basis"],
            "age_at_draft": r["age_at_draft"],
            "position_full": r["position_full"],
            "height": r["height"],
            "weight": r["weight"],
            "bats": r["bats"],
            "throws": r["throws"],
            "report": r["report"],
        }
        extras = {k: v for k, v in extras.items() if v is not None and v != ""}
        out.append({
            "source": DRAFT_SOURCE,
            "snapshot_date": meta["snapshot_date"],
            "interval_label": meta["interval_label"],
            "player_key": r["player_key"],
            "player_name": r["player_name"],
            "position": r["position"],
            "school": r["school"],
            "college_commit": r["college_commit"],
            "player_type": r["player_type"],
            "draft_year": meta["class_year"],
            # NULL on a scoped board. A College Top 50's rank 1 and an HS Top
            # 100's rank 1 are two different players and neither is the first
            # pick of the class; draft_export averages latest-rank-per-SOURCE
            # and would read both as a whole-class rank.
            "rank": r["rank"] if rank_is_global else None,
            # BA publishes no amateur grades. Rank-only, and absent is recorded
            # as absent rather than filled from anything.
            "fv": None,
            "risk": None,
            "status": "draft_active",
            "tools": {"_extras": extras} if extras else None,
            "fv_plus": False,
            # draft_players columns the writer also upserts.
            "bats": r["bats"],
            "throws": r["throws"],
            "height": r["height"],
            "weight": r["weight"],
        })
    return out


def insert_ba_draft_snapshots(rows: list[dict]) -> int:
    """Write amateur rows through storage.insert_draft_snapshots.

    THE CONFLICT KEY IS (source, interval_label, player_key), DO UPDATE. So a
    re-ingest of the SAME board is idempotent in content: snapshot_date,
    player_name, draft_year, rank, fv, status and fv_plus are overwritten with
    the incoming values, while position, school, college_commit, player_type,
    risk and tools_json are COALESCEd and therefore keep a stored value the new
    parse could not supply. It adds no rows, and the returned count is rows
    TOUCHED, not rows created.

    Two consequences worth stating rather than discovering:

      * Because the scope is in interval_label, the five boards cannot overwrite
        each other. Because the DATE is not, a LATER vintage of the same scope
        (BA's next 2027 Top 100) would overwrite the current one IN PLACE rather
        than land beside it as a second vintage. That is the convention the other
        draft feeds already use (MLB Pipeline 2026 Draft Top 250 holds snapshot
        dates from 2026-06-08 to 2026-08-10 under one label), and it is the
        opposite of what the org path does, so it is recorded here.
      * storage.insert_draft_snapshots ALSO upserts `draft_players`, keyed on
        player_key alone. That is a SECOND table written by this call.
    """
    import storage
    return storage.insert_draft_snapshots(rows)


# ---------------------------------------------------------------------------
# Drop-folder walk
# ---------------------------------------------------------------------------

_CSV_COLUMNS = (
    "season", "board", "org", "team_name", "snapshot_date", "interval_label",
    "rank", "player_name", "player_key", "resolution", "position",
    "position_full", "fv", "ba_raw_grade", "ba_risk", "adjusted_expected",
    "adjusted_identity_ok", "previous_rank", "age", "height", "weight",
    "bats", "throws", "tools_json", "ba_tools_raw_json", "ba_tool_variants_json",
)


def _write_normalized_csv(board: dict, path: Path) -> None:
    meta = board["meta"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_CSV_COLUMNS))
        w.writeheader()
        for r in board["rows"]:
            w.writerow({
                "season": meta["season"], "board": meta["board"],
                "org": meta["org"], "team_name": meta["team_name"],
                "snapshot_date": meta["snapshot_date"],
                "interval_label": meta["interval_label"],
                "rank": r["rank"], "player_name": r["player_name"],
                "player_key": r.get("player_key") or "",
                "resolution": r.get("resolution") or "",
                "position": r["position"] or "",
                "position_full": r["position_full"] or "",
                "fv": r["fv"] if r["fv"] is not None else "",
                "ba_raw_grade": r["ba_raw_grade"] if r["ba_raw_grade"] is not None else "",
                "ba_risk": r["ba_risk"] or "",
                "adjusted_expected": r["adjusted_expected"] if r["adjusted_expected"] is not None else "",
                # None means "not checkable" (no risk published), which is a
                # different fact from False ("checked and it broke"). Kept
                # distinct in the CSV rather than collapsed to a blank.
                "adjusted_identity_ok": ("" if r["adjusted_identity_ok"] is None
                                         else int(r["adjusted_identity_ok"])),
                "previous_rank": r["previous_rank"] if r["previous_rank"] is not None else "",
                "age": r["age"] if r["age"] is not None else "",
                "height": r["height"] or "", "weight": r["weight"] or "",
                "bats": r["bats"] or "", "throws": r["throws"] or "",
                "tools_json": json.dumps(r["tools"], sort_keys=True) if r["tools"] else "",
                "ba_tools_raw_json": json.dumps(r["ba_tools_raw"], sort_keys=True) if r["ba_tools_raw"] else "",
                "ba_tool_variants_json": (json.dumps(r["tool_variants"], sort_keys=True)
                                          if r.get("tool_variants") else ""),
            })


_DRAFT_CSV_COLUMNS = (
    "class_year", "scope", "snapshot_date", "interval_label", "rank",
    "rank_is_global", "player_name", "player_key", "position", "position_full",
    "school", "college_commit", "commit_label", "commit_kind", "commit_raw",
    "pool", "pool_basis", "player_type", "age_at_draft", "height", "weight",
    "bats", "throws", "fv",
)


def _count_by(rows: list[dict], field: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[str(r.get(field))] = out.get(str(r.get(field)), 0) + 1
    return dict(sorted(out.items()))


def _write_draft_csv(board: dict, path: Path) -> None:
    meta = board["meta"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_DRAFT_CSV_COLUMNS))
        w.writeheader()
        for r in board["rows"]:
            w.writerow({
                "class_year": meta["class_year"], "scope": meta["scope"],
                "snapshot_date": meta["snapshot_date"],
                "interval_label": meta["interval_label"],
                "rank": r["rank"],
                "rank_is_global": int(bool(meta["rank_is_global"])),
                "player_name": r["player_name"],
                "player_key": r.get("player_key") or "",
                "position": r["position"] or "",
                "position_full": r["position_full"] or "",
                "school": r["school"] or "",
                "college_commit": r["college_commit"] or "",
                "commit_label": r["commit_label"] or "",
                "commit_kind": r["commit_kind"] or "",
                "commit_raw": r["commit_raw"] or "",
                "pool": r["pool"] or "", "pool_basis": r["pool_basis"],
                "player_type": r["player_type"] or "",
                "age_at_draft": r["age_at_draft"] if r["age_at_draft"] is not None else "",
                "height": r["height"] or "", "weight": r["weight"] or "",
                "bats": r["bats"] or "", "throws": r["throws"] or "",
                # Always empty. BA publishes no amateur grade, and the column
                # exists so that stays visible in the artifact.
                "fv": "",
            })


def process_file(path: Path, *, resolve: bool = True) -> dict:
    """Parse one drop file end to end. Never writes to the DB."""
    meta = parse_filename(path.name)
    if meta is None:
        raise BoardFormatError(
            f"filename {path.name!r} does not match "
            f"ba__{{season}}__{{board}}__{{team}}[__{{YYYY-MM-DD}}].md with a "
            f"known board ({'/'.join(BOARDS)}) and a known club slug. The "
            f"filename is load-bearing: one probed board carried no season, "
            f"board or team anywhere in its body.")

    text = path.read_text(encoding="utf-8")
    evidence = scan_content_dates(text, meta["season"])
    snapshot_date, refusals, warnings = resolve_snapshot_date(meta, evidence)
    meta["snapshot_date"] = snapshot_date
    meta["snapshot_date_basis"] = "filename" if meta.get("pubdate") else "convention"

    # AMATEUR DRAFT BOARDS TAKE A SEPARATE PATH ALL THE WAY DOWN: a different
    # parser (no grades), a different key namespace (draft_{year}_{slug}), a
    # different label shape and a different target table. The one thing they must
    # never share is `snapshots`, because an amateur in the active prospect pool
    # joins consensus FV, the prospect board and the trade machine.
    if meta.get("is_draft"):
        if refusals:
            return {"meta": meta, "rows": [], "refusals": refusals,
                    "warnings": warnings, "content_evidence": evidence,
                    "is_draft": True, "unknown_risks": [],
                    "adjusted_identity_failures": [], "tool_issues": [],
                    "pool_disagreements": [], "pre_fangraphs_era": False}
        board = parse_draft_board(text, meta)
        board["content_evidence"] = evidence
        board["refusals"] = refusals
        board["warnings"] = warnings
        board["is_draft"] = True
        board["unknown_risks"] = []
        board["adjusted_identity_failures"] = []
        board["tool_issues"] = []
        board["pre_fangraphs_era"] = False
        if board["meta"]["grades_found"]:
            refusals.append(
                f"this draft board publishes grade field(s) "
                f"{board['meta']['grades_found']}, which no amateur board in the "
                f"corpus does (0 of 500 rows). Reading them as FV is a modelling "
                f"decision with its own gate - which scale, adjusted or raw, "
                f"normalized against what reference - and it must not arrive as a "
                f"silently populated column.")
        if board["meta"]["missing_ranks"]:
            warnings.append(
                f"ranks missing from the published sequence: "
                f"{board['meta']['missing_ranks'][:12]}. Kept verbatim; the board "
                f"is labelled by its published extent "
                f"({board['meta']['board_size']}), not by its row count.")
        if not board["meta"]["rank_is_global"]:
            warnings.append(
                f"SCOPED BOARD: this is a {board['meta']['scope']}, so its rank "
                f"orders that pool only and is NOT comparable with a whole-class "
                f"rank. draft_export averages the latest rank per SOURCE, so the "
                f"published rank is withheld from the `rank` column and preserved "
                f"at _extras.ba_scope_rank instead.")
        if board["pool_disagreements"]:
            by_kind: dict[str, int] = {}
            for d in board["pool_disagreements"]:
                by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
            warnings.append(
                f"pool disagreements {by_kind} over {len(board['rows'])} rows. The "
                f"BOARD-level pool wins in every case; these are counted so an "
                f"override of a board-level truth is visible rather than silent.")
        if resolve:
            board["identity"] = resolve_draft_identities(
                board["rows"], meta["class_year"])
        return board

    board = parse_board(text, meta)
    board["content_evidence"] = evidence
    board["refusals"] = refusals
    # Warnings raised INSIDE parse_board (currently only the unpopulated header
    # counter) join the dating warnings, so one list carries everything a reader
    # of the artifact has to see.
    board["warnings"] = warnings + list(board["meta"].get("parse_warnings") or [])

    # The org-list guard applies to ORG boards only. A global Top 100 is the
    # case the guard exists to let through: its rank IS globally meaningful, so
    # requiring it to look like an org list would be exactly backwards. Assert
    # the inverse instead, so a global board that somehow built an org-shaped
    # label is refused just as loudly.
    if board["meta"].get("is_global"):
        # A GLOBAL board carries its org PER ROW. An org-less pro row is worse
        # than useless on the board, so an unmapped club is a refusal, not a
        # shrug: it means BA changed a club spelling and every row using it would
        # otherwise be ingested with org NULL.
        unmapped = sorted({r["club_line"] for r in board["rows"]
                           if r.get("club_line") and not r.get("row_org")})
        missing_club = [r["rank"] for r in board["rows"] if not r.get("club_line")]
        if unmapped or missing_club:
            refusals.append(
                f"global board rows carry a club this tree cannot map: "
                f"unmapped {unmapped}, no club line at rank(s) {missing_club[:12]}. "
                f"On a global list the club is a per-row fact and meta['org'] is "
                f"None, so these rows would be ingested with no org at all.")
        if validate_org_label(board["meta"]["interval_label"]) is None:
            refusals.append(
                f"interval_label {board['meta']['interval_label']!r} is a GLOBAL "
                f"board but MATCHES consensus._ORG_LIST_LABEL_RE, so it would be "
                f"treated as an org list and its ranks would be withheld from "
                f"implied_fv_from_rank. A global list's rank is meaningful and "
                f"must not carry org-list protection.")
    else:
        label_problem = validate_org_label(board["meta"]["interval_label"])
        if label_problem:
            refusals.append(label_problem)

    # An unknown risk label is a genuine format change and must not pass
    # silently: it means either a new BA vocabulary or a parse landing in the
    # wrong field, and both put a wrong number in an FV column downstream.
    unknown_risks = sorted({
        r["ba_risk"] for r in board["rows"]
        if r["ba_risk"] and r["ba_risk"].strip().lower() not in KNOWN_RISK_LABELS})
    if unknown_risks:
        refusals.append(
            f"unrecognised risk label(s) {unknown_risks}. Known vocabulary is "
            f"{sorted(KNOWN_RISK_LABELS)}. A new label needs its penalty derived "
            f"against a board that publishes an Adjusted Grade before it is used.")
    board["unknown_risks"] = unknown_risks

    # Adjusted-grade identity audit over the whole board.
    broken = [r for r in board["rows"] if r["adjusted_identity_ok"] is False]
    board["adjusted_identity_failures"] = [
        {"rank": r["rank"], "name": r["player_name"], "raw": r["ba_raw_grade"],
         "risk": r["ba_risk"], "published_adjusted": r["fv"],
         "expected_adjusted": r["adjusted_expected"]} for r in broken]

    board["tool_issues"] = [
        {"rank": r["rank"], "name": r["player_name"], **issue}
        for r in board["rows"] for issue in r["tool_issues"]]

    # PRE-2017 SCALE HAZARD. grade_normalization corrects each source onto the
    # FanGraphs FV scale, keyed by (source, role, cycle-year), REFERENCE
    # "fangraphs". FanGraphs in this database starts 2017-02-15, so a pre-2017
    # BA board has no contemporaneous reference and the thin-cell fallback
    # pools the overlap across ALL years INCLUDING FUTURE ONES
    # (grade_normalization.py:120-127). That is leak D1 of the audit plan,
    # reproduced on a new source. The parser stamps the era and refuses to
    # guess; choosing a basis is a modelling decision with its own gate.
    board["pre_fangraphs_era"] = snapshot_date < "2017-02-15"

    if resolve:
        board["identity"] = resolve_identities(board["rows"], meta["org"],
                                               snapshot_date=snapshot_date)
    return board


def insert_ba_snapshots(snaps: list[Snapshot]) -> int:
    """Write BA rows into `snapshots` ONLY, never into `players`.

    This deliberately does NOT reuse storage.insert_snapshots, and the reason is
    a live hazard rather than a style preference. That helper also upserts the
    `players` identity row with

        org         = COALESCE(excluded.org, players.org)
        player_name = excluded.player_name

    so the INCOMING value wins in both cases. These are HISTORICAL boards: a
    2023 org list carries each player's 2023 club, and pushing that through
    would rewrite `players.org` to a three-year-old team for everyone who has
    since been traded. The corpus is full of them (Arjun Nimmala reads TOR on
    the 2026 Blue Jays board and LAA in the database today, which is correct on
    both counts). It would also overwrite accented names with BA's ASCII
    spelling, turning "Jose Rodriguez" into the stored form of a player the
    database currently has as "Jose Rodriguez" with the accents.

    Writing only `snapshots` is safe because `org` there is a per-row,
    per-source, per-date fact, which is exactly what a board publishes. And no
    `players` row ever needs creating: resolve_identities settles onto keys that
    already exist and sends everything else to the unresolved report, so an
    unknown player is never written at all.
    """
    import storage
    n = 0
    with storage.connect() as con:
        for s in snaps:
            tools_json = json.dumps(s.tools) if s.tools else None
            cur = con.execute(
                """INSERT INTO snapshots
                     (source, snapshot_date, interval_label, player_key,
                      player_name, position, org, rank, fv, status,
                      tools_json, fv_plus)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                     snapshot_date = excluded.snapshot_date,
                     position      = COALESCE(excluded.position, snapshots.position),
                     org           = COALESCE(excluded.org, snapshots.org),
                     rank          = excluded.rank,
                     fv            = excluded.fv,
                     status        = excluded.status,
                     tools_json    = COALESCE(excluded.tools_json, snapshots.tools_json),
                     fv_plus       = excluded.fv_plus""",
                (s.source, s.snapshot_date, s.interval_label, s.player_key,
                 s.player_name, s.position, s.org, s.rank, s.fv, s.status,
                 tools_json, 1 if s.fv_plus else 0),
            )
            n += cur.rowcount
    return n


def ingest_drops(*, apply: bool = False, resolve: bool = True,
                 inbox: Path | None = None) -> dict:
    """Walk the inbox. Parse, report, and only write to the DB under apply."""
    inbox = inbox or INBOX_DIR
    files = sorted(p for p in inbox.glob("ba__*.md"))
    results, wrote = [], 0
    for path in files:
        entry: dict = {"file": path.name}
        try:
            board = process_file(path, resolve=resolve)
        except BoardFormatError as exc:
            entry.update({"status": "REFUSED", "reason": str(exc)})
            results.append(entry)
            continue

        entry.update({
            "status": "REFUSED" if board["refusals"] else "PARSED",
            "meta": board["meta"],
            "refusals": board["refusals"],
            "warnings": board["warnings"],
            "is_draft": bool(board.get("is_draft")),
            "unknown_risks": board["unknown_risks"],
            # What this board actually carries, so a season whose format lost a
            # whole field shows up as a number rather than as silence.
            "coverage": {
                k: sum(1 for r in board["rows"] if r.get(k) not in (None, "", {}))
                for k in (("fv", "position", "school", "college_commit",
                           "player_type", "age_at_draft", "height")
                          if board.get("is_draft") else
                          ("fv", "ba_raw_grade", "ba_risk", "tools", "position",
                           "age", "previous_rank", "row_org"))
            },
            "n_rows": len(board["rows"]),
            "adjusted_identity_failures": board["adjusted_identity_failures"],
            "tool_issues": board["tool_issues"],
            "pre_fangraphs_era": board["pre_fangraphs_era"],
            "content_evidence": {
                "in_season_count": board["content_evidence"]["in_season_count"],
                "latest_explicit_date": board["content_evidence"]["latest_explicit_date"],
                "years_referenced": board["content_evidence"]["years_referenced"],
            },
        })
        if resolve and board.get("is_draft"):
            ident = board["identity"]
            entry["identity"] = {
                "n_resolved": ident["n_resolved"],
                "n_unresolved": 0,
                "unresolved": [],
                "n_distinct_keys": ident["n_distinct_keys"],
                "key_collisions": ident["key_collisions"],
            }
            entry["pool_split"] = _count_by(board["rows"], "player_type")
            entry["pool_disagreements"] = board["pool_disagreements"]
        elif resolve:
            ident = board["identity"]
            entry["identity"] = {
                "n_resolved": ident["n_resolved"],
                "n_unresolved": ident["n_unresolved"],
                "unresolved": ident["unresolved"],
                "org_mismatch": ident["org_mismatch"],
                # A row the admission bar refused is a row this board WOULD have
                # merged onto the wrong human. It is reported at the same level
                # as an unresolved name, never buried in a count.
                "n_quarantined": ident["n_quarantined"],
                "quarantined": ident["quarantined"],
                "admitted_with_conflict": ident["admitted_with_conflict"],
            }

        out_csv = PROCESSED_DIR / (path.stem + ".csv")
        if board.get("is_draft"):
            _write_draft_csv(board, out_csv)
        else:
            _write_normalized_csv(board, out_csv)
        # relative_to RAISES when the processed dir is not under the repo, which
        # is exactly the shape a test (or a relocated drop tree) uses. The
        # artifact path is a report field, so it must never be the thing that
        # aborts an ingest mid-walk.
        try:
            entry["normalized_csv"] = str(out_csv.relative_to(_BASE))
        except ValueError:
            entry["normalized_csv"] = str(out_csv)

        if apply and not board["refusals"]:
            # THE BRANCH THAT MUST NEVER FALL THROUGH. A draft board writes
            # draft_snapshots (and draft_players, inside the storage helper) and
            # NOTHING ELSE. An amateur reaching `snapshots` would join the active
            # prospect pool, and from there consensus FV, the prospect board and
            # the trade machine.
            if board.get("is_draft"):
                draft_rows = to_draft_rows(board)
                wrote += insert_ba_draft_snapshots(draft_rows)
                entry["inserted"] = len(draft_rows)
                entry["target_table"] = "draft_snapshots"
            else:
                snaps = to_snapshots(board)
                wrote += insert_ba_snapshots(snaps)
                entry["inserted"] = len(snaps)
                entry["target_table"] = "snapshots"
            archived = PROCESSED_DIR / path.name
            shutil.move(str(path), str(archived))
            try:
                entry["archived_to"] = str(archived.relative_to(_BASE))
            except ValueError:
                entry["archived_to"] = str(archived)
        results.append(entry)

    return {"files": len(files), "results": results, "rows_written": wrote,
            "applied": apply}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write parsed boards into prospects.db and archive the "
                         "source file (default is a dry run that only reports)")
    ap.add_argument("--no-resolve", action="store_true",
                    help="skip identity resolution (parse-only smoke test)")
    ap.add_argument("--inbox", default=None)
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = ingest_drops(apply=args.apply, resolve=not args.no_resolve,
                          inbox=Path(args.inbox) if args.inbox else None)

    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return 1 if any(r["status"] == "REFUSED" for r in report["results"]) else 0

    print(f"{report['files']} board file(s) in the inbox\n")
    refused = 0
    for r in report["results"]:
        print(f"--- {r['file']}: {r['status']}")
        if r["status"] == "REFUSED" and "reason" in r:
            refused += 1
            print(f"    {r['reason']}")
            continue
        m = r.get("meta", {})
        if r.get("is_draft"):
            print(f"    DRAFT class {m.get('class_year')} {m.get('scope')}, "
                  f"{r['n_rows']} rows, snapshot_date {m.get('snapshot_date')} "
                  f"(publication date from filename) -> draft_snapshots")
            print(f"    rank is {'GLOBAL' if m.get('rank_is_global') else 'SCOPE-LOCAL (withheld from rank column)'}")
        else:
            print(f"    {m.get('team_name')} {m.get('season')} {m.get('board')}, "
                  f"{r['n_rows']} rows, snapshot_date {m.get('snapshot_date')} "
                  f"({m.get('snapshot_date_basis')})")
        print(f"    label: {m.get('interval_label')!r}")
        cov = r.get("coverage") or {}
        if cov:
            print("    coverage: " + "  ".join(
                f"{k}={v}/{r['n_rows']}" for k, v in cov.items()))
        for msg in r.get("refusals") or []:
            refused += 1
            print(f"    REFUSED: {msg}")
        for msg in r.get("warnings") or []:
            print(f"    warn: {msg}")
        if r.get("pre_fangraphs_era"):
            print("    NOTE pre-2017: no contemporaneous FanGraphs reference to "
                  "normalize against. Basis is a gated modelling decision.")
        for f in r.get("adjusted_identity_failures") or []:
            print(f"    ADJUSTED-GRADE IDENTITY BROKE at rank {f['rank']} "
                  f"({f['name']}): {f['raw']} - penalty({f['risk']}) = "
                  f"{f['expected_adjusted']}, board published {f['published_adjusted']}")
        for t in r.get("tool_issues") or []:
            print(f"    TOOL {t['kind']} at rank {t['rank']} ({t['name']}): {t}")
        if r.get("pool_split"):
            print(f"    player_type split: {r['pool_split']}")
        for d in (r.get("pool_disagreements") or [])[:8]:
            print(f"      POOL DISAGREEMENT rank {d['rank']} ({d['name']}): board "
                  f"says {d['board_pool']}, {d['kind']} says {d['row_pool']} "
                  f"(school {d['school']!r}, age {d['age_at_draft']}). Board wins.")
        ident = r.get("identity")
        if ident and ident.get("key_collisions") is not None:
            print(f"    identity: {ident['n_resolved']} rows -> "
                  f"{ident['n_distinct_keys']} distinct draft keys, "
                  f"{len(ident['key_collisions'])} collision(s)")
            for c in ident["key_collisions"]:
                print(f"      KEY COLLISION {c['player_key']}: ranks {c['ranks']} "
                      f"{c['names']}")
        elif ident:
            print(f"    identity: {ident['n_resolved']} resolved, "
                  f"{ident['n_unresolved']} unresolved, "
                  f"{ident.get('n_quarantined', 0)} quarantined")
            for u in ident["unresolved"]:
                print(f"      UNRESOLVED rank {u['rank']}: {u['name']} "
                      f"(would be {u['would_be_key']})")
            for q in ident.get("quarantined") or []:
                print(f"      QUARANTINED rank {q['rank']}: {q['name']} would "
                      f"have merged onto {q['player_key']} - {q['reason']}")
            for a in ident.get("admitted_with_conflict") or []:
                print(f"      ADMITTED WITH CONFLICT rank {a['rank']}: {a['name']} "
                      f"on {a['player_key']} - {a['reason']}")
            for o in ident["org_mismatch"]:
                print(f"      ORG MISMATCH rank {o['rank']}: {o['name']} "
                      f"board {o['board_org']} vs db {o['db_org']}")
        print(f"    normalized csv -> {r['normalized_csv']}")
    if report["applied"]:
        print(f"\nwrote {report['rows_written']} snapshot rows")
    else:
        print("\nDRY RUN. Nothing was written to prospects.db. Re-run with --apply.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
