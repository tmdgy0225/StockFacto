"""StockFacto Harness API.

    uvicorn api.main:app --reload --port 8000   (backend/ 디렉터리에서 실행)

frontend/dist 가 있으면 같은 서버에서 정적 파일로 서빙한다(단일 배포).
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from harness import failures
from harness.agents import make_agent
from harness.config import ROOT_DIR, get_case, load_cases, load_rules, load_strategy_rules
from harness.eval import run_eval
from harness.handoff import ApprovalError, decide, load_trace
from harness.pipeline import new_run_id, run_pipeline
from harness.review import make_reviewer

app = FastAPI(title="StockFacto Harness API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# run_id -> {"events": [...], "done": bool}. 단일 프로세스 데모용 인메모리 저장소. trace 는 runs/ 에 영속화된다.
_RUNS: dict[str, dict] = {}


class RunRequest(BaseModel):
    case_id: str
    mode: Literal["harness", "control"] = "harness"
    agent: Literal["mock", "claude"] = "mock"


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]


class EvalRequest(BaseModel):
    agent: Literal["mock", "claude"] = "mock"
    case_ids: list[str] | None = None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/cases")
def cases() -> list[dict]:
    return [
        {"id": c["id"], "title": c["title"], "symbol": c["symbol"], "request": c["request"], "tags": c.get("tags", [])}
        for c in load_cases()
    ]


@app.get("/api/rules")
def rules() -> dict:
    return {"rules": load_rules(), "strategy_rules": load_strategy_rules()}


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict:
    try:
        case = get_case(req.case_id)
    except KeyError:
        raise HTTPException(404, "case not found") from None
    try:
        agent = make_agent(req.agent, case)
    except Exception as e:  # anthropic 미설치/인증 누락 등
        raise HTTPException(400, f"agent init failed: {e}") from e

    run_id = new_run_id()
    state = {"events": [], "done": False}
    _RUNS[run_id] = state

    def work() -> None:
        try:
            run_pipeline(case, agent, req.mode, sink=state["events"].append, run_id=run_id, use_memory=True,
                         reviewer=make_reviewer())
        except Exception as e:
            state["events"].append({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            state["done"] = True

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    state = _RUNS.get(run_id)
    if state is None:
        raise HTTPException(404, "run not found")

    async def stream():
        i = 0
        while True:
            events = state["events"]
            while i < len(events):
                yield f"data: {json.dumps(events[i], ensure_ascii=False)}\n\n"
                i += 1
            if state["done"] and i >= len(state["events"]):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        trace = load_trace(run_id)
    except ApprovalError:
        trace = None
    if trace is None:
        raise HTTPException(404, "run not found")
    return trace


@app.post("/api/runs/{run_id}/approval")
def approve(run_id: str, req: ApprovalRequest) -> dict:
    try:
        return decide(run_id, req.decision)
    except ApprovalError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/failures")
def failure_memory() -> dict:
    return failures.load()


@app.post("/api/eval")
def evaluate(req: EvalRequest) -> dict:
    return run_eval(req.agent, req.case_ids)


_DIST = ROOT_DIR / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
