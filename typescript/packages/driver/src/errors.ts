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
 * Parses a header value as a non-negative base-10 integer, or `undefined`.
 *
 * Used for `Retry-After` and `X-ArcadeDB-Commit-Index`. Anything else - an HTTP-date (which
 * `Retry-After` is allowed to be, though ArcadeDB never sends one), a negative or fractional
 * number, an empty value, trailing junk - yields `undefined` rather than throwing: an error that
 * could not be built because a back-off hint was malformed would replace the failure the caller
 * actually needs to see. A value past `Number.MAX_SAFE_INTEGER` is dropped too rather than being
 * silently rounded, since a commit index that is off by one is worse than an absent one.
 */
function parseNonNegativeInteger(value: string | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  const trimmed = value.trim();
  if (!/^[0-9]+$/.test(trimmed)) return undefined;
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) ? parsed : undefined;
}

/**
 * The same rule for a value that arrived as JSON rather than as header text - the in-band
 * `retryAfter`/`commitIndex` of a streamed error event.
 */
export function nonNegativeIntegerOrUndefined(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

/**
 * Fields of an `ArcadeDBError` that never come from the JSON error body. On a buffered response
 * they are headers, which `fromResponse` reads; on a streamed response they travel in band, and
 * the streaming facades pass them here directly.
 */
export interface ArcadeDBErrorExtras {
  retryAfter?: number;
  commitIndex?: number;
}

/** Reads `Retry-After` and `X-ArcadeDB-Commit-Index` off a response. Never throws. */
function extrasFromHeaders(headers: Headers): ArcadeDBErrorExtras {
  return {
    retryAfter: parseNonNegativeInteger(headers.get("Retry-After")),
    commitIndex: parseNonNegativeInteger(headers.get("X-ArcadeDB-Commit-Index")),
  };
}

/**
 * Thrown by every `ArcadeDBServer`/`ArcadeDBDatabase` facade method when the
 * server answers with a non-2xx status. Carries the HTTP status plus
 * whatever the server's JSON error body contributed; every field beyond
 * `status` is optional because the body may be absent, unparsable, or
 * missing individual fields.
 *
 * NON-2XX IS THE COMMON CASE, NOT THE ONLY ONE. For a buffered call `status`
 * is whatever the exchange actually carried, and `facade/data.ts`'s `asQueryResponse` throws
 * one with `status: 200` when the buffered `query`/`command` calls - the ones
 * that route through `asQueryResponse` - get back a 200 carrying a streamed
 * ndjson event instead of the buffered envelope they asked for. (`queryStream`/
 * `commandStream` in `facade/stream.ts` request that encoding on purpose and
 * decode it themselves, never reaching `asQueryResponse`.) For a buffered
 * call, that is a successful HTTP exchange whose body this client cannot
 * honestly turn into a `QueryEnvelope`, so it is reported as an error rather
 * than as an empty envelope asserting a completeness nobody claimed. A
 * streaming call's own in-band `error` event raises this same class of error
 * for a different reason, and with the event's in-band `status` rather than
 * the 200 its exchange carried (200 only when the event names none) - see
 * `facade/stream.ts`'s `raiseOnErrorEvent`.
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
  /**
   * Seconds to wait before retrying, when the server named a back-off: the `Retry-After` header on
   * a buffered response, or the in-band `retryAfter` of a streamed error event (a header cannot be
   * added once a stream has started). Present on a 503 when the node cannot execute the request yet
   * (e.g. a snapshot install) and on a 409 when an identical request is still in flight. `0` is a
   * real value - retry now - so test it against `undefined`, not for truthiness.
   */
  readonly retryAfter?: number;
  /**
   * Last applied Raft index on the node that answered: the `X-ArcadeDB-Commit-Index` header on a
   * buffered response, or the in-band `commitIndex` of a streamed batch error. Still a valid
   * read-your-writes barrier on a failure - send it back as `X-ArcadeDB-Read-After` and a later
   * read waits until that index is applied - because whatever a partial write already committed is
   * covered by it. Absent on a standalone (non-replicated) database, and absent rather than `0`
   * when the server sent none.
   */
  readonly commitIndex?: number;

  constructor(status: number, body?: unknown, requestId?: string, extras?: ArcadeDBErrorExtras) {
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
    this.retryAfter = extras?.retryAfter;
    this.commitIndex = extras?.commitIndex;
    // Restore the prototype chain: extending built-ins gets clobbered when
    // the target is transpiled to ES5, and costs nothing when it isn't.
    Object.setPrototypeOf(this, ArcadeDBError.prototype);
  }

  /**
   * Builds an `ArcadeDBError` from a fetch `Response` and the (already
   * read) body openapi-fetch produced for a non-2xx result. Reads the
   * `X-Request-Id` response header as the correlation id, ahead of any the
   * body carried, and `Retry-After` / `X-ArcadeDB-Commit-Index` into
   * `retryAfter` / `commitIndex`.
   */
  static fromResponse(response: Response, body: unknown): ArcadeDBError {
    return new ArcadeDBError(
      response.status,
      body,
      response.headers.get("X-Request-Id") ?? undefined,
      extrasFromHeaders(response.headers),
    );
  }
}

/** Keeps the string elements of `value` when it is an array; an empty array otherwise. */
function stringList(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

/**
 * Thrown by `db.ts.write()` when the server answers 400 with a JSON body - the contract's
 * `TimeSeriesWriteError`. Every `ArcadeDBError` field is filled the usual way; this adds what the
 * server reports about the samples.
 *
 * A write is NOT atomic. `written` samples landed even though the call failed, and only `dropped`
 * ones did not, so a failed write is something to reconcile rather than re-send whole: re-sending
 * the batch writes the `written` samples a second time. The four lists say why samples were
 * dropped, each naming a measurement or key; each is empty, never absent, when the server sent
 * none:
 *
 * - `unknownTypes`: measurements naming a type that does not exist.
 * - `nonTimeSeriesTypes`: measurements naming a type that exists but is not a time-series type.
 * - `unavailableTypes`: measurements naming a time-series type whose storage engine failed to
 *   load (the server log says why).
 * - `undeclaredKeys`: tag or field keys the measurement's type does not declare in that role.
 *   Capped at 100 entries by the server. A server started with
 *   `arcadedb.timeSeriesUndeclaredKeys=ignore` stores such samples with the undeclared keys
 *   discarded instead of dropping them.
 *
 * Any other non-2xx status from `ts.write` - and a 400 whose body is not a JSON object - stays a
 * plain `ArcadeDBError`.
 */
export class TimeSeriesWriteError extends ArcadeDBError {
  /** Samples ingested before the request was refused. `undefined` only if the body omitted it. */
  readonly written?: number;
  /** Samples discarded. `undefined` only if the body omitted it. */
  readonly dropped?: number;
  readonly unknownTypes: readonly string[];
  readonly nonTimeSeriesTypes: readonly string[];
  readonly unavailableTypes: readonly string[];
  readonly undeclaredKeys: readonly string[];

  constructor(status: number, body?: unknown, requestId?: string, extras?: ArcadeDBErrorExtras) {
    super(status, body, requestId, extras);
    const record = body !== null && typeof body === "object" ? (body as Record<string, unknown>) : {};
    this.name = "TimeSeriesWriteError";
    this.written = typeof record.written === "number" ? record.written : undefined;
    this.dropped = typeof record.dropped === "number" ? record.dropped : undefined;
    this.unknownTypes = stringList(record.unknownTypes);
    this.nonTimeSeriesTypes = stringList(record.nonTimeSeriesTypes);
    this.unavailableTypes = stringList(record.unavailableTypes);
    this.undeclaredKeys = stringList(record.undeclaredKeys);
    // The parent's setPrototypeOf pinned ArcadeDBError.prototype; restore this class's own.
    Object.setPrototypeOf(this, TimeSeriesWriteError.prototype);
  }

  /** As `ArcadeDBError.fromResponse`, building a `TimeSeriesWriteError`. */
  static override fromResponse(response: Response, body: unknown): TimeSeriesWriteError {
    return new TimeSeriesWriteError(
      response.status,
      body,
      response.headers.get("X-Request-Id") ?? undefined,
      extrasFromHeaders(response.headers),
    );
  }
}
