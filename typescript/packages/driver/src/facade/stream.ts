import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import { buildCommandBody, buildQueryBody, sessionHeader } from "../internal/request-body.js";
import type { CommandOptions, QueryOptions } from "./data.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

export type NdJsonQueryEvent = components["schemas"]["NdJsonQueryEvent"];

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
 *
 * A third property is invisible to any test that consumes the stream to exhaustion: **an abandoned
 * stream must be cancelled, not merely unlocked.** The headline use of a streaming API is to stop
 * early -
 *
 * ```ts
 * for await (const event of db.queryStream({ ... })) {
 *   if (enough) break;
 * }
 * ```
 *
 * - and `break` runs this generator's `finally` (via the generator's `return()`, delegated inward
 * by `yield*`). `reader.releaseLock()` alone is not enough there: releasing a lock is not
 * cancelling, so the response body would be left unread and uncancelled mid-transfer, and the
 * socket never returned to the pool until the whole thing is garbage-collected. `reader.cancel()`
 * is what actually tears the body down; on a stream already read to `done` it is a no-op, so the
 * exhausted case pays nothing for it. Its rejection is swallowed because the `finally` must not
 * replace the caller's own reason for leaving the loop - an in-band `error` event, a `JSON.parse`
 * failure, or nothing at all - with a teardown failure.
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
    await reader.cancel().catch(() => undefined);
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
