# Mathematical Governance

Every substantive mathematical transformation used in future research in this
repository must have a **mathematical contract** before it is trusted, and
that contract must live in version control next to the code that implements
it (a docstring-adjacent `.md` file or a structured block in the module
docstring — not only in a chat transcript).

## What a contract must contain

For a transformation producing a quantity such as

```
S_i = f(x_i1, x_i2, ..., x_ip)
```

the contract must specify, at minimum:

1. **Symbol definitions** — what each `x` and `S` actually is, in words a
   non-author can check.
2. **Units** — velocity in mph or m/s? Run value in runs or in fractional
   wins? A metric without stated units is not yet a contract.
3. **Domain** — what inputs are valid (e.g. velocity ∈ (0, 110] mph; a
   negative or 300 mph reading is out of domain, not just an outlier).
4. **Formula** — written out, not just "see the code."
5. **Assumptions** — what must be true of the data or the world for this
   formula to mean what it claims (independence assumptions, distributional
   assumptions, stationarity assumptions, etc.).
6. **Expected range** — what the output should plausibly look like, so an
   out-of-range result is detectable without re-deriving the formula.
7. **Treatment of missing values** — see the missingness classification in
   `docs/DATA_GOVERNANCE.md` (`ERROR / DROP / IMPUTE / MISSING_CATEGORY /
   NOT_APPLICABLE`); a contract must pick one per input, not leave it
   implicit in whatever `pandas` happens to do.
8. **Edge-case behavior** — zero pitches, a single pitcher, a tie, a
   division by zero denominator, an unknown pitch-type code.
9. **Aggregation rule** — how per-pitch quantities roll up to
   per-pitcher-season, per-team, etc., and whether that rollup is a simple
   mean, a weighted mean, a rate-of-rates, or something else.
10. **Weighting rule** — if any observation is weighted differently from any
    other, the contract states the weight and the justification.

## Dimensional analysis

Where a quantity has physical or baseball units, check dimensional
consistency before trusting the formula, independent of whether the code
runs:

| Quantity | Unit |
|---|---|
| Velocity | length / time |
| Spin | rotations / time |
| Movement | length |
| Release position | length |
| Run value | runs |
| A rate statistic | an explicitly stated denominator (per pitch? per PA? per 100 pitches?) |

A mathematically executable expression can still be conceptually invalid if
its units don't reconcile — e.g. adding a per-pitch rate to a per-game count
without normalizing first.

## Executable mathematics (Part S)

Where mathematics implies an identity, encode the identity as a test in
`tests/invariants/`, not as a correlation check. If `A = B + C`:

```python
assert abs(A - (B + C)) < tolerance   # tolerance named in config/research.yaml
```

Never substitute `corr(A, B + C) ≈ 1` for this. High correlation with a
systematic offset or scale error will still pass a correlation check and
silently corrupt every downstream number.

## Double implementation for critical formulas (Part T)

For sufficiently consequential formulas (anything feeding a claim registered
as `MATHEMATICAL` or `EMPIRICAL` in `registry/claims/`), require two
independently written implementations compared against each other:

- Implementation A: the production-like, likely vectorized version.
- Implementation B: a deliberately simple, transparent reference
  implementation — ideally written by re-reading the contract, not by
  reading implementation A's code.

Two implementations that both call the same shared helper function are
**not independent** — they will reproduce the same bug if the helper is
wrong. Document the actual independence level achieved
(`FULLY_INDEPENDENT`, `SHARED_HELPERS`, `SHARED_LIBRARY_ONLY`) next to the
comparison test; don't imply more independence than was achieved.

## Numerical precision (Part BO)

Tolerances are centralized in `config/research.yaml` under
`numerical_tolerance`, not scattered as bare `1e-6` literals through the
test suite. Exact integer/accounting identities use `exact_identity: 0.0`.
Floating-point transformations use a named, justified tolerance. If a new
kind of comparison needs a new tolerance, add it to `research.yaml` with a
one-line justification for the chosen value, rather than inventing a number
inline.

See `src/eephus_research/validation/identities.py` for the reusable
identity-checking helper this program built (Part S/T).
