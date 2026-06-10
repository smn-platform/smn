import { Routes, Route, Navigate } from "react-router-dom";
import { useState } from "react";
import { getApiKey, setApiKey } from "./api/client";
import WorkflowList from "./components/WorkflowList";
import Editor from "./components/Editor";

export default function App() {
  const [apiKey, setKey] = useState(getApiKey());
  const [keyInput, setKeyInput] = useState("");

  function handleConnect() {
    const k = keyInput.trim();
    if (!k) return;
    // Write to localStorage synchronously BEFORE updating state so that
    // child components that immediately call the API can read it.
    setApiKey(k);
    setKey(k);
  }

  if (!apiKey) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", gap: 16 }}>
        <div style={{ textAlign: "center", marginBottom: 8 }}>
          <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>SMN Studio</div>
          <div style={{ color: "var(--muted)", fontSize: 13 }}>Enter your SMN API key to continue</div>
        </div>
        <form
          style={{ display: "flex", gap: 8, width: 360 }}
          onSubmit={e => { e.preventDefault(); handleConnect(); }}
        >
          <input
            type="password"
            placeholder="smn_..."
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            style={{ flex: 1 }}
            autoFocus
            autoComplete="current-password"
          />
          <button type="submit" className="btn-primary" disabled={!keyInput}>
            Connect
          </button>
        </form>
        <div style={{ fontSize: 12, color: "var(--dim)", textAlign: "center", lineHeight: 1.7 }}>
          Get a key: <code style={{ fontFamily: "monospace", fontSize: 11, background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>POST /api/v1/auth/bootstrap</code>
          <br />
          <span>with body <code style={{ fontFamily: "monospace", fontSize: 11, background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>{`{"tenant_name":"my-org"}`}</code></span>
        </div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<WorkflowList />} />
      <Route path="/workflows/:id" element={<Editor />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
