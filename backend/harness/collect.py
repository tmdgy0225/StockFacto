"""[1] Multi-source 수집.

- SNS·뉴스: 테스트용 가상 시나리오(data/cases.json). 실제 인물·사실과 무관하다.
- DART: 실제 Open DART 공시. 기본은 `python -m harness.snapshot` 으로 고정한 스냅샷을 쓰고(재현성),
  HARNESS_LIVE_DART=1 이면 실행 시점에 실시간으로 조회한다.
"""
from __future__ import annotations

import os

from . import dart


def collect(case: dict) -> dict:
    if os.environ.get("HARNESS_LIVE_DART") == "1":
        disclosures = dart.company_disclosures(case["corp_code"], case["as_of"])
        source = "live"
    else:
        disclosures = case.get("dart", [])
        source = f"snapshot {case.get('dart_snapshot', {}).get('fetched_at', '')}".strip()
    return {
        "sns": case["sources"].get("sns", []),
        "news": case["sources"].get("news", []),
        "dart": disclosures,
        "dart_source": source,
    }
