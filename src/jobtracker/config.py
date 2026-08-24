"""Loads the editable YAML config files (companies, filters, scoring, comp bands)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml


def _default_config_dir() -> str:
    # src/jobtracker/config.py -> repo_root/config
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(repo_root, "config")


def _load_yaml(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Config:
    companies: list[dict]
    filters: dict
    scoring: dict
    comp_bands: dict
    config_dir: str

    def active_companies(self) -> list[dict]:
        return [c for c in self.companies if c.get("active", True)]

    def company_by_name(self, name: str) -> dict | None:
        for c in self.companies:
            if c["name"] == name:
                return c
        return None


def load_config(config_dir: str | None = None) -> Config:
    config_dir = config_dir or _default_config_dir()

    companies_doc = _load_yaml(os.path.join(config_dir, "companies.yaml"))
    filters_doc = _load_yaml(os.path.join(config_dir, "filters.yaml"))
    scoring_doc = _load_yaml(os.path.join(config_dir, "scoring.yaml"))
    comp_bands_doc = _load_yaml(os.path.join(config_dir, "comp_bands.yaml"))

    return Config(
        companies=companies_doc["companies"],
        filters=filters_doc,
        scoring=scoring_doc,
        comp_bands=comp_bands_doc["bands"],
        config_dir=config_dir,
    )
