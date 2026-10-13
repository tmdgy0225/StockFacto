"""Open DART API 클라이언트 (공시검색 list.json, 고유번호 corpCode.xml).

API 키는 환경변수 DART_API_KEY (backend/.env) 에서 읽는다.
"""
from __future__ import annotations

import io
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

from .config import BACKEND_DIR

BASE_URL = "https://opendart.fss.or.kr/api"
CORP_CODES_CACHE = BACKEND_DIR / "data" / "cache" / "corp_codes.json"
LIST_FIELDS = ("corp_code", "corp_name", "stock_code", "report_nm", "rcept_no", "rcept_dt")


class DartError(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise DartError("DART_API_KEY 가 설정되지 않았습니다 (backend/.env).")
    return key


def _get(path: str, params: dict) -> bytes:
    query = urllib.parse.urlencode({"crtfc_key": api_key(), **params})
    with urllib.request.urlopen(f"{BASE_URL}/{path}?{query}", timeout=30) as resp:
        return resp.read()


def search(bgn_de: str, end_de: str, corp_code: str | None = None, pblntf_ty: str | None = None,
           corp_cls: str | None = None, max_pages: int = 10) -> list[dict]:
    """공시검색(list.json). 날짜는 YYYYMMDD. corp_code 없이 검색하면 기간은 최대 3개월."""
    params = {"bgn_de": bgn_de, "end_de": end_de, "page_count": 100}
    if corp_code:
        params["corp_code"] = corp_code
    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty
    if corp_cls:
        params["corp_cls"] = corp_cls
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        body = json.loads(_get("list.json", {**params, "page_no": page}).decode("utf-8"))
        status = body.get("status")
        if status == "013":  # 조회된 데이터 없음
            break
        if status != "000":
            raise DartError(f"DART API error {status}: {body.get('message')}")
        rows += [{k: (r.get(k) or "").strip() for k in LIST_FIELDS} for r in body.get("list", [])]
        if page >= int(body.get("total_page", 1)):
            break
    return rows


def company_disclosures(corp_code: str, as_of: str, days: int = 30) -> list[dict]:
    """as_of(YYYY-MM-DD) 기준 과거 days 일 공시. as_of 이후 공시는 포함하지 않는다(미래 정보 차단)."""
    end = date.fromisoformat(as_of)
    return search((end - timedelta(days=days)).strftime("%Y%m%d"), end.strftime("%Y%m%d"), corp_code=corp_code)


def corp_codes(refresh: bool = False) -> list[dict]:
    """상장사 고유번호 목록 (corpCode.xml). 로컬에 캐시한다."""
    if CORP_CODES_CACHE.exists() and not refresh:
        return json.loads(CORP_CODES_CACHE.read_text(encoding="utf-8"))
    with zipfile.ZipFile(io.BytesIO(_get("corpCode.xml", {}))) as zf:
        root = ET.fromstring(zf.read(zf.namelist()[0]))
    listed = [
        {"corp_code": el.findtext("corp_code"), "corp_name": el.findtext("corp_name").strip(),
         "stock_code": el.findtext("stock_code").strip()}
        for el in root.iter("list")
        if (el.findtext("stock_code") or "").strip()
    ]
    CORP_CODES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CORP_CODES_CACHE.write_text(json.dumps(listed, ensure_ascii=False), encoding="utf-8")
    return listed


def find_corp(name: str) -> dict | None:
    """상장사명(정확히 일치) → {corp_code, corp_name, stock_code}."""
    for corp in corp_codes():
        if corp["corp_name"] == name:
            return corp
    return None
