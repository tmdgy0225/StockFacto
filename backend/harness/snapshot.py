"""DART 스냅샷 갱신: 각 케이스의 실제 회사 공시를 Open DART 에서 조회해 cases.json 에 고정한다.

    python -m harness.snapshot          # 전체 케이스 갱신
    python -m harness.snapshot --check  # 갱신 후 기대 판정(expected_fact_status)과 다르면 실패

A/B 평가는 이 스냅샷을 입력으로 쓰므로 언제 돌려도 결과가 같다(재현성).
실시간 조회로 돌리려면 HARNESS_LIVE_DART=1 로 실행한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import dart
from .config import CASES_PATH, load_cases
from .context import check_claim


def refresh(check: bool = False) -> int:
    cases = load_cases()
    mismatches = 0
    for case in cases:
        corp = dart.find_corp(case["symbol"])
        if corp is None:
            raise dart.DartError(f"{case['id']}: 상장사 '{case['symbol']}' 를 찾을 수 없습니다.")
        case["corp_code"], case["stock_code"] = corp["corp_code"], corp["stock_code"]
        rows = dart.company_disclosures(case["corp_code"], case["as_of"])
        case["dart"] = rows
        case["dart_snapshot"] = {"fetched_at": date.today().isoformat(), "source": "opendart list.json",
                                 "window_days": 30, "count": len(rows)}

        facts = [check_claim(c, case["corp_code"], rows) for c in case.get("claims", [])]
        status = "VERIFIED" if facts and all(f["status"] == "VERIFIED" for f in facts) else "UNVERIFIED"
        expected = case.get("expected_fact_status")
        ok = expected is None or expected == status
        mismatches += not ok
        evidence = next((f["evidence"]["report_nm"] for f in facts if f["evidence"]), "-")
        print(f"{'OK ' if ok else 'DIFF'} {case['id']} {case['symbol']:<12} 공시 {len(rows):>3}건  판정={status:<10} 근거={evidence}")

    CASES_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n저장: {CASES_PATH}")
    return 1 if (check and mismatches) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh DART snapshots in cases.json")
    parser.add_argument("--check", action="store_true", help="기대 판정과 다르면 종료 코드 1")
    sys.exit(refresh(parser.parse_args().check))


if __name__ == "__main__":
    main()
