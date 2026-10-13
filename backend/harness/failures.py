"""실패 기록(Failures) 저장소: Strategy Agent 가 과거에 반복한 위반을 누적하고 다음 실행 프롬프트에 주입한다.

    python -m harness.failures           # 누적 현황 보기
    python -m harness.failures --reset   # 초기화

- 저장 위치: backend/runs/failures.json (실행 상태이므로 git 에 올리지 않는다)
- 기록: 웹/API 로 실행한 하네스 런(write=True)의 모든 시도 위반
- 주입: use_memory=True 인 런의 Plan 다음에 "과거 실패 기록" 섹션으로 추가
- A/B 평가는 재현성을 위해 기본적으로 기록·주입하지 않는다 (ADR-0004)
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .config import RUNS_DIR, rule_meta

FAILURES_PATH = RUNS_DIR / "failures.json"
MAX_EXAMPLES = 3


def _path(path: Path | None) -> Path:
    return path or FAILURES_PATH  # 실행 시점에 조회 (테스트에서 monkeypatch 가능)


def load(path: Path | None = None) -> dict:
    path = _path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"updated": None, "runs": 0, "rules": {}}


def save(data: dict, path: Path | None = None) -> None:
    path = _path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record(attempts: list[dict], path: Path | None = None) -> dict:
    """한 런의 시도 목록(Attempt dict)에서 위반을 누적한다."""
    data = load(path)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    data["runs"] += 1
    data["updated"] = now
    seen_in_run: set[str] = set()
    for attempt in attempts:
        for v in attempt["violations"]:
            entry = data["rules"].setdefault(v["rule_id"], {"count": 0, "runs": 0, "last_seen": None, "examples": []})
            entry["count"] += 1
            entry["last_seen"] = now
            if v["message"] not in entry["examples"]:
                entry["examples"] = (entry["examples"] + [v["message"]])[-MAX_EXAMPLES:]
            if v["rule_id"] not in seen_in_run:
                entry["runs"] += 1
                seen_in_run.add(v["rule_id"])
    save(data, path)
    return data


def top(n: int = 5, path: Path | None = None) -> list[tuple[str, dict]]:
    rules = load(path)["rules"]
    return sorted(rules.items(), key=lambda kv: (kv[1]["runs"], kv[1]["count"]), reverse=True)[:n]


def render_for_prompt(n: int = 5, path: Path | None = None) -> str | None:
    items = top(n, path)
    if not items:
        return None
    lines = ["## 과거 실패 기록 (이전 런에서 반복된 위반 — 처음부터 피할 것)"]
    for rule_id, e in items:
        lines.append(f"- {rule_id} {rule_meta(rule_id)['title']}: {e['runs']}개 런에서 {e['count']}회 발생."
                     f" 예: {e['examples'][-1]} → {rule_meta(rule_id)['fix_hint']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy Agent failure memory")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.reset:
        save({"updated": None, "runs": 0, "rules": {}})
        print("실패 기록을 초기화했습니다.")
        return
    data = load()
    print(f"누적 런: {data['runs']}  (갱신: {data['updated']})")
    for rule_id, e in top(20):
        print(f"  {rule_id}  런 {e['runs']:>3}  발생 {e['count']:>3}  최근: {e['examples'][-1]}")


if __name__ == "__main__":
    main()
