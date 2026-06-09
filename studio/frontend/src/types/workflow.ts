// Shared TypeScript types mirroring the backend Pydantic schemas.

export type NodeType = "agent" | "llm_prompt" | "http" | "condition" | "delay" | "trigger";

export interface NodePosition {
  x: number;
  y: number;
}

export interface NodeData {
  label: string;
  config: Record<string, unknown>;
}

export interface WorkflowNode {
  id: string;
  type: NodeType;
  position: NodePosition;
  data: NodeData;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export interface WorkflowTrigger {
  type: "manual" | "webhook" | "schedule";
  config: Record<string, unknown>;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface Workflow {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  definition: WorkflowDefinition;
  triggers: WorkflowTrigger[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRunStep {
  id: string;
  node_id: string;
  node_type: string;
  node_label: string;
  status: "pending" | "running" | "completed" | "failed";
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  error?: string;
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  tenant_id: string;
  status: "pending" | "running" | "completed" | "failed";
  trigger_type: string;
  trigger_data?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
  steps: WorkflowRunStep[];
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

// Node palette metadata — what the sidebar shows
export interface NodeMeta {
  type: NodeType;
  label: string;
  description: string;
  color: string;
  defaultConfig: Record<string, unknown>;
}

export const NODE_PALETTE: NodeMeta[] = [
  {
    type: "agent",
    label: "SMN Agent",
    description: "Run a governed SMN agent",
    color: "#3b82f6",
    defaultConfig: { input_template: "", model: "", policy_name: "default" },
  },
  {
    type: "llm_prompt",
    label: "LLM Prompt",
    description: "Raw LLM call with a template",
    color: "#10b981",
    defaultConfig: { system_prompt: "", user_message: "", model: "" },
  },
  {
    type: "http",
    label: "HTTP Request",
    description: "Call an external API",
    color: "#f59e0b",
    defaultConfig: { url: "", method: "GET", headers: {}, body: "" },
  },
  {
    type: "condition",
    label: "Condition",
    description: "Branch on a comparison",
    color: "#8b5cf6",
    defaultConfig: { left: "", op: "==", right: "" },
  },
  {
    type: "delay",
    label: "Delay",
    description: "Wait before continuing",
    color: "#6b7280",
    defaultConfig: { seconds: 1 },
  },
];
