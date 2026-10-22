"""rbridge: run an R script offline with JSON in and JSON out.

R is an OFFLINE fitting tool for this repo (docs/r/R_BAKEOFF.md section 0): no served path,
exporter, nightly or monthly step calls this module. A lab writes its inputs to a JSON file,
`run_r` runs one `.R` file as `Rscript <script> <in.json> <out.json>`, and the lab reads the
output JSON back. Anything that would ship is the JSON the lab writes, read by Python.

Rscript is found on PATH, then at the R 4.6.1 install path (shells started before R joined the
user PATH on 2026-10-19 do not see it). `find_rscript()` returns None when R is absent, so a
test can skip cleanly.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R_DIR = ROOT / "tools" / "r"
FALLBACK_RSCRIPT = (Path("C:/Program Files/R/R-4.6.1/bin/Rscript.exe"),)
#: the CRAN packages the bake-off pins (docs/r/R_ENV.md)
PACKAGES = ("mgcv", "lme4", "glmmTMB", "survival", "flexsurv", "quantreg", "jsonlite")


class RError(RuntimeError):
    """An R run that exited non-zero or wrote no output."""


def find_rscript() -> str | None:
    """The Rscript executable, or None when R is not installed."""
    env = os.environ.get("RSCRIPT")
    if env and Path(env).exists():
        return env
    got = shutil.which("Rscript")
    if got:
        return got
    for p in FALLBACK_RSCRIPT:
        if p.exists():
            return str(p)
    return None


def available() -> bool:
    return find_rscript() is not None


def run_r(script: str | Path, payload, *, timeout: float = 3600.0, workdir: Path | None = None,
          keep: bool = False) -> dict:
    """Run `script` with `payload` written as JSON; return the parsed output JSON.

    The script is called as `Rscript --vanilla <script> <in.json> <out.json>` and must write the
    output file. stdout and stderr come back under `_r_stdout` and `_r_stderr` (truncated)."""
    rs = find_rscript()
    if rs is None:
        raise RError("Rscript not found (R is not installed)")
    script = Path(script)
    if not script.is_absolute():
        script = (R_DIR / script) if (R_DIR / script).exists() else (ROOT / script)
    if not script.exists():
        raise RError(f"no R script at {script}")
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="rbridge_"))
    tmp.mkdir(parents=True, exist_ok=True)
    fin, fout = tmp / "in.json", tmp / "out.json"
    if fout.exists():
        fout.unlink()
    fin.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    proc = subprocess.run([rs, "--vanilla", str(script), str(fin), str(fout)],
                          capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not fout.exists():
        raise RError(f"{script.name} exited {proc.returncode}: {proc.stderr[-4000:]}")
    out = json.loads(fout.read_text(encoding="utf-8"))
    if isinstance(out, dict):
        out["_r_stdout"] = proc.stdout[-4000:]
        out["_r_stderr"] = proc.stderr[-4000:]
    if not keep and workdir is None:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def versions() -> dict:
    """{"R": "4.6.1", "packages": {name: version or None}} from the installed R."""
    code = ("v <- sapply(c(%s), function(p) tryCatch(as.character(packageVersion(p)), "
            "error = function(e) NA_character_)); "
            "cat(jsonlite::toJSON(list(R = paste(R.version$major, R.version$minor, sep = '.'), "
            "packages = as.list(v)), auto_unbox = TRUE, na = 'null'))"
            % ", ".join(f'"{p}"' for p in PACKAGES))
    rs = find_rscript()
    if rs is None:
        raise RError("Rscript not found (R is not installed)")
    proc = subprocess.run([rs, "--vanilla", "-e", code], capture_output=True, text=True,
                          timeout=120)
    if proc.returncode != 0:
        raise RError(proc.stderr[-2000:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    print(json.dumps({"rscript": find_rscript(), **(versions() if available() else {})}, indent=1))
