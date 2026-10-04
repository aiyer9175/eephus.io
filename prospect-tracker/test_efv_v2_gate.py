# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-15 pins (docs/efv-v2/DRIVER_SYSTEM_V2.md s5): the eFV v2 registration draft and the
registered statistic.

1. docs/efv-v2/EFV_V2_GATE.md exists, is marked DRAFT, has an empty results section, and
   carries the numbers it names from their artifacts (the weights, the statistic's
   constants).
2. A DRAFT never opens the reserved guard: gate_sha_committed is False for a commit whose
   gate document is a draft, True only for one marked REGISTERED (checked on a scratch
   repository), and the guard refuses every reserved vintage without it.
3. efv_v2_stat: the identical output map leaves consensus unchanged and the within
   statistic blind to it; groups below MIN_GROUP_ROWS leave the within statistic; the
   paired interval is deterministic and zero for a rater against itself.
4. No em-dash in the draft; nothing groups by consensus-FV level.
5. s10, the screening lab: registered text, no number from any read.
6. Amendment A6: the R-VM look sizes in s2.2 are efv_rvm_look_n's counts on data/debuts.json
   (within 5 rows per side), its floors are the [S] arithmetic, and the count reads no outcome.

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

import efv_v2_stat as S
import efv_vintage_frame as F

ROOT = Path(__file__).parent
GATE = ROOT / F.GATE_DOC
ASSEMBLY = ROOT / "data" / "efv_v2_assembly.json"


def _text() -> str:
    if not GATE.exists():
        pytest.skip("docs/efv-v2/EFV_V2_GATE.md absent")
    return GATE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. the draft
# ---------------------------------------------------------------------------

def test_the_gate_is_a_draft_until_its_preconditions_hold():
    t = _text()
    status = [ln.strip() for ln in t.splitlines()
              if ln.strip().startswith(F.GATE_STATUS_PREFIX)]
    assert status == ["Registration status: DRAFT"]
    assert F.gate_doc_registered(t) is False
    for pid in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
        assert f"| {pid} |" in t, pid


def test_results_section_is_empty():
    t = _text()
    # s9 runs to the next rule or heading (s10, the screening lab, follows it)
    body = re.split(r"\n(?:---|## )", t.split("## 9. Results", 1)[1], maxsplit=1)[0]
    body = body.strip()
    assert body.startswith("(Empty.") and body.count("\n") == 0


def test_the_draft_names_the_statistic_and_its_disclosure():
    t = _text()
    for s in ("within (side, vintage)", "pooled", "identical output map",
              "vm1", "S1", "+0.0058", "-0.0131", "+0.018", "-0.008"):
        assert s in t, s
    assert f"at least {S.MIN_GROUP_ROWS} rows" in t
    assert f"B {S.B_DEFAULT}" in t and f"seed {S.SEED_DEFAULT}" in t


def test_the_draft_carries_the_registered_weights():
    t = _text()
    if not ASSEMBLY.exists():
        pytest.skip("data/efv_v2_assembly.json not built")
    doc = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    w = doc["weights"]
    # P5 (2026-10-04, POST_EPOCH_REBUILD) re-derived the weights once on the frozen fWAR
    # label; s4.3 still prints the draft-time eWAR v2 table, and the draft is re-taken only
    # at registration (s4.6, P4), never edited above its part 9 by the re-derivation. The
    # pin returns by itself once s4.3 carries the assembly's weights.
    if ((doc.get("label") or {}).get("provider") == "fwar"
            and "| hit | 0.599508 |" in t and w["hit"]["w_skill"] != 0.599508):
        pytest.xfail("P5 re-derived the weights on the frozen fWAR label; the draft's "
                     "s4.3 re-take at registration (P4) is owed")
    for side in ("hit", "pit"):
        for k in ("w_skill", "w_time"):
            v = w[side][k]
            assert (f"{v:g}" in t) or (f"{v}" in t), (side, k, v)


def test_the_draft_carries_the_forking_path_count_and_b9():
    t = _text()
    for s in ("275", "347", "39 closed arms", "R-LV exposure", "B9a", "B9b",
              "reserved_vm", "W3 = 0"):
        assert s in t, s


def test_no_dash_characters_in_the_draft():
    t = _text()
    assert "—" not in t and "–" not in t


# ---------------------------------------------------------------------------
# 2. a draft never opens the guard
# ---------------------------------------------------------------------------

def test_gate_doc_registered_reads_only_the_final_status_line():
    reg = F.GATE_STATUS_REGISTERED
    assert F.gate_doc_registered(f"# t\n\n{reg}\n\nbody") is True
    assert F.gate_doc_registered(f"# t\n\n  {reg}  \r\nbody") is True
    assert F.gate_doc_registered("# t\n\nRegistration status: DRAFT\n") is False
    assert F.gate_doc_registered(f"{reg}\nRegistration status: DRAFT\n") is False
    assert F.gate_doc_registered(f"the final line will read {reg}\n") is False
    assert F.gate_doc_registered("") is False
    assert F.gate_doc_registered(None) is False


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_only_a_registered_commit_opens_the_guard(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "docs" / "efv-v2").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    doc = repo / F.GATE_DOC
    doc.write_text("# gate\n\nRegistration status: DRAFT\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "draft")
    draft = _git(repo, "rev-parse", "HEAD")
    doc.write_text(f"# gate\n\n{F.GATE_STATUS_REGISTERED}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "registered")
    final = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(F, "ROOT", repo)
    assert F.gate_sha_committed(draft) is False
    assert F.gate_sha_committed(final) is True
    with pytest.raises(F.ReservedFrameError):
        F.guard_score_request(2020, gate_sha=draft)
    F.guard_score_request(2020, gate_sha=final)


def test_the_committed_draft_does_not_open_the_guard():
    r = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%H", "--",
                        F.GATE_DOC], capture_output=True, text=True)
    sha = r.stdout.strip()
    if r.returncode != 0 or not sha:
        pytest.skip("the gate draft is not committed yet")
    shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha}:./{F.GATE_DOC}"],
                           capture_output=True, text=True, encoding="utf-8")
    if F.gate_doc_registered(shown.stdout):
        pytest.skip("the committed gate is REGISTERED")
    assert F.gate_sha_committed(sha) is False
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            F.guard_score_request(V, gate_sha=sha)


# ---------------------------------------------------------------------------
# 3. the statistic
# ---------------------------------------------------------------------------

def _toy(seed=7, groups=("hit|2017", "hit|2018", "pit|2017"), n=40):
    rng = np.random.default_rng(seed)
    g, c, y, a, keys = [], [], [], [], []
    for gi, name in enumerate(groups):
        cons = rng.choice([40.0, 45.0, 50.0, 55.0], size=n) + 5.0 * gi
        out = 0.1 * cons + rng.normal(0, 2, n)
        g += [name] * n
        c += cons.tolist()
        y += out.tolist()
        a += (cons + rng.normal(0, 3, n)).tolist()
        keys += [f"{name}:{i}" for i in range(n)]
    return keys, g, np.array(y), np.array(c), np.array(a)


def test_the_map_leaves_consensus_unchanged():
    _, g, _, c, _ = _toy()
    assert np.allclose(S.map_scores(c, g, c), c)


def test_the_within_statistic_reads_order_inside_groups_only():
    keys, g, y, c, a = _toy()
    codes = np.asarray(g)
    keep = S.kept_groups(codes)
    w_raw = S.within(a, y, codes, keep)[0]
    shifted = a * 3.0 + np.where(codes == "pit|2017", 100.0, 0.0)
    assert S.within(shifted, y, codes, keep)[0] == pytest.approx(w_raw, abs=1e-12)
    assert np.allclose(S.map_scores(shifted, g, c), S.map_scores(a, g, c))
    # the map keeps order inside a group (weakly: repeated consensus values tie rows)
    m = S.map_scores(a, g, c)
    for u in np.unique(codes):
        ix = np.where(codes == u)[0]
        o = ix[np.argsort(a[ix])]
        assert np.all(np.diff(m[o]) >= -1e-12)
        assert sorted(m[ix]) == pytest.approx(sorted(c[ix]))


def test_paired_within_reads_the_own_score_not_the_mapped_one():
    keys, g, y, c, a = _toy()
    pos = y > np.quantile(y, 0.8)
    d = S.paired_delta(keys, g, y, pos, a, c, c, statistic="within", B=60)
    codes = np.asarray(g)
    keep = S.kept_groups(codes)
    assert d["a"] == pytest.approx(round(S.within(a, y, codes, keep)[0], 5))


def test_small_groups_leave_the_within_statistic():
    keys, g, y, c, a = _toy(groups=("hit|2017", "pit|2017"), n=30)
    g = g[:30] + ["pit|2017"] * (S.MIN_GROUP_ROWS - 1) + ["x"] * (30 - S.MIN_GROUP_ROWS + 1)
    keep = S.kept_groups(np.asarray(g))
    assert "hit|2017" in keep and "pit|2017" not in keep and "x" not in keep
    val, n_rows, n_groups = S.within(a, y, np.asarray(g), keep)
    assert (n_rows, n_groups) == (30, 1)


def test_paired_delta_is_deterministic_and_zero_against_itself():
    keys, g, y, c, a = _toy()
    pos = y > np.quantile(y, 0.8)
    for stat in S.STATISTICS:
        same = S.paired_delta(keys, g, y, pos, a, a, c, statistic=stat, B=200)
        assert same["delta"] == 0.0 and same["ci95"] == [0.0, 0.0]
        one = S.paired_delta(keys, g, y, pos, a, c, c, statistic=stat, B=200)
        two = S.paired_delta(keys, g, y, pos, a, c, c, statistic=stat, B=200)
        assert one == two and one["status"] == "derived"
    with pytest.raises(ValueError):
        S.paired_delta(keys, g, y, pos, a, c, c, statistic="mean")


def test_the_within_point_is_the_size_weighted_mean_of_group_rhos():
    keys, g, y, c, a = _toy()
    codes = np.asarray(g)
    want, tot = 0.0, 0
    for u in np.unique(codes):
        m = codes == u
        rx = np.argsort(np.argsort(a[m]))
        ry = np.argsort(np.argsort(y[m]))
        want += np.corrcoef(rx, ry)[0, 1] * m.sum()
        tot += m.sum()
    got = S.within(a, y, codes, S.kept_groups(codes))[0]
    assert got == pytest.approx(want / tot, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. gate compliance
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv", "fv_band",
           "fv_bin")


def test_the_statistic_groups_nothing_by_grade():
    tree = ast.parse((ROOT / "efv_v2_stat.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)


def test_the_draft_names_no_fv_cell_stratum():
    t = _text().lower()
    assert not re.search(r"\bfv ?(35|40|45|50|55|60|65)\+? (cell|band|bucket|tier)", t)


# ---------------------------------------------------------------------------
# 5. s10, the screening lab (EFV3_B6): registered text, no number from any read
# ---------------------------------------------------------------------------

LAB = ROOT / "tools" / "efv_screen_lab.py"


def _s10() -> str:
    t = _text()
    assert "## 10. Screening lab" in t
    return t.split("## 10. Screening lab", 1)[1]


def _lab_wave() -> list[str]:
    """The frozen wave-1 names off the lab's source (no import: the lab pulls in the
    frame builders)."""
    tree = ast.parse(LAB.read_text(encoding="utf-8"))
    for node in tree.body:
        target = (node.target if isinstance(node, ast.AnnAssign) else
                  node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "CANDIDATES":
            return [kv.value for d in node.value.elts
                    for k, kv in zip(d.keys, d.values)
                    if isinstance(k, ast.Constant) and k.value == "name"]
    raise AssertionError("CANDIDATES not found in the lab")


def test_s10_lists_the_lab_s_frozen_wave_and_nothing_else():
    s10 = _s10()
    if not LAB.exists():
        pytest.skip("tools/efv_screen_lab.py absent")
    wave = _lab_wave()
    assert len(wave) == 7
    table = s10.split("### 10.9", 1)[1].split("### 10.10", 1)[0]
    listed = re.findall(r"^\| `(\w+)` \|", table, flags=re.M)
    assert listed == wave
    assert "m = 7" in s10 and "`seasons_at_level_pit` is not screened" in s10
    assert "seasons_at_level_pit" not in wave


def test_s10_carries_the_registered_rule():
    s10 = _s10()
    for s in ("B 2000", "seed 20260906", "one-sided 95% lower bound", "Three N(0,1) noise",
              "500-draw permutation null", "kill rule 1", "2026-11-15", "EPOCH_RUN",
              "Z1_RUN", "consensus-FV cell", "PROSPECT_ANCHOR_GATE",
              "NOT_ADJUDICATED_EXPLORATORY"):
        assert s in s10, s
    for clause in "abcdefg":
        assert f"({clause})" in s10, clause
    for v in ("PASS", "VETO_ON_AUC", "NULL", "NULL_AUC_ONLY", "NULL_HOLM",
              "NOT_ADJUDICATED_NO_RHO_FLOOR", "NOT_ADJUDICATED_NO_AUC_FLOOR",
              "NOT_ADJUDICATED_NO_HOLM"):
        assert f"`{v}`" in s10, v


def test_s10_holds_no_number_from_a_read():
    s10 = _s10()
    # rule constants only (B 2000, 500 draws, alpha 0.05, 1.645): no rho, delta, floor,
    # interval or share
    assert not re.search(r"(?<![\w.])[+-]?0\.\d{3,}", s10)
    assert not re.search(r"\d+(\.\d+)? ?(%|percent)\b", s10.replace("95%", ""))


# ---------------------------------------------------------------------------
# 6. the R-VM look sizes (amendment A6, s2.2): counts only, no outcome read
# ---------------------------------------------------------------------------

import efv_rvm_look_n as RVM  # noqa: E402

DEBUTS = ROOT / "data" / "debuts.json"
_LOOK_ROW = re.compile(
    r"^\|\s*look (\d)\s*\|[^|]+\|\s*(vm2|consensus_present)\s*\|\s*(\d*)\s*\|\s*(\d*)\s*\|"
    r"\s*(?:about )?([\d,]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|$")


def _look_rows() -> dict:
    t = _text()
    s22 = t.split("### 2.2 ", 1)[1].split("\n---", 1)[0]
    rows = {}
    for ln in s22.splitlines():
        m = _LOOK_ROW.match(ln.strip())
        if m:
            look, rule, hit, pit, n, mde, z, dn = m.groups()
            rows[(int(look), rule)] = {
                "hit": int(hit) if hit else None, "pit": int(pit) if pit else None,
                "n": int(n.replace(",", "")), "mde95": float(mde), "z": float(z),
                "delta_needed": float(dn)}
    return rows


class _Trap(dict):
    """A record that refuses any key the count must not read."""
    BANNED = ("career_war", "surplus", "fv_close", "fv_high", "fv_low", "fv_open",
              "debuted_value", "sabermetrics", "career_stats")

    def get(self, k, default=None):
        assert k not in self.BANNED, k
        return super().get(k, default)

    def __getitem__(self, k):
        assert k not in self.BANNED, k
        return super().__getitem__(k)


def _pt(date, cons=None, **src):
    return {"snapshot_date": date, "consensus_fv": cons,
            "per_source": {s: {"fv_published": v} for s, v in src.items()}}


def _fixture() -> list[dict]:
    return [
        # both scored sources inside the window: vm2 and consensus_present
        _Trap(player_key="a", debut_date="2025-06-01", position="SS",
              points=[_pt("2025-02-01", 45.0, fangraphs=45.0),
                      _pt("2025-03-01", 45.0, mlb_pipeline=50.0)]),
        # consensus only, one source: consensus_present only
        _Trap(player_key="b", debut_date="2025-07-01", position="RHP",
              points=[_pt("2025-02-10", 40.0, mlb_pipeline=40.0)]),
        # an April debut closes the window at the debut day: the later read is out
        _Trap(player_key="c", debut_date="2025-04-05", position="LHP",
              points=[_pt("2025-02-01", 50.0, fangraphs=50.0),
                      _pt("2025-04-20", 50.0, mlb_pipeline=50.0)]),
        # reads only in the prior year's window: counted as a debut, no rule
        _Trap(player_key="d", debut_date="2025-08-01", position="CF",
              points=[_pt("2024-03-01", 45.0, fangraphs=45.0, mlb_pipeline=45.0)]),
        # another cohort
        _Trap(player_key="e", debut_date="2026-05-01", position="C",
              points=[_pt("2026-02-01", 45.0, fangraphs=45.0, mlb_pipeline=45.0)]),
        # a side the routing cannot place
        _Trap(player_key="f", debut_date="2025-09-01", position="",
              points=[_pt("2025-02-01", None, fangraphs=40.0, mlb_pipeline=40.0)]),
    ]


def _side(rec):
    pos = rec.get("position") or ""
    return None if not pos else pos.endswith("HP")


def test_cohort_counts_on_a_fixture():
    c = RVM.cohort_counts(_fixture(), 2025, is_pitcher=_side)
    assert c["debuts"] == {"hit": 2, "pit": 2, "unknown": 1, "total": 5}
    assert c["vm2"] == {"hit": 1, "pit": 0, "unknown": 1, "total": 2}
    assert c["consensus_present"] == {"hit": 1, "pit": 2, "unknown": 0, "total": 3}
    nxt = RVM.cohort_counts(_fixture(), 2026, is_pitcher=_side)
    assert nxt["vm2"]["total"] == 1 and nxt["debuts"]["total"] == 1
    sizes = RVM.cohort_counts([], 2027, is_pitcher=_side)
    assert sizes["debuts"]["total"] == 0


def test_the_floor_tool_reproduces_the_program_probe():
    # [S] printed 0.0596 / 0.0421 / 0.0344 and delta needed 0.1161 / 0.0548 / 0.0354
    assert [RVM.mde95(n) for n in (210, 420, 630)] == [0.0596, 0.0421, 0.0344]
    assert [RVM.delta_needed(n, z) for n, z in zip((210, 420, 630), RVM.OBF_Z)] == \
        [0.1161, 0.0548, 0.0354]
    assert RVM.mde95(812) == 0.0303
    assert RVM.OBF_Z == (3.205, 2.141, 1.694)


def test_the_gate_floors_are_the_tool_at_the_printed_n():
    rows = _look_rows()
    assert {(1, "vm2"), (1, "consensus_present"), (2, "vm2"), (2, "consensus_present"),
            (3, "vm2"), (3, "consensus_present")} == set(rows)
    for (look, _rule), r in rows.items():
        assert r["z"] == RVM.OBF_Z[look - 1]
        assert r["mde95"] == RVM.mde95(r["n"])
        assert r["delta_needed"] == pytest.approx(RVM.delta_needed(r["n"], r["z"]), abs=1e-9)
        if r["hit"] is not None:
            assert r["hit"] + r["pit"] == r["n"]
    assert RVM.LOOK_RULE == "vm2"
    t = _text()
    assert "The rule the look uses: vm2, 149 rows at look 1." in t
    assert re.search(r"sha256\s+[0-9a-f]{64}", t.split("### 2.2 ", 1)[1].split("\n---", 1)[0])


def test_the_gate_look1_n_matches_the_count_on_disk():
    if not DEBUTS.exists():
        pytest.skip("data/debuts.json not built; the gate names the sha256 it was counted on")
    rows = _look_rows()
    debuts = json.loads(DEBUTS.read_text(encoding="utf-8"))
    c = RVM.cohort_counts(debuts, F.R_VM_FIRST_DEBUT_YEAR)
    for rule in RVM.RULES:
        g = rows[(1, rule)]
        for side in ("hit", "pit"):
            assert abs(c[rule][side] - g[side]) <= 5, (rule, side, c[rule][side], g[side])
        assert c[rule]["unknown"] <= 5


def test_the_program_row_carries_the_counted_n():
    prog = (ROOT / "docs" / "efv-v2" / "PROGRAM.md").read_text(encoding="utf-8")
    rows = _look_rows()
    vm2 = [rows[(k, "vm2")]["n"] for k in (1, 2, 3)]
    assert f"| {vm2[0]} / {vm2[1]} / about {vm2[2]} " in prog
    assert "| 210 / 420 / 630 |" not in prog


def test_the_count_reads_no_outcome_and_the_rvm_pins_hold():
    tree = ast.parse((ROOT / "efv_rvm_look_n.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in _Trap.BANNED, node.value
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else None)
        if name:
            assert "war" not in name.lower() and "outcome" not in name.lower(), name
            assert not any(t in name.lower() for t in _BANNED), name
    assert not imported & {"war_source", "efv_labels", "efv_model", "ewar", "efv_v2_stat"}
    assert F.reserved_vm_pins() == []


# ---------------------------------------------------------------------------
# 7. s8.1 to s8.4, the stratum matrix (EFV3_D5): registered text, no number from a read
# ---------------------------------------------------------------------------

def _s8() -> str:
    t = _text()
    return t.split("## 8. Hypotheses and decision rules", 1)[1].split("## 9. Results", 1)[0]


def test_s8_registers_the_strata_module_s_cells():
    import efv_strata as ST
    s8 = _s8()
    assert "### 8.1 The stratum matrix" in s8 and "efv_strata.py" in s8
    for dim in ST.DIMENSIONS:
        if dim in ("list_year", "source_disagreement"):
            continue
        for cell in ST.CELLS[dim]:
            assert cell in s8, (dim, cell)
    assert "FG minus Pipeline gap at or above 10 FV" in s8
    assert "at least 40 rows" in s8 and "789 of 2,862" in s8
    for frag in ("2026-11-20", "14 days after the fWAR epoch's step Z entry",
                 "PROSPECT_ANCHOR_GATE.md", "never by editing"):
        assert frag in s8, frag


def test_s8_carries_family_s_the_vocabulary_and_the_tier_freeze():
    s8 = _s8()
    for s in ("Family S clause", "E3-Q4 = A", "NO ship consequence", "descriptive by the gate",
              "_holm_family", "pooled (within degenerate: k groups)",
              "frozen pending the anchor look", "source_backtest._tier_table",
              "source_cohort_accuracy.py", "tools/efv_scoreboard.py"):
        assert s in s8, s
    for r in ("AHEAD", "BEHIND", "EQUIVALENT", "UNRESOLVED", "FLAGGED_UNCORRECTED",
              "UNPOWERED", "NOT_SCORED", "DEVELOPMENT", "RESERVED_PENDING"):
        assert f"| {r} |" in s8, r
    assert "LANE_D_cells.json" in _text().split("## 6. Forking paths", 1)[1].split("## 7.", 1)[0]


def test_s8_holds_no_number_from_a_read():
    s8 = _s8()
    # rule constants only (0.02, 0.05, 1.645, B 2000): no rho, delta, floor or interval
    assert not re.search(r"(?<![\w.])[+-]?0\.\d{3,}", s8.replace("1.645", ""))
