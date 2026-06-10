/**
 * API client for SMN Studio backend.
 * Reads the API key from localStorage (set on first use via the key prompt).
 * In production the app is served from /studio so all paths are relative.
 */

import type { Workflow, WorkflowDefinition, WorkflowRun, WorkflowTrigger } from "../types/workflow";

export const API_BASE = "/studio/api/v1";
export const KEY_STORAGE = "smn_api_key";

export function getApiKey(): string {
  return localStorage.getItem(KEY_STORAGE) ?? "";
}

export function setApiKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key);
}

export function clearApiKey(): void {
  localStorage.removeItem(KEY_STORAGE);
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getApiKey(),
      ...(options?.headers ?? {}),
    },
  });

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? "Request failed");
  return data as T;
}

export interface WorkflowCreatePayload {
  name: string;
  description?: string;
  definition?: WorkflowDefinition;
  triggers?: WorkflowTrigger[];
}

export interface WorkflowUpdatePayload {
  name?: string;
  description?: string;
  definition?: WorkflowDefinition;
  triggers?: WorkflowTrigger[];
  is_active?: boolean;
}

export const api = {
  workflows: {
    list: (): Promise<Workflow[]> => req("/workflows"),

    get: (id: string): Promise<Workflow> => req(`/workflows/${id}`),

    create: (payload: WorkflowCreatePayload): Promise<Workflow> =>
      req("/workflows", {
        method: "POST",
        body: JSON.stringify({
          definition: { nodes: [], edges: [] },
          triggers: [],
          ...payload,
        }),
      }),

    update: (id: string, payload: WorkflowUpdatePayload): Promise<Workflow> =>
      req(`/workflows/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),

    delete: (id: string): Promise<void> =>
      req(`/workflows/${id}`, { method: "DELETE" }),

    run: (id: string, input: Record<string, unknown> = {}): Promise<WorkflowRun> =>
      req(`/workflows/${id}/run`, {
        method: "POST",
        body: JSON.stringify({ input }),
      }),

    listRuns: (id: string): Promise<WorkflowRun[]> => req(`/workflows/${id}/runs`),

    createWebhook: (id: string): Promise<{ id: string; token: string; url: string }> =>
      req(`/workflows/${id}/webhooks`, { method: "POST" }),
  },

  runs: {
    get: (id: string): Promise<WorkflowRun> => req(`/runs/${id}`),
  },
};
