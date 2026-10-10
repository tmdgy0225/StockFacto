"""PEV(Plan-Execute-Verify) 파이프라인 + Self-Healing 루프.

mode="harness": 수집 → 팩트체크 → Plan → [Execute → Lint → Sandbox → Gate → (실패 시) Heal] × 최대 N회
mode="control": 수집 → Execute 1회 → 출하. 검증기는 관찰 전용으로만 돌려 "출하된 코드의 위험도"를 계측한다.

모든 단계는 이벤트로 방출되고(sink), 최종 결과는 RunTrace 로 남는다. 평가 지표는 trace 에서 집계한다.
"""
from __future__ import annotations

import difflib
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .agents import AgentError, AgentRequest, StrategyAgent
from .agents import prompt as prompts
from .collect import collect
from .config import load_rules
from .context import build_context
from .handoff import write_artifacts
from .plan import make_plan
from .prices import generate_bars
from .verify.lint import lint
from .verify.quality_gate import evaluate
from .verify.sandbox import run_backtest
from .violations import Violation, fingerprint

EventSink = Callable[[dict], None]


@dataclass
class Attempt:
    n: int
    code: str
    diff: str
    violations: list[dict]
    passed: bool
    metrics: dict | None = None
    equity_curve: list[float] = field(default_factory=list)
    stage_ms: dict = field(default_factory=dict)
    tokens: dict = field(default_factory=dict)


@dataclass
class RunTrace:
    run_id: str
    case_id: str
    case_title: str
    mode: str
    agent: str
    started_at: str
    status: str = "RUNNING"  # PASSED | ESCALATED | RELEASED(control) | ERROR
    unsafe: bool | None = None  # 최종 출하된 코드가 규칙 위반을 포함하는가
    context: dict = field(default_factory=dict)
    plan: dict | None = None
    attempts: list[Attempt] = field(default_factory=list)
    escalation_reason: str | None = None
    approval: str | None = None  # PENDING | APPROVED | REJECTED
    finished_at: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def run_pipeline(case: dict, agent: StrategyAgent, mode: str = "harness", sink: EventSink | None = None,
                 run_id: str | None = None, write: bool = True) -> RunTrace:
    emit = sink or (lambda _e: None)
    started = time.perf_counter()
    trace = RunTrace(run_id or new_run_id(), case["id"], case["title"], mode, agent.name, _now())

    def stage(name: str, status: str, attempt: int | None = None, **detail) -> None:
        emit({"type": "stage", "stage": name, "status": status, "attempt": attempt, "detail": detail})

    # [1] 수집
    stage("collect", "running")
    collected = collect(case)
    stage("collect", "done", sns=len(collected["sns"]), news=len(collected["news"]), dart=len(collected["dart"]))

    # [2] Context Filter Engine (DART 크로스체크) — 대조군에서도 계측용으로 계산만 한다
    ctx = build_context(case, collected)
    trace.context = {k: ctx[k] for k in ("fact_status", "max_weight", "facts", "compact", "tokens")}
    bars = generate_bars(case["prices"])

    try:
        if mode == "control":
            _run_control(case, agent, ctx, bars, trace, stage, emit)
        else:
            stage("context", "done", fact_status=ctx["fact_status"], max_weight=ctx["max_weight"], tokens=ctx["tokens"])
            trace.plan = make_plan(case, ctx)
            stage("plan", "done", **trace.plan)
            _run_harness(case, agent, ctx, bars, trace, stage, emit)
    except AgentError as e:
        trace.status, trace.escalation_reason = "ERROR", str(e)
        stage("execute", "fail", message=str(e))

    trace.finished_at = _now()
    trace.duration_ms = int((time.perf_counter() - started) * 1000)
    if write:
        write_artifacts(trace)
        stage("handoff", "done", run_id=trace.run_id)
    emit({"type": "done", "trace": trace.to_dict()})
    return trace


def _run_harness(case, agent, ctx, bars, trace: RunTrace, stage, emit) -> None:
    healing = load_rules()["healing"]
    max_weight = ctx["max_weight"]
    system = prompts.harness_system()
    feedback: list[dict] = []
    previous_code: str | None = None
    history: list[tuple[str, ...]] = []

    for n in range(1, healing["max_attempts"] + 1):
        stage("execute", "running", n)
        user = prompts.harness_user(trace.plan, ctx, feedback, previous_code)
        out = agent.generate(AgentRequest("harness", n, system, user, feedback, previous_code))
        stage("execute", "done", n, input_tokens=out.input_tokens, output_tokens=out.output_tokens)

        attempt = _verify(n, out, previous_code, bars, max_weight, case["symbol"], enforce=True, stage=stage)
        trace.attempts.append(attempt)
        emit({"type": "attempt", "attempt": asdict(attempt)})

        if attempt.passed:
            trace.status, trace.unsafe, trace.approval = "PASSED", False, "PENDING"
            return

        fp = fingerprint([Violation(**v) for v in attempt.violations])
        history.append(fp)
        if len(history) >= healing["no_progress_repeats"] and len(set(history[-healing["no_progress_repeats"]:])) == 1:
            trace.status = "ESCALATED"
            trace.escalation_reason = f"진전 없음: 동일 위반 {list(fp)} 이(가) {healing['no_progress_repeats']}회 연속 발생"
            stage("heal", "fail", n, reason=trace.escalation_reason)
            return
        if n < healing["max_attempts"]:
            stage("heal", "running", n, rules=list(fp))
        feedback, previous_code = attempt.violations, attempt.code

    trace.status = "ESCALATED"
    trace.escalation_reason = f"최대 시도 {healing['max_attempts']}회 초과"
    stage("heal", "fail", healing["max_attempts"], reason=trace.escalation_reason)


def _run_control(case, agent, ctx, bars, trace: RunTrace, stage, emit) -> None:
    stage("execute", "running", 1)
    out = agent.generate(AgentRequest("control", 1, prompts.control_system(), prompts.control_user(case, ctx)))
    stage("execute", "done", 1, input_tokens=out.input_tokens, output_tokens=out.output_tokens)
    # 대조군은 검증 결과와 무관하게 출하된다. 검증기는 관찰 전용(enforce=False)으로 실제 위험을 계측한다.
    attempt = _verify(1, out, None, bars, ctx["max_weight"], case["symbol"], enforce=False, stage=stage)
    trace.attempts.append(attempt)
    emit({"type": "attempt", "attempt": asdict(attempt)})
    trace.status, trace.unsafe = "RELEASED", not attempt.passed


def _verify(n, out, previous_code, bars, max_weight, symbol, enforce, stage) -> Attempt:
    stage_ms: dict[str, int] = {}
    t0 = time.perf_counter()
    stage("lint", "running", n)
    violations = lint(out.code, max_weight)
    stage_ms["lint"] = int((time.perf_counter() - t0) * 1000)
    metrics, curve = None, []

    lint_blocks = any(v.rule_id in ("R-000", "R-005") for v in violations)
    if violations and (enforce or lint_blocks):
        # Shift-left: lint 실패 시 비싼 백테스트를 건너뛴다. (대조군은 실행 가능한 코드면 끝까지 계측)
        stage("lint", "fail", n, violations=[v.to_dict() for v in violations])
        stage("sandbox", "skip", n)
        stage("gate", "skip", n)
    else:
        stage("lint", "fail" if violations else "pass", n, violations=[v.to_dict() for v in violations])
        stage("sandbox", "running", n)
        result = run_backtest(out.code, bars, max_weight, symbol, enforce=enforce)
        stage_ms["sandbox"] = result.duration_ms
        metrics, curve = result.metrics, result.equity_curve
        violations += result.violations
        stage("sandbox", "pass" if not result.violations else "fail", n,
              violations=[v.to_dict() for v in result.violations], metrics=metrics)
        if result.metrics:
            gate = evaluate(result, max_weight)
            violations += gate
            stage("gate", "pass" if not gate and not violations else "fail", n, violations=[v.to_dict() for v in gate])
        else:
            stage("gate", "skip", n)

    diff = "".join(difflib.unified_diff(
        (previous_code or "").splitlines(keepends=True), out.code.splitlines(keepends=True),
        fromfile=f"attempt_{n - 1}.py", tofile=f"attempt_{n}.py",
    )) if previous_code else ""
    return Attempt(
        n=n, code=out.code, diff=diff, violations=[v.to_dict() for v in _unique(violations)],
        passed=not violations, metrics=metrics, equity_curve=curve, stage_ms=stage_ms,
        tokens={"input": out.input_tokens, "output": out.output_tokens},
    )


def _unique(violations: list[Violation]) -> list[Violation]:
    seen, out = set(), []
    for v in violations:
        key = (v.rule_id, v.stage, v.message)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
