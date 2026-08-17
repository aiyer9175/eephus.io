"""Regression test: the seed recorded in pyproject.toml must match config/research.yaml.

If these two ever drift, whichever one code actually reads becomes an
undocumented silent default -- exactly what Part Z exists to prevent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from eephus_research.utils.seed import get_default_seed

_ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_and_research_yaml_seeds_agree():
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    pyproject_seed = pyproject["tool"]["eephus_research"]["default_seed"]

    with (_ROOT / "config" / "research.yaml").open("r", encoding="utf-8") as fh:
        research_yaml = yaml.safe_load(fh)
    yaml_seed = research_yaml["seed"]["default"]

    assert pyproject_seed == yaml_seed


def test_get_default_seed_matches_config():
    with (_ROOT / "config" / "research.yaml").open("r", encoding="utf-8") as fh:
        research_yaml = yaml.safe_load(fh)
    assert get_default_seed() == research_yaml["seed"]["default"]
