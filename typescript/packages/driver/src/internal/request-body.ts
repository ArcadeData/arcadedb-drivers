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
 * Shared by `facade/data.ts`'s buffered `executeCommand` and `facade/stream.ts`'s streaming
 * `commandStream` - both send the same body to `/api/v1/command/{database}` and differ only in
 * `Accept`, so this has exactly one definition rather than one per call site.
 */
export function buildCommandBody(
  opts: CommandOptions,
): { command: string; language: string; params?: Record<string, never> } {
  return {
    command: opts.command,
    language: opts.language,
    params: opts.params as Record<string, never> | undefined,
  };
}

/**
 * Builds the JSON body for `/query`: `buildCommandBody`'s fields plus `limit`, sent only when
 * supplied. Composes from `buildCommandBody` rather than repeating its fields so a field added to
 * `CommandOptions` reaches both `/query` and `/command` bodies automatically instead of only the
 * one call site someone remembered to update.
 *
 * Shared by `facade/data.ts`'s buffered `executeQuery` and `facade/stream.ts`'s streaming
 * `queryStream` - both send the same body to `/api/v1/query/{database}` and differ only in
 * `Accept`, so this has exactly one definition rather than one per call site.
 */
export function buildQueryBody(
  opts: QueryOptions,
): { command: string; language: string; params?: Record<string, never>; limit?: number } {
  return { ...buildCommandBody(opts), limit: opts.limit };
}
