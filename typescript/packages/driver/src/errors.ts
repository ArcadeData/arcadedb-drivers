/**
 * Fields ArcadeDB's error responses may carry. The server does not guarantee
 * any of them are present, so every field is optional and parsing never
 * throws: a body that is missing, `null`, or not an object simply yields an
 * error with no extra detail beyond the HTTP status.
 */
interface ArcadeDBErrorBody {
  error?: string;
  exception?: string;
  detail?: string;
  requestId?: string;
  help?: string;
  exceptionArgs?: string;
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function parseBody(body: unknown): ArcadeDBErrorBody {
  if (body === null || body === undefined || typeof body !== "object") {
    return {};
  }
  const record = body as Record<string, unknown>;
  return {
    error: stringOrUndefined(record.error),
    exception: stringOrUndefined(record.exception),
    detail: stringOrUndefined(record.detail),
    requestId: stringOrUndefined(record.requestId),
    help: stringOrUndefined(record.help),
    exceptionArgs: stringOrUndefined(record.exceptionArgs),
  };
}

/**
 * Thrown by every `ArcadeDBServer`/`ArcadeDBDatabase` facade method when the
 * server answers with a non-2xx status. Carries the HTTP status plus
 * whatever the server's JSON error body contributed; every field beyond
 * `status` is optional because the body may be absent, unparsable, or
 * missing individual fields.
 *
 * NON-2XX IS THE COMMON CASE, NOT THE ONLY ONE. `status` is whatever the
 * exchange actually carried, and `facade/data.ts`'s `asQueryResponse` throws
 * one with `status: 200` when `/query` or `/command` answers 200 with a
 * streamed ndjson event - an encoding this client never requests. That is a
 * successful HTTP exchange whose body this client cannot honestly turn into a
 * `QueryEnvelope`, so it is reported as an error rather than as an empty
 * envelope asserting a completeness nobody claimed.
 *
 * The consequence for callers: `err.status` alone no longer classifies a
 * failure. Code shaped like `if (err.status >= 500) retry()` has a case it
 * cannot decide from the status - a 200 here is a protocol mismatch, never
 * transient, and retrying it will not help. Branch on `err.error` (or simply
 * do not retry a 2xx) when that distinction matters.
 *
 * `raw`, the unwrapped openapi-fetch client, never throws this (or anything
 * else) - it returns `{ data, error }` instead. That asymmetry is
 * deliberate: `ArcadeDBError` is a facade-only concern.
 */
export class ArcadeDBError extends Error {
  readonly status: number;
  readonly error?: string;
  readonly exception?: string;
  readonly detail?: string;
  /**
   * Correlation id for matching this failure against server logs. The
   * server sets the `X-Request-Id` response header on every response,
   * generating one when the client sent none, so this is populated
   * unconditionally rather than only when the caller happened to send its
   * own `X-Request-Id` request header.
   */
  readonly requestId?: string;
  /** Actionable guidance for handling this error, when the server supplied any. */
  readonly help?: string;
  /**
   * Extra exception arguments, when the server supplied any. Despite the
   * plural name, the contract types this as a plain string, not an array -
   * passed through as-is rather than parsed or coerced.
   */
  readonly exceptionArgs?: string;

  constructor(status: number, body?: unknown, requestId?: string) {
    const parsed = parseBody(body);
    const resolvedRequestId = requestId ?? parsed.requestId;
    super(parsed.error ?? parsed.detail ?? `ArcadeDB request failed with status ${status}`);
    this.name = "ArcadeDBError";
    this.status = status;
    this.error = parsed.error;
    this.exception = parsed.exception;
    this.detail = parsed.detail;
    this.requestId = resolvedRequestId;
    this.help = parsed.help;
    this.exceptionArgs = parsed.exceptionArgs;
    // Restore the prototype chain: extending built-ins gets clobbered when
    // the target is transpiled to ES5, and costs nothing when it isn't.
    Object.setPrototypeOf(this, ArcadeDBError.prototype);
  }

  /**
   * Builds an `ArcadeDBError` from a fetch `Response` and the (already
   * read) body openapi-fetch produced for a non-2xx result. Reads the
   * `X-Request-Id` response header as a fallback correlation id when the
   * body itself did not carry one.
   */
  static fromResponse(response: Response, body: unknown): ArcadeDBError {
    return new ArcadeDBError(response.status, body, response.headers.get("X-Request-Id") ?? undefined);
  }
}
