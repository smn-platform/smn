/**
 * SMN TypeScript SDK — main client.
 *
 * Usage:
 *   import { SMNClient } from '@smn/sdk';
 *   const client = new SMNClient({ apiKey: 'smn_...' });
 *   const agent = await client.agents.create({ name: 'analyst', model: 'gpt-4o' });
 */

import { raiseForStatus, type ErrorBody } from "./errors.js";
import type {
  Agent,
  APIKey,
  APIKeyCreated,
  AuditEntry,
  BillingStatus,
  BootstrapResult,
  ChainVerification,
  CreateAgentRequest,
  CreateKeyRequest,
  CreatePolicyRequest,
  CreateTaskRequest,
  CustomerResult,
  Framework,
  HealthCheck,
  ListAuditParams,
  ListPage,
  ListParams,
  ListTasksParams,
  Policy,
  StreamEvent,
  SubscriptionResult,
  SystemHealth,
  Task,
  TenantOverview,
  TenantUpdateResult,
  UpdateAgentRequest,
  UpdateTenantRequest,
  UsageSummary,
} from "./types.js";

// ═══════════════════════════════════════════════════════════════════
//  HTTP Transport
// ═══════════════════════════════════════════════════════════════════

interface ClientOptions {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
}

interface RequestOptions {
  method: string;
  path: string;
  body?: unknown;
  params?: Record<string, string | number | undefined>;
  idempotencyKey?: string;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

class Transport {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeout: number;
  private readonly maxRetries: number;

  constructor(opts: ClientOptions) {
    this.apiKey = opts.apiKey;
    this.baseUrl = (opts.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.timeout = opts.timeout ?? 30_000;
    this.maxRetries = opts.maxRetries ?? 3;
  }

  async request<T>(opts: RequestOptions): Promise<T> {
    const url = new URL(this.baseUrl + opts.path);
    if (opts.params) {
      for (const [k, v] of Object.entries(opts.params)) {
        if (v !== undefined) url.searchParams.set(k, String(v));
      }
    }

    const headers: Record<string, string> = {
      "X-API-Key": this.apiKey,
      "Content-Type": "application/json",
    };
    if (opts.idempotencyKey) {
      headers["Idempotency-Key"] = opts.idempotencyKey;
    }

    const init: RequestInit = {
      method: opts.method,
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: AbortSignal.timeout(this.timeout),
    };

    let lastError: unknown;
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const resp = await fetch(url.toString(), init);
        if (resp.status === 204) return undefined as T;

        const body = (await resp.json()) as Record<string, unknown>;
        if (resp.ok) return body as T;

        // Retry on 429 and 5xx
        if ((resp.status === 429 || resp.status >= 500) && attempt < this.maxRetries) {
          await sleep(500 * 2 ** attempt);
          continue;
        }

        raiseForStatus(resp.status, body as { error?: ErrorBody }, resp.headers.get("x-request-id") ?? undefined);
      } catch (err) {
        lastError = err;
        // Don't retry API errors
        if (err instanceof (await import("./errors.js")).APIError) throw err;
        if (attempt < this.maxRetries) {
          await sleep(500 * 2 ** attempt);
          continue;
        }
      }
    }
    throw lastError;
  }

  async *streamSSE(
    path: string,
    body: unknown,
  ): AsyncGenerator<StreamEvent, void, void> {
    const url = new URL(this.baseUrl + path);
    const resp = await fetch(url.toString(), {
      method: "POST",
      headers: {
        "X-API-Key": this.apiKey,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout),
    });

    if (!resp.ok) {
      const errBody = (await resp.json()) as { error?: ErrorBody };
      raiseForStatus(resp.status, errBody, resp.headers.get("x-request-id") ?? undefined);
    }

    const reader = resp.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();

    let buffer = "";
    let currentEvent = "message";
    let currentData = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          currentData = line.slice(5).trim();
        } else if (line === "") {
          if (currentData) {
            yield { event: currentEvent, data: currentData };
            currentEvent = "message";
            currentData = "";
          }
        }
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
//  Resource classes
// ═══════════════════════════════════════════════════════════════════

class AgentsResource {
  constructor(private t: Transport) {}

  create(req: CreateAgentRequest, idempotencyKey?: string): Promise<Agent> {
    return this.t.request({
      method: "POST",
      path: "/api/v1/agents",
      body: {
        name: req.name,
        description: req.description ?? "",
        model: req.model ?? "anthropic/claude-sonnet-4-6-20250415",
        risk_level: req.risk_level ?? "limited",
        policy_name: req.policy_name ?? "default",
        scopes: req.scopes ?? [],
        max_cost_per_task: req.max_cost_per_task ?? 5.0,
      },
      idempotencyKey,
    });
  }

  list(params?: ListParams): Promise<ListPage<Agent>> {
    return this.t.request({
      method: "GET",
      path: "/api/v1/agents",
      params: { limit: params?.limit ?? 20, offset: params?.offset ?? 0 },
    });
  }

  get(agentId: string): Promise<Agent> {
    return this.t.request({ method: "GET", path: `/api/v1/agents/${agentId}` });
  }

  update(agentId: string, req: UpdateAgentRequest): Promise<Agent> {
    return this.t.request({ method: "PATCH", path: `/api/v1/agents/${agentId}`, body: req });
  }

  delete(agentId: string): Promise<void> {
    return this.t.request({ method: "DELETE", path: `/api/v1/agents/${agentId}` });
  }
}

class TasksResource {
  constructor(private t: Transport) {}

  create(req: CreateTaskRequest, idempotencyKey?: string): Promise<Task> {
    return this.t.request({
      method: "POST",
      path: "/api/v1/tasks",
      body: req,
      idempotencyKey,
    });
  }

  list(params?: ListTasksParams): Promise<ListPage<Task>> {
    return this.t.request({
      method: "GET",
      path: "/api/v1/tasks",
      params: {
        limit: params?.limit ?? 20,
        offset: params?.offset ?? 0,
        agent_id: params?.agent_id,
        status: params?.status,
      },
    });
  }

  get(taskId: string): Promise<Task> {
    return this.t.request({ method: "GET", path: `/api/v1/tasks/${taskId}` });
  }

  stream(req: CreateTaskRequest): AsyncGenerator<StreamEvent, void, void> {
    return this.t.streamSSE("/api/v1/stream", req);
  }
}

class PoliciesResource {
  constructor(private t: Transport) {}

  create(req: CreatePolicyRequest, idempotencyKey?: string): Promise<Policy> {
    return this.t.request({
      method: "POST",
      path: "/api/v1/policies",
      body: req,
      idempotencyKey,
    });
  }

  list(params?: ListParams): Promise<ListPage<Policy>> {
    return this.t.request({
      method: "GET",
      path: "/api/v1/policies",
      params: { limit: params?.limit ?? 20, offset: params?.offset ?? 0 },
    });
  }

  get(policyId: string): Promise<Policy> {
    return this.t.request({ method: "GET", path: `/api/v1/policies/${policyId}` });
  }

  frameworks(): Promise<Framework[]> {
    return this.t.request({ method: "GET", path: "/api/v1/policies/frameworks" });
  }
}

class AuditResource {
  constructor(private t: Transport) {}

  list(params?: ListAuditParams): Promise<ListPage<AuditEntry>> {
    return this.t.request({
      method: "GET",
      path: "/api/v1/audit",
      params: {
        limit: params?.limit ?? 100,
        offset: params?.offset ?? 0,
        agent_id: params?.agent_id,
        task_id: params?.task_id,
        event_type: params?.event_type,
      },
    });
  }

  verify(): Promise<ChainVerification> {
    return this.t.request({ method: "GET", path: "/api/v1/audit/verify" });
  }
}

class KeysResource {
  constructor(private t: Transport) {}

  create(req: CreateKeyRequest, idempotencyKey?: string): Promise<APIKeyCreated> {
    return this.t.request({
      method: "POST",
      path: "/api/v1/auth/keys",
      body: req,
      idempotencyKey,
    });
  }

  list(params?: ListParams): Promise<ListPage<APIKey>> {
    return this.t.request({
      method: "GET",
      path: "/api/v1/auth/keys",
      params: { limit: params?.limit ?? 20, offset: params?.offset ?? 0 },
    });
  }

  revoke(keyId: string): Promise<void> {
    return this.t.request({ method: "DELETE", path: `/api/v1/auth/keys/${keyId}` });
  }
}

class BillingResource {
  constructor(private t: Transport) {}

  createCustomer(email?: string): Promise<CustomerResult> {
    return this.t.request({ method: "POST", path: "/api/v1/billing/customer", body: { email } });
  }

  subscribe(tier: string = "core"): Promise<SubscriptionResult> {
    return this.t.request({ method: "POST", path: "/api/v1/billing/subscribe", body: { tier } });
  }

  status(): Promise<BillingStatus> {
    return this.t.request({ method: "GET", path: "/api/v1/billing/status" });
  }
}

class AdminResource {
  constructor(private t: Transport) {}

  tenants(params?: ListParams): Promise<ListPage<TenantOverview>> {
    return this.t.request({
      method: "GET",
      path: "/api/v1/admin/tenants",
      params: { limit: params?.limit ?? 20, offset: params?.offset ?? 0 },
    });
  }

  updateTenant(tenantId: string, req: UpdateTenantRequest): Promise<TenantUpdateResult> {
    return this.t.request({ method: "PATCH", path: `/api/v1/admin/tenants/${tenantId}`, body: req });
  }

  health(): Promise<SystemHealth> {
    return this.t.request({ method: "GET", path: "/api/v1/admin/health" });
  }

  usage(): Promise<UsageSummary[]> {
    return this.t.request({ method: "GET", path: "/api/v1/admin/usage" });
  }

  tenantUsage(tenantId: string): Promise<UsageSummary> {
    return this.t.request({ method: "GET", path: `/api/v1/admin/usage/${tenantId}` });
  }
}

// ═══════════════════════════════════════════════════════════════════
//  Main client
// ═══════════════════════════════════════════════════════════════════

export class SMNClient {
  readonly agents: AgentsResource;
  readonly tasks: TasksResource;
  readonly policies: PoliciesResource;
  readonly audit: AuditResource;
  readonly keys: KeysResource;
  readonly billing: BillingResource;
  readonly admin: AdminResource;

  private readonly transport: Transport;

  constructor(opts: ClientOptions) {
    this.transport = new Transport(opts);
    this.agents = new AgentsResource(this.transport);
    this.tasks = new TasksResource(this.transport);
    this.policies = new PoliciesResource(this.transport);
    this.audit = new AuditResource(this.transport);
    this.keys = new KeysResource(this.transport);
    this.billing = new BillingResource(this.transport);
    this.admin = new AdminResource(this.transport);
  }

  health(): Promise<HealthCheck> {
    return this.transport.request({ method: "GET", path: "/api/v1/health" });
  }

  static async bootstrap(opts: {
    tenantName: string;
    keyName?: string;
    baseUrl?: string;
  }): Promise<BootstrapResult> {
    const baseUrl = (opts.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    const resp = await fetch(`${baseUrl}/api/v1/auth/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_name: opts.tenantName,
        key_name: opts.keyName ?? "default",
      }),
    });

    if (!resp.ok) {
      const body = (await resp.json()) as { error?: ErrorBody };
      raiseForStatus(resp.status, body, resp.headers.get("x-request-id") ?? undefined);
    }

    return (await resp.json()) as BootstrapResult;
  }
}
