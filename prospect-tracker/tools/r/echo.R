# rbridge smoke script: reads {"x": [numbers]} and writes their sum, mean and the R version.
args <- commandArgs(trailingOnly = TRUE)
suppressPackageStartupMessages(library(jsonlite))
inp <- fromJSON(args[1])
x <- as.numeric(inp$x)
out <- list(sum = sum(x), mean = mean(x), n = length(x),
            r = paste(R.version$major, R.version$minor, sep = "."))
write(toJSON(out, auto_unbox = TRUE, digits = NA), args[2])
