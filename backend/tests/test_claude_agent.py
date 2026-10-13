"""ClaudeAgent 를 네트워크 없이 검증한다 (가짜 클라이언트 주입). 실제 API 호출은 하지 않는다."""
from types import SimpleNamespace

import pytest

from harness.agents import AgentError, AgentRequest
from harness.agents.claude import ClaudeAgent


class FakeMessages:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.text, self.stop_reason, self.calls = text, stop_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=80),
        )


def agent_with(text: str, stop_reason: str = "end_turn") -> tuple[ClaudeAgent, FakeMessages]:
    messages = FakeMessages(text, stop_reason)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeAgent(model="claude-opus-5-5", client=client), messages


def test_first_attempt_extracts_code_and_sends_expected_request():
    agent, messages = agent_with("```python\nclass Strategy:\n    pass\n```")
    out = agent.generate(AgentRequest("harness", 1, "SYSTEM", "USER"))
    assert out.code == "class Strategy:\n    pass\n" and out.patches is None
    assert (out.input_tokens, out.output_tokens) == (1200, 80)
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["system"] == "SYSTEM" and call["messages"] == [{"role": "user", "content": "USER"}]
    assert call["fallbacks"] == "default"


def test_patch_mode_parses_json_patches():
    agent, _ = agent_with('```json\n{"patches": [{"op": "delete", "start": 2, "end": 2}]}\n```')
    out = agent.generate(AgentRequest("harness", 2, "S", "U", [{"rule_id": "R-001"}], "a\nb\n", "patch"))
    assert out.code == "" and out.patches == [{"op": "delete", "start": 2, "end": 2}]


def test_patch_mode_falls_back_to_full_code():
    agent, _ = agent_with("```python\nclass Strategy:\n    pass\n```")
    out = agent.generate(AgentRequest("harness", 2, "S", "U", [{"rule_id": "R-001"}], "a\n", "patch"))
    assert out.patches is None and out.code.startswith("class Strategy")


def test_refusal_raises_agent_error():
    agent, _ = agent_with("", stop_reason="refusal")
    with pytest.raises(AgentError):
        agent.generate(AgentRequest("harness", 1, "S", "U"))
