import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import { decodeNdJson } from "../internal/ndjson.js";
import { buildCommandBody, buildQueryBody, sessionHeader } from "../internal/request-body.js";
import type { CommandOptions, QueryOptions } from "./data.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

export type NdJsonQueryEvent = components["schemas"]["NdJsonQueryEvent"];

/**
 * Turns one raw `NdJsonQueryEvent` stream into the public generator's contract: an in-band `error`
 * event (D-M7-3) raises `ArcadeDBError` instead of being yielded, after every event that arrived
 * before it has already been handed to the caller. This is a failure the server could only report
 * after the 200 status line was already sent - the status cannot be taken back once the stream has
 * started, so the contract puts it in band instead. Raising it here means the streaming and
 * buffered paths fail the same way: both end in a thrown `ArcadeDBError`, never a returned one.
 */
async function* raiseOnErrorEvent(events: AsyncGenerator<NdJsonQueryEvent>): AsyncGenerator<NdJsonQueryEvent> {
  for await (const event of events) {
    if (event.error !== undefined) {
      throw new ArcadeDBError(200, { error: event.error.message ?? "the stream reported an error" });
    }
    yield event;
  }
}

/**
 * D-M7-1: this module rides the existing generated client - `client.POST(..., { parseAs: "stream" })`
 * - rather than calling `fetch` directly or standing up a second client. `parseAs: "stream"` hands
 * back `response.body` (a `ReadableStream<Uint8Array>`) unparsed instead of JSON-decoding it, but
 * the request that produces that response still goes through the same base URL and the same auth
 * middleware every other call on this client goes through, and openapi-fetch still reads a non-ok
 * response as text/JSON independently of `parseAs` - so the existing `ArcadeDBError` mapping keeps
 * working here too. A second transport was exactly what this milestone risked needing before
 * `parseAs: "stream"` was found to make that unnecessary: hand-writing a second client able to
 * reapply auth and reproduce the error mapping would have doubled the surface this repository has
 * to keep in step with the server, for a feature that only needed a different way to read one
 * response body.
 *
 * What IS hand-written is `decodeNdJson`: the transform from raw bytes to `NdJsonQueryEvent`s. See
 * its doc comment for the two chunk-boundary defects that transform must not have.
 */
async function* streamEvents(
  client: RawClient,
  path: "/api/v1/query/{database}" | "/api/v1/command/{database}",
  database: string,
  sessionId: string | undefined,
  body: { command: string; language: string; params?: Record<string, never>; limit?: number },
): AsyncGenerator<NdJsonQueryEvent> {
  const { data, error, response } = await client.POST(path, {
    params: { path: { database }, header: sessionHeader(sessionId) },
    body,
    headers: { Accept: "application/x-ndjson" },
    parseAs: "stream",
  });
  if (!response.ok) {
    throw ArcadeDBError.fromResponse(response, error);
  }
  // `data` is `response.body`: `null` when the runtime reports no body (e.g. a genuinely empty
  // response), and typed as possibly `undefined` only because it shares a discriminated union
  // with the error branch already ruled out above by the `response.ok` check.
  if (data === null || data === undefined) {
    return;
  }
  yield* raiseOnErrorEvent(decodeNdJson<NdJsonQueryEvent>(data));
}

/** Streams `POST /api/v1/query/{database}` as `application/x-ndjson`, yielding one event per line. */
export async function* queryStream(
  client: RawClient,
  database: string,
  sessionId: string | undefined,
  opts: QueryOptions,
): AsyncGenerator<NdJsonQueryEvent> {
  yield* streamEvents(client, "/api/v1/query/{database}", database, sessionId, buildQueryBody(opts));
}

/**
 * Streams `POST /api/v1/command/{database}` as `application/x-ndjson`, yielding one event per
 * line. Only a read-only statement can stream; see `ArcadeDBDatabase.commandStream`'s doc comment
 * for why a mutating one is refused.
 */
export async function* commandStream(
  client: RawClient,
  database: string,
  sessionId: string | undefined,
  opts: CommandOptions,
): AsyncGenerator<NdJsonQueryEvent> {
  yield* streamEvents(client, "/api/v1/command/{database}", database, sessionId, buildCommandBody(opts));
}
