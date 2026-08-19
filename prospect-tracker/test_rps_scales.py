"""RPS+ three-scales resolution (2026-08-19, owner default): rename per surface
plus the inert-term removal.

Background (2026-08-14 audit finding): three surfaces served three different
scales under the single name `rps_plus`:

  active board -> in-browser cohort RATIO, 100 * (raw+100) / (cohort mean+100),
                  position-adjusted, clamp 0-250 (prospx _buildRpsPlusCache)
  draft        -> 100 + 15z off college perf, clamp 60-140 (draft_export.py)
  overseas     -> 100 + 15z within league cohort, pitcher sign-flipped
                  (overseas_export.py)

and the active TBS branch carried a statline.rps_plus term (weight 0.22) that
was NEVER populated (0 of 4,505 rows), so the term was silently inert on
actives for its whole life.

Resolution under test:
  1. The draft payload key is `rps_draft_plus`, the overseas key is
     `rps_intl_plus`, the active board keeps the browser ratio. Distinct names
     end-to-end.
  2. No consumer reads the retired shared name where it no longer exists
     (exporters, the prospx client, and the other in-repo payload readers).
  3. TBS parity: removing a never-present term from a presence-filtered,
     weight-renormalized composite is an exact no-op, and the active branch
     weights are frozen at their pre-change values.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).parent
PROSPX = HERE / "prospx" / "index.html"
DRAFT_EXPORT = HERE / "draft_export.py"
OVERSEAS_EXPORT = HERE / "overseas_export.py"

# In-repo readers of the draft / overseas payloads (grep-established
# 2026-08-19). If a new reader appears it must use the per-surface keys.
OTHER_PAYLOAD_READERS = [
    "draft_source_backtest.py",
    "efv_score.py",
    "fa_market.py",
    "headshots.py",
    "ifa_export.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_line_comments(text: str) -> str:
    """Drop // line comments (start-of-line or whitespace-preceded, so URLs
    like https:// survive) and <!-- --> blocks, leaving live code only."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    out = []
    for line in text.splitlines():
        stripped = re.sub(r"(^|\s)//.*$", r"\1", line)
        out.append(stripped)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 1. Three scales, three names, end-to-end
# ---------------------------------------------------------------------------

def test_draft_export_serves_rps_draft_plus_on_the_draft_scale():
    src = _read(DRAFT_EXPORT)
    # The draft key exists and carries the draft scale: 100 + 15z, clamp 60-140.
    assert 'p["rps_draft_plus"] = max(60, min(140, int(round(100 + 15 * cperf_z_p))))' in src
    assert 'p["rps_draft_plus"] = None' in src


def test_overseas_export_serves_rps_intl_plus_with_pitcher_sign_flip():
    src = _read(OVERSEAS_EXPORT)
    # The intl key exists, pitcher side sign-flipped (lower_better=True).
    assert 'p["rps_intl_plus"] = _cohort_plus(raw_perf_pit, ps_raw, lower_better=True)' in src
    assert 'p["rps_intl_plus"] = _cohort_plus(raw_perf_hit, ps_raw, lower_better=False)' in src
    # The intl scale is 100 + 15z, clamp 60-140, inside _cohort_plus.
    assert "return max(60, min(140, int(round(100 + 15 * z))))" in src


def test_active_board_keeps_the_browser_ratio_scale():
    src = _read(PROSPX)
    # The active RPS+ is the cohort ratio with the 0-250 clamp.
    assert "plus = (100 * (raw + 100) / (m + 100));" in src
    assert "plus = Math.round(Math.max(0, Math.min(250, plus)));" in src


def test_prospx_tbs_reads_the_per_surface_keys():
    src = _read(PROSPX)
    assert "(p.rps_draft_plus != null) ? p.rps_draft_plus : null" in src
    assert "(p.rps_intl_plus  != null) ? p.rps_intl_plus  : null" in src
    # Each branch consumes its own surface's key.
    assert "_tbsNorm(rpsDraftPlus,  80, 130), 0.21" in src
    assert "_tbsNorm(rpsIntlPlus,   80, 130), 0.20" in src


def test_three_names_are_distinct():
    names = {"rps_draft_plus", "rps_intl_plus", "rps_plus"}
    assert len(names) == 3


# ---------------------------------------------------------------------------
# 2. No consumer reads the retired shared name where it no longer exists
# ---------------------------------------------------------------------------

def test_exporters_no_longer_write_the_shared_key():
    for path in (DRAFT_EXPORT, OVERSEAS_EXPORT):
        src = _read(path)
        assert 'p["rps_plus"]' not in src, f"{path.name} still writes rps_plus"


def test_prospx_has_no_live_member_read_of_rps_plus():
    # `.rps_plus` member reads covered payload fields (p.rps_plus,
    # statline.rps_plus, sl.rps_plus). All are retired; the string id
    # "rps_plus" (leaderboard stat key, glossary term, scatter axis) is the
    # ACTIVE browser metric id and legitimately stays.
    live = _strip_line_comments(_read(PROSPX))
    hits = [
        (i + 1, line.strip())
        for i, line in enumerate(live.splitlines())
        if re.search(r"\.rps_plus\b", line)
    ]
    assert not hits, f"live member reads of retired rps_plus remain: {hits}"


def test_other_payload_readers_do_not_use_the_shared_key():
    for name in OTHER_PAYLOAD_READERS:
        path = HERE / name
        if not path.exists():
            continue
        assert "rps_plus" not in _read(path), f"{name} reads the retired shared key"


# ---------------------------------------------------------------------------
# 3. TBS parity: removing the never-present term is an exact no-op
# ---------------------------------------------------------------------------

def _tbs_base(parts):
    """Mirror of _tiebreakerScoreRaw's aggregation: presence-filter, then
    weight-renormalize (prospx/index.html, the loop over `parts`)."""
    present_sum = 0.0
    present_weight = 0.0
    for v, w in parts:
        if v is not None:
            present_sum += v * w
            present_weight += w
    if present_weight == 0:
        return 0.0
    return 100.0 * present_sum / present_weight


def test_tbs_parity_removing_null_rps_term_is_exact():
    # Fixture: active-branch part values (already _tbsNorm-ed to 0-1), spanning
    # full, partial, and near-empty signal rows. The OLD shape carried
    # [None, 0.22] for the statline.rps_plus term; the NEW shape omits it.
    fixtures = [
        [0.80, 0.55, 0.40, 0.30, 0.62, 0.50],
        [0.10, None, 0.95, None, 0.33, 0.00],
        [None, None, None, None, 0.50, None],
        [1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [None, None, None, None, None, None],
    ]
    weights = [0.24, 0.20, 0.10, 0.08, 0.10, 0.06]
    for vals in fixtures:
        old_parts = list(zip(vals, weights)) + [(None, 0.22)]  # inert term
        new_parts = list(zip(vals, weights))                    # term removed
        assert _tbs_base(old_parts) == _tbs_base(new_parts), (
            "removing a null term changed the renormalized composite"
        )


def test_active_tbs_weights_frozen_at_pre_change_values():
    # The active branch's parts list, as shipped BEFORE this change (the
    # statline.rps_plus weighted read was already gone since 2026-07-29; this
    # change only deleted a dead unused local). Byte-identical composite
    # requires these exact weights, in this order.
    src = _read(PROSPX)
    active = re.search(
        r"ACTIVE MiLB TBS.*?parts = \[(.*?)\];", src, flags=re.DOTALL
    )
    assert active, "active TBS parts list not found"
    block = active.group(1)
    weights = re.findall(r",\s*(0\.\d+)\]", block)
    assert weights == ["0.24", "0.20", "0.10", "0.08", "0.10", "0.06"], (
        f"active TBS weights moved: {weights}"
    )
    # And no rps term rides in the active parts list.
    assert "rps" not in _strip_line_comments(block).lower()


def test_active_tbs_branch_has_no_dead_rps_local():
    # The leftover `const rps = _rpsPlusValue(p)` local (computed, never used)
    # was deleted 2026-08-19. The active branch must not reintroduce it
    # without a gate (see the in-file comment: reviving the term moves served
    # ordering and dollars).
    src = _read(PROSPX)
    fn = re.search(
        r"function _tiebreakerScoreRaw\(p, opts\) \{(.*?)\n\}", src, flags=re.DOTALL
    )
    assert fn, "_tiebreakerScoreRaw not found"
    body = _strip_line_comments(fn.group(1))
    assert "_rpsPlusValue" not in body, "dead rps local is back in TBS"
    assert "statline.rps_plus" not in body


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failures else 0)
