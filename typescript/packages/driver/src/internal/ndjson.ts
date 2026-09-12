/**
 * Decodes a `ReadableStream<Uint8Array>` of newline-delimited JSON into `T`s.
 *
 * Generic over the event type because two endpoints stream ndjson with different event
 * shapes - `NdJsonQueryEvent` from query/command, `NdJsonBatchEvent` from batch. The decoding
 * is identical; only the parsed type differs.
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
export async function* decodeNdJson<T>(stream: ReadableStream<Uint8Array>): AsyncGenerator<T> {
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
        yield JSON.parse(line) as T;
      }
    }
    remainder += decoder.decode();
    if (remainder.trim() !== "") {
      yield JSON.parse(remainder) as T;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
