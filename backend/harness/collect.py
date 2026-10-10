"""[1] Multi-source 수집.

A/B 테스트 재현성을 위해 기본은 고정 fixture(data/cases.json)를 사용한다.
DART_API_KEY 가 설정되어 있고 케이스에 live_dart=true 이면 Open DART list.json 을 실제로 조회한다.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"


def collect(case: dict) -> dict:
    dart = case.get("dart", [])
    api_key = os.environ.get("DART_API_KEY")
    if api_key and case.get("live_dart"):
        dart = fetch_dart_list(api_key, case["corp_code"], case["as_of"])
    return {"sns": case["sources"].get("sns", []), "news": case["sources"].get("news", []), "dart": dart}


def fetch_dart_list(api_key: str, corp_code: str, as_of: str, days: int = 30) -> list[dict]:
    end = date.fromisoformat(as_of)
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": (end - timedelta(days=days)).strftime("%Y%m%d"),
        "end_de": end.strftime("%Y%m%d"),
        "page_count": 100,
    }
    with urllib.request.urlopen(f"{DART_LIST_URL}?{urllib.parse.urlencode(params)}", timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("status") not in ("000", "013"):  # 013 = 조회된 데이터 없음
        raise RuntimeError(f"DART API error {body.get('status')}: {body.get('message')}")
    return body.get("list", [])
