/**
 * Runs panel — shows recent workflow executions with per-step status.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api/client";
import type { WorkflowRun } from "../types/workflow";

interface Props {
  workflowId: string;
  refreshTick: number; // increment to force refresh
}

const STATUS_COLOR: Record<string, string> = {
  pending: "var(--dim)",
  running: "var(--amber)",
  completed: "var(--accent)",
  failed: "var(--danger)",
};

export default function RunsPanel({ workflowId, refreshTick }: Props) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.workflows.listRuns(workflowId);
      setRuns(data);
      // Auto-expand the most recent run
      if (data.length > 0) setExpanded(prev => prev ?? data[0].id);
      // Keep polling while any run is active
      const hasActive = data.some(r => r.status === "pending" || r.status === "running");
      if (hasActive) {
        pollRef.current = setTimeout(() => void load(), 1500);
      }
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    void load();
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [load, refreshTick]);

  return (
    <div style={{ padding: "12px 16px", overflowY: "auto", maxHeight: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--dim)" }}>
          Recent Runs
        </div>
        {loading && <span style={{ fontSize: 11, color: "var(--dim)" }}>Loading…</span>}
        {!loading && runs.some(r => r.status === "pending" || r.status === "running") && (
          <span title="Polling for updates" style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--amber)", display: "inline-block", animation: "pulse 1.2s infinite" }} />
        )}
      </div>

      {runs.length === 0 && !loading && (
        <div style={{ color: "var(--dim)", fontSize: 12 }}>No runs yet. Hit Run to execute.</div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {runs.map(run => (
          <div key={run.id} style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
            <div
              style={{ padding: "8px 12px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
              onClick={() => setExpanded(expanded === run.id ? null : run.id)}
            >
              <div style={{ fontSize: 12 }}>
                <span style={{ fontWeight: 600, color: STATUS_COLOR[run.status] ?? "var(--muted)" }}>
                  {run.status.toUpperCase()}
                </span>
                <span style={{ color: "var(--dim)", marginLeft: 8 }}>{run.trigger_type}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--dim)" }}>
                {new Date(run.created_at).toLocaleTimeString()}
              </div>
            </div>

            {expanded === run.id && (
              <div style={{ borderTop: "1px solid var(--border)", padding: "8px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
                {run.steps.length === 0 && (
                  <div style={{ fontSize: 11, color: "var(--dim)" }}>No steps recorded yet.</div>
                )}
                {run.steps.map(step => (
                  <div key={step.id} style={{ display: "flex", gap: 8, fontSize: 11, alignItems: "center" }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_COLOR[step.status] ?? "var(--dim)", flexShrink: 0, display: "inline-block" }} />
                    <span style={{ color: "var(--muted)", flex: 1 }}>{step.node_label || step.node_id}</span>
                    {step.duration_ms != null && (
                      <span style={{ color: "var(--dim)" }}>{step.duration_ms} ms</span>
                    )}
                  </div>
                ))}
                {run.error && (
                  <div style={{ marginTop: 4, fontSize: 11, color: "var(--danger)", background: "rgba(239,68,68,0.08)", borderRadius: 4, padding: "4px 8px" }}>
                    {run.error}
                  </div>
                )}
                {run.output && (
                  <details style={{ marginTop: 4 }}>
                    <summary style={{ fontSize: 11, color: "var(--dim)", cursor: "pointer" }}>Output</summary>
                    <pre style={{ fontSize: 10, color: "var(--muted)", marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                      {JSON.stringify(run.output, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
