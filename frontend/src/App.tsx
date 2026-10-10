import { useEffect, useMemo, useRef, useState } from "react";
import { api, subscribe } from "./api";
import type { AgentName, Attempt, CaseSummary, EvalReport, HarnessEvent, Mode, StageName, Trace } from "./types";

const STAGES: { id: StageName; label: string }[] = [
  { id: "collect", label: "수집" },
  { id: "context", label: "DART 팩트체크" },
  { id: "plan", label: "Plan" },
  { id: "execute", label: "Execute" },
  { id: "lint", label: "Static Linter" },
  { id: "sandbox", label: "Sandbox" },
  { id: "gate", label: "Quality Gate" },
  { id: "heal", label: "Self-Healing" },
  { id: "handoff", label: "Handoff" },
];

const pct = (x: number | null | undefined, digits = 0) => (x == null ? "-" : `${(x * 100).toFixed(digits)}%`);

export default function App() {
  const [tab, setTab] = useState<"run" | "eval">("run");
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">SF</span>
          <div>
            <h1>StockFacto Harness</h1>
            <p>PEV 루프 · Static Linter · Sandbox · Quality Gate · Self-Healing</p>
          </div>
        </div>
        <nav className="tabs">
          <button className={tab === "run" ? "active" : ""} onClick={() => setTab("run")}>파이프라인 실행</button>
          <button className={tab === "eval" ? "active" : ""} onClick={() => setTab("eval")}>A/B 평가</button>
        </nav>
      </header>
      {tab === "run" ? <RunView /> : <EvalView />}
    </div>
  );
}

/* ------------------------------------------------------------------ 실행 화면 */

function RunView() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [caseId, setCaseId] = useState<string>("");
  const [mode, setMode] = useState<Mode>("harness");
  const [agent, setAgent] = useState<AgentName>("mock");
  const [events, setEvents] = useState<HarnessEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [traceOverride, setTraceOverride] = useState<Trace | null>(null);
  const unsubscribe = useRef<() => void>();

  useEffect(() => {
    api.cases().then((c) => {
      setCases(c);
      setCaseId(c[0]?.id ?? "");
    }).catch((e) => setError(`백엔드에 연결할 수 없습니다: ${e.message}`));
    return () => unsubscribe.current?.();
  }, []);

  const start = async () => {
    unsubscribe.current?.();
    setEvents([]);
    setTraceOverride(null);
    setError(null);
    setRunning(true);
    try {
      const { run_id } = await api.startRun(caseId, mode, agent);
      unsubscribe.current = subscribe(run_id, (e) => setEvents((prev) => [...prev, e]), () => setRunning(false));
    } catch (e) {
      setError((e as Error).message);
      setRunning(false);
    }
  };

  const stageState = useMemo(() => {
    const state: Partial<Record<StageName, { status: string; attempt: number | null }>> = {};
    for (const e of events) if (e.type === "stage") state[e.stage] = { status: e.status, attempt: e.attempt };
    return state;
  }, [events]);
  const attempts = events.filter((e): e is Extract<HarnessEvent, { type: "attempt" }> => e.type === "attempt").map((e) => e.attempt);
  const doneTrace = events.find((e): e is Extract<HarnessEvent, { type: "done" }> => e.type === "done")?.trace ?? null;
  const trace = traceOverride ?? doneTrace;
  const runError = events.find((e): e is Extract<HarnessEvent, { type: "error" }> => e.type === "error");
  const selected = cases.find((c) => c.id === caseId);

  return (
    <main className="layout">
      <aside className="panel sidebar">
        <h2>테스트 케이스</h2>
        <ul className="cases">
          {cases.map((c) => (
            <li key={c.id}>
              <button className={c.id === caseId ? "case active" : "case"} onClick={() => setCaseId(c.id)} disabled={running}>
                <span className="case-id">{c.id}</span>
                <span className="case-title">{c.title}</span>
                <span className="tags">{c.tags.map((t) => <i key={t}>{t}</i>)}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="controls">
          <label>방식</label>
          <div className="segmented">
            <button className={mode === "harness" ? "on" : ""} onClick={() => setMode("harness")} disabled={running}>하네스 (실험군)</button>
            <button className={mode === "control" ? "on" : ""} onClick={() => setMode("control")} disabled={running}>단순 프롬프트 (대조군)</button>
          </div>
          <label>에이전트</label>
          <select value={agent} onChange={(e) => setAgent(e.target.value as AgentName)} disabled={running}>
            <option value="mock">Mock (결정론적, 무료)</option>
            <option value="claude">Claude (API 키 필요)</option>
          </select>
          <button className="primary" onClick={start} disabled={running || !caseId}>{running ? "실행 중…" : "실행"}</button>
        </div>
      </aside>

      <section className="content">
        {error && <div className="banner bad">{error}</div>}
        {runError && <div className="banner bad">{runError.message}</div>}
        {selected && (
          <div className="panel request">
            <span className="label">사용자 요청</span>
            <p>“{selected.request}”</p>
          </div>
        )}
        {events.length > 0 && <Pipeline state={stageState} mode={mode} />}
        {trace && <ContextCard trace={trace} />}
        {attempts.map((a) => <AttemptCard key={a.n} attempt={a} isLast={a.n === attempts.length} />)}
        {trace && <ResultCard trace={trace} onDecided={setTraceOverride} />}
        {events.length === 0 && !error && (
          <div className="empty">
            케이스와 방식을 고른 뒤 <b>실행</b>을 누르세요. 같은 케이스를 대조군/실험군으로 각각 돌려 비교할 수 있습니다.
          </div>
        )}
      </section>
    </main>
  );
}

function Pipeline({ state, mode }: { state: Partial<Record<StageName, { status: string; attempt: number | null }>>; mode: Mode }) {
  const visible = mode === "control" ? STAGES.filter((s) => !["context", "plan", "heal"].includes(s.id)) : STAGES;
  return (
    <div className="panel pipeline">
      {visible.map((s) => {
        const st = state[s.id];
        return (
          <div key={s.id} className={`stage ${st?.status ?? "idle"}`}>
            <span className="dot" />
            <span className="stage-label">{s.label}</span>
            {st?.attempt ? <span className="stage-attempt">#{st.attempt}</span> : null}
          </div>
        );
      })}
      {mode === "control" && <p className="note">대조군: 검증기는 관찰 전용으로만 실행되며, 결과와 무관하게 코드가 출하됩니다.</p>}
    </div>
  );
}

function ContextCard({ trace }: { trace: Trace }) {
  const { context, plan } = trace;
  return (
    <div className="panel">
      <h3>Context Filter · Plan</h3>
      <div className="kv">
        <div><span>팩트 상태</span><b className={context.fact_status === "VERIFIED" ? "good" : "warn"}>{context.fact_status}</b></div>
        <div><span>비중 상한</span><b>{pct(context.max_weight)}</b></div>
        <div><span>MDD 한도</span><b>{plan ? pct(plan.max_mdd) : "-"}</b></div>
        <div><span>토큰(추정)</span><b>{context.tokens.raw} → {context.tokens.compact} ({pct(context.tokens.reduction)} 절감)</b></div>
      </div>
      <table className="table">
        <thead><tr><th>주장</th><th>출처</th><th>DART 판정</th><th>근거 공시</th></tr></thead>
        <tbody>
          {context.facts.map((f, i) => (
            <tr key={i}>
              <td>{f.type}{f.counterparty ? ` · ${f.counterparty}` : ""}{f.amount_krw ? ` · ${(f.amount_krw / 1e8).toLocaleString()}억` : ""}</td>
              <td>{f.source}</td>
              <td><b className={f.status === "VERIFIED" ? "good" : "warn"}>{f.status}</b></td>
              <td>{f.evidence ? `${f.evidence.report_nm} (${f.evidence.rcept_dt})` : "공시 없음"}</td>
            </tr>
          ))}
          {context.facts.length === 0 && <tr><td colSpan={4}>검증할 주장이 없습니다 → UNVERIFIED 로 취급</td></tr>}
        </tbody>
      </table>
      {plan && plan.conflicts.length > 0 && (
        <ul className="conflicts">{plan.conflicts.map((c) => <li key={c}>{c}</li>)}</ul>
      )}
    </div>
  );
}

function AttemptCard({ attempt, isLast }: { attempt: Attempt; isLast: boolean }) {
  const [view, setView] = useState<"code" | "diff">(attempt.diff ? "diff" : "code");
  const [open, setOpen] = useState(isLast);
  useEffect(() => setOpen(isLast), [isLast]);
  const m = attempt.metrics;
  return (
    <div className={`panel attempt ${attempt.passed ? "passed" : "failed"}`}>
      <button className="attempt-head" onClick={() => setOpen(!open)}>
        <span className="badge">{attempt.passed ? "PASS" : "FAIL"}</span>
        <b>시도 #{attempt.n}</b>
        <span className="muted">{attempt.violations.map((v) => v.rule_id).filter((x, i, a) => a.indexOf(x) === i).join(" · ") || "위반 없음"}</span>
        <span className="muted right">tokens in {attempt.tokens.input} / out {attempt.tokens.output}</span>
      </button>
      {open && (
        <div className="attempt-body">
          {attempt.violations.length > 0 && (
            <table className="table">
              <thead><tr><th>rule</th><th>단계</th><th>줄</th><th>메시지</th><th>fix_hint (에이전트에 재주입)</th></tr></thead>
              <tbody>
                {attempt.violations.map((v, i) => (
                  <tr key={i}>
                    <td><code>{v.rule_id}</code></td>
                    <td>{v.stage}</td>
                    <td>{v.line ?? "-"}</td>
                    <td>{v.message}</td>
                    <td className="muted">{v.fix_hint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {m && (
            <div className="metrics">
              <div><span>MDD</span><b>{pct(m.mdd, 1)}</b></div>
              <div><span>수익률</span><b>{pct(m.total_return, 2)}</b></div>
              <div><span>최대 체결 비중</span><b>{pct(m.max_weight_used)}</b></div>
              <div><span>거래 / 손절 / 거부</span><b>{m.trades} / {m.stop_hits} / {m.rejected_orders}</b></div>
              <Sparkline values={attempt.equity_curve} />
            </div>
          )}
          <div className="code-tabs">
            <button className={view === "code" ? "on" : ""} onClick={() => setView("code")}>코드</button>
            {attempt.diff && <button className={view === "diff" ? "on" : ""} onClick={() => setView("diff")}>직전 시도 대비 diff</button>}
          </div>
          <pre className="code">
            {view === "code"
              ? attempt.code
              : attempt.diff.split("\n").map((line, i) => (
                  <span key={i} className={line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : ""}>{line + "\n"}</span>
                ))}
          </pre>
        </div>
      )}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 220, h = 48;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / span) * (h - 4) - 2}`).join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label="자산 곡선">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function ResultCard({ trace, onDecided }: { trace: Trace; onDecided: (t: Trace) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const decide = async (d: "approve" | "reject") => {
    setBusy(true);
    try {
      onDecided(await api.approve(trace.run_id, d));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  let tone = "bad", title = "", body = "";
  if (trace.status === "PASSED") {
    tone = "good";
    title = `검증 통과 · ${trace.attempts.length}회 시도`;
    body = "모든 게이트를 통과했습니다. 사람 승인(@RequiresApproval) 후에만 모의 주문 티켓이 생성됩니다.";
  } else if (trace.status === "ESCALATED") {
    tone = "warn";
    title = "출하 차단 · 사람 검토 필요 (fail-closed)";
    body = trace.escalation_reason ?? "";
  } else if (trace.status === "RELEASED") {
    tone = trace.unsafe ? "bad" : "good";
    title = trace.unsafe ? "대조군: 위험 코드가 그대로 출하됨" : "대조군: 출하됨 (위반 없음)";
    body = "단순 프롬프트 방식은 검증 없이 코드를 출하합니다. 위 시도 카드의 위반은 관찰 전용 계측 결과입니다.";
  } else if (trace.status === "ERROR") {
    title = "에이전트 오류";
    body = trace.escalation_reason ?? "";
  }

  return (
    <div className={`panel result ${tone}`}>
      <h3>{title}</h3>
      <p>{body}</p>
      <p className="muted">run_id: {trace.run_id} · {trace.duration_ms}ms · 산출물: backend/runs/{trace.run_id}/</p>
      {trace.status === "PASSED" && trace.approval === "PENDING" && (
        <div className="actions">
          <button className="primary" disabled={busy} onClick={() => decide("approve")}>승인 → 모의 주문 티켓 생성</button>
          <button disabled={busy} onClick={() => decide("reject")}>반려</button>
        </div>
      )}
      {trace.approval && trace.approval !== "PENDING" && <p><b>{trace.approval === "APPROVED" ? "승인됨 · order_ticket.json 생성" : "반려됨"}</b></p>}
      {err && <p className="bad-text">{err}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ 평가 화면 */

function EvalView() {
  const [agent, setAgent] = useState<AgentName>("mock");
  const [report, setReport] = useState<EvalReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.evaluate(agent));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const s = report?.summary;
  return (
    <main className="eval">
      <div className="panel eval-head">
        <div>
          <h2>A/B 평가: 단순 프롬프트 vs 하네스</h2>
          <p className="muted">전체 케이스를 두 방식으로 실행하고 지표를 집계합니다. Claude 선택 시 API 비용이 발생합니다.</p>
        </div>
        <div className="actions">
          <select value={agent} onChange={(e) => setAgent(e.target.value as AgentName)} disabled={busy}>
            <option value="mock">Mock</option>
            <option value="claude">Claude</option>
          </select>
          <button className="primary" onClick={run} disabled={busy}>{busy ? "평가 중…" : "평가 실행"}</button>
        </div>
      </div>
      {error && <div className="banner bad">{error}</div>}
      {s && (
        <>
          <div className="stats">
            <Stat label="위험 코드 방출률" control={pct(s.control.unsafe_release_rate)} harness={pct(s.harness.unsafe_release_rate)} goal="목표 0%" />
            <Stat label="Self-Healing 성공률" control="-" harness={pct(s.harness.self_healing_rate)} goal="목표 > 85%" />
            <Stat label="사람 검수 필요 런" control={`${s.control.human_review_runs}`} harness={`${s.harness.human_review_runs}`} goal="검증 세금 대리 지표" />
            <Stat label="컨텍스트 토큰 절감(추정)" control="-" harness={pct(s.token_reduction)} goal="목표 > 80%" />
          </div>
          <div className="panel">
            <table className="table">
              <thead><tr><th>케이스</th><th>팩트</th><th>대조군</th><th>대조군 MDD</th><th>하네스</th><th>시도별 위반</th><th>하네스 MDD</th></tr></thead>
              <tbody>
                {report!.rows.map((r) => (
                  <tr key={r.case_id}>
                    <td><b>{r.case_id}</b> {r.title}</td>
                    <td>{r.fact_status}</td>
                    <td><b className={r.control_unsafe ? "bad-text" : "good"}>{r.control_unsafe ? "UNSAFE" : "safe"}</b> <span className="muted">{r.control_rules.join(", ")}</span></td>
                    <td>{pct(r.control_mdd, 1)}</td>
                    <td><b className={r.harness_status === "PASSED" ? "good" : "warn"}>{r.harness_status}</b> ({r.harness_attempts})</td>
                    <td className="muted">{r.harness_rules_seen.map((x) => (x.length ? x.join("+") : "✓")).join(" → ")}</td>
                    <td>{pct(r.harness_mdd, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}

function Stat({ label, control, harness, goal }: { label: string; control: string; harness: string; goal: string }) {
  return (
    <div className="panel stat">
      <span className="label">{label}</span>
      <div className="stat-row">
        <div><span className="muted">대조군</span><b>{control}</b></div>
        <div><span className="muted">하네스</span><b className="accent">{harness}</b></div>
      </div>
      <span className="muted small">{goal}</span>
    </div>
  );
}
