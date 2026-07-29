"""SCRATCH: zero-information control for the price-residual result.

Under the NULL that the market knows exactly what our projection knows and
nothing more, does regressing (realized WAR - proj) on (log price - f(proj))
still return a positive coefficient purely from shared projection error?
"""
import numpy as np
rng = np.random.default_rng(7)
N = 1097

def run(market_extra_sd, obs_sd=0.9, price_noise=0.55, reps=200):
    out = []
    for _ in range(reps):
        T = rng.normal(1.2, 1.15, N)                     # true talent (WAR units)
        obs = T + rng.normal(0, obs_sd, N)               # platform-season observation
        lam = 1.15**2 / (1.15**2 + obs_sd**2)            # optimal shrink
        proj = 1.2 + lam * (obs - 1.2)                   # our projection (Marcel-like)
        # market signal: sees T plus its OWN private info of quality market_extra_sd
        # market_extra_sd = inf -> market sees nothing extra (pure null)
        if market_extra_sd is None:
            m_obs = obs                                  # NULL: identical information
        else:
            priv = T + rng.normal(0, market_extra_sd, N)
            m_obs = (obs / obs_sd**2 + priv / market_extra_sd**2) / (1/obs_sd**2 + 1/market_extra_sd**2)
        logprice = 0.45 * m_obs + rng.normal(0, price_noise, N)
        war = T + rng.normal(0, 0.85, N)                 # realized (season noise)
        X = np.column_stack([np.ones(N), proj, proj**2])
        b, *_ = np.linalg.lstsq(X, logprice, rcond=None)
        pres = logprice - X @ b
        y = war - proj
        XX = np.column_stack([X, pres])
        bb, *_ = np.linalg.lstsq(XX, y, rcond=None)
        out.append(bb[-1])
    return np.mean(out), np.std(out)

m, s = run(None)
print(f"NULL (market sees EXACTLY our information): beta = {m:+.3f} +- {1.96*s:.3f}")
for extra in (2.0, 1.2, 0.8, 0.5):
    m2, s2 = run(extra)
    print(f"market has private signal sd={extra:.1f}:      beta = {m2:+.3f} +- {1.96*s2:.3f}")
print("\nobserved in real data: beta = +0.343 (se 0.057)")
print("\nSensitivity of the null to how noisy our projection is:")
for osd in (0.6, 0.9, 1.2, 1.5):
    m3, s3 = run(None, obs_sd=osd)
    print(f"  obs_sd={osd}: null beta = {m3:+.3f} +- {1.96*s3:.3f}")
