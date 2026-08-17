from __future__ import annotations

import logging
from pathlib import Path

from eephus_research.utils.logging_config import configure_logging, get_logger

_REAL_CONFIG = Path(__file__).resolve().parents[2] / "config" / "logging.yaml"


def test_configure_logging_with_real_config_does_not_raise():
    configure_logging(_REAL_CONFIG)
    logger = get_logger("eephus_research")
    assert logger.level == logging.INFO or logger.getEffectiveLevel() == logging.INFO


def test_configure_logging_falls_back_when_config_missing(tmp_path, caplog):
    missing = tmp_path / "does_not_exist.yaml"
    configure_logging(missing)  # should not raise, falls back to basicConfig
    logger = get_logger("eephus_research")
    assert logger is not None


def test_get_logger_returns_named_logger():
    logger = get_logger("eephus_research.test")
    assert logger.name == "eephus_research.test"
