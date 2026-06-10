/**
 * Right sidebar — plain-English configuration for each node type.
 * Designed for non-technical users: no model strings, no API jargon.
 */

import { useState, useEffect } from "react";
import type { WorkflowNode } from "../types/workflow";

interface Props {
  node: WorkflowNode | null;
  onChange: (id: string, label: string, config: Record<string, unknown>) => void;
}

// Friendly operator labels → raw backend value
const OPERATORS: { label: string; value: string }[] = [
  { label: "equals", value: "==" },
  { label: "does not equal", value: "!=" },
  { label: "is greater than", value: ">" },
  { label: "is at least", value: ">=" },
  { label: "is less than", value: "<" },
  { label: "is at most", value: "<=" },
  { label: "contains", value: "contains" },
  { label: "starts with", value: "startswith" },
  { label: "ends with", value: "endswith" },
];

// Friendly model list — power users can still type custom values
const AI_MODELS: { label: string; value: string }[] = [
  { label: "Default (recommended)", value: "" },
  { label: "Claude Sonnet — balanced", value: "anthropic/claude-sonnet-4-5" },
  { label: "Claude Haiku — fast & cheap", value: "anthropic/claude-haiku-3-5" },
  { label: "GPT-4o — OpenAI flagship", value: "openai/gpt-4o" },
  { label: "GPT-4o Mini — fast & cheap", value: "openai/gpt-4o-mini" },
  { label: "Custom…", value: "__custom__" },
];

const NODE_TYPE_LABELS: Record<string, string> = {
  agent: "AI Agent",
  llm_prompt: "AI Prompt",
  http: "Web Request",
  condition: "Branch (If/Else)",
  delay: "Wait / Delay",
  trigger: "Trigger",
};

const NODE_TYPE_ICONS: Record<string, string> = {
  agent: "🤖",
  llm_prompt: "💬",
  http: "🌐",
  condition: "🔀",
  delay: "⏱",
  trigger: "⚡",
};

export default function ConfigPanel({ node, onChange }: Props) {
  const [label, setLabel] = useState("");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [customModel, setCustomModel] = useState(false);

  useEffect(() => {
    if (node) {
      setLabel(node.data.label || "");
      const c = { ...node.data.config };
      setConfig(c);
      // Detect if model is a custom value not in our list
      const modelVal = str(c.model);
      setCustomModel(!!modelVal && !AI_MODELS.some(m => m.value === modelVal));
    }
  }, [node?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!node) {
    return (
      <div style={{ width: 280, background: "var(--surface)", borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24, gap: 10 }}>
        <div style={{ fontSize: 28, opacity: 0.3 }}>☰</div>
        <div style={{ color: "var(--dim)", fontSize: 13, textAlign: "center", lineHeight: 1.6 }}>
          Click any node on the canvas to configure it
        </div>
      </div>
    );
  }

  function set(key: string, value: unknown) {
    const next = { ...config, [key]: value };
    setConfig(next);
    onChange(node!.id, label, next);
  }

  function updateLabel(v: string) {
    setLabel(v);
    onChange(node!.id, v, config);
  }

  function selectModel(v: string) {
    if (v === "__custom__") {
      setCustomModel(true);
      set("model", "");
    } else {
      setCustomModel(false);
      set("model", v);
    }
  }

  const modelValue = str(config.model);
  const modelSelectValue = customModel ? "__custom__" : (modelValue in Object.fromEntries(AI_MODELS.map(m => [m.value, true])) ? modelValue : "");

  return (
    <div style={{ width: 280, background: "var(--surface)", borderLeft: "1px solid var(--border)", overflowY: "auto", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div style={{ padding: "14px 16px 10px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
          <span style={{ fontSize: 18 }}>{NODE_TYPE_ICONS[node.type] ?? "⬡"}</span>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{NODE_TYPE_LABELS[node.type] ?? node.type}</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--dim)" }}>
          Step ID: <code style={{ fontFamily: "monospace", background: "rgba(255,255,255,0.06)", padding: "0 4px", borderRadius: 3 }}>{node.id}</code>
          <span style={{ marginLeft: 8, opacity: 0.6 }}>· ⌫ to delete</span>
        </div>
      </div>

      <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14 }}>

        {/* Step name */}
        <Field label="Step name" hint="Give this step a clear name so you can reference it later">
          <input
            value={label}
            onChange={e => updateLabel(e.target.value)}
            placeholder={NODE_TYPE_LABELS[node.type] ?? "Step name…"}
          />
        </Field>

        {/* ── AI Agent ── */}
        {node.type === "agent" && <>
          <Field label="What should this AI agent do?" hint="Describe the task in plain English. Use {step-id.output} to pass data from a previous step.">
            <textarea
              rows={4}
              value={str(config.input_template)}
              onChange={e => set("input_template", e.target.value)}
              placeholder="E.g. Summarise the following text and highlight the 3 most important points: {trigger.text}"
            />
          </Field>
          <ModelPicker value={modelSelectValue} customModel={customModel} customValue={modelValue} onSelect={selectModel} onCustomChange={v => set("model", v)} />
          <Field label="Safety policy" hint="Controls what this agent is allowed to do">
            <select value={str(config.policy_name) || "default"} onChange={e => set("policy_name", e.target.value)}>
              <option value="default">Default (balanced)</option>
              <option value="high_risk">High risk (extra checks)</option>
              <option value="eu_ai_act">EU AI Act compliant</option>
            </select>
          </Field>
        </>}

        {/* ── LLM Prompt ── */}
        {node.type === "llm_prompt" && <>
          <ModelPicker value={modelSelectValue} customModel={customModel} customValue={modelValue} onSelect={selectModel} onCustomChange={v => set("model", v)} />
          <Field label="AI role / background" hint="Tell the AI what kind of expert it should behave as">
            <textarea
              rows={3}
              value={str(config.system_prompt)}
              onChange={e => set("system_prompt", e.target.value)}
              placeholder="E.g. You are a concise business analyst who writes clear executive summaries."
            />
          </Field>
          <Field label="Message to send" hint="The question or request. Use {step-id.output} to include data from earlier steps.">
            <textarea
              rows={4}
              value={str(config.user_message)}
              onChange={e => set("user_message", e.target.value)}
              placeholder={"E.g. Summarise this report in 3 bullet points:\n{trigger.text}"}
            />
          </Field>
        </>}

        {/* ── HTTP Request ── */}
        {node.type === "http" && <>
          <Field label="Action">
            <div style={{ display: "flex", gap: 4 }}>
              {["GET", "POST", "PUT", "DELETE"].map(m => (
                <button
                  key={m}
                  type="button"
                  onClick={() => set("method", m)}
                  style={{
                    flex: 1, padding: "6px 0", fontSize: 12, fontWeight: 600,
                    background: (str(config.method) || "GET") === m ? "var(--primary)" : "var(--surface-2)",
                    color: (str(config.method) || "GET") === m ? "#fff" : "var(--muted)",
                    border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer",
                  }}
                >{m}</button>
              ))}
            </div>
          </Field>
          <Field label="URL to call" hint="Must start with https://. Supports {step-id.field} templates.">
            <input
              value={str(config.url)}
              onChange={e => set("url", e.target.value)}
              placeholder="https://api.example.com/endpoint"
            />
          </Field>
          {(str(config.method) || "GET") !== "GET" && (
            <Field label="Data to send (JSON)" hint={'Use {"key": "{step-id.value}"} to include dynamic data'}>
              <textarea
                rows={3}
                value={typeof config.body === "object" && config.body !== null ? JSON.stringify(config.body, null, 2) : str(config.body)}
                onChange={e => {
                  // Try to parse as JSON, fall back to raw string
                  try { set("body", JSON.parse(e.target.value)); }
                  catch { set("body", e.target.value); }
                }}
                placeholder={'{"message": "{trigger.text}"}'}
              />
            </Field>
          )}
        </>}

        {/* ── Condition / Branch ── */}
        {node.type === "condition" && <>
          <InfoBox>
            This step splits the workflow into two paths.<br />
            The <strong style={{ color: "var(--accent)" }}>✓ True</strong> path runs when the condition is met.<br />
            The <strong style={{ color: "var(--danger)" }}>✗ False</strong> path runs when it isn't.
          </InfoBox>
          <Field label="Check this value" hint="Use {step-id.field} to reference a previous step's output">
            <input value={str(config.left)} onChange={e => set("left", e.target.value)} placeholder="{node-1.output}" />
          </Field>
          <Field label="Condition">
            <select value={str(config.op) || "=="} onChange={e => set("op", e.target.value)}>
              {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
            </select>
          </Field>
          <Field label="Compare against">
            <input value={str(config.right)} onChange={e => set("right", e.target.value)} placeholder="success" />
          </Field>
        </>}

        {/* ── Delay ── */}
        {node.type === "delay" && <>
          <InfoBox>Pauses the workflow for the specified duration before continuing.</InfoBox>
          <Field label="Wait for (seconds)" hint="Maximum 5 minutes (300 seconds)">
            <input
              type="number" min={1} max={300} step={1}
              value={num(config.seconds, 5)}
              onChange={e => set("seconds", Number(e.target.value))}
            />
            {num(config.seconds, 5) >= 60 && (
              <div style={{ fontSize: 11, color: "var(--amber)", marginTop: 4 }}>
                ≈ {(num(config.seconds, 5) / 60).toFixed(1)} minutes
              </div>
            )}
          </Field>
        </>}

        {/* Data reference hint */}
        {node.type !== "trigger" && node.type !== "delay" && (
          <details style={{ marginTop: 4 }}>
            <summary style={{ fontSize: 11, color: "var(--dim)", cursor: "pointer", userSelect: "none" }}>
              How to use data from earlier steps
            </summary>
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--muted)", background: "var(--surface-2)", borderRadius: 6, padding: "10px 12px", lineHeight: 1.8 }}>
              Type <code style={{ fontFamily: "monospace", background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>{"{step-id.output}"}</code> anywhere in a text field to insert the output of a previous step.<br /><br />
              This step's ID is <code style={{ fontFamily: "monospace", background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>{node.id}</code> — other steps can reference <code style={{ fontFamily: "monospace", background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>{`{${node.id}.output}`}</code>.
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────

function ModelPicker({ value, customModel, customValue, onSelect, onCustomChange }: {
  value: string; customModel: boolean; customValue: string;
  onSelect: (v: string) => void; onCustomChange: (v: string) => void;
}) {
  return (
    <Field label="AI model to use" hint="Not sure? Leave on Default.">
      <select value={value} onChange={e => onSelect(e.target.value)}>
        {AI_MODELS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
      </select>
      {customModel && (
        <input
          style={{ marginTop: 6 }}
          value={customValue}
          onChange={e => onCustomChange(e.target.value)}
          placeholder="provider/model-name"
        />
      )}
    </Field>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 5 }}>{label}</div>
      {children}
      {hint && <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 5, lineHeight: 1.5 }}>{hint}</div>}
    </div>
  );
}

function InfoBox({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 12, color: "var(--muted)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px 12px", lineHeight: 1.7 }}>
      {children}
    </div>
  );
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return "";
  return String(v);
}

function num(v: unknown, fallback: number): number {
  const n = Number(v);
  return isNaN(n) ? fallback : n;
}
