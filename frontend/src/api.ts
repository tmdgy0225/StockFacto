import type { AgentName, CaseSummary, EvalReport, HarnessEvent, Mode, Trace } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  cases: () => request<CaseSummary[]>("/api/cases"),
  startRun: (case_id: string, mode: Mode, agent: AgentName) =>
    request<{ run_id: string }>("/api/runs", { method: "POST", body: JSON.stringify({ case_id, mode, agent }) }),
  approve: (runId: string, decision: "approve" | "reject") =>
    request<Trace>(`/api/runs/${runId}/approval`, { method: "POST", body: JSON.stringify({ decision }) }),
  evaluate: (agent: AgentName) => request<EvalReport>("/api/eval", { method: "POST", body: JSON.stringify({ agent }) }),
};

export function subscribe(runId: string, onEvent: (e: HarnessEvent) => void, onEnd: () => void): () => void {
  const source = new EventSource(`/api/runs/${runId}/events`);
  source.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  source.addEventListener("end", () => {
    source.close();
    onEnd();
  });
  source.onerror = () => {
    source.close();
    onEnd();
  };
  return () => source.close();
}
