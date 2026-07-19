# Box handoff — 2026-07-19

Two feature sets landed on `main` this session need work that can ONLY run on the
production box (canonical `prospects.db` seed, current-vintage matrix, live StatsAPI,
owner restamp). Everything below is deferred to the box on purpose — the dev machine
cannot regenerate a served artifact without corrupting it (degraded-data rule), and
its matrix is a restored-from-git vintage so any gate here is PRELIMINARY.

Do these in order. Each step says what to run, what to check, and the rollback.

---

## A. Projections "Current (2026)" view — populate the live data

Commit `5937064`. The `#now=1` view renders nothing until an export bakes the
`current` block (it needs live StatsAPI standings + schedule, which fail on the dev
box). No gate — additive and dark-launched.

1. Run the normal nightly export (`run_monthly.py` daily tail, or
   `python -c "import proj_export; proj_export.export()"`).
2. **Check** `data/mlb_projections.json`: `current_season == 2026`, `mc_schedule_source`
   is `"live"` (or `"balanced_fallback"` if the schedule fetch missed), and a spot
   team's `team_outlook[i].current` has non-null `curWins`, `playoffPct`, `sos`.
3. **Verify** the board: open `/projections/#now=1&view=teams` — the Current (2026)
   slate shows records / Pythag / playoff-odds bars / SOS; `/projections/#view=teams`
   (no flag) is unchanged.
4. Promotion (optional, later): once soaked, flip `NOW_DEFAULT` in
   `assets/projections.js` to surface it without the `#now=1` flag.
5. **Rollback:** none needed — absent/failed data just hides the view.

---

## B. eFV levers — gates, then flip winners, then restamp

Commit `34983f2`. All number-moving levers are OFF by default. Run each gate on the
canonical matrix; flip ONLY the winners; then regenerate + restamp.

### B0. Prereqs
- Canonical `prospects.db` seed + a REAL matrix (`data/xfv_{hitter,pitcher}_matrix.json`
  with a non-zero `target_censored` column — the dev matrix is all-zero, which is why
  the gate abstained locally). Rebuild the matrix if needed:
  `python -c "import efv_dataset as d; [d.run(True,s) for s in ('hit','pit')]"`.

### B1. C1 reliability regen — already live, just confirm
- `regen_all` now calls `efv_reliability.build`. Run it (or a full `regen_all`):
  `python efv_reliability.py`.
- **Check** `data/xfv_reliability.json`: fresh `generated_at`, `tripwire.tripped`
  (expect `false` — the standing bust-bucket ECE ~0.12 is below the 0.14 threshold).
  Diagnostic only; no served number moves, no restamp.

### B2. P1 provisional prior — gate, then maybe flip
- **Run:** `python tools/efv_provisional_prior_lab.py` → `data/xfv_provisional_prior_eval.json`.
- **Clause 1 (do separately):** run the flagship eval OFF vs ON and assert bit-identity:
  ```
  # OFF (flag false): note data/xfv_eval.json pooled rho / MAE / AUC
  # temporarily set efv_provisional_prior.enabled: true, re-run efv_model.run for both sides
  # assert the eval metrics are byte-identical (provisional rows are NOT in that eval)
  ```
  Any change ⇒ a leak into the flagship path ⇒ STOP, it's a bug, do not ship.
- **Verdict:** PASS all of clauses 1-5 (see `docs/efv-provisional-prior/GATES.md`) ⇒
  set `efv_provisional_prior.enabled: true` in `value_framework_config.yaml`.
  FAIL ⇒ commit the eval artifact as a committed loss, leave the flag false.
- **Sanity:** confirm the Cholowsky/Gracia rows move UP and no low-pedigree twin does.

### B3. S1 super-two blend — gate, then maybe flip
- Wire the callers to pass `super_two_known=False` for genuinely-unknown serviced
  players (today every call uses the default `True`, so S1 is inert until a caller
  opts in). Then run the surplus backtest (`surplus_backtest_real.py`).
- **Verdict:** clauses in `docs/surplus-levers/GATES.md#s1`. PASS ⇒ set
  `surplus_levers.super_two_population_blend: true`. FAIL ⇒ committed loss.

### B4. S2 positional scarcity — EXPECTED COMMITTED LOSS, do not ship the current table
- The `trade_value.positional_scarcity` table is AAV-fit and double-counts the
  positional value already in WAR. Clause 0 of `docs/surplus-levers/GATES.md#s2`
  fails by construction on that table. **Leave both S2 flags false**; only revisit
  after a clean, non-AAV re-estimation of the multiplier. Record the loss.

### B5. Regenerate + restamp (only for levers that PASSED)
- `python efv_export.py --all` (or the nightly `regen_all`) to rebuild `data/xfv.json`;
  `python bayes_trade_value.py` path to rebuild `data/trade_values.json` (now carrying
  `xfv_war_6yr` for the TM tiebreak regardless of P1/S1/S2).
- **Owner restamp:** review the golden diff of `data/xfv.json` / `data/trade_values.json`
  and commit the served-number change with the gate verdict in the message (program
  rule: landed model changes move to `CHANGELOG.md` with their commit).
- **Rollback:** flip the lever's flag back to `false` and re-run the export; the flags
  make every lever independently reversible without a code revert.

### B6. TM tiebreak — no gate, ships with the next export
- `data/trade_values.json` will carry `xfv_war_6yr` after any export (B5 or a nightly);
  `assets/trademachine.js` already uses it. **Check** a `$0`-floor tie block on
  `/trademachine/` now orders by projected WAR within the same grade.

---

## Regenerated audit docs
After any served-number change, regenerate (never hand-edit) the registry/audit docs:
`python tools/gen_audit_docs.py` → `MODEL_REGISTRY.md` / `SITE_MAP.md` / `DATA_SOURCES.md`.
