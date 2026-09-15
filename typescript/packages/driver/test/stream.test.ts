import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";
import type { NdJsonQueryEvent } from "../src/index.js";

/** Builds an ndjson `Response` whose body is delivered as one chunk per `lines` entry. */
function ndjsonResponse(lines: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(new TextEncoder().encode(line + "\n"));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "application/x-ndjson" } });
}

/** Builds a `Response` whose body is delivered exactly as the given raw chunks, verbatim - no added newlines. */
function chunkedResponse(chunks: Uint8Array[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "application/x-ndjson" } });
}

/**
 * Builds an ndjson `Response` whose underlying source records whether it was cancelled.
 *
 * `cancelled()` is the only thing that distinguishes a decoder which merely releases its reader's
 * lock from one that actually tears the body down. A test that breaks out of the loop and asserts
 * no exception was thrown passes against either.
 */
function cancellableNdjsonResponse(lines: string[]): { response: Response; cancelled: () => boolean } {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(new TextEncoder().encode(line + "\n"));
    },
    cancel() {
      cancelled = true;
    },
  });
  return {
    response: new Response(body, { status: 200, headers: { "content-type": "application/x-ndjson" } }),
    cancelled: () => cancelled,
  };
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function collect(iter: AsyncGenerator<NdJsonQueryEvent>): Promise<NdJsonQueryEvent[]> {
  const events: NdJsonQueryEvent[] = [];
  for await (const event of iter) events.push(event);
  return events;
}

describe("ArcadeDBDatabase.queryStream", () => {
  it("sends Accept: application/x-ndjson and POSTs to /api/v1/query/{database} with the same body query builds", async () => {
    let capturedRequest: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedRequest = request;
      return ndjsonResponse([]);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V", params: { x: 1 } }));

    expect(capturedRequest?.method).toBe("POST");
    expect(new URL(capturedRequest!.url).pathname).toBe("/api/v1/query/mydb");
    expect(capturedRequest?.headers.get("accept")).toBe("application/x-ndjson");
    await expect(capturedRequest!.clone().json()).resolves.toEqual({
      language: "sql",
      command: "SELECT FROM V",
      params: { x: 1 },
    });
  });

  it("yields each event in order, including the stats trailer, without swallowing it", async () => {
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ record: { a: 1 } }),
        JSON.stringify({ record: { a: 2 } }),
        JSON.stringify({ stats: { limit: 100, returned: 2, truncated: false } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));

    expect(events).toEqual([
      { record: { a: 1 } },
      { record: { a: 2 } },
      { stats: { limit: 100, returned: 2, truncated: false } },
    ]);
  });

  it("reassembles a line split across two chunks", async () => {
    const fetchMock = vi.fn(async () =>
      chunkedResponse([new TextEncoder().encode('{"record":{"a":'), new TextEncoder().encode("1}}\n")]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));

    expect(events).toEqual([{ record: { a: 1 } }]);
  });

  it("reassembles a multibyte UTF-8 character split across two chunks", async () => {
    // "café" - the trailing "é" is 2 bytes (0xC3 0xA9) in UTF-8; split so the first chunk ends
    // mid-character. Decoding each chunk independently (no `{ stream: true }`) mangles this into
    // U+FFFD replacement characters instead of reassembling "é".
    const fullLine = JSON.stringify({ record: { name: "café" } }) + "\n";
    const encoded = new TextEncoder().encode(fullLine);
    const splitIndex = fullLine.indexOf("é") > -1 ? new TextEncoder().encode(fullLine.split("é")[0]).length + 1 : 1;
    const chunk1 = encoded.slice(0, splitIndex);
    const chunk2 = encoded.slice(splitIndex);
    const fetchMock = vi.fn(async () => chunkedResponse([chunk1, chunk2]));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));

    expect(events).toEqual([{ record: { name: "café" } }]);
  });

  it("yields the trailing chunk's event even with no final newline", async () => {
    const fetchMock = vi.fn(async () => chunkedResponse([new TextEncoder().encode('{"record":{"a":1}}')]));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));

    expect(events).toEqual([{ record: { a: 1 } }]);
  });

  it("yields nothing and does not throw for an empty stream", async () => {
    const fetchMock = vi.fn(async () => ndjsonResponse([]));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));

    expect(events).toEqual([]);
  });

  it("raises ArcadeDBError on an in-band error event, after delivering events seen before it", async () => {
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([JSON.stringify({ record: { a: 1 } }), JSON.stringify({ error: { message: "boom" } })]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const seen: NdJsonQueryEvent[] = [];
    let caught: unknown;
    try {
      for await (const event of server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" })) {
        seen.push(event);
      }
    } catch (err) {
      caught = err;
    }

    expect(seen).toEqual([{ record: { a: 1 } }]);
    expect(caught).toBeInstanceOf(ArcadeDBError);
  });

  it("raises ArcadeDBError with the status on a non-2xx response, exactly as query does", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: "bad request" }, 400));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    let caught: unknown;
    try {
      await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ArcadeDBError);
    expect((caught as ArcadeDBError).status).toBe(400);
    expect((caught as ArcadeDBError).error).toBe("bad request");
  });

  it("cancels the response body when the caller breaks out of the loop early", async () => {
    // The stream is never closed by its source, so it stands in for a transfer still in flight
    // when the caller walks away. `releaseLock()` on its own would leave it that way forever.
    const { response, cancelled } = cancellableNdjsonResponse([
      JSON.stringify({ record: { a: 1 } }),
      JSON.stringify({ record: { a: 2 } }),
    ]);
    const fetchMock = vi.fn(async () => response);
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const seen: NdJsonQueryEvent[] = [];
    for await (const event of server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" })) {
      seen.push(event);
      break;
    }

    expect(seen).toEqual([{ record: { a: 1 } }]);
    expect(cancelled()).toBe(true);
  });

  it("does not disturb a stream that was consumed to exhaustion", async () => {
    // The same assertion from the other side: cancelling in the `finally` must be a no-op once the
    // reader has already seen `done`, not something that turns a complete read into a failure.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([JSON.stringify({ record: { a: 1 } }), JSON.stringify({ stats: { returned: 1 } })]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").queryStream({ language: "sql", command: "SELECT FROM V" }));

    expect(events).toEqual([{ record: { a: 1 } }, { stats: { returned: 1 } }]);
  });
});

describe("ArcadeDBDatabase.commandStream", () => {
  it("reaches /api/v1/command/{database}", async () => {
    let capturedRequest: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedRequest = request;
      return ndjsonResponse([JSON.stringify({ stats: { limit: -1, returned: 0, truncated: false } })]);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").commandStream({ language: "sql", command: "SELECT FROM V" }));

    expect(new URL(capturedRequest!.url).pathname).toBe("/api/v1/command/mydb");
    expect(capturedRequest?.headers.get("accept")).toBe("application/x-ndjson");
    expect(events).toEqual([{ stats: { limit: -1, returned: 0, truncated: false } }]);
  });
});
