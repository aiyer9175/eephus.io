# Consumer Map

Required Final Deliverable. The polished, final version of `CONSUMER_AUDIT.md` — who consumes what, once implementation reaches the exit criteria in `IMPLEMENTATION_ROADMAP.md`. Presented as a target-state map, with today's actual (empty) state stated plainly alongside it.

| Module | Today's real consumer | Target consumer (post-implementation) | Implementation phase that builds the wiring |
|---|---|---|---|
| Module 1 (Stuff) | None | `stuff_plus_aaa`'s own model (as additional features) **or** a new standalone PROSPX pitcher-card surface — decided by Phase A's outcome, not both | A |
| Module 2 (Arsenal) | None | A new field on the same surface Module 3 lands on (no separate page) | B, C |
| Module 3 (Miss, tracked) | None | PROSPX pitcher cards, alongside `stuff_plus_aaa`'s existing pill | C |
| Module 6 (Result Rate, outcome-only) | None | PROSPX pitcher cards for AA/High-A/untracked-Low-A pitchers specifically (a population `stuff_plus_aaa` doesn't cover at all) | C |
| Module 4 (Ground-Ball) | None | Same surface as Module 3, once its own reliability clears | D |
| Module 5 (Damage Suppression) | None | **No target consumer** — held back (`ARCHITECTURE_SIMPLIFICATION.md`) | Not scheduled |

## Systems confirmed NOT to be consumers, and why

- **`playing-time-model/`** — hitter-only, actively filters pitcher rows. Structurally cannot consume any pitcher-quality output.
- **`advancement_pace/`** — AST-import-guarded against consuming any predictive/valuation system. Structurally cannot consume this research's outputs even if wired.
- **`pitcher_ewar`/`milb_pitcher_ewar`** — not a real consumer candidate in this environment; private, inaccessible.
- **`/mlbstats/` leaderboards** — season-grain, MLB-level (`sem_plus`/`rem_plus`); a MiLB pitch-grain module doesn't fit this surface without a new leaderboard type, not evaluated as in-scope for the roadmap above.

## The standing rule this map encodes

Per `CONSUMER_AUDIT.md`'s central finding (reinforced by the `milb-decision-plus` precedent): **a row in this table only counts once real code reads the output**, not once a document says it should. `IMPLEMENTATION_ROADMAP.md`'s exit criteria for Phase C explicitly requires the module to appear in `SITE_MAP.md`'s generated route index — a verifiable, automatically-checked signal that the wiring is real, not just intended.

## Observed evidence / Inference / Speculation

The "today's real consumer: None" column is Observed evidence (confirmed absence, `CONSUMER_AUDIT.md`). The "target consumer" column is Inference/design intent, explicitly not yet real, and flagged as exactly the kind of claim that must not be mistaken for a completed integration.

## Future work

Re-generate this map once any Implementation Phase actually closes, replacing "target" with "confirmed" for the rows it affects.
