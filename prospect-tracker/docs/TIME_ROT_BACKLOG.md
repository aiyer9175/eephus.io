# Time-rotted tests: the enumerated backlog

Swept 2026-08-14 after the THIRD instance in two sessions fired. Read-only audit
across 193 test files and 2,154 date literals, intersected against the 41
production sites that compare a value to a `date.today()`-derived cutoff.

## The pattern

A test hardcodes a date in a fixture. Production compares that date to a ROLLING
window derived from today. The test passes until today advances past the window,
then fails with no code change, on a predictable calendar day.

Three confirmed firings:

| test | fixture | window | rotted |
| --- | --- | --- | --- |
| `test_farm_rank_and_letter_are_deterministic` | 2025-02-12 | `storage.INACTIVE_MONTHS = 18` | 2026-08-13 |
| `test_extractors_need_the_untrimmed_split[_hitter_split]` | 2026-07-30 | `statcast_metrics` `window_days = 14` | 2026-08-14 |
| `test_extractors_need_the_untrimmed_split[_pitcher_split]` | 2026-07-30 | same | 2026-08-14 |

Both are fixed by deriving the fixture date from `date.today()`.

## The dominant gate

Almost every remaining item routes through ONE gate:
`storage.export_timeseries_json` drops a player from the active pool when
`fv_stale and play_stale` (`storage.py:10948`). `fv_stale = latest_date < cutoff`
(`:10932`), `cutoff = _inactive_cutoff()` = today minus 18 months
(`:1029-1040`, `INACTIVE_MONTHS = 18` at `:134`). In a synthetic fixture with no
`career_stats`, `play_stale` is UNCONDITIONALLY True (`:10860-10864`), so the
conjunction reduces to `fv_stale` alone and the whole test rides on one date.

A fixture dated `N` goes stale on the first day `cutoff > N`, i.e.
**N + 18 calendar months + 1 day**.

## RANKED BACKLOG, with the calendar date each will fire

| rots on | file:line | fixture | failure mode |
| --- | --- | --- | --- |
| ~~2026-12-02~~ REPAIRED 2026-10-04 (TIMEROT_1202) | `test_storage_export.py` `test_extras_present_flag_reflects_data` (was `:114`) | was 2025-06-01, now `_extras_vintages()`: today minus 60 days and 151 days before that | was: `beta` goes inactive, `_player()` returns None, AttributeError at `:123` |
| **2027-02-01** | `test_storage_export.py:99` | 2025-07-31 | `alpha` gone, `:109` asserts `p is not None` |
| **2027-02-01** | `test_storage_export.py:205` | 2025-07-31 | `delta` gone, fails at `:218` |
| **2027-02-01** | `test_storage_export.py:236` | 2025-07-31 | `eps` gone, fails at `:244` |
| **2027-07-23** | `test_storage_export.py:261` | 2026-01-22 | `ped_yes` gone, `.get()` on None at `:269` |
| **2027-08-15** | `test_storage_export.py:273` | 2026-02-14 | `ped_no` gone, TypeError at `:281` |
| **2027-08-17** | `test_consensus.py:417` | 2026-02-16 | `:433` `active_count == 3` becomes 0 |
| **2027-08-17** | `test_age.py:114` | 2026-02-16 | `payload["players"][0]` IndexError |
| **2027-08-17** | `test_age_level.py:102` | 2026-02-16 | same |
| **2027-08-17** | `test_age_level.py:143` | 2026-02-16 | same |
| **2027-08-17** | `test_arsenal_statcast.py:284` | 2026-02-16 | same |

Line numbers in `test_storage_export.py` rows are as of the TIMEROT_1202 repair
(2026-10-04), which inserted the `_extras_vintages()` helper and moved every later
line down by 22 or 23. The repair fixed only the 2026-12-02 row; the 2027-02-01 trio
was left by default (it fires 2027-02-01). The repair was proven by running the test
under a FakeDate clock set to 2026-12-02, 2027-02-01, 2027-08-17, 2027-12-31 and
2028-03-01 (all pass), with a control showing the old literals lose `beta` on
2026-12-02 and still pass on 2026-12-01.

This CONFIRMS and refines a prediction a prior session made from the same file
("newest dates 2025-06-01 and 2025-07-31 ... around 2026-12 and 2027-01"). The
exact days are 2026-12-02 and 2027-02-01.

## Why these were NOT fixed in the same pass

The dates are load bearing in ASSERTIONS as well as fixtures
(`assert dates[0] == "2025-07-31"` at `:224`, `assert by_date["2025-06-01"]` at
the old `:127` (repaired by TIMEROT_1202), `assert entry.get("date") == "2025-07-31"`
at `:345`), and several tests
depend on the RELATIVE ordering of two or three dates. A blanket substitution
would break green tests. The nearest firing is 110 days out, so the honest trade
was to enumerate precisely rather than refactor ten tests at speed. Each wants a
module-level anchor derived from today, preserving relative order, with the
assertions pointed at the same anchor.

## Verified NOT at risk, despite near dates

Checked rather than assumed, because a backlog that cries wolf gets ignored:

- `test_storage_export.py:448` (2025-02-12, `grad_one`): `status="debuted"` peels
  to `grads` at `storage.py:10817-10819`, BEFORE any date gate. Immune.
- `test_storage_export.py:453` (2026-02-14, `active_one`): no assertion depends on it.
- `test_storage_export.py:302` (2025-07-31, `multi_src_player`): asserts only on the
  scout_reports sidecar, which harvests active + graduate + inactive
  (`storage.py:15642-15647`).
- `test_graduation_rules.py:417` (2024-08-01): asserts membership in a UNION of
  buckets, so it survives the gate flipping which bucket.
- `consensus.py` and `movement.py` make ZERO `today()` calls, which clears the
  large date populations in `test_consensus.py`'s timeseries tests and
  `test_farm_movement.py`.
- Tests that INJECT the clock are structurally immune: `test_card_market.py`
  (`as_of=`), `test_org_tendencies.py` (`today=`), `test_leaderboard_vintages.py`
  (`on_date=`), `test_betting_close_job.py` (`now=`), `test_eta.py`
  (`snapshot_date=`), `test_efv_stale_anchor*.py` (`today=`).

**Clock injection is the structural fix.** Deriving the fixture from today is the
cheap fix; letting the test pass a clock is the one that cannot rot.

## NOT rot, and must not be "fixed" as though it were

`test_model_registry.py:120` `assert mr.STALE_DAYS > oldest` will fire around
**2026-09-08**, sooner than anything above, and it is NOT this defect. It is the
inverse: a fixed bar against a live artifact age that grows daily. Measured now,
the oldest registered artifact is 65 days (`fa_dpw_series`, `age_source="artifact"`)
against `STALE_DAYS = 90`.

Its own docstring forbids the tempting fix: "lower it until something trips is not
a move this test permits, and a bar tuned to produce an alarm on a healthy tree is
a false alarm rather than a finding." When it fires, the correct response is to
REGENERATE the stale artifact, not to raise `STALE_DAYS`. Recorded here so nobody
reaches for the constant.

## Standing rule this produces

A test fixture whose date must sit inside a rolling window is a time bomb with a
known fuse length. Derive it from `date.today()`, or better, give the production
function an injectable clock and pass one. Three have fired in two sessions; the
next is 110 days out.
