# R_BAKEOFF item (a): the year-over-year WAR rate change as a penalized GAM with a player random
# effect (docs/r/R_BAKEOFF.md section 3). One job per (fold, side):
#   dv ~ role + s(age1, k = 10) + s(pid, bs = "re"), weights w (mean 1), bam(method = "fREML").
# Test prediction: the fixed part plus the player's random effect when the player has a training
# pair, else 0. Also returns the fixed curve over `ages` at the reference role.
args <- commandArgs(trailingOnly = TRUE)
suppressPackageStartupMessages({library(jsonlite); library(mgcv)})
inp <- fromJSON(args[1], simplifyVector = FALSE)
out <- list()
for (job in inp$jobs) {
  id <- job$id
  tr <- job$train
  te <- job$test
  d <- data.frame(dv = as.numeric(unlist(tr$dv)), age1 = as.numeric(unlist(tr$age1)),
                  role = factor(unlist(tr$role)), pid = factor(unlist(tr$pid)),
                  w = as.numeric(unlist(tr$w)))
  d$w <- d$w / mean(d$w)
  fml <- if (nlevels(d$role) > 1) dv ~ role + s(age1, k = 10) + s(pid, bs = "re") else
    dv ~ s(age1, k = 10) + s(pid, bs = "re")
  m <- bam(fml, data = d, weights = w, method = "fREML", discrete = FALSE)
  lev_role <- levels(d$role)
  lev_pid <- levels(d$pid)
  ref_role <- job$ref_role
  if (!(ref_role %in% lev_role)) ref_role <- lev_role[1]
  te_role <- unlist(te$role)
  te_role[!(te_role %in% lev_role)] <- ref_role
  nd <- data.frame(age1 = as.numeric(unlist(te$age1)), role = factor(te_role, levels = lev_role),
                   pid = factor(rep(lev_pid[1], length(te_role)), levels = lev_pid))
  fixed <- as.numeric(predict(m, newdata = nd, exclude = "s(pid)"))
  cf <- coef(m)
  re_names <- grep("^s\\(pid\\)\\.", names(cf), value = TRUE)
  re <- setNames(as.numeric(cf[re_names]), lev_pid)
  tp <- as.character(unlist(te$pid))
  re_te <- ifelse(tp %in% lev_pid, re[tp], 0)
  re_te[is.na(re_te)] <- 0
  ages <- as.numeric(unlist(job$ages))
  cd <- data.frame(age1 = ages, role = factor(rep(ref_role, length(ages)), levels = lev_role),
                   pid = factor(rep(lev_pid[1], length(ages)), levels = lev_pid))
  curve <- as.numeric(predict(m, newdata = cd, exclude = "s(pid)"))
  vc <- tryCatch(gam.vcomp(m), error = function(e) NULL)
  sd_pid <- NA_real_
  if (!is.null(vc)) {
    vv <- if (is.matrix(vc)) vc[, 1] else vc
    k <- grep("pid", names(vv))
    if (length(k)) sd_pid <- as.numeric(vv[k[1]])
  }
  out[[id]] <- list(pred = fixed + re_te, fixed = fixed, curve = curve, ages = ages,
                    ref_role = ref_role, sd_pid = sd_pid, n_train = nrow(d),
                    n_players = length(lev_pid), n_test_seen = sum(tp %in% lev_pid),
                    edf_age = sum(m$edf[grep("^s\\(age1\\)", names(cf))]))
}
write(toJSON(list(jobs = out, mgcv = as.character(packageVersion("mgcv"))), auto_unbox = TRUE,
             digits = NA, na = "null"), args[2])
