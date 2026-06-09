/**
 * Left sidebar — drag node types onto the canvas to add them.
 */

import type { NodeMeta } from "../types/workflow";
import { NODE_PALETTE } from "../types/workflow";

interface Props {
  onDragStart: (e: React.DragEvent, meta: NodeMeta) => void;
}

export default function NodePalette({ onDragStart }: Props) {
  return (
    <div style={{ width: 200, background: "var(--surface)", borderRight: "1px solid var(--border)", padding: 12, display: "flex", flexDirection: "column", gap: 4, overflowY: "auto" }}>
      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--dim)", marginBottom: 8, paddingLeft: 4 }}>
        Nodes
      </div>
      {NODE_PALETTE.map(meta => (
        <div
          key={meta.type}
          draggable
          onDragStart={e => onDragStart(e, meta)}
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "10px 12px",
            cursor: "grab",
            userSelect: "none",
            transition: "border-color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.borderColor = meta.color)}
          onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
        >
          <div style={{ fontSize: 13, fontWeight: 600, color: meta.color, marginBottom: 2 }}>
            {meta.label}
          </div>
          <div style={{ fontSize: 11, color: "var(--dim)" }}>{meta.description}</div>
        </div>
      ))}
    </div>
  );
}
