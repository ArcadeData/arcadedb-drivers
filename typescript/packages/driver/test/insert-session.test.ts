import { afterEach, describe, expect, it, vi } from "vitest";
import { ArcadeDBError, basicAuth, bearerAuth, createClient } from "../src/index.js";
import type { WebSocketEventLike, WebSocketLike } from "../src/index.js";

type Frame = Record<string, unknown>;
type Listener = (event: WebSocketEventLike) => void;

/**
 * An in-process stand-in for the server's `/ws` endpoint. `behave` is the "server": it receives
 * each frame the client sends and answers through `reply`. Frames are delivered on a later tick,
 * as a real socket would, so the client's wait logic is exercised rather than short-circuited.
 */
class FakeSocket implements WebSocketLike {
  static instances: FakeSocket[] = [];
  static behave: (frame: Frame, socket: FakeSocket) => void = () => undefined;
  static refuseConnection = false;

  readonly sent: Frame[] = [];
  closedWith: number | undefined;
  private readonly listeners = new Map<string, Listener[]>();

  constructor(
    readonly url: string,
    readonly options?: { headers?: Record<string, string> },
  ) {
    FakeSocket.instances.push(this);
    setTimeout(() => {
      if (FakeSocket.refuseConnection) this.emit("error", { message: "Unexpected server response: 401" });
      else this.emit("open", {});
    }, 0);
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  send(data: string): void {
    const frame = JSON.parse(data) as Frame;
    this.sent.push(frame);
    FakeSocket.behave(frame, this);
  }

  close(code?: number): void {
    if (this.closedWith !== undefined) return;
    this.closedWith = code ?? 1005;
    setTimeout(() => this.emit("close", { code: this.closedWith, reason: "" }), 0);
  }

  reply(frame: Frame): void {
    setTimeout(() => this.emit("message", { data: JSON.stringify(frame) }), 0);
  }

  /** The server hanging up on its own. */
  drop(): void {
    setTimeout(() => this.emit("close", { code: 1006, reason: "gone" }), 0);
  }

  private emit(type: string, event: WebSocketEventLike): void {
    for (const l of this.listeners.get(type) ?? []) l(event);
  }
}

const ack = (seq: number, inserted: number): Frame => ({
  result: "ok",
  action: "batchAck",
  sessionId: "S1",
  chunkSeq: seq,
  received: inserted,
  inserted,
  updated: 0,
  ignored: 0,
  failed: 0,
});

const committed = (outcome: string): Frame => ({
  result: "ok",
  action: "committed",
  sessionId: "S1",
  outcome,
  summary: { received: 0, inserted: 0, updated: 0, ignored: 0, failed: 0, executionTimeMs: 1, partialCommit: false },
});

const errorFrame = (detail: string): Frame => ({
  result: "error",
  action: "error",
  error: "Insert session error",
  detail,
  sessionId: "S1",
});

/** A well-behaved server: answers every frame the way the real one does for a healthy session. */
let joined = false;

function healthyServer(extra?: Partial<Record<string, (frame: Frame, socket: FakeSocket) => void>>): void {
  FakeSocket.behave = (frame, socket) => {
    const custom = extra?.[frame.action as string];
    if (custom) return custom(frame, socket);
    switch (frame.action) {
      case "start": {
        joined = Boolean(frame.transactionId);
        const options = (frame.options ?? {}) as Frame;
        socket.reply({
          result: "ok",
          action: "started",
          sessionId: frame.sessionId ?? "S1",
          database: frame.database,
          transactionMode: options.transactionMode ?? "per_stream",
          conflictMode: "error",
          validateOnly: false,
          ...(frame.transactionId ? { transactionId: frame.transactionId } : {}),
        });
        return;
      }
      case "chunk":
        socket.reply(ack(frame.chunkSeq as number, (frame.records as unknown[]).length));
        return;
      case "commit":
      case "rollback":
        socket.reply(committed(joined ? "detached" : (frame.action as string)));
        return;
    }
  };
}

function client(opts: { baseUrl?: string } = {}) {
  return createClient({
    baseUrl: opts.baseUrl ?? "http://localhost:2480",
    auth: basicAuth("root", "pw"),
    WebSocket: FakeSocket,
  });
}

afterEach(() => {
  FakeSocket.instances = [];
  FakeSocket.behave = () => undefined;
  FakeSocket.refuseConnection = false;
  vi.unstubAllGlobals();
});

describe("db.insertSession: opening", () => {
  it("connects to /ws with the client's Authorization header and sends start", async () => {
    healthyServer();
    const session = await client().db("shop").insertSession({
      targetType: "Person",
      transactionMode: "per_batch",
      conflictMode: "update",
      keyColumns: ["id"],
      updateColumnsOnConflict: ["name"],
      validateOnly: true,
    });
    const socket = FakeSocket.instances[0];
    expect(socket.url).toBe("ws://localhost:2480/ws");
    expect(socket.options?.headers?.Authorization).toBe(`Basic ${btoa("root:pw")}`);
    expect(socket.sent[0]).toEqual({
      action: "start",
      database: "shop",
      options: {
        targetType: "Person",
        transactionMode: "per_batch",
        conflictMode: "update",
        keyColumns: ["id"],
        updateColumnsOnConflict: ["name"],
        validateOnly: true,
      },
    });
    expect(session.sessionId).toBe("S1");
    expect(session.database).toBe("shop");
    expect(session.transactionMode).toBe("per_batch");
    expect(session.transactionId).toBeUndefined();
    await session.close();
  });

  it("maps https to wss, keeps a base path, and passes a bearer token through", async () => {
    healthyServer();
    const server = createClient({ baseUrl: "https://db.example.com/arcade/", auth: bearerAuth("AU-1"), WebSocket: FakeSocket });
    await server.db("d").insertSession();
    expect(FakeSocket.instances[0].url).toBe("wss://db.example.com/arcade/ws");
    expect(FakeSocket.instances[0].options?.headers?.Authorization).toBe("Bearer AU-1");
  });

  it("sends no options argument when the client has no credentials", async () => {
    healthyServer();
    const server = createClient({ baseUrl: "http://localhost:2480", WebSocket: FakeSocket });
    await server.db("d").insertSession();
    expect(FakeSocket.instances[0].options).toBeUndefined();
  });

  it("sends a client-chosen sessionId, and omits it otherwise", async () => {
    healthyServer();
    await client().db("d").insertSession({ sessionId: "mine" });
    await client().db("d").insertSession();
    expect(FakeSocket.instances[0].sent[0].sessionId).toBe("mine");
    expect("sessionId" in FakeSocket.instances[1].sent[0]).toBe(false);
  });

  it("raises ArcadeDBError carrying the server's detail when start is refused, and drops the socket", async () => {
    FakeSocket.behave = (frame, socket) => socket.reply(errorFrame("Insert session 'mine' already exists"));
    const err = await client().db("d").insertSession({ sessionId: "mine" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect((err as ArcadeDBError).detail).toBe("Insert session 'mine' already exists");
    expect((err as ArcadeDBError).message).toContain("already exists");
    expect((err as ArcadeDBError).status).toBe(0);
    expect(FakeSocket.instances[0].closedWith).toBe(1000);
  });

  it("raises ArcadeDBError when the connection is refused", async () => {
    FakeSocket.refuseConnection = true;
    const err = await client().db("d").insertSession().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect((err as ArcadeDBError).detail).toContain("401");
  });

  it("times out when the server never answers start", async () => {
    FakeSocket.behave = () => undefined;
    await expect(client().db("d").insertSession({ timeoutMs: 30 })).rejects.toThrow(/Timeout of 30ms/);
    expect(FakeSocket.instances[0].closedWith).toBe(1000);
  });

  it("explains when the runtime has no WebSocket and none was injected", async () => {
    vi.stubGlobal("WebSocket", undefined);
    const server = createClient({ baseUrl: "http://localhost:2480" });
    await expect(server.db("d").insertSession()).rejects.toThrow(/No WebSocket implementation/);
  });

  it("a per-session WebSocket overrides the client's", async () => {
    healthyServer();
    class Other extends FakeSocket {}
    const server = createClient({ baseUrl: "http://localhost:2480", WebSocket: class { constructor() { throw new Error("must not be used"); } } as never });
    await server.db("d").insertSession({ WebSocket: Other });
    expect(FakeSocket.instances[0]).toBeInstanceOf(Other);
  });
});

describe("db.insertSession: chunks", () => {
  it("numbers chunks from 1, contiguously, carries @class per record, and calls onBatchAck before returning", async () => {
    healthyServer();
    const seen: number[] = [];
    const session = await client().db("d").insertSession({ targetType: "Person", onBatchAck: (a) => seen.push(a.chunkSeq) });
    const a1 = await session.sendChunk([{ name: "a" }, { "@class": "Other", name: "b" }]);
    const a2 = await session.sendChunk([{ name: "c" }]);
    expect(a1.inserted).toBe(2);
    expect(a2.chunkSeq).toBe(2);
    expect(seen).toEqual([1, 2]);
    expect(session.lastChunkSeq).toBe(2);
    const socket = FakeSocket.instances[0];
    expect(socket.sent[1]).toEqual({
      action: "chunk",
      sessionId: "S1",
      chunkSeq: 1,
      records: [{ name: "a" }, { "@class": "Other", name: "b" }],
    });
    expect(socket.sent[2].chunkSeq).toBe(2);
  });

  it("a chunk refused as a whole rejects, leaves the session open, and the retry reuses its sequence number", async () => {
    let refuse = true;
    healthyServer({
      chunk: (frame, socket) => {
        const records = frame.records as unknown[];
        if (refuse && records.length > 4) {
          refuse = false;
          socket.reply(errorFrame("Chunk 1 carries 5 records, more than the 4 allowed by 'arcadedb.server.wsMaxInsertChunkRows'"));
        } else socket.reply(ack(frame.chunkSeq as number, records.length));
      },
    });
    const session = await client().db("d").insertSession();
    const err = await session.sendChunk([{}, {}, {}, {}, {}]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect((err as ArcadeDBError).message).toContain("more than the 4");
    expect(session.lastChunkSeq).toBe(0);
    expect(session.open).toBe(true);

    const retry = await session.sendChunk([{}, {}]);
    expect(retry.chunkSeq).toBe(1);
    expect(FakeSocket.instances[0].sent.filter((f) => f.action === "chunk").map((f) => f.chunkSeq)).toEqual([1, 1]);
  });

  it("a whole-chunk failure (rowIndex -1) is acknowledged, flagged, passed to onBatchAck, and does not advance the sequence", async () => {
    let failOnce = true;
    healthyServer({
      chunk: (frame, socket) => {
        const n = (frame.records as unknown[]).length;
        if (failOnce) {
          failOnce = false;
          socket.reply({ ...ack(frame.chunkSeq as number, 0), received: n, failed: n, errors: [{ rowIndex: -1, code: "DUPLICATE_KEY", error: "dup" }] });
        } else socket.reply(ack(frame.chunkSeq as number, n));
      },
    });
    const seen: boolean[] = [];
    const session = await client().db("d").insertSession({ transactionMode: "per_batch", onBatchAck: (a) => seen.push(a.wholeChunkFailed) });
    const failed = await session.sendChunk([{}, {}]);
    expect(failed.wholeChunkFailed).toBe(true);
    expect(session.lastChunkSeq).toBe(0);
    expect(session.open).toBe(true);
    const replay = await session.sendChunk([{}, {}]);
    expect(replay.wholeChunkFailed).toBe(false);
    expect(session.lastChunkSeq).toBe(1);
    expect(seen).toEqual([true, false]);
    expect(FakeSocket.instances[0].sent.filter((f) => f.action === "chunk").map((f) => f.chunkSeq)).toEqual([1, 1]);
  });

  it("a frame over wsMaxInsertFrameSize closes the connection (1009) with no error frame, and the session is gone", async () => {
    healthyServer({ chunk: (_f, socket) => setTimeout(() => (socket as unknown as { emit: (t: string, e: object) => void }).emit("close", { code: 1009, reason: "Message too big" }), 0) });
    const session = await client().db("d").insertSession();
    const err = await session.sendChunk([{ big: "x".repeat(10) }]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect((err as ArcadeDBError).message).toContain("closed the /ws connection");
    expect((err as ArcadeDBError).detail).toContain("1009");
    expect(session.open).toBe(false);
    expect(session.lastChunkSeq).toBe(0);
    await expect(session.sendChunk([{}])).rejects.toThrow(/is closed/);
    await expect(session.close()).resolves.toBeUndefined();
  });

  it("an expiry that answers the awaited chunk ends the session", async () => {
    healthyServer({ chunk: (_f, socket) => socket.reply({ ...errorFrame("idle for 30000ms"), error: "Insert session expired" }) });
    const session = await client().db("d").insertSession();
    await expect(session.sendChunk([{}])).rejects.toThrow(/idle for/);
    expect(session.open).toBe(false);
    await expect(session.sendChunk([{}])).rejects.toThrow(/is closed/);
  });

  it("a Security error ends the session", async () => {
    healthyServer({
      chunk: (_f, socket) => socket.reply({ ...errorFrame("User does not have access to database 'd'."), error: "Security error" }),
    });
    const session = await client().db("d").insertSession();
    const err = await session.sendChunk([{}]).catch((e: unknown) => e);
    expect((err as ArcadeDBError).error).toBe("Security error");
    expect(session.open).toBe(false);
  });

  it("an Insert session error saying 'not found or expired' ends the session", async () => {
    healthyServer({ chunk: (_f, socket) => socket.reply(errorFrame("Insert session 'S1' not found or expired")) });
    const session = await client().db("d").insertSession();
    await expect(session.sendChunk([{}])).rejects.toThrow(/not found or expired/);
    expect(session.open).toBe(false);
  });

  it("an Internal error ends the session", async () => {
    healthyServer({ chunk: (_f, socket) => socket.reply({ ...errorFrame("NPE"), error: "Internal error" }) });
    const session = await client().db("d").insertSession();
    await expect(session.sendChunk([{}])).rejects.toThrow(/NPE/);
    expect(session.open).toBe(false);
  });

  it("an unrecognised error title leaves the session open, as in the Go and Python clients", async () => {
    healthyServer({ chunk: (_f, socket) => socket.reply({ ...errorFrame("slow down"), error: "Too many frames in flight" }) });
    const session = await client().db("d").insertSession();
    await expect(session.sendChunk([{}])).rejects.toThrow(/slow down/);
    expect(session.open).toBe(true);
  });

  it("a row-cap refusal and a skip-ahead refusal leave the session open", async () => {
    let n = 0;
    healthyServer({
      chunk: (frame, socket) => {
        n += 1;
        if (n === 1) socket.reply(errorFrame("Chunk 1 carries 5 records, more than the 4 allowed by 'arcadedb.server.wsMaxInsertChunkRows'. Split it into smaller chunks"));
        else if (n === 2) socket.reply(errorFrame("Chunk 1 skips ahead of the last applied chunk 0"));
        else socket.reply(ack(frame.chunkSeq as number, 1));
      },
    });
    const session = await client().db("d").insertSession();
    await expect(session.sendChunk([{}, {}, {}, {}, {}])).rejects.toThrow(/Split it/);
    expect(session.open).toBe(true);
    await expect(session.sendChunk([{}])).rejects.toThrow(/skips ahead/);
    expect(session.open).toBe(true);
    expect((await session.sendChunk([{}])).chunkSeq).toBe(1);
  });

  it("a row the server cannot apply is reported in the ack, not thrown", async () => {
    healthyServer({
      chunk: (frame, socket) =>
        socket.reply({ ...ack(frame.chunkSeq as number, 1), received: 2, failed: 1, errors: [{ rowIndex: 1, error: "no such type" }] }),
    });
    const session = await client().db("d").insertSession();
    const result = await session.sendChunk([{ a: 1 }, { "@class": "NoSuchType" }]);
    expect(result.failed).toBe(1);
    expect(result.errors).toEqual([{ rowIndex: 1, error: "no such type" }]);
    expect(result.wholeChunkFailed).toBe(false);
    expect(session.lastChunkSeq).toBe(1);
  });

  it("refuses a second call while a frame is in flight, without sending it", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    const first = session.sendChunk([{ a: 1 }]);
    await expect(session.sendChunk([{ a: 2 }])).rejects.toThrow(/frame in flight/);
    await first;
    expect(FakeSocket.instances[0].sent.filter((f) => f.action === "chunk")).toHaveLength(1);
  });

  it("times out when a chunk is never answered, and the session is then closed", async () => {
    healthyServer({ chunk: () => undefined });
    const session = await client().db("d").insertSession({ timeoutMs: 30 });
    await expect(session.sendChunk([{}])).rejects.toThrow(/Timeout of 30ms/);
    expect(session.open).toBe(false);
    await expect(session.sendChunk([{}])).rejects.toThrow(/is closed/);
  });

  it("reports a connection the server drops while a frame is awaited", async () => {
    healthyServer({ chunk: (_f, socket) => socket.drop() });
    const session = await client().db("d").insertSession();
    const err = await session.sendChunk([{}]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect((err as ArcadeDBError).message).toContain("closed the /ws connection");
    expect(session.open).toBe(false);
  });

  it("reports an unsolicited error frame (idle sweep) instead of skipping it, and sends nothing", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    await session.sendChunk([{}]);
    FakeSocket.instances[0].reply({ ...errorFrame("Insert session expired: idle"), error: "Insert session expired" });
    await new Promise((r) => setTimeout(r, 10));

    const before = FakeSocket.instances[0].sent.length;
    const err = await session.sendChunk([{}]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect((err as ArcadeDBError).message).toContain("expired");
    expect(FakeSocket.instances[0].sent).toHaveLength(before);
    expect(session.open).toBe(false);
  });

  it("reports an unsolicited error that arrives while the next answer is awaited", async () => {
    healthyServer({ chunk: (_f, socket) => socket.reply({ ...errorFrame("session swept"), error: "Insert session expired" }) });
    const session = await client().db("d").insertSession();
    await expect(session.sendChunk([{}])).rejects.toThrow(/session swept/);
  });
});

describe("db.insertSession: ending", () => {
  it("commit returns the committed frame and closes the session", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    await session.sendChunk([{}]);
    const result = await session.commit();
    expect(result.outcome).toBe("commit");
    expect(session.open).toBe(false);
    await expect(session.sendChunk([{}])).rejects.toThrow(/is closed/);
    await expect(session.commit()).rejects.toThrow(/is closed/);
  });

  it("rollback returns the committed frame", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    expect((await session.rollback()).outcome).toBe("rollback");
  });

  it("close() rolls back a session still open, then drops the connection; it is idempotent", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    await session.sendChunk([{}]);
    await session.close();
    await session.close();
    const socket = FakeSocket.instances[0];
    expect(socket.sent.map((f) => f.action)).toEqual(["start", "chunk", "rollback"]);
    expect(socket.closedWith).toBe(1000);
  });

  it("close() after commit sends no rollback", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    await session.commit();
    await session.close();
    expect(FakeSocket.instances[0].sent.map((f) => f.action)).toEqual(["start", "commit"]);
  });

  it("close() swallows a failing rollback", async () => {
    healthyServer({ rollback: (_f, socket) => socket.reply(errorFrame("boom")) });
    const session = await client().db("d").insertSession();
    await expect(session.close()).resolves.toBeUndefined();
    expect(FakeSocket.instances[0].closedWith).toBe(1000);
  });

  it("a commit the server refuses still closes the session", async () => {
    healthyServer({ commit: (_f, socket) => socket.reply(errorFrame("duplicate key")) });
    const session = await client().db("d").insertSession();
    await expect(session.commit()).rejects.toThrow(/duplicate key/);
    expect(session.open).toBe(false);
  });

  it("supports await using", async () => {
    healthyServer();
    const session = await client().db("d").insertSession();
    await session[Symbol.asyncDispose]();
    expect(FakeSocket.instances[0].closedWith).toBe(1000);
  });
});

describe("db.insertSession: joining a transaction", () => {
  /** An HTTP server that only knows begin/commit/rollback, handing out the session id TX-1. */
  function txClient() {
    const calls: string[] = [];
    const fetchImpl = (async (input: Request | string | URL) => {
      const request = input instanceof Request ? input : new Request(input);
      calls.push(`${request.method} ${new URL(request.url).pathname}`);
      return new Response(null, { status: 204, headers: { "arcadedb-session-id": "TX-1" } });
    }) as typeof fetch;
    const server = createClient({ baseUrl: "http://localhost:2480", auth: basicAuth("root", "pw"), fetch: fetchImpl, WebSocket: FakeSocket });
    return { server, calls };
  }

  it("sends the transaction's id with transactionMode none, and commit answers detached", async () => {
    healthyServer();
    const { server, calls } = txClient();
    await server.db("d").transaction(async (tx) => {
      const session = await tx.insertSession({ targetType: "Person", joinTransaction: true });
      expect(session.transactionMode).toBe("none");
      expect(session.transactionId).toBe("TX-1");
      await session.sendChunk([{ name: "a" }]);
      const result = await session.commit();
      expect(result.outcome).toBe("detached");
    });
    const start = FakeSocket.instances[0].sent[0];
    expect(start.transactionId).toBe("TX-1");
    expect(start.options).toEqual({ targetType: "Person", transactionMode: "none" });
    expect(calls).toEqual(["POST /api/v1/begin/d", "POST /api/v1/commit/d"]);
  });

  it("refuses joinTransaction outside a transaction, client-side, before connecting", async () => {
    healthyServer();
    await expect(client().db("d").insertSession({ joinTransaction: true })).rejects.toThrow(/no open transaction/);
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("refuses joinTransaction combined with a transactionMode other than none", async () => {
    healthyServer();
    const { server } = txClient();
    await server.db("d").transaction(async (tx) => {
      await expect(tx.insertSession({ joinTransaction: true, transactionMode: "per_batch" })).rejects.toThrow(/requires transactionMode "none"/);
    });
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("a session opened on a tx handle WITHOUT joinTransaction does not join", async () => {
    healthyServer();
    const { server } = txClient();
    await server.db("d").transaction(async (tx) => {
      const s = await tx.insertSession();
      await s.close();
    });
    expect("transactionId" in FakeSocket.instances[0].sent[0]).toBe(false);
  });
});
