import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Workflow } from "../types/workflow";

export default function WorkflowList() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      const wfs = await api.workflows.list();
      setWorkflows(wfs);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function handleCreate() {
    if (!newName.trim()) return;
    try {
      const wf = await api.workflows.create({ name: newName.trim() });
      navigate(`/workflows/${wf.id}`);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm("Delete this workflow?")) return;
    try {
      await api.workflows.delete(id);
      setWorkflows(ws => ws.filter(w => w.id !== id));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "40px 24px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 32 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>SMN Studio</h1>
          <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 2 }}>Visual workflow builder</div>
        </div>
        <button className="btn-primary" onClick={() => setCreating(true)}>+ New Workflow</button>
      </div>

      {/* Create form */}
      {creating && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 16, marginBottom: 16, display: "flex", gap: 8 }}>
          <input
            autoFocus
            placeholder="Workflow name…"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") void handleCreate(); if (e.key === "Escape") setCreating(false); }}
            style={{ flex: 1 }}
          />
          <button className="btn-primary" onClick={() => void handleCreate()} disabled={!newName.trim()}>Create</button>
          <button className="btn-ghost" onClick={() => setCreating(false)}>Cancel</button>
        </div>
      )}

      {error && (
        <div style={{ color: "var(--danger)", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: "var(--radius)", padding: "10px 14px", marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading && <div style={{ color: "var(--muted)", textAlign: "center", paddingTop: 40 }}>Loading…</div>}

      {!loading && workflows.length === 0 && (
        <div style={{ textAlign: "center", color: "var(--dim)", paddingTop: 60 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⬡</div>
          <div>No workflows yet. Create one to get started.</div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {workflows.map(wf => (
          <div
            key={wf.id}
            onClick={() => navigate(`/workflows/${wf.id}`)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "14px 16px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center", transition: "border-color 0.15s" }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--border-hover)")}
            onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
          >
            <div>
              <div style={{ fontWeight: 600, marginBottom: 2 }}>{wf.name}</div>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>
                {wf.definition.nodes.length} node{wf.definition.nodes.length !== 1 ? "s" : ""}
                {" · "}
                {wf.is_active ? <span style={{ color: "var(--accent)" }}>active</span> : <span style={{ color: "var(--dim)" }}>inactive</span>}
              </div>
            </div>
            <button
              className="btn-ghost"
              style={{ fontSize: 12, padding: "4px 10px", color: "var(--danger)", borderColor: "transparent" }}
              onClick={e => void handleDelete(wf.id, e)}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
