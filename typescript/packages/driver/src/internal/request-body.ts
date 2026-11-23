import type { CommandOptions, QueryOptions } from "../facade/data.js";

/**
 * Request header carrying the session id that scopes a call to one transaction.
 *
 * Lives here, not in `facade/data.ts`, for the same reason `sessionHeader`/`buildCommandBody`/
 * `buildQueryBody` below do: `facade/data.ts`'s buffered `query`/`command` and `facade/stream.ts`'s
 * streaming `queryStream`/`commandStream` send the identical header and the identical body to the
 * identical endpoints, differing only in `Accept` - so there must be exactly one definition of
 * each, shared by both, or the two paths can silently drift apart. See `internal/unwrap.ts`'s doc
 * comment for the established pattern this follows: a single implementation living under
 * `internal/` so two facade modules (or facade and `index.ts`) can share it without importing one
 * another.
 */
export const SESSION_HEADER = "arcadedb-session-id";

/** Attaches the session header when `sessionId` is set; omits it otherwise. */
export function sessionHeader(sessionId: string | undefined): { [SESSION_HEADER]?: string } | undefined {
  return sessionId === undefined ? undefined : { [SESSION_HEADER]: sessionId };
}

/**
 * Request header labelling the work a request runs, for `list queries` and
 * `terminate queries tag <label>` on the server. Accepted by `/query`, `/command`, `/begin` and
 * `/batch`; on `/begin` it labels every statement of the transaction that carries no label of its
 * own.
 */
export const QUERY_TAG_HEADER = "X-ArcadeDB-Query-Tag";

/**
 * Attaches the query-tag header when `queryTag` is a non-empty string; omits it otherwise.
 *
 * The tag is sent exactly as given. The contract caps it at 256 printable characters, and this
 * client deliberately does not check that: the rule is the server's, and a client-side copy of it
 * would only drift from the server's the first time either side changed it. Nor does the contract
 * say what the server does with a tag past the cap - a 26.11.1-SNAPSHOT server accepted a
 * 257-character one without error - so do not count on a refusal either.
 */
export function queryTagHeader(queryTag: string | undefined): { [QUERY_TAG_HEADER]?: string } {
  return queryTag ? { [QUERY_TAG_HEADER]: queryTag } : {};
}

/**
 * The header parameters `/query` and `/command` share, buffered and streamed alike: the session
 * header and the query-tag header, each only when set. `undefined` when neither is, so a call
 * outside a transaction with no tag sends no extra headers at all.
 */
export function statementHeaders(
  sessionId: string | undefined,
  queryTag: string | undefined,
): { [SESSION_HEADER]?: string; [QUERY_TAG_HEADER]?: string } | undefined {
  const headers = { ...sessionHeader(sessionId), ...queryTagHeader(queryTag) };
  return Object.keys(headers).length === 0 ? undefined : headers;
}

/**
 * The `signal` a `/query` or `/command` call is sent with: the caller's `signal` as it is when there
 * is no `timeoutMs`, `undefined` when there is neither - the request then carries no signal at all,
 * exactly as before these options existed - and otherwise a signal of this function's own that
 * aborts when the caller's does or when `timeoutMs` runs out, whichever is first. Shared by the
 * buffered and the streamed calls, for the reason `statementHeaders` is. See
 * `CommandOptions.signal` and `CommandOptions.timeoutMs`.
 *
 * `AbortSignal.any` is deliberately not used: it needs Node 20.3, and `engines` allows any Node 20.
 * Nor is `AbortSignal.timeout`, which Node keeps alive only through weak references; here the
 * pending timer's callback holds the controller, so the signal lives as long as the deadline does.
 * The timer is `unref`'d where the runtime has that, as `AbortSignal.timeout`'s is, so a pending
 * deadline does not keep a process alive.
 *
 * Returns the signal and `done`, which the caller must run once the call has settled - in a
 * `finally`, after the response body has been read, since `timeoutMs` bounds that too. `done` clears
 * the timer and removes the listener on the caller's signal, so a long-lived signal shared by many
 * calls holds a listener only for each call still running, not for each one whose deadline has not
 * yet passed. Firing either side runs it as well.
 */
export function callSignal({ signal, timeoutMs }: CommandOptions): [AbortSignal | undefined, () => void] {
  if (timeoutMs === undefined) return [signal, () => undefined];
  const controller = new AbortController();
  const done = (): void => {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  };
  const abort = (reason: unknown): void => {
    done();
    controller.abort(reason);
  };
  const onAbort = (): void => abort(signal?.reason);
  const timer = setTimeout(
    () => abort(new DOMException(`The operation timed out after ${timeoutMs}ms`, "TimeoutError")),
    timeoutMs,
  );
  (timer as { unref?: () => void }).unref?.();
  if (signal?.aborted) onAbort();
  else signal?.addEventListener("abort", onAbort);
  return [controller.signal, done];
}

/**
 * Builds the JSON body for `/command`. Only `params` is cast: it is typed `Record<string, never>`
 * in the generated schema (an openapi-typescript artifact for "untyped object", not a real
 * restriction), so a caller-supplied `Record<string, unknown>` needs a narrow cast to satisfy it.
 * `command` and `language` are passed through with their real types and are NOT cast, so a type
 * change to, or removal of, either required field still fails `tsc` here instead of only failing
 * on the wire.
 *
 * This does NOT extend to a field being removed from the contract outright: this function has an
 * annotated return type, so the object literal handed to `body:` at each call site is not checked
 * as a fresh literal, and excess-property checking never fires for a stray field that no longer
 * exists on the target type.
 *
 * The body is built field by field rather than by spreading `opts`, which is what keeps
 * `queryTag` - a header, see `queryTagHeader` - out of it.
 *
 * Shared by `facade/data.ts`'s buffered `executeCommand` and `facade/stream.ts`'s streaming
 * `commandStream` - both send the same body to `/api/v1/command/{database}` and differ only in
 * `Accept`, so this has exactly one definition rather than one per call site.
 */
export function buildCommandBody(
  opts: CommandOptions,
): { command: string; language: string; params?: Record<string, never>; limit?: number } {
  return {
    command: opts.command,
    language: opts.language,
    params: opts.params as Record<string, never> | undefined,
    limit: opts.limit,
  };
}

/**
 * Builds the JSON body for `/query`: exactly `buildCommandBody`'s, `limit` included, since
 * `QueryRequest` and `CommandRequest` carry the same fields. Delegates rather than repeating them
 * so a field added to `CommandOptions` reaches both `/query` and `/command` bodies automatically
 * instead of only the one call site someone remembered to update.
 *
 * Shared by `facade/data.ts`'s buffered `executeQuery` and `facade/stream.ts`'s streaming
 * `queryStream` - both send the same body to `/api/v1/query/{database}` and differ only in
 * `Accept`, so this has exactly one definition rather than one per call site.
 */
export function buildQueryBody(
  opts: QueryOptions,
): { command: string; language: string; params?: Record<string, never>; limit?: number } {
  return buildCommandBody(opts);
}
