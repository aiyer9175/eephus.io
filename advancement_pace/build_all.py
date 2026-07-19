# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Reproducible end-to-end build: level history -> scores -> publication -> contracts.

Usage: python build_all.py   (venv: ~/swing_plus/.venv)
Exit code 2 on any contract failure (fail-closed; nothing partial is published).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

STEPS = [
    ("Phase 1-2  level history", [PY, str(ROOT / "build_history.py")]),
    ("Phase 3-12 scores + publication + contract", [PY, str(ROOT / "publication.py")]),
    ("Contract & isolation tests", [PY, "-m", "pytest", str(ROOT / "tests"), "-q"]),
]


def main():
    for name, cmd in STEPS:
        print(f"== {name}")
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            print(f"FAILED: {name}")
            sys.exit(2)
    print("BUILD COMPLETE — artifact staged, all contracts green.")


if __name__ == "__main__":
    main()
