/**
 * Main workflow editor — React Flow canvas with palette, config panel, and runs panel.
 *
 * Layout:
 *  [NodePalette 200px] | [React Flow canvas flex] | [ConfigPanel/RunsPanel 260px]
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from "@xyflow/react";

import { api } from "../api/client";
import type { NodeMeta, Workflow, WorkflowEdge, WorkflowNode } from "../types/workflow";
import NodePalette from "./NodePalette";
import ConfigPanel from "./ConfigPanel";
import RunsPanel from "./RunsPanel";
import StudioNode from "./StudioNode";

// Register custom node type — used for all SMN node types
const nodeTypes = {
  agent: StudioNode,
  llm_prompt: StudioNode,
  http: StudioNode,
  condition: StudioNode,
  delay: StudioNode,
  trigger: StudioNode,
};

// Convert from API types to React Flow types
function toRFNode(n: WorkflowNode): Node {
  return { id: n.id, type: n.type, position: n.position, data: { label: n.data.label, config: n.data.config } };
}
function toRFEdge(e: WorkflowEdge): Edge {
  return { id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle ?? undefined, targetHandle: e.targetHandle ?? undefined };
}
function fromRFNode(n: Node): WorkflowNode {
  const d = n.data as { label?: string; config?: Record<string, unknown> };
  return { id: n.id, type: n.type as WorkflowNode["type"], position: n.position, data: { label: d.label ?? "", config: d.config ?? {} } };
}
function fromRFEdge(e: Edge): WorkflowEdge {
  return { id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle ?? null, targetHandle: e.targetHandle ?? null };
}

let nodeSeq = 1;
function nextId() { return `node-${nodeSeq++}`; }

type RightPanel = "config" | "runs";

export default function Editor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [runTick, setRunTick] = useState(0);
  const [rightPanel, setRightPanel] = useState<RightPanel>("config");
  const [error, setError] = useState<string | null>(null);

  const rfInstance = useRef<ReactFlowInstance | null>(null);

  // ── Load workflow ─────────────────────────────────────────────
  useEffect(() => {
    if (!id) return;
    api.workflows.get(id).then(wf => {
      setWorkflow(wf);
      setNodes(wf.definition.nodes.map(toRFNode));
      setEdges(wf.definition.edges.map(toRFEdge));
    }).catch(e => setError(String(e)));
  }, [id]);

  // ── React Flow callbacks ──────────────────────────────────────
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes(ns => applyNodeChanges(changes, ns));
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges(es => applyEdgeChanges(changes, es));
  }, []);

  const onConnect = useCallback((connection: Connection) => {
    setEdges(es => addEdge({ ...connection, id: `e-${Date.now()}` }, es));
  }, []);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
    setRightPanel("config");
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  // ── Drag-from-palette ─────────────────────────────────────────
  function onDragStart(e: React.DragEvent, meta: NodeMeta) {
    e.dataTransfer.setData("application/smn-node", JSON.stringify(meta));
    e.dataTransfer.effectAllowed = "move";
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/smn-node");
    if (!raw || !rfInstance.current) return;

    const meta: NodeMeta = JSON.parse(raw);
    const position = rfInstance.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });

    const newNode: Node = {
      id: nextId(),
      type: meta.type,
      position,
      data: { label: meta.label, config: { ...meta.defaultConfig } },
    };
    setNodes(ns => [...ns, newNode]);
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }

  // ── Config panel callback ─────────────────────────────────────
  function onNodeConfigChange(id: string, label: string, config: Record<string, unknown>) {
    setNodes(ns =>
      ns.map(n => n.id === id ? { ...n, data: { ...n.data, label, config } } : n)
    );
  }

  // ── Save ──────────────────────────────────────────────────────
  async function handleSave() {
    if (!workflow) return;
    setSaving(true);
    setError(null);
    try {
      await api.workflows.update(workflow.id, {
        definition: {
          nodes: nodes.map(fromRFNode),
          edges: edges.map(fromRFEdge),
        },
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  // ── Run ───────────────────────────────────────────────────────
  async function handleRun() {
    if (!workflow) return;
    setRunning(true);
    setError(null);
    try {
      // Save first so the backend runs the current canvas state
      await api.workflows.update(workflow.id, {
        definition: { nodes: nodes.map(fromRFNode), edges: edges.map(fromRFEdge) },
      });
      await api.workflows.run(workflow.id);
      setRightPanel("runs");
      // Bump tick so RunsPanel refreshes
      setTimeout(() => setRunTick(t => t + 1), 500);
      setTimeout(() => setRunTick(t => t + 1), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  const selectedNode = nodes.find(n => n.id === selectedNodeId) ?? null;

  // ── Render ────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Top bar */}
      <div style={{ height: 52, background: "var(--surface)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12, padding: "0 16px", flexShrink: 0 }}>
        <button className="btn-ghost" style={{ padding: "4px 10px", fontSize: 13 }} onClick={() => navigate("/")}>
          ← Back
        </button>
        <div style={{ fontWeight: 600, fontSize: 15 }}>{workflow?.name ?? "Loading…"}</div>
        <div style={{ flex: 1 }} />
        {error && <div style={{ fontSize: 12, color: "var(--danger)", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{error}</div>}
        <button
          style={{ padding: "4px 10px", fontSize: 12, background: "transparent", border: "1px solid var(--border)", borderRadius: 6, color: rightPanel === "runs" ? "var(--primary)" : "var(--muted)", cursor: "pointer" }}
          onClick={() => setRightPanel(rightPanel === "runs" ? "config" : "runs")}
        >
          Runs
        </button>
        <button className="btn-ghost" onClick={() => void handleSave()} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button className="btn-primary" onClick={() => void handleRun()} disabled={running || saving}>
          {running ? "Running…" : "▶ Run"}
        </button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <NodePalette onDragStart={onDragStart} />

        {/* Canvas */}
        <div style={{ flex: 1 }} onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onInit={inst => { rfInstance.current = inst; }}
            fitView
            deleteKeyCode="Delete"
            style={{ background: "var(--bg)" }}
          >
            <Background color="var(--border)" gap={24} />
            <Controls />
          </ReactFlow>
        </div>

        {/* Right panel — config or runs */}
        <div style={{ width: 260, background: "var(--surface)", borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
          {rightPanel === "config" ? (
            <ConfigPanel node={selectedNode ? { id: selectedNode.id, type: selectedNode.type as WorkflowNode["type"], position: selectedNode.position, data: selectedNode.data as WorkflowNode["data"] } : null} onChange={onNodeConfigChange} />
          ) : (
            workflow && <RunsPanel workflowId={workflow.id} refreshTick={runTick} />
          )}
        </div>
      </div>
    </div>
  );
}
