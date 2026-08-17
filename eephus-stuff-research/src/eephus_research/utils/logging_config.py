"""Loads config/logging.yaml (Part BL: log enough to matter, not so much it's unusable)."""
from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml


def configure_logging(config_path: str | Path = "config/logging.yaml") -> None:
    path = Path(config_path)
    if not path.exists():
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            "logging config not found at %s; falling back to basicConfig", path
        )
        return
    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
