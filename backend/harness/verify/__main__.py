"""Verification Command: 전략 파일 하나를 하네스 검증기(Lint → Sandbox → Gate)로 검사한다.

    python -m harness.verify strategy.py --max-weight 0.05 [--pattern pump_dump]

종료 코드 0 = 통과, 1 = 위반 있음. 파이프라인과 같은 검증기를 사용한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..prices import generate_bars
from .lint import lint
from .quality_gate import evaluate
from .sandbox import run_backtest


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a strategy file with the StockFacto harness")
    parser.add_argument("file", type=Path)
    parser.add_argument("--max-weight", type=float, default=0.05, help="비중 상한 (기본: DART 미확인 5%%)")
    parser.add_argument("--pattern", default="pump_dump", choices=["uptrend", "flat", "pump_dump", "gap_down"])
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    code = args.file.read_text(encoding="utf-8")
    violations = lint(code, args.max_weight)
    metrics = None
    if not violations:
        result = run_backtest(code, generate_bars({"pattern": args.pattern, "seed": args.seed}), args.max_weight)
        violations += result.violations
        metrics = result.metrics
        if result.metrics:
            violations += evaluate(result, args.max_weight)

    print(json.dumps({"passed": not violations, "metrics": metrics, "violations": [v.to_dict() for v in violations]},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
