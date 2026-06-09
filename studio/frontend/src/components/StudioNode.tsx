/**
 * Custom React Flow node component — used for all SMN Studio node types.
 * Colour-coded by type, shows label, handles on left (input) and right (output).
 * Condition nodes have two right-side handles: "true" (top) and "false" (bottom).
 */

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { NODE_PALETTE } from "../types/workflow";

const TYPE_COLOR: Record<string, string> = Object.fromEntries(
  NODE_PALETTE.map(n => [n.type, n.color])
);

function StudioNode({ data, type, selected }: NodeProps) {
  const color = TYPE_COLOR[type as string] ?? "#6b7280";
  const isCondition = type === "condition";
  const isTrigger = type === "trigger";

  return (
    <div
      style={{
        background: "var(--surface)",
        border: `2px solid ${selected ? color : "var(--border)"}`,
        borderRadius: 10,
        minWidth: 160,
        boxShadow: selected ? `0 0 0 3px ${color}33` : "none",
        transition: "border-color 0.15s, box-shadow 0.15s",
        overflow: "hidden",
      }}
    >
      {/* Header strip */}
      <div style={{ background: color, padding: "6px 12px", fontSize: 11, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "#fff", opacity: 0.9 }}>
        {type === "llm_prompt" ? "LLM Prompt" : type === "http" ? "HTTP" : type}
      </div>

      {/* Label */}
      <div style={{ padding: "8px 12px", fontSize: 13, fontWeight: 500, color: "var(--text)", wordBreak: "break-word" }}>
        {(data as { label?: string }).label || "(unnamed)"}
      </div>

      {/* Input handle — left */}
      {!isTrigger && (
        <Handle type="target" position={Position.Left} style={{ background: "var(--muted)", width: 10, height: 10 }} />
      )}

      {/* Output handles — right */}
      {isCondition ? (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            style={{ background: "var(--success)", width: 10, height: 10, top: "35%" }}
          />
          <Handle
            type="source"
            position={Position.Right}
            id="false"
            style={{ background: "var(--danger)", width: 10, height: 10, top: "65%" }}
          />
        </>
      ) : (
        <Handle
          type="source"
          position={Position.Right}
          id="output"
          style={{ background: color, width: 10, height: 10 }}
        />
      )}
    </div>
  );
}

export default memo(StudioNode);
