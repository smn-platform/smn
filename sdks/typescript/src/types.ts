/**
 * TypeScript response types for the SMN API.
 */

export interface Agent {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  model: string;
  risk_level: string;
  policy_name: string;
  scopes: string[];
  max_cost_per_task: number;
  is_active: boolean;
}

export interface Task {
  id: string;
  agent_id: string;
  input_text: string;
  status: string;
  output_text: string | null;
  error: string | null;
  total_cost_usd: number | null;
  total_steps: number | null;
  model_used: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Policy {
  id: string;
  tenant_id: string;
  name: string;
  version: number;
  is_active: boolean;
  content: string;
}

export interface Framework {
  name: string;
  description: string;
  version: string;
}

export interface AuditEntry {
  id: string;
  tenant_id: string;
  agent_id: string | null;
  task_id: string | null;
  event_type: string;
  detail: string;
  timestamp: string;
  chain_hash: string;
}

export interface ChainVerification {
  is_valid: boolean;
  message: string;
}

export interface APIKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
}

export interface APIKeyCreated extends APIKey {
  raw_key: string;
}

export interface BootstrapResult {
  tenant_id: string;
  api_key: string;
}

export interface CustomerResult {
  stripe_customer_id: string;
}

export interface SubscriptionResult {
  subscription_id: string;
  client_secret: string | null;
}

export interface BillingStatus {
  tenant_id: string;
  plan_tier: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  subscription_status: string | null;
  current_period_end: string | null;
}

export interface TenantOverview {
  id: string;
  name: string;
  plan_tier: string;
  is_active: boolean;
  agent_count: number;
  task_count: number;
}

export interface SystemHealth {
  status: string;
  uptime_seconds: number;
  database: string;
  redis: string;
}

export interface UsageSummary {
  tenant_id: string;
  total_tasks: number;
  total_cost_usd: number;
  active_agents: number;
}

export interface TenantUpdateResult {
  id: string;
  name: string;
  plan_tier: string;
  is_active: boolean;
  rate_limit_rpm: number;
}

export interface HealthCheck {
  status: string;
  version: string;
  service: string;
  checks?: {
    database: { status: string; detail?: string };
    redis: { status: string; detail?: string };
  };
}

export interface StreamEvent {
  event: string;
  data: string;
}

// Request types
export interface CreateAgentRequest {
  name: string;
  description?: string;
  model?: string;
  risk_level?: string;
  policy_name?: string;
  scopes?: string[];
  max_cost_per_task?: number;
}

export interface UpdateAgentRequest {
  description?: string;
  model?: string;
  risk_level?: string;
  policy_name?: string;
  scopes?: string[];
  max_cost_per_task?: number;
  is_active?: boolean;
}

export interface CreateTaskRequest {
  agent_id: string;
  input_text: string;
  async_execution?: boolean;
}

export interface CreatePolicyRequest {
  name: string;
  content: string;
}

export interface CreateKeyRequest {
  name: string;
  scopes?: string[];
  expires_at?: string;
}

export interface ListParams {
  limit?: number;
  offset?: number;
}

export interface ListPage<T> {
  object: "list";
  data: T[];
  has_more: boolean;
  total_count: number;
  limit: number;
  offset: number;
}

export interface ListTasksParams extends ListParams {
  agent_id?: string;
  status?: string;
}

export interface ListAuditParams extends ListParams {
  agent_id?: string;
  task_id?: string;
  event_type?: string;
}

export interface UpdateTenantRequest {
  is_active?: boolean;
  plan_tier?: string;
  rate_limit_rpm?: number;
}
