# Expansion E15 — Incremental Value Audit (new features)

- DEF coverage: 85% have OAA; SPEED coverage: 87%; out-of-options rate: 17.4%

## Individual blocks vs champion (test 2023-25)
champion                       {'R2': np.float64(0.7172), 'MAE': 93.4, 'RMSE': 123.5, 'rho': 0.8626}
+DEF (OAA/FRV)                 {'R2': np.float64(0.7169), 'MAE': 93.4, 'RMSE': 123.5, 'rho': 0.8632}   Δ {'R2': np.float64(-0.0003), 'MAE': 0.0, 'RMSE': 0.0, 'rho': 0.0006}
+OPT (out-of-options)          {'R2': np.float64(0.7171), 'MAE': 93.4, 'RMSE': 123.5, 'rho': 0.8627}   Δ {'R2': np.float64(-0.0001), 'MAE': 0.0, 'RMSE': 0.0, 'rho': 0.0001}
+SPEED (sprint)                {'R2': np.float64(0.7168), 'MAE': 93.7, 'RMSE': 123.5, 'rho': 0.8629}   Δ {'R2': np.float64(-0.0004), 'MAE': 0.3, 'RMSE': 0.0, 'rho': 0.0003}
+POSLIFE (position)            {'R2': np.float64(0.7159), 'MAE': 93.1, 'RMSE': 123.7, 'rho': 0.8617}   Δ {'R2': np.float64(-0.0013), 'MAE': -0.3, 'RMSE': 0.2, 'rho': -0.0009}

## Cumulative (adding blocks that individually helped R2)

- blocks kept (individually R2-positive): []

## VERDICT — all four REJECTED for incumbent PA

| block | ΔR² | verdict |
|---|---|---|
| DEF (OAA/FRV) | -0.0003 | reject |
| OPT (out-of-options) | -0.0001 | reject |
| SPEED (sprint) | -0.0004 | reject |
| POSLIFE (position) | -0.0013 | reject |

Segment check (where thin usage history should let attributes matter) — no add
anywhere: pa_t<100 MAE 64.0→64.3 (DEF); glove-first (oaa≥5, pa<350, n=54) 109.7
→108.9 (noise); out-of-options players themselves 106.4→106.3.

**Why:** a player's own recent PA/starts history + Opening-Day roster status is
a NEAR-SUFFICIENT STATISTIC for these static attributes. Teams already revealed
their valuation of glove/speed/roster-flexibility through how much they played
him — so the raw attribute is redundant. Same mediation lesson as org (E10),
GM, manager (E13), and FV-for-incumbents (parent M6). Only signals that change
the trajectory in ways history can't contain add value for incumbents: injury
(new event), the current OD decision, transactions.

**Where they'd still be worth testing:** the PROSPECT model (thin MLB history),
where FV already won (E11). Defense/speed plausibly help a glove-first prospect
debut — flagged for the prospect slice, not the incumbent champion.

**Implication for contract (#4, on hold):** unlike these, a freshly-signed FA
deal is a FORWARD commitment NOT yet in usage history — so contract is the one
remaining candidate plausibly NOT mediated by past usage. Worth the collection
effort precisely because it's the exception to this pattern.
