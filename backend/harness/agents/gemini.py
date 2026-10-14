"""Gemini 기반 Strategy Agent (선택). GEMINI_API_KEY (backend/.env) 가 필요하다.

Claude 에이전트와 같은 방식으로 매 시도를 독립된 단일 요청으로 보낸다.
무료 등급은 분당 요청 수 제한이 있어 429/503 응답에는 잠깐 기다렸다가 재시도한다.
"""
from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors, types

from .base import AgentError, AgentOutput, AgentRequest, extract_code, extract_patches

DEFAULT_MODEL = "gemini-3.5-flash"  # flash-latest 는 무료 등급에서 응답이 2~3분 걸려 고정 버전 사용
RETRY_CODES = {429, 500, 503}
MAX_RETRIES = 4


class GeminiAgent:
    name = "gemini"

    def __init__(self, model: str | None = None, client: genai.Client | None = None, sleep=time.sleep):
        if client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise AgentError("GEMINI_API_KEY 가 설정되지 않았습니다 (backend/.env).")
            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model or os.environ.get("HARNESS_GEMINI_MODEL", DEFAULT_MODEL)
        self._sleep = sleep

    def generate(self, req: AgentRequest) -> AgentOutput:
        response = self._call(req)
        text = response.text or ""
        if not text.strip():
            reason = None
            if response.candidates:
                reason = response.candidates[0].finish_reason
            raise AgentError(f"Gemini 빈 응답 (finish_reason={reason})")

        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage else 0
        # 사고(thinking) 토큰도 출력 비용이므로 함께 센다.
        output_tokens = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0

        if req.edit_mode == "patch" and req.previous_code is not None:
            patches = extract_patches(text)
            if patches is not None:
                return AgentOutput("", input_tokens, output_tokens, patches=patches)
            # 패치 대신 전체 코드를 낸 경우: 하네스가 rewrite 로 기록하고 그대로 검증한다.
        return AgentOutput(extract_code(text), input_tokens, output_tokens)

    def _call(self, req: AgentRequest):
        config = types.GenerateContentConfig(system_instruction=req.system, max_output_tokens=16000)
        delay = 5.0
        for attempt in range(MAX_RETRIES + 1):
            try:
                return self.client.models.generate_content(model=self.model, contents=req.user, config=config)
            except errors.APIError as e:
                if e.code in RETRY_CODES and attempt < MAX_RETRIES:
                    self._sleep(delay)
                    delay *= 2
                    continue
                raise AgentError(f"Gemini API 오류 {e.code}: {e.message}") from e
        raise AgentError("Gemini API 재시도 횟수 초과")
