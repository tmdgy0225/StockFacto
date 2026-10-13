from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AgentRequest:
    mode: str  # harness | control
    attempt: int
    system: str
    user: str
    feedback: list[dict] = field(default_factory=list)  # 직전 시도의 Violation.to_dict() 목록
    previous_code: str | None = None
    edit_mode: str = "rewrite"  # rewrite: 전체 코드 출력 | patch: 직전 코드에 대한 패치 목록 출력


@dataclass
class AgentOutput:
    code: str  # edit_mode=patch 로 패치를 낸 경우 빈 문자열 (하네스가 적용 후 채운다)
    input_tokens: int
    output_tokens: int
    patches: list[dict] | None = None


class AgentError(RuntimeError):
    pass


class StrategyAgent(Protocol):
    name: str

    def generate(self, req: AgentRequest) -> AgentOutput: ...


_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    blocks = _CODE_BLOCK.findall(text)
    return (max(blocks, key=len) if blocks else text).strip() + "\n"


def extract_patches(text: str) -> list[dict] | None:
    """```json {"patches": [...]} ``` 블록이 있으면 패치 목록을 반환. 없거나 형식이 다르면 None."""
    for block in _JSON_BLOCK.findall(text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("patches"), list):
            return data["patches"]
    return None
