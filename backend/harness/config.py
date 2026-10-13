from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = HARNESS_DIR.parent
ROOT_DIR = BACKEND_DIR.parent
RULES_PATH = HARNESS_DIR / "rules.yaml"
STRATEGY_RULES_PATH = HARNESS_DIR / "prompts" / "strategy_agent.md"
CASES_PATH = BACKEND_DIR / "data" / "cases.json"
RUNS_DIR = BACKEND_DIR / "runs"
ENV_PATH = BACKEND_DIR / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    """backend/.env 의 KEY=VALUE 를 환경변수로 읽는다. 이미 설정된 환경변수가 우선한다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


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
def load_strategy_rules() -> str:
    return STRATEGY_RULES_PATH.read_text(encoding="utf-8")


@lru_cache
def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get_case(case_id: str) -> dict:
    for case in load_cases():
        if case["id"] == case_id:
            return case
    raise KeyError(f"unknown case id: {case_id}")
