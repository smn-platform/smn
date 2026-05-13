import { describe, it, expect, vi, beforeEach } from "vitest";
import { SMNClient } from "../src/client.js";
import {
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  BadRequestError,
  RateLimitError,
} from "../src/errors.js";

const BASE_URL = "http://test-smn:8000";
const API_KEY = "smn_test_key_1234567890";

function listEnvelope(items: unknown[], opts?: { total?: number; limit?: number; offset?: number }) {
  const limit = opts?.limit ?? 20;
  const offset = opts?.offset ?? 0;
  const totalCount = opts?.total ?? items.length;
  return {
    object: "list",
    data: items,
    has_more: offset + limit < totalCount,
    total_count: totalCount,
    limit,
    offset,
  };
}

const AGENT_RESPONSE = {
  id: "agent-1",
  tenant_id: "tenant-1",
  name: "analyst",
  description: "Test agent",
  model: "gpt-4o",
  risk_level: "limited",
  policy_name: "default",
  scopes: ["api:full"],
  max_cost_per_task: 5.0,
  is_active: true,
};

const TASK_RESPONSE = {
  id: "task-1",
  agent_id: "agent-1",
  input_text: "Hello",
  status: "completed",
  output_text: "Hi there!",
  error: null,
  total_cost_usd: 0.01,
  total_steps: 1,
  model_used: "gpt-4o",
  started_at: "2026-04-18T10:00:00Z",
  completed_at: "2026-04-18T10:00:05Z",
};

function mockFetch(status: number, body: unknown, headers?: Record<string, string>) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers(headers ?? {}),
  });
}

function client(): SMNClient {
  return new SMNClient({ apiKey: API_KEY, baseUrl: BASE_URL, maxRetries: 0 });
}

describe("SMNClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("health", () => {
    it("returns health check", async () => {
      globalThis.fetch = mockFetch(200, { status: "healthy", version: "0.1.0", service: "smn" });
      const h = await client().health();
      expect(h.status).toBe("healthy");
      expect(h.version).toBe("0.1.0");
    });
  });

  describe("agents", () => {
    it("creates an agent", async () => {
      globalThis.fetch = mockFetch(201, AGENT_RESPONSE);
      const agent = await client().agents.create({ name: "analyst", model: "gpt-4o" });
      expect(agent.id).toBe("agent-1");
      expect(agent.name).toBe("analyst");
    });

    it("lists agents", async () => {
      globalThis.fetch = mockFetch(200, listEnvelope([AGENT_RESPONSE]));
      const page = await client().agents.list();
      expect(page.data).toHaveLength(1);
      expect(page.data[0].name).toBe("analyst");
      expect(page.total_count).toBe(1);
      expect(page.has_more).toBe(false);
    });

    it("gets an agent by id", async () => {
      globalThis.fetch = mockFetch(200, AGENT_RESPONSE);
      const agent = await client().agents.get("agent-1");
      expect(agent.id).toBe("agent-1");
    });

    it("updates an agent", async () => {
      const updated = { ...AGENT_RESPONSE, description: "Updated" };
      globalThis.fetch = mockFetch(200, updated);
      const agent = await client().agents.update("agent-1", { description: "Updated" });
      expect(agent.description).toBe("Updated");
    });

    it("deletes an agent", async () => {
      globalThis.fetch = mockFetch(204, undefined);
      await expect(client().agents.delete("agent-1")).resolves.toBeUndefined();
    });
  });

  describe("tasks", () => {
    it("creates a task", async () => {
      globalThis.fetch = mockFetch(201, TASK_RESPONSE);
      const task = await client().tasks.create({ agent_id: "agent-1", input_text: "Hello" });
      expect(task.status).toBe("completed");
    });

    it("lists tasks with filters", async () => {
      globalThis.fetch = mockFetch(200, listEnvelope([TASK_RESPONSE], { limit: 10 }));
      const page = await client().tasks.list({ agent_id: "agent-1", status: "completed", limit: 10 });
      expect(page.data).toHaveLength(1);
      expect(page.limit).toBe(10);
    });

    it("gets a task by id", async () => {
      globalThis.fetch = mockFetch(200, TASK_RESPONSE);
      const task = await client().tasks.get("task-1");
      expect(task.output_text).toBe("Hi there!");
    });
  });

  describe("policies", () => {
    it("creates a policy", async () => {
      const pol = { id: "pol-1", tenant_id: "t-1", name: "strict", version: 1, is_active: true, content: "max_steps: 5" };
      globalThis.fetch = mockFetch(201, pol);
      const result = await client().policies.create({ name: "strict", content: "max_steps: 5" });
      expect(result.name).toBe("strict");
    });

    it("lists policies", async () => {
      globalThis.fetch = mockFetch(200, listEnvelope([]));
      const page = await client().policies.list();
      expect(page.data).toEqual([]);
      expect(page.total_count).toBe(0);
    });
  });

  describe("audit", () => {
    it("verifies chain", async () => {
      globalThis.fetch = mockFetch(200, { is_valid: true, message: "OK" });
      const result = await client().audit.verify();
      expect(result.is_valid).toBe(true);
    });
  });

  describe("billing", () => {
    it("gets status", async () => {
      globalThis.fetch = mockFetch(200, {
        tenant_id: "t-1", plan_tier: "core",
        stripe_customer_id: null, stripe_subscription_id: null,
        subscription_status: null, current_period_end: null,
      });
      const status = await client().billing.status();
      expect(status.plan_tier).toBe("core");
    });
  });

  describe("keys", () => {
    it("lists keys", async () => {
      globalThis.fetch = mockFetch(200, listEnvelope([]));
      const page = await client().keys.list();
      expect(page.data).toEqual([]);
      expect(page.total_count).toBe(0);
    });
  });

  describe("headers", () => {
    it("sends api key header", async () => {
      const fn = mockFetch(200, { status: "healthy", version: "0.1.0", service: "smn" });
      globalThis.fetch = fn;
      await client().health();
      const headers = fn.mock.calls[0][1].headers as Record<string, string>;
      expect(headers["X-API-Key"]).toBe(API_KEY);
    });

    it("sends idempotency key header", async () => {
      const fn = mockFetch(201, AGENT_RESPONSE);
      globalThis.fetch = fn;
      await client().agents.create({ name: "test" }, "idem-123");
      const headers = fn.mock.calls[0][1].headers as Record<string, string>;
      expect(headers["Idempotency-Key"]).toBe("idem-123");
    });
  });
});

describe("Error handling", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("401 raises AuthenticationError", async () => {
    globalThis.fetch = mockFetch(401, {
      error: { type: "authentication_error", code: "invalid_api_key", message: "Bad key" },
    });
    await expect(client().agents.list()).rejects.toThrow(AuthenticationError);
  });

  it("403 raises AuthorizationError", async () => {
    globalThis.fetch = mockFetch(403, {
      error: { type: "authorization_error", code: "insufficient_scope", message: "No admin" },
    });
    await expect(client().admin.tenants()).rejects.toThrow(AuthorizationError);
  });

  it("404 raises NotFoundError", async () => {
    globalThis.fetch = mockFetch(404, {
      error: { type: "invalid_request_error", code: "resource_not_found", message: "Agent not found." },
    });
    await expect(client().agents.get("missing")).rejects.toThrow(NotFoundError);
  });

  it("400 raises BadRequestError", async () => {
    globalThis.fetch = mockFetch(400, {
      error: { type: "invalid_request_error", code: "bad_request", message: "Bad" },
    });
    await expect(client().agents.create({ name: "test" })).rejects.toThrow(BadRequestError);
  });

  it("429 raises RateLimitError", async () => {
    globalThis.fetch = mockFetch(429, {
      error: { type: "rate_limit_error", code: "rate_limit_exceeded", message: "Slow down" },
    });
    await expect(client().agents.list()).rejects.toThrow(RateLimitError);
  });

  it("error includes request id", async () => {
    globalThis.fetch = mockFetch(
      401,
      { error: { type: "authentication_error", code: "invalid_api_key", message: "Bad" } },
      { "x-request-id": "req_abc123" },
    );
    try {
      await client().agents.list();
    } catch (err) {
      expect(err).toBeInstanceOf(AuthenticationError);
      expect((err as AuthenticationError).requestId).toBe("req_abc123");
    }
  });
});
