"""[2] Context Filter Engine: DART 공시 기반 Cross-Fact Check + 컨텍스트 압축.

SNS·뉴스의 주장(claim)을 DART 공시 목록과 결정론적으로 대조해 VERIFIED / UNVERIFIED 를 판정하고,
판정 결과로 비중 상한(max_weight)을 결정한다. LLM 은 이 판정에 관여하지 않는다.
"""
from __future__ import annotations

import json
import math
from datetime import date

from .config import load_rules


def estimate_tokens(text: str) -> int:
    """토큰 수 추정치(UTF-8 바이트 / 3). 같은 방식으로 원문과 압축본을 비교하기 위한 상대 지표."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def _parse_dart_date(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def check_claim(claim: dict, corp_code: str, disclosures: list[dict]) -> dict:
    cfg = load_rules()["fact_check"]
    keywords = cfg["claim_keywords"].get(claim["type"], [])
    claim_date = date.fromisoformat(claim["date"])
    for d in disclosures:
        if d.get("corp_code") != corp_code:
            continue
        if abs((_parse_dart_date(d["rcept_dt"]) - claim_date).days) > cfg["window_days"]:
            continue
        if any(k in d["report_nm"] for k in keywords):
            return {**claim, "status": "VERIFIED", "evidence": {"report_nm": d["report_nm"], "rcept_no": d.get("rcept_no"), "rcept_dt": d["rcept_dt"]}}
    return {**claim, "status": "UNVERIFIED", "evidence": None}


def build_context(case: dict, collected: dict) -> dict:
    facts = [check_claim(c, case["corp_code"], collected["dart"]) for c in case.get("claims", [])]
    status = "VERIFIED" if facts and all(f["status"] == "VERIFIED" for f in facts) else "UNVERIFIED"
    max_weight = load_rules()["risk"]["weight_cap"][status]

    compact = {
        "symbol": case["symbol"],
        "fact_status": status,
        "max_weight": max_weight,
        "claims": [
            {
                "type": f["type"],
                "amount_krw": f.get("amount_krw"),
                "counterparty": f.get("counterparty"),
                "source": f.get("source"),
                "status": f["status"],
                "dart": f["evidence"]["report_nm"] if f["evidence"] else None,
            }
            for f in facts
        ],
        "headlines": [n["title"][:60] for n in collected["news"][:3]],
    }
    raw_text = "\n".join(
        [s["text"] for s in collected["sns"]]
        + [f"{n['title']}\n{n['body']}" for n in collected["news"]]
        + [json.dumps(collected["dart"], ensure_ascii=False)]
    )
    compact_text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    raw_tokens, compact_tokens = estimate_tokens(raw_text), estimate_tokens(compact_text)
    return {
        "fact_status": status,
        "max_weight": max_weight,
        "dart_source": collected.get("dart_source", "fixture"),
        "dart_count": len(collected["dart"]),
        "facts": facts,
        "compact": compact,
        "compact_text": compact_text,
        "raw_text": raw_text,
        "tokens": {
            "raw": raw_tokens,
            "compact": compact_tokens,
            "reduction": round(1 - compact_tokens / raw_tokens, 4) if raw_tokens else 0.0,
        },
    }
