import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";

/**
 * `signal` and `timeoutMs` on `query`, `command`, `queryStream` and `commandStream` (issue #200).
 *
 * The fetch mocks below honour `request.signal` the way a real `fetch` does: a pending request
 * rejects with the signal's `reason`, and a response body already being read errors with it. A mock
 * that ignored the signal would let every test here pass against a client that never sent one.
 */

const ENVELOPE = { result: [], limit: 100, returned: 0, truncated: false };

/** A fetch that never answers until `request.signal` aborts it. */
function hangingFetch() {
  const seen: Request[] = [];
  const fetchMock = vi.fn(
    (request: Request) =>
      new Promise<Response>((_resolve, reject) => {
        seen.push(request);
        const { signal } = request;
        if (signal.aborted) reject(signal.reason);
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      }),
  );
  return { fetch: fetchMock as unknown as typeof fetch, seen };
}

/**
 * A fetch that answers 200 at once with one ndjson record, then keeps the body open until
 * `request.signal` aborts it - the way a real `fetch` errors `response.body` on abort.
 */
function openStreamFetch() {
  const fetchMock = vi.fn(async (request: Request) => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(JSON.stringify({ record: { n: 1 } }) + "\n"));
        request.signal.addEventListener("abort", () => controller.error(request.signal.reason), { once: true });
      },
    });
    return new Response(body, { status: 200, headers: { "content-type": "application/x-ndjson" } });
  });
  return fetchMock as unknown as typeof fetch;
}

async function drain(stream: AsyncGenerator<unknown>): Promise<unknown[]> {
  const out: unknown[] = [];
  for await (const event of stream) out.push(event);
  return out;
}

describe("per-call signal and timeoutMs", () => {
  for (const method of ["query", "command"] as const) {
    it(`${method}: aborting the caller's signal rejects with its reason, not ArcadeDBError`, async () => {
      const { fetch, seen } = hangingFetch();
      const db = createClient({ baseUrl: "https://example.com", fetch }).db("mydb");
      const controller = new AbortController();
      const reason = new Error("caller gave up");

      const call = db[method]({ language: "sql", command: "SELECT 1", signal: controller.signal });
      await vi.waitFor(() => expect(seen).toHaveLength(1));
      controller.abort(reason);

      await expect(call).rejects.toBe(reason);
      expect(seen[0].signal.aborted).toBe(true);
    });

    it(`${method}: timeoutMs rejects with a TimeoutError`, async () => {
      const { fetch } = hangingFetch();
      const db = createClient({ baseUrl: "https://example.com", fetch }).db("mydb");

      const error = await db[method]({ language: "sql", command: "SELECT 1", timeoutMs: 20 }).catch((e: unknown) => e);

      expect(error).not.toBeInstanceOf(ArcadeDBError);
      expect((error as DOMException).name).toBe("TimeoutError");
    });

    it(`${method}: with both, the caller's signal still aborts before the timeout`, async () => {
      const { fetch, seen } = hangingFetch();
      const db = createClient({ baseUrl: "https://example.com", fetch }).db("mydb");
      const controller = new AbortController();
      const reason = new Error("first");

      const call = db[method]({ language: "sql", command: "SELECT 1", signal: controller.signal, timeoutMs: 60_000 });
      await vi.waitFor(() => expect(seen).toHaveLength(1));
      controller.abort(reason);

      await expect(call).rejects.toBe(reason);
    });

    it(`${method}: with both, the timeout fires when the caller's signal does not`, async () => {
      const { fetch } = hangingFetch();
      const db = createClient({ baseUrl: "https://example.com", fetch }).db("mydb");
      const controller = new AbortController();

      const error = await db[method]({ language: "sql", command: "SELECT 1", signal: controller.signal, timeoutMs: 20 }).catch(
        (e: unknown) => e,
      );

      expect((error as DOMException).name).toBe("TimeoutError");
    });

    it(`${method}: neither option reaches the request body`, async () => {
      let body: unknown;
      const fetchMock = vi.fn(async (request: Request) => {
        body = await request.clone().json();
        return new Response(JSON.stringify(ENVELOPE), { status: 200, headers: { "content-type": "application/json" } });
      });
      const db = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch }).db("mydb");

      await db[method]({ language: "sql", command: "SELECT 1", signal: new AbortController().signal, timeoutMs: 60_000 });

      expect(body).toEqual({ language: "sql", command: "SELECT 1" });
    });
  }

  it("an already-aborted signal rejects without the call ever answering", async () => {
    const { fetch } = hangingFetch();
    const db = createClient({ baseUrl: "https://example.com", fetch }).db("mydb");
    const reason = new Error("already");

    await expect(db.query({ language: "sql", command: "SELECT 1", signal: AbortSignal.abort(reason) })).rejects.toBe(reason);
  });

  for (const method of ["queryStream", "commandStream"] as const) {
    it(`${method}: timeoutMs bounds the whole stream, not just the request`, async () => {
      const db = createClient({ baseUrl: "https://example.com", fetch: openStreamFetch() }).db("mydb");
      const seen: unknown[] = [];

      const error = await (async () => {
        for await (const event of db[method]({ language: "sql", command: "SELECT 1", timeoutMs: 30 })) seen.push(event);
      })().catch((e: unknown) => e);

      expect(seen).toEqual([{ record: { n: 1 } }]);
      expect((error as DOMException).name).toBe("TimeoutError");
    });

    it(`${method}: aborting the caller's signal mid-stream errors the iteration with its reason`, async () => {
      const db = createClient({ baseUrl: "https://example.com", fetch: openStreamFetch() }).db("mydb");
      const controller = new AbortController();
      const reason = new Error("stop reading");
      const stream = db[method]({ language: "sql", command: "SELECT 1", signal: controller.signal });

      await expect(stream.next()).resolves.toEqual({ done: false, value: { record: { n: 1 } } });
      controller.abort(reason);

      await expect(drain(stream)).rejects.toBe(reason);
    });
  }
});
