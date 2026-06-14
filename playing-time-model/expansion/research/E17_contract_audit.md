# Expansion E17 — Contract Value Audit (E15 exception test)

- contract-covered target years: [np.int64(2023), np.int64(2024), np.int64(2025)]; incumbent rows 1990; with a contract record 40%

## Leave-one-year-out CV (2023/24/25), all covered incumbents
              model    n     R2  MAE  RMSE    rho
           champion 1990 0.6877 94.6 129.7 0.8448
champion + contract 1990 0.6832 95.2 130.7 0.8444

## Players WITH a contract record (n=791)
              model   n     R2   MAE  RMSE    rho
           champion 791 0.5432 114.9 146.7 0.7400
champion + contract 791 0.5343 116.9 148.1 0.7351

## Multiyear-guaranteed players (the 'plays through slumps' segment, n=199)
              model   n     R2   MAE  RMSE    rho
           champion 199 0.5648 107.0 138.2 0.7195
champion + contract 199 0.5651 107.5 138.1 0.7173

## Verdict
Contract ships only if it improves OOS here — this is the one feature not
mediated by usage history, so it's the real test of the E15 ceiling.

## VERDICT — contract REJECTED (the E15 ceiling holds)
Leave-one-year-out CV (2023/24/25): champion R² .688 → .683 with contract;
contract-record players (n=791) .543 → .534; multiyear-guaranteed (n=199,
the "plays through slumps" segment) .565 → .565 flat. NO-ADD even where the
forward-commitment hypothesis is strongest.

WHY: even a fresh FA deal is mediated by the Opening-Day roster — a big
signing is on the active roster (on_active_od) and was recently good (talent +
usage). The contract's "he'll play" signal is already realized in the roster
placement + talent we observe. Forward-commitment didn't survive the data.

Caveat: contract coverage partial (2023 thin n=226; 75% name-match; LOYO is a
smaller train than full history) — somewhat underpowered. But flat-to-negative
on the target segment + sound mechanism → no-add stands; prior now strongly
against. Could revisit with fuller historical Spotrac coverage.

## META-FINDING (closes the incumbent feature hunt)
EVERY static/contextual attribute tested — org (E10), GM, manager (E13),
defense/speed/options/position (E15), prospect defense/speed (E16), and now
contract (E17) — is MEDIATED by the concrete observables already in the
champion: recent usage history + Opening-Day roster + injury. The incumbent PA
model is at its cross-sectional ceiling. Productive frontiers are elsewhere:
prospect slice (FV won, E11), in-season updating (big win, E14), role/platoon
outputs (new info, E12/E13).
