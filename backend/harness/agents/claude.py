"""Claude 기반 Strategy Agent (선택). ANTHROPIC_API_KEY 또는 `ant auth login` 프로필이 필요하다.

매 시도를 독립된 단일 요청으로 보낸다(직전 코드 + 실패 로그를 user 프롬프트에 포함).
대화 히스토리를 누적하지 않아 시도 간 상태가 피드백 JSON 으로만 전달된다.
"""
from __future__ import annotations

import os

import anthropic

from .base import AgentError, AgentOutput, AgentRequest, extract_code


class ClaudeAgent:
    name = "claude"

    def __init__(self, model: str | None = None):
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("HARNESS_MODEL", "claude-opus-5-5")

    def generate(self, req: AgentRequest) -> AgentOutput:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                output_config={"effort": os.environ.get("HARNESS_EFFORT", "medium")},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=req.system,
                messages=[{"role": "user", "content": req.user}],
            )
        except anthropic.APIConnectionError as e:
            raise AgentError(f"Claude API 연결 실패: {e}") from e
        except anthropic.RateLimitError as e:
            raise AgentError("Claude API 요청 한도 초과") from e
        except anthropic.APIStatusError as e:
            raise AgentError(f"Claude API 오류 {e.status_code}: {e.message}") from e

        if response.stop_reason == "refusal":
            raise AgentError("모델이 요청을 거절했습니다.")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise AgentError(f"빈 응답 (stop_reason={response.stop_reason})")
        return AgentOutput(extract_code(text), response.usage.input_tokens, response.usage.output_tokens)
