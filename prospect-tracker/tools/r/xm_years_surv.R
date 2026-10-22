# R_BAKEOFF item (b): contract years as an interval-censored duration (docs/r/R_BAKEOFF.md
# section 4). One job per winter: T in (Y - 1, Y] (left-censored on (0, 1] for one-year deals),
# flexsurvreg(Surv(lo, hi, type = "interval2") ~ x, dist = "gengamma"), falling back to "lnorm"
# when the fit fails or its Hessian is not positive definite. Returns the median of T for every
# test row. A job with `mode` "fit_lnorm" returns the lognormal coefficients instead (the planted
# truth of check P1).
args <- commandArgs(trailingOnly = TRUE)
suppressPackageStartupMessages({library(jsonlite); library(survival); library(flexsurv)})
inp <- fromJSON(args[1], simplifyVector = FALSE)

as_mat <- function(rows) {
  m <- do.call(rbind, lapply(rows, function(r) as.numeric(unlist(r))))
  if (is.null(dim(m))) m <- matrix(m, nrow = 1)
  colnames(m) <- paste0("x", seq_len(ncol(m)))
  m
}

fit_one <- function(d, xn, dist) {
  fml <- as.formula(paste("Surv(lo, hi, type = 'interval2') ~", paste(xn, collapse = " + ")))
  f <- tryCatch(flexsurvreg(fml, data = d, dist = dist), error = function(e) NULL)
  if (is.null(f)) return(NULL)
  ok <- isTRUE(f$opt$convergence == 0)
  pd <- tryCatch({
    h <- f$opt$hessian
    !is.null(h) && all(is.finite(h)) && all(eigen(h, symmetric = TRUE, only.values = TRUE)$values > 0)
  }, error = function(e) FALSE)
  if (!ok || !pd) return(NULL)
  f
}

out <- list()
for (job in inp$jobs) {
  X <- as_mat(job$train_x)
  y <- as.numeric(unlist(job$train_y))
  lo <- ifelse(y <= 1, NA_real_, y - 1)
  d <- data.frame(lo = lo, hi = y, X)
  xn <- colnames(X)
  if (identical(job$mode, "fit_lnorm")) {
    f <- fit_one(d, xn, "lnorm")
    if (is.null(f)) stop("planted truth: the lognormal fit failed")
    cf <- f$res[, "est"]
    out[[job$id]] <- list(mode = "fit_lnorm", meanlog = as.numeric(cf["meanlog"]),
                          sdlog = as.numeric(cf["sdlog"]),
                          beta = as.numeric(cf[xn]), names = xn)
    next
  }
  dist_used <- "gengamma"
  f <- fit_one(d, xn, "gengamma")
  if (is.null(f)) {
    dist_used <- "lnorm"
    f <- fit_one(d, xn, "lnorm")
  }
  if (is.null(f)) stop(paste("job", job$id, ": both fits failed"))
  Xt <- as_mat(job$test_x)
  nd <- data.frame(Xt)
  med <- predict(f, newdata = nd, type = "quantile", p = 0.5)
  medv <- if (is.data.frame(med)) as.numeric(med$.pred_quantile) else as.numeric(unlist(med))
  if (length(medv) != nrow(Xt)) {
    medv <- sapply(seq_len(nrow(Xt)), function(i)
      as.numeric(summary(f, newdata = nd[i, , drop = FALSE], type = "median", tidy = TRUE)$est))
  }
  out[[job$id]] <- list(dist = dist_used, median = medv, loglik = as.numeric(f$loglik),
                        n_train = nrow(d), aic = as.numeric(f$AIC))
}
write(toJSON(list(jobs = out, flexsurv = as.character(packageVersion("flexsurv"))),
             auto_unbox = TRUE, digits = NA, na = "null"), args[2])
