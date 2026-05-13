/**
 * SMN SDK error classes — mirror the server-side structured error format.
 */

export interface ErrorBody {
  type: string;
  code: string;
  message: string;
  param?: string;
  request_id?: string;
}

export class SMNError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SMNError";
  }
}

export class APIError extends SMNError {
  readonly statusCode: number;
  readonly errorType: string;
  readonly code: string;
  readonly param?: string;
  readonly requestId?: string;

  constructor(
    message: string,
    statusCode: number,
    errorType: string,
    code: string,
    param?: string,
    requestId?: string,
  ) {
    super(message);
    this.name = "APIError";
    this.statusCode = statusCode;
    this.errorType = errorType;
    this.code = code;
    this.param = param;
    this.requestId = requestId;
  }
}

export class AuthenticationError extends APIError {
  constructor(message = "Invalid or missing API key.", code = "invalid_api_key", requestId?: string) {
    super(message, 401, "authentication_error", code, undefined, requestId);
    this.name = "AuthenticationError";
  }
}

export class AuthorizationError extends APIError {
  constructor(message = "Insufficient permissions.", code = "insufficient_scope", requestId?: string) {
    super(message, 403, "authorization_error", code, undefined, requestId);
    this.name = "AuthorizationError";
  }
}

export class NotFoundError extends APIError {
  constructor(message = "Resource not found.", code = "resource_not_found", param?: string, requestId?: string) {
    super(message, 404, "invalid_request_error", code, param, requestId);
    this.name = "NotFoundError";
  }
}

export class BadRequestError extends APIError {
  constructor(message = "Bad request.", code = "bad_request", param?: string, requestId?: string) {
    super(message, 400, "invalid_request_error", code, param, requestId);
    this.name = "BadRequestError";
  }
}

export class ValidationError extends APIError {
  constructor(message = "Validation error.", code = "validation_error", param?: string, requestId?: string) {
    super(message, 422, "invalid_request_error", code, param, requestId);
    this.name = "ValidationError";
  }
}

export class RateLimitError extends APIError {
  constructor(message = "Rate limit exceeded.", code = "rate_limit_exceeded", requestId?: string) {
    super(message, 429, "rate_limit_error", code, undefined, requestId);
    this.name = "RateLimitError";
  }
}

const STATUS_TO_ERROR = new Map<number, (msg: string, code: string, param?: string, reqId?: string) => APIError>([
  [400, (m, c, p, r) => new BadRequestError(m, c, p, r)],
  [401, (m, c, _p, r) => new AuthenticationError(m, c, r)],
  [403, (m, c, _p, r) => new AuthorizationError(m, c, r)],
  [404, (m, c, p, r) => new NotFoundError(m, c, p, r)],
  [422, (m, c, p, r) => new ValidationError(m, c, p, r)],
  [429, (m, c, _p, r) => new RateLimitError(m, c, r)],
]);

export function raiseForStatus(
  statusCode: number,
  body: { error?: ErrorBody },
  requestId?: string,
): never {
  const err = body.error ?? { type: "api_error", code: "unknown", message: "Unknown error" };
  const factory = STATUS_TO_ERROR.get(statusCode);
  const reqId = requestId ?? err.request_id;

  if (factory) {
    throw factory(err.message, err.code, err.param, reqId);
  }

  throw new APIError(
    err.message,
    statusCode,
    err.type,
    err.code,
    err.param,
    reqId,
  );
}
