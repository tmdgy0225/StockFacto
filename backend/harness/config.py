from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = HARNESS_DIR.parent
ROOT_DIR = BACKEND_DIR.parent
RULES_PATH = HARNESS_DIR / "rules.yaml"
AGENTS_MD_PATH = ROOT_DIR / "AGENTS.md"
CASES_PATH = BACKEND_DIR / "data" / "cases.json"
RUNS_DIR = BACKEND_DIR / "runs"


@lru_cache
def load_rules() -> dict:
    with RULES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def rule_meta(rule_id: str) -> dict:
    for rule in load_rules()["rules"]:
        if rule["id"] == rule_id:
            return rule
    raise KeyError(f"unknown rule id: {rule_id}")


@lru_cache
def load_agents_md() -> str:
    return AGENTS_MD_PATH.read_text(encoding="utf-8")


@lru_cache
def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get_case(case_id: str) -> dict:
    for case in load_cases():
        if case["id"] == case_id:
            return case
    raise KeyError(f"unknown case id: {case_id}")
