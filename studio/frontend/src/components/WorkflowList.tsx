import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, clearApiKey } from "../api/client";
import type { Workflow } from "../types/workflow";

function Step({ n, text }: { n: number; text: string }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <span style={{ width: 20, height: 20, borderRadius: "50%", background: "var(--primary)", color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>{n}</span>
      <span style={{ color: "var(--muted)", lineHeight: 1.5 }}>{text}</span>
    </div>
  );
}

export default function WorkflowList() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [copilotPrompt, setCopilotPrompt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draftNotes, setDraftNotes] = useState<string[]>([]);

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

  async function handleCopilotCreate() {
    const prompt = copilotPrompt.trim();
    if (!prompt) return;
    setDrafting(true);
    setError(null);
    setDraftNotes([]);
    try {
      const draft = await api.copilot.draftWorkflow(prompt);
      const wf = await api.workflows.create({
        name: draft.name,
        description: draft.description,
        definition: draft.definition,
      });
      setDraftNotes(draft.notes);
      navigate(`/workflows/${wf.id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setDrafting(false);
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
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            style={{ background: "transparent", border: "none", fontSize: 12, color: "var(--dim)", cursor: "pointer", padding: "4px 8px" }}
            title="Change API key"
            onClick={() => { clearApiKey(); window.location.reload(); }}
          >
            Change key
          </button>
          <button className="btn-primary" onClick={() => setCreating(true)}>+ New Workflow</button>
        </div>
      </div>

      {/* Create form */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 16, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 10 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Build from a description</div>
            <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 2 }}>
              Describe the workflow you want. SMN will draft editable steps on the canvas.
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--accent)", background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.18)", borderRadius: 999, padding: "3px 8px", whiteSpace: "nowrap" }}>
            Copilot preview
          </div>
        </div>
        <textarea
          rows={3}
          value={copilotPrompt}
          onChange={e => setCopilotPrompt(e.target.value)}
          placeholder="E.g. When a new client form arrives, extract the key details, decide if it is urgent, then send a summary to my team."
          onKeyDown={e => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") void handleCopilotCreate();
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginTop: 10 }}>
          <div style={{ color: "var(--dim)", fontSize: 11 }}>Press Ctrl+Enter to draft</div>
          <button className="btn-primary" onClick={() => void handleCopilotCreate()} disabled={!copilotPrompt.trim() || drafting}>
            {drafting ? "Drafting..." : "Draft workflow"}
          </button>
        </div>
        {draftNotes.length > 0 && (
          <div style={{ marginTop: 10, color: "var(--muted)", fontSize: 12 }}>
            {draftNotes[0]}
          </div>
        )}
      </div>

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
        <div style={{ textAlign: "center", color: "var(--muted)", paddingTop: 40, display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
          <div style={{ fontSize: 36, marginBottom: 4 }}>⬡</div>
          <div style={{ fontWeight: 600, fontSize: 15 }}>No workflows yet</div>
          <div style={{ color: "var(--dim)", fontSize: 13, lineHeight: 1.8, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "20px 28px", textAlign: "left", maxWidth: 400 }}>
            <div style={{ fontWeight: 600, color: "var(--muted)", marginBottom: 10 }}>How it works</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Step n={1} text="Click «+ New Workflow» to create one" />
              <Step n={2} text="Drag nodes from the left panel onto the canvas" />
              <Step n={3} text="Click a node to configure it in the right panel" />
              <Step n={4} text="Connect nodes by dragging from the ▶ handle on the right edge to the ● handle on the left" />
              <Step n={5} text="Press Save then ▶ Run to execute" />
            </div>
          </div>
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
