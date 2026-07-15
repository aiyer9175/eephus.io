# PATCH_NOTES -- BUCKET-AGE-HEAD candidate wiring (2026-07-15)

**STATUS: DO NOT SHIP. The pre-registered gate FAILED (G4 grade monotone-sanity;
see SUMMARY.md / results.json). These files are the exact candidate
implementation, preserved for the mandatory re-run (rerun_marker) so a future
PASS can ship without re-derivation. Nothing here has been applied to the repo
tree (workspace-only copies).**

## Files

- `patched/value_framework.py` -- full-file copy of the production module plus
  the head. Verified: `p_bucket_given_fv` output is byte-identical to
  production across fv 20-80 x both roles (max abs diff 0.0), so its five
  non-eFV consumers are untouched.
- `patched/efv_score.py` -- full-file copy; ONE functional line changes.
- `patched/data/xfv_bucket_age_head.json` -- the fitted production head cells
  (resolved labeled pitcher matrix, n=1569, all decision years), with the
  shrink constant, band conventions, provenance, and the rerun marker.

## What was added to value_framework.py

New code only (no existing function bodies changed except one cache-clear line):

1. `_bucket_age_head()` -- `lru_cache` loader for
   `data/xfv_bucket_age_head.json`. Missing/malformed file returns None: the
   head is an overlay, never a dependency (the `_fitted()` pattern).
2. `_bucket_age_band(age)` -- `le22` (age<23) / `23_24` (23<=age<25) /
   `25p` (age>=25); None/non-finite -> None.
3. `p_bucket_given_fv_age(fv, is_pitcher, age=None)` -- PIT-ONLY head:
   `w*emp + (1-w)*p_bucket_given_fv(fv, True)` with `w = n/(n+25)` for the
   `(int(round(fv/5)*5), age_band)` cell; hitters, missing age, missing head
   file, or unfitted bands return the incumbent exactly (verified equal).
4. `_reset_caches()` additionally clears `_bucket_age_head` (it reads a data
   file, same reason `_fitted` is cleared). This is the only touched existing
   function; it has no output surface.

## What was changed in efv_score.py

`run_live()` only (the live-board scorer). The published live 5-bucket outcome
odds line:

```python
probs = vf.p_bucket_given_fv(xfv_grade, is_pit) or []
```

becomes

```python
probs = vf.p_bucket_given_fv_age(xfv_grade, is_pit, age=age) or []
```

using the `age` already computed for surplus pricing (age_now, falling back to
`_age_at(birth_date, CURRENT_SEASON)`). Hitter rows and age-less rows are
unchanged by construction (helper falls back to the incumbent). The resolved
view `run()` and the backgrade path keep the incumbent (the design scopes the
head to live pit scoring).

DELIBERATELY NOT WIRED: the standalone `p_bust` chip and `dist.p_bust` still
read `vf.sv_distribution` (the engine's ETA-decayed distribution). Overriding
them with the head would change pit rows beyond the head itself whenever
`eta != 1`; aligning the chip with `p_bucket.bust` is a ship-time owner
decision, flagged inline.

## Verification (verify_patch.py, all passed)

1. Incumbent `p_bucket_given_fv`: prod vs patched max abs diff **0.0**
   (241 grades x 2 roles).
2. Head parity vs the gate lab's `head_prob`: max abs diff **2.2e-16**
   (241 grades x 9 ages).
3. Fallback identity (hitter / age None / unfitted band / fv None): exact.
4. `patched/efv_score.py` byte-compiles; unified diff shows exactly one
   functional line + comment block.

## Ship checklist IF a future re-run passes (per the rerun marker)

- Re-fit `xfv_bucket_age_head.json` on the then-current resolved matrix.
- Move the head JSON into repo `data/`, apply both file diffs, golden bump,
  registry row + eval artifact (model-audit standing rule), copy_lint.
- Decide the `p_bust` chip alignment (above).
- F-SIDE standing gates S1-S5 must be re-checked (the head changes published
  pit outcome odds; S3 references pit BENCH/GOOD log-loss).
