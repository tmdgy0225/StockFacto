"""② Sandbox Backtest (Non-AI): 전략 코드를 격리된 프로세스에서 가상 백테스트하고 MDD 를 계측한다.

기본은 `python -I` 서브프로세스(+ 제한된 builtins, import 화이트리스트, 타임아웃).
HARNESS_SANDBOX=docker 로 설정하면 네트워크 차단·메모리 제한된 Docker 컨테이너에서 실행한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import load_rules
from ..violations import Violation, violation

STAGE = "sandbox"
RUNNER = Path(__file__).with_name("sandbox_runner.py")


@dataclass
class SandboxResult:
    ok: bool
    metrics: dict = field(default_factory=dict)
    equity_curve: list[float] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    duration_ms: int = 0


def _command(container: str) -> list[str]:
    if os.environ.get("HARNESS_SANDBOX") == "docker":
        image = os.environ.get("HARNESS_SANDBOX_IMAGE", "python:3.12-slim")
        return [
            "docker", "run", "--rm", "-i", "--name", container,
            "--network=none", "--memory=256m", "--cpus=1", "--pids-limit=64", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
            "-v", f"{RUNNER.parent}:/sandbox:ro", image, "python", "-I", "/sandbox/sandbox_runner.py",
        ]
    return [sys.executable, "-I", str(RUNNER)]


def run_backtest(code: str, bars: list[dict], max_weight: float, symbol: str = "", enforce: bool = True,
                 timeout_sec: float | None = None, ctx_max_weight: float | None = None) -> SandboxResult:
    cfg = load_rules()
    req = {
        "code": code,
        "bars": bars,
        "symbol": symbol,
        "max_weight": max_weight,
        "ctx_max_weight": max_weight if ctx_max_weight is None else ctx_max_weight,
        "enforce": enforce,
        "stop_min": cfg["risk"]["stop_loss"]["min_distance"],
        "stop_max": cfg["risk"]["stop_loss"]["max_distance"],
        "allowed_imports": cfg["sandbox"]["allowed_imports"],
    }
    timeout = timeout_sec if timeout_sec is not None else cfg["sandbox"]["timeout_sec"]
    started = time.perf_counter()
    container = f"stockfacto-sbx-{uuid.uuid4().hex[:12]}"
    try:
        proc = subprocess.run(_command(container), input=json.dumps(req).encode("utf-8"), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.environ.get("HARNESS_SANDBOX") == "docker":
            # docker CLI 프로세스만 죽으면 컨테이너는 계속 돈다 → 명시적으로 종료
            subprocess.run(["docker", "kill", container], capture_output=True)
        return SandboxResult(False, violations=[violation("R-007", STAGE, f"실행 시간 초과({timeout}s): 무한 루프 의심")],
                             duration_ms=_ms(started))

    if proc.returncode != 0 or not proc.stdout:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["unknown"]
        return SandboxResult(False, violations=[violation("R-007", STAGE, f"샌드박스 프로세스 비정상 종료: {tail[0]}")],
                             duration_ms=_ms(started))

    data = json.loads(proc.stdout.decode("utf-8"))
    found = [
        violation(v["rule_id"], STAGE, f"{v['message']} (bar {v['first_bar']}부터 {v['count']}회)")
        for v in data["violations"]
    ]
    if data["error"]:
        err = data["error"]
        where = f" (bar {err['bar']})" if err.get("bar") is not None else ""
        found.append(violation("R-007", STAGE, f"{err['type']}: {err['message']}{where}", err.get("line")))
    return SandboxResult(data["ok"] and not found, data["metrics"], data["equity_curve"], found, _ms(started))


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
