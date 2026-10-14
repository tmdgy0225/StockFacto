"""GeminiAgent 를 네트워크 없이 검증한다 (가짜 클라이언트 주입). 실제 API 호출은 하지 않는다."""
from types import SimpleNamespace

import pytest
from google.genai import errors

from harness.agents import AgentError, AgentRequest
from harness.agents.gemini import GeminiAgent


def response(text, prompt=900, out=60, thoughts=30):
    return SimpleNamespace(
        text=text, candidates=[SimpleNamespace(finish_reason="STOP")],
        usage_metadata=SimpleNamespace(prompt_token_count=prompt, candidates_token_count=out, thoughts_token_count=thoughts),
    )


class FakeModels:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def agent_with(*results):
    models = FakeModels(*results)
    sleeps: list[float] = []
    agent = GeminiAgent(model="gemini-flash-latest", client=SimpleNamespace(models=models), sleep=sleeps.append)
    return agent, models, sleeps


def test_first_attempt_extracts_code_and_counts_thinking_tokens():
    agent, models, _ = agent_with(response("```python\nclass Strategy:\n    pass\n```"))
    out = agent.generate(AgentRequest("harness", 1, "SYSTEM", "USER"))
    assert out.code == "class Strategy:\n    pass\n" and out.patches is None
    assert (out.input_tokens, out.output_tokens) == (900, 90)
    call = models.calls[0]
    assert call["model"] == "gemini-flash-latest" and call["contents"] == "USER"
    assert call["config"].system_instruction == "SYSTEM"


def test_patch_mode_parses_json_patches():
    agent, _, _ = agent_with(response('```json\n{"patches": [{"op": "delete", "start": 1, "end": 1}]}\n```'))
    out = agent.generate(AgentRequest("harness", 2, "S", "U", [{"rule_id": "R-001"}], "a\n", "patch"))
    assert out.patches == [{"op": "delete", "start": 1, "end": 1}] and out.code == ""


def test_rate_limit_is_retried_with_backoff():
    limited = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    agent, models, sleeps = agent_with(limited, limited, response("```python\nx = 1\n```"))
    out = agent.generate(AgentRequest("harness", 1, "S", "U"))
    assert out.code == "x = 1\n" and len(models.calls) == 3 and sleeps == [5.0, 10.0]


def test_non_retryable_error_becomes_agent_error():
    bad = errors.ClientError(400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}})
    agent, _, sleeps = agent_with(bad)
    with pytest.raises(AgentError):
        agent.generate(AgentRequest("harness", 1, "S", "U"))
    assert sleeps == []


def test_empty_response_raises():
    agent, _, _ = agent_with(response(None))
    with pytest.raises(AgentError):
        agent.generate(AgentRequest("harness", 1, "S", "U"))
