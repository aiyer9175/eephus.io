# R environment for the offline fits (R_ENV)

Written 2026-10-22 by task R_TOOLCHAIN_BAKEOFF. R is an OFFLINE fitting tool in this repo
(`docs/r/R_BAKEOFF.md` section 0): no served path, exporter, nightly or monthly step, page or
deploy step calls R. A fit that ships would ship as a JSON file of coefficients that Python reads,
so the live box and the port to git.eephus.io never need R.

## Interpreter

- R 4.6.1 (2026-06-24 ucrt), installed at `C:/Program Files/R/R-4.6.1` and added to the user
  PATH on 2026-10-19. Shells started before that do not see it; `tools/rbridge.py` falls back to
  `C:/Program Files/R/R-4.6.1/bin/Rscript.exe`, and the environment variable `RSCRIPT` overrides
  both.
- Packages install to the user library `C:/Users/noah/AppData/Local/R/win-library/4.6`, from CRAN
  only (`https://cloud.r-project.org`, Windows binaries).

## Pinned packages

The seven packages the bake-off uses, as installed on 2026-10-22. The full dependency closure
(83 packages, every one from CRAN) is pinned in `docs/r/renv.lock`, written by renv 1.3.1.

| package | version | used for |
|---|---|---|
| mgcv | 1.9-4 | penalized GAM with a player random effect (item a) |
| lme4 | 2.0-6 | crossed random intercepts, glmer and lmer (item c) |
| glmmTMB | 1.1.15.2 | the fallback engine for item c |
| survival | 3.8-6 | the Surv interval-censoring object (item b) |
| flexsurv | 2.3.2 | the parametric duration fit (item b) |
| quantreg | 6.1 | installed for quantile fits; no item reads it yet |
| jsonlite | 2.0.0 | JSON in and JSON out for every script |

## Restoring on another machine

```
Rscript -e "install.packages('renv', repos = 'https://cloud.r-project.org')"
Rscript -e "renv::restore(lockfile = 'docs/r/renv.lock', prompt = FALSE)"
```

Then `python tools/rbridge.py` prints the R and package versions it finds, and
`python -m pytest -p no:cacheprovider test_rbridge.py` checks them against this table and the
lockfile. Without R those tests skip; nothing else in the repo needs R.

## The bridge

`tools/rbridge.py` runs one script from `tools/r/` as `Rscript --vanilla <script> <in.json>
<out.json>`. A script reads only its input file and writes only its output file. A non-zero exit
or a missing output raises `rbridge.RError` with the tail of R's stderr.
