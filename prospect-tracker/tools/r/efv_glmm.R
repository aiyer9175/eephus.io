# R_BAKEOFF item (c): crossed random intercepts on top of X3's ridge staged model
# (docs/r/R_BAKEOFF.md section 5). One job per (fold, stage, run): the base stage's linear
# predictor is an OFFSET, and
#   y ~ 1 + offset(off) + (1 | org) + (1 | ls) + (1 | ec)
# is fitted with lme4 (glmer binomial for stage R, lmer Gaussian for stages T and Q), weights w
# scaled to mean 1. A convergence message from lme4 sends the job to glmmTMB with the same
# formula; if that fails too the job returns engine "base" (no random effect, intercept 0).
# Returns the fixed intercept and every group's conditional mode.
args <- commandArgs(trailingOnly = TRUE)
suppressPackageStartupMessages({library(jsonlite); library(lme4); library(glmmTMB)})
inp <- fromJSON(args[1], simplifyVector = FALSE)

re_list <- function(r) {
  out <- list()
  for (g in names(r)) {
    v <- r[[g]][, 1]
    out[[g]] <- as.list(setNames(as.numeric(v), rownames(r[[g]])))
  }
  out
}

fit_lme4 <- function(d, family) {
  fml <- y ~ 1 + offset(off) + (1 | org) + (1 | ls) + (1 | ec)
  m <- tryCatch(suppressWarnings(suppressMessages(
    if (family == "binomial") {
      glmer(fml, data = d, family = binomial, weights = w,
            control = glmerControl(optimizer = "bobyqa"))
    } else {
      lmer(fml, data = d, weights = w, REML = TRUE,
           control = lmerControl(optimizer = "bobyqa"))
    })), error = function(e) NULL)
  if (is.null(m)) return(NULL)
  msg <- m@optinfo$conv$lme4$messages
  if (!is.null(msg) && length(msg) && !all(grepl("singular", msg))) return(NULL)
  vc <- as.data.frame(VarCorr(m))
  sds <- setNames(as.list(vc$sdcor[vc$grp != "Residual"]), vc$grp[vc$grp != "Residual"])
  list(engine = if (family == "binomial") "glmer" else "lmer",
       intercept = as.numeric(fixef(m)[1]), re = re_list(ranef(m)), sd = sds,
       singular = isSingular(m))
}

fit_tmb <- function(d, family) {
  fml <- y ~ 1 + offset(off) + (1 | org) + (1 | ls) + (1 | ec)
  fam <- if (family == "binomial") binomial() else gaussian()
  m <- tryCatch(suppressWarnings(glmmTMB(fml, data = d, family = fam, weights = w)),
                error = function(e) NULL)
  if (is.null(m) || !isTRUE(m$sdr$pdHess)) return(NULL)
  r <- ranef(m)$cond
  vc <- VarCorr(m)$cond
  sds <- lapply(vc, function(x) as.numeric(attr(x, "stddev")))
  list(engine = "glmmTMB", intercept = as.numeric(fixef(m)$cond[1]), re = re_list(r), sd = sds,
       singular = FALSE)
}

out <- list()
for (job in inp$jobs) {
  d <- data.frame(y = as.numeric(unlist(job$y)), off = as.numeric(unlist(job$offset)),
                  w = as.numeric(unlist(job$w)),
                  org = factor(unlist(job$org)), ls = factor(unlist(job$ls)),
                  ec = factor(unlist(job$ec)))
  d$w <- d$w / mean(d$w)
  res <- fit_lme4(d, job$family)
  if (is.null(res)) res <- fit_tmb(d, job$family)
  if (is.null(res)) res <- list(engine = "base", intercept = 0, re = list(), sd = list(),
                                singular = NA)
  res$n <- nrow(d)
  out[[job$id]] <- res
}
write(toJSON(list(jobs = out, lme4 = as.character(packageVersion("lme4")),
                  glmmTMB = as.character(packageVersion("glmmTMB"))),
             auto_unbox = TRUE, digits = NA, na = "null"), args[2])
