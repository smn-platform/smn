/**
 * Right sidebar — shows a config form for the currently selected node.
 * Each node type renders its own set of fields.
 */

import { useState, useEffect } from "react";
import type { WorkflowNode } from "../types/workflow";

interface Props {
  node: WorkflowNode | null;
  onChange: (id: string, label: string, config: Record<string, unknown>) => void;
}

const OPERATORS = ["==", "!=", ">", ">=", "<", "<=", "contains", "startswith", "endswith"];

export default function ConfigPanel({ node, onChange }: Props) {
  const [label, setLabel] = useState("");
  const [config, setConfig] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (node) {
      setLabel(node.data.label || "");
      setConfig({ ...node.data.config });
    }
  }, [node?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!node) {
    return (
      <div style={{ width: 260, background: "var(--surface)", borderLeft: "1px solid var(--border)", padding: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "var(--dim)", fontSize: 13, textAlign: "center" }}>
          Select a node to configure it
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

  return (
    <div style={{ width: 260, background: "var(--surface)", borderLeft: "1px solid var(--border)", padding: 16, overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--dim)" }}>
        {node.type.replace("_", " ")}
      </div>

      {/* Common: label */}
      <div className="field">
        <label>Label</label>
        <input value={label} onChange={e => updateLabel(e.target.value)} placeholder="Node label…" />
      </div>

      {/* Agent */}
      {node.type === "agent" && (
        <>
          <Field label="Input template" help="Use {{node_id.output}} to pass data">
            <textarea rows={3} value={str(config.input_template)} onChange={e => set("input_template", e.target.value)} placeholder="What would you like the agent to do?" />
          </Field>
          <Field label="Model" help="Leave blank to use default">
            <input value={str(config.model)} onChange={e => set("model", e.target.value)} placeholder="anthropic/claude-sonnet-4-6-20250415" />
          </Field>
          <Field label="Policy">
            <input value={str(config.policy_name)} onChange={e => set("policy_name", e.target.value)} placeholder="default" />
          </Field>
        </>
      )}

      {/* LLM Prompt */}
      {node.type === "llm_prompt" && (
        <>
          <Field label="Model" help="Leave blank to use default">
            <input value={str(config.model)} onChange={e => set("model", e.target.value)} placeholder="anthropic/claude-sonnet-4-6-20250415" />
          </Field>
          <Field label="System prompt">
            <textarea rows={3} value={str(config.system_prompt)} onChange={e => set("system_prompt", e.target.value)} placeholder="You are a helpful assistant…" />
          </Field>
          <Field label="User message" help="Supports {{node_id.field}} templates">
            <textarea rows={3} value={str(config.user_message)} onChange={e => set("user_message", e.target.value)} placeholder="Summarise: {{trigger.text}}" />
          </Field>
        </>
      )}

      {/* HTTP */}
      {node.type === "http" && (
        <>
          <Field label="Method">
            <select value={str(config.method) || "GET"} onChange={e => set("method", e.target.value)}>
              {["GET", "POST", "PUT", "PATCH", "DELETE"].map(m => <option key={m}>{m}</option>)}
            </select>
          </Field>
          <Field label="URL" help="https://... only. Supports templates.">
            <input value={str(config.url)} onChange={e => set("url", e.target.value)} placeholder="https://api.example.com/v1/..." />
          </Field>
          <Field label="Body (JSON or template)">
            <textarea rows={3} value={str(config.body)} onChange={e => set("body", e.target.value)} placeholder='{"key": "{{trigger.value}}"}' />
          </Field>
          <Field label="Timeout (seconds)">
            <input type="number" min={1} max={60} value={num(config.timeout_seconds, 30)} onChange={e => set("timeout_seconds", Number(e.target.value))} />
          </Field>
        </>
      )}

      {/* Condition */}
      {node.type === "condition" && (
        <>
          <div style={{ fontSize: 12, color: "var(--muted)", background: "var(--surface-2)", borderRadius: 6, padding: "8px 10px" }}>
            True edge → next node when condition passes<br />False edge → next node when it fails
          </div>
          <Field label="Left value" help="Supports {{node_id.field}}">
            <input value={str(config.left)} onChange={e => set("left", e.target.value)} placeholder="{{node-1.output}}" />
          </Field>
          <Field label="Operator">
            <select value={str(config.op) || "=="} onChange={e => set("op", e.target.value)}>
              {OPERATORS.map(op => <option key={op}>{op}</option>)}
            </select>
          </Field>
          <Field label="Right value">
            <input value={str(config.right)} onChange={e => set("right", e.target.value)} placeholder="success" />
          </Field>
        </>
      )}

      {/* Delay */}
      {node.type === "delay" && (
        <Field label="Wait (seconds)" help="Max 300 seconds">
          <input type="number" min={0.1} max={300} step={0.1} value={num(config.seconds, 1)} onChange={e => set("seconds", Number(e.target.value))} />
        </Field>
      )}
    </div>
  );
}

function Field({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {help && <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 4 }}>{help}</div>}
    </div>
  );
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

function num(v: unknown, fallback: number): number {
  const n = Number(v);
  return isNaN(n) ? fallback : n;
}
