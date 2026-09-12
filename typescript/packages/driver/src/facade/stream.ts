import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import type { CommandOptions, QueryOptions } from "./data.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/** Request header carrying the session id that scopes a call to one transaction. */
const SESSION_HEADER = "arcadedb-session-id";

export type NdJsonQueryEvent = components["schemas"]["NdJsonQueryEvent"];

/** Attaches the session header when `sessionId` is set; omits it otherwise. */
function sessionHeader(sessionId: string | undefined): { [SESSION_HEADER]?: string } | undefined {
  return sessionId === undefined ? undefined : { [SESSION_HEADER]: sessionId };
}

/**
 * Builds the JSON body for `/query`: `language`, `command`, `params` and, when supplied, `limit`.
 * Mirrors `facade/data.ts`'s `buildQueryBody`; kept separate rather than imported so this module's
 * only import from `facade/data.ts` stays the two option types, not its private helpers.
 */
function buildQueryBody(
  opts: QueryOptions,
): { command: string; language: string; params?: Record<string, never>; limit?: number } {
  return {
    command: opts.command,
    language: opts.language,
    params: opts.params as Record<string, never> | undefined,
    limit: opts.limit,
  };
}

/** Builds the JSON body for `/command`: `language`, `command` and `params`. Mirrors `buildQueryBody` minus `limit`. */
function buildCommandBody(opts: CommandOptions): { command: string; language: string; params?: Record<string, never> } {
  return {
    command: opts.command,
    language: opts.language,
    params: opts.params as Record<string, never> | undefined,
  };
}

/**
 * Decodes a `ReadableStream<Uint8Array>` of newline-delimited JSON into `NdJsonQueryEvent`s.
 *
 * Two properties matter here, and both are invisible to a test that feeds whole lines in whole
 * chunks:
 *
 * 1. **Buffering across chunks.** The stream is not guaranteed to hand a chunk boundary that lines
 *    up with a `\n` - the server decides where TCP segments (and its own flush points) fall, not
 *    this client. `decode(chunk).split("\n")` per chunk silently drops or splits an event whenever
 *    a line straddles two chunks. A `remainder` string carries whatever the last chunk left
 *    unterminated into the next one, and is flushed once after the stream ends in case the final
 *    chunk had no trailing newline at all.
 * 2. **Decoding with `{ stream: true }`.** A multi-byte UTF-8 character can itself be split across
 *    a chunk boundary, independently of where the newlines fall. A fresh `TextDecoder().decode()`
 *    per chunk treats each chunk as a complete, self-contained byte sequence and turns a split
 *    character into U+FFFD replacement characters. Reusing one `TextDecoder` across chunks with
 *    `{ stream: true }` holds back an incomplete trailing sequence until the next chunk supplies
 *    the rest.
 *
 * Blank lines (a stray trailing `\n\n`, or the empty string a `split` leaves at the very end) are
 * skipped rather than yielded or thrown on.
 */
async function* decodeNdJson(stream: ReadableStream<Uint8Array>): AsyncGenerator<NdJsonQueryEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let remainder = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      remainder += decoder.decode(value, { stream: true });
      const lines = remainder.split("\n");
      remainder = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim() === "") continue;
        yield JSON.parse(line) as NdJsonQueryEvent;
      }
    }
    remainder += decoder.decode();
    if (remainder.trim() !== "") {
      yield JSON.parse(remainder) as NdJsonQueryEvent;
    }
  } finally {
    reader.releaseLock();
  }
}

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
  yield* raiseOnErrorEvent(decodeNdJson(data));
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

/** Streams `POST /api/v1/command/{database}` as `application/x-ndjson`, yielding one event per line. */
export async function* commandStream(
  client: RawClient,
  database: string,
  sessionId: string | undefined,
  opts: CommandOptions,
): AsyncGenerator<NdJsonQueryEvent> {
  yield* streamEvents(client, "/api/v1/command/{database}", database, sessionId, buildCommandBody(opts));
}
