from __future__ import annotations

from .base import AgentError, AgentOutput, AgentRequest, StrategyAgent
from .mock import MockAgent


def make_agent(name: str, case: dict) -> StrategyAgent:
    if name == "mock":
        return MockAgent(case)
    if name == "claude":
        from .claude import ClaudeAgent  # anthropic 패키지는 선택 의존성

        return ClaudeAgent()
    if name == "gemini":
        from .gemini import GeminiAgent  # google-genai 패키지는 선택 의존성

        return GeminiAgent()
    raise ValueError(f"unknown agent: {name}")


__all__ = ["AgentError", "AgentOutput", "AgentRequest", "StrategyAgent", "MockAgent", "make_agent"]
