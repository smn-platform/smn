/**
 * SMN TypeScript SDK — public API surface.
 *
 * @example
 * ```ts
 * import { SMNClient } from '@smn/sdk';
 *
 * const client = new SMNClient({ apiKey: 'smn_...' });
 * const agents = await client.agents.list();
 * ```
 */

export { SMNClient } from "./client.js";

export {
  SMNError,
  APIError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  BadRequestError,
  ValidationError,
  RateLimitError,
} from "./errors.js";

export type {
  Agent,
  Task,
  Policy,
  Framework,
  AuditEntry,
  ChainVerification,
  APIKey,
  APIKeyCreated,
  BootstrapResult,
  CustomerResult,
  SubscriptionResult,
  BillingStatus,
  TenantOverview,
  SystemHealth,
  UsageSummary,
  TenantUpdateResult,
  HealthCheck,
  StreamEvent,
  CreateAgentRequest,
  UpdateAgentRequest,
  CreateTaskRequest,
  CreatePolicyRequest,
  CreateKeyRequest,
  ListPage,
  ListParams,
  ListTasksParams,
  ListAuditParams,
  UpdateTenantRequest,
} from "./types.js";
