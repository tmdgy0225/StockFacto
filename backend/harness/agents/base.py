from __future__ import annotations

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


@dataclass
class AgentOutput:
    code: str
    input_tokens: int
    output_tokens: int


class AgentError(RuntimeError):
    pass


class StrategyAgent(Protocol):
    name: str

    def generate(self, req: AgentRequest) -> AgentOutput: ...


_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    blocks = _CODE_BLOCK.findall(text)
    return (max(blocks, key=len) if blocks else text).strip() + "\n"
