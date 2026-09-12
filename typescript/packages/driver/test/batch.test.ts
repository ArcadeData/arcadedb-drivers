import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";
import type { NdJsonBatchEvent } from "../src/index.js";

function ndjsonResponse(lines: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(new TextEncoder().encode(line + "\n"));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "application/x-ndjson" } });
}

/**
 * Builds an ndjson `Response` whose underlying source records whether it was cancelled.
 *
 * Duplicated from `stream.test.ts` rather than imported: importing one test file's module from
 * another re-executes its top-level `describe`/`it` registrations a second time (vitest has no
 * notion of "just import the helpers"), silently doubling that file's test count.
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

async function collect(iter: AsyncGenerator<NdJsonBatchEvent>): Promise<NdJsonBatchEvent[]> {
  const events: NdJsonBatchEvent[] = [];
  for await (const event of iter) events.push(event);
  return events;
}

const ROWS = {
  vertices: [{ type: "Person", id: "a", properties: { name: "Ann" } }],
  edges: [{ type: "Knows", from: "a", to: "#1:7" }],
};

describe("ArcadeDBDatabase.batchLoad", () => {
  it("POSTs the serialized ndjson payload to /api/v1/batch/{database}", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({ verticesCreated: 1, edgesCreated: 1 }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").batchLoad(ROWS);

    expect(captured?.method).toBe("POST");
    expect(new URL(captured!.url).pathname).toBe("/api/v1/batch/mydb");
    expect(captured?.headers.get("content-type")).toBe("application/x-ndjson");
    const body = await captured!.clone().text();
    expect(body.split("\n").filter((l) => l !== "").map((l) => JSON.parse(l))).toEqual([
      { "@type": "vertex", "@class": "Person", "@id": "a", name: "Ann" },
      { "@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7" },
    ]);
  });

  it("passes tuning options through as query parameters, spelled as the contract spells them", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({}, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").batchLoad({ ...ROWS, options: { commitEvery: 5000, lightEdges: true } });

    const url = new URL(captured!.url);
    expect(url.searchParams.get("commitEvery")).toBe("5000");
    expect(url.searchParams.get("lightEdges")).toBe("true");
  });

  it("omits a query parameter entirely when its option is absent", async () => {
    // Not "sends an empty value": an absent option must leave the parameter off the
    // URL, so the server applies its own default rather than parsing "".
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({}, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").batchLoad({ ...ROWS, options: { commitEvery: 10 } });

    const url = new URL(captured!.url);
    expect(url.searchParams.has("commitEvery")).toBe(true);
    expect(url.searchParams.has("batchSize")).toBe(false);
    expect(url.searchParams.has("wal")).toBe(false);
  });

  it("throws ArcadeDBError when the server refuses the load", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ error: "Missing @class at line 1", verticesCreated: 0, partialCommit: false }, 400),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(server.db("mydb").batchLoad(ROWS)).rejects.toBeInstanceOf(ArcadeDBError);
  });
});

describe("ArcadeDBDatabase.batchLoadStream", () => {
  it("sends Accept: application/x-ndjson", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return ndjsonResponse([JSON.stringify({ summary: { verticesCreated: 1 } })]);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await collect(server.db("mydb").batchLoadStream(ROWS));

    expect(captured?.headers.get("accept")).toBe("application/x-ndjson");
  });

  it("yields every progress event, then the summary", async () => {
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { phase: "vertices", verticesCreated: 1, idMapping: { a: "#1:0" } } }),
        JSON.stringify({ progress: { phase: "edges", edgesCreated: 1 } }),
        JSON.stringify({ summary: { verticesCreated: 1, edgesCreated: 1, idMappingStreamed: true, idMappingSize: 1 } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").batchLoadStream(ROWS));

    expect(events).toHaveLength(3);
    expect(events[0]?.progress?.phase).toBe("vertices");
    expect(events[2]?.summary).toBeDefined();
  });

  it("passes idMapping fragments through without merging them (D5)", async () => {
    // The facade must NOT accumulate. The server streams the mapping precisely so a
    // million-vertex load never has to hold a million entries client-side; merging
    // here would reintroduce exactly the cost streaming exists to avoid.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { idMapping: { a: "#1:0" } } }),
        JSON.stringify({ progress: { idMapping: { b: "#1:1" } } }),
        JSON.stringify({ summary: { idMappingStreamed: true, idMappingSize: 2 } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const events = await collect(server.db("mydb").batchLoadStream(ROWS));

    expect(events[0]?.progress?.idMapping).toEqual({ a: "#1:0" });
    expect(events[1]?.progress?.idMapping).toEqual({ b: "#1:1" });
    expect(events[2]?.summary).not.toHaveProperty("idMapping");
  });

  it("throws ArcadeDBError when the load fails BEFORE the stream starts (D6, channel one)", async () => {
    // The status line has not been sent yet, so the server can still answer with a
    // real HTTP status and the buffered error body.
    const fetchMock = vi.fn(async () => jsonResponse({ error: "Missing @class at line 1" }, 400));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(collect(server.db("mydb").batchLoadStream(ROWS))).rejects.toBeInstanceOf(ArcadeDBError);
  });

  it("throws ArcadeDBError carrying the in-band status when the terminal line is an error (D6, channel two)", async () => {
    // Once the stream has started the 200 status line cannot be taken back, so the
    // failure travels in band. It must fail the caller the SAME way channel one does.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { verticesCreated: 1 } }),
        JSON.stringify({ error: { error: "boom", status: 400, partialCommit: true } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(collect(server.db("mydb").batchLoadStream(ROWS))).rejects.toMatchObject({ status: 400 });
  });

  it("yields the events that arrived before an in-band error, then throws", async () => {
    // The throw must not swallow work the caller was already told about: a partial
    // commit is durable, and those progress counts are how a caller learns what
    // may have landed.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ progress: { verticesCreated: 2 } }),
        JSON.stringify({ error: { error: "boom", status: 500 } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const seen: NdJsonBatchEvent[] = [];
    await expect(
      (async () => {
        for await (const event of server.db("mydb").batchLoadStream(ROWS)) seen.push(event);
      })(),
    ).rejects.toBeInstanceOf(ArcadeDBError);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.progress?.verticesCreated).toBe(2);
  });

  it("cancels the response body when the caller breaks out of the loop early", async () => {
    // Same hazard `stream.test.ts` pins for queryStream: a decoder that only releases its
    // reader's lock on early abandonment leaks the connection instead of tearing the body down.
    // batchLoadStream shares `decodeNdJson` with queryStream/commandStream, but nothing exercised
    // that sharing from the batch side before this test.
    const { response, cancelled } = cancellableNdjsonResponse([
      JSON.stringify({ progress: { verticesCreated: 1 } }),
      JSON.stringify({ progress: { verticesCreated: 2 } }),
    ]);
    const fetchMock = vi.fn(async () => response);
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const seen: NdJsonBatchEvent[] = [];
    for await (const event of server.db("mydb").batchLoadStream(ROWS)) {
      seen.push(event);
      break;
    }

    expect(seen).toHaveLength(1);
    expect(cancelled()).toBe(true);
  });

  it("records that status is an unclassified fallback when statusMapped is false (D6)", async () => {
    // The contract says: key on `exception` here, not on `status`, because 500 is
    // the fallback rather than the status the buffered encoding would have chosen.
    const fetchMock = vi.fn(async () =>
      ndjsonResponse([
        JSON.stringify({ error: { error: "engine failure", status: 500, statusMapped: false, exception: "java.lang.IllegalStateException" } }),
      ]),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(collect(server.db("mydb").batchLoadStream(ROWS))).rejects.toMatchObject({
      status: 500,
      exception: "java.lang.IllegalStateException",
    });
  });
});
