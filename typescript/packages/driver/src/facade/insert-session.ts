import type { Middleware } from "openapi-fetch";
import { ArcadeDBError } from "../errors.js";

/**
 * The slice of the WebSocket API this client uses. The runtime's global `WebSocket` (Node 22+,
 * browsers, Deno, Bun) satisfies it, and so does the `ws` package's class, which is what a Node 20
 * caller injects. Frames are read through `addEventListener` because that is the one reading API
 * all of them share.
 */
export interface WebSocketLike {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  addEventListener(
    type: "open" | "message" | "error" | "close",
    listener: (event: WebSocketEventLike) => void,
  ): void;
}

/** The union of the event fields this client reads; each event type carries only its own subset. */
export interface WebSocketEventLike {
  data?: unknown;
  code?: number;
  reason?: string;
  message?: string;
  error?: unknown;
}

/**
 * A WebSocket class. `options.headers` is passed **only when the client has credentials to send**
 * (an `Authorization` header), and it is a non-standard second argument: `ws` and Node's built-in
 * `WebSocket` read it, a browser's `WebSocket` does not - see the README's insert-session section.
 */
export type WebSocketConstructor = new (url: string, options?: { headers?: Record<string, string> }) => WebSocketLike;

/** What `createClient` hands the database handle so it can open a `/ws` connection. */
export interface InsertSessionContext {
  baseUrl: string;
  auth?: Middleware;
  WebSocket?: WebSocketConstructor;
}

/** The server's commit policy for an insert session. `none` is what joining a transaction uses. */
export type InsertTransactionMode = "per_stream" | "per_batch" | "per_row" | "none";
/** What the server does with a row whose key already exists. */
export type InsertConflictMode = "error" | "update" | "ignore" | "abort";

/** One record of a chunk: its properties, plus an optional `@class` that overrides `targetType` for that record. */
export type InsertRecord = Record<string, unknown>;

/** One row the server could not apply, as it appears in a `batchAck`'s `errors`. */
export interface InsertRowError {
  rowIndex?: number;
  [key: string]: unknown;
}

/** The server's `batchAck` frame: one per accepted chunk. */
export interface BatchAck {
  action: "batchAck";
  result?: string;
  sessionId: string;
  chunkSeq: number;
  received: number;
  inserted: number;
  updated: number;
  ignored: number;
  failed: number;
  /** Present only when at least one row failed. A failed row does not refuse the chunk. */
  errors?: InsertRowError[];
  /** True when the server recognised the chunk as one it had already applied and did not apply it again. */
  replay?: boolean;
  /**
   * Set by this client, not sent by the server: true when the chunk failed AS A WHOLE - its own
   * transaction could not commit, so nothing in it is durable,
   * `failed` equals `received`, and `errors` holds one entry with `rowIndex` -1. Only a
   * `per_batch` session produces it: under `per_stream` a failure of that kind (a duplicate key
   * found at commit time) is an `error` answering `commit()`, and the session is then gone. The server has
   * not advanced its watermark, so `lastChunkSeq` does not advance either: resend the same records
   * (or a split of them) and they go out under the same sequence number.
   */
  wholeChunkFailed: boolean;
}

/** The totals carried by a `committed` frame. */
export interface InsertSummary {
  received: number;
  inserted: number;
  updated: number;
  ignored: number;
  failed: number;
  executionTimeMs: number;
  /** True when chunks already acknowledged are committed whatever this frame says (`per_batch`, `per_row`). */
  partialCommit: boolean;
  /** Set when the session joined an HTTP transaction. */
  externalTransaction?: boolean;
  transactionId?: string;
}

/**
 * The server's `committed` frame, the answer to both `commit()` and `rollback()`. `outcome` is
 * `"detached"` for a session that joined a transaction: it decided nothing, and the rows become
 * durable only when the transaction itself is committed over HTTP.
 */
export interface CommittedFrame {
  action: "committed";
  result?: string;
  sessionId: string;
  outcome: "commit" | "rollback" | "detached";
  summary: InsertSummary;
}

export interface InsertSessionOptions {
  /**
   * The id to open the session under. Left out, the server generates one (`session.sessionId`).
   * A client-chosen id lives in ONE namespace shared by every connection to the server, so two
   * clients choosing the same id collide; prefer the generated one.
   */
  sessionId?: string;
  /** Default type of every record, overridable per record with `@class`. */
  targetType?: string;
  /** Commit policy. Defaults server-side to `per_stream`. Cannot be combined with `joinTransaction` unless `"none"`. */
  transactionMode?: InsertTransactionMode;
  /** Defaults server-side to `error`. */
  conflictMode?: InsertConflictMode;
  keyColumns?: string[];
  updateColumnsOnConflict?: string[];
  /** Rows are received, parsed and counted; nothing is written. */
  validateOnly?: boolean;
  /**
   * Write into the transaction this handle is already inside, instead of opening one on the
   * server. Only meaningful on the `tx` handle passed to `db.transaction()`; on any other handle
   * the call is refused client-side, because there is nothing to join. The session's `commit()`
   * then answers `outcome: "detached"` and commits nothing: the transaction commits when
   * `db.transaction()`'s callback resolves.
   */
  joinTransaction?: boolean;
  /** Called with every `batchAck` before `sendChunk` returns it. */
  onBatchAck?: (ack: BatchAck) => void;
  /** How long one frame exchange (and the connect) may take. Default 60000. */
  timeoutMs?: number;
  /** A WebSocket class for this session, overriding the client's and the runtime's global. */
  WebSocket?: WebSocketConstructor;
}

/** Status carried by every `ArcadeDBError` raised here: there is no HTTP status on a frame. */
const NO_HTTP_STATUS = 0;
const DEFAULT_TIMEOUT_MS = 60_000;

function sessionError(message: string, detail?: string, cause?: unknown): ArcadeDBError {
  const err = new ArcadeDBError(NO_HTTP_STATUS, { error: message, detail });
  if (cause !== undefined) err.cause = cause;
  return err;
}

/** An `error` frame as an `ArcadeDBError`. `message` carries the detail, which is where the server says what was wrong. */
function frameError(frame: Record<string, unknown>, sessionId: string): ArcadeDBError {
  const err = new ArcadeDBError(NO_HTTP_STATUS, frame);
  const detail = typeof frame.detail === "string" ? frame.detail : undefined;
  const kind = typeof frame.error === "string" ? frame.error : "Insert session error";
  err.message = `${kind} on /ws insert session '${sessionId}'${detail ? `: ${detail}` : ""}`;
  return err;
}

function toWebSocketUrl(baseUrl: string): string {
  const url = new URL(baseUrl);
  if (url.protocol === "https:") url.protocol = "wss:";
  else if (url.protocol === "http:") url.protocol = "ws:";
  url.pathname = `${url.pathname.replace(/\/+$/, "")}/ws`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

/**
 * The `Authorization` value the client's auth middleware would put on a request. `auth` is an
 * openapi-fetch middleware, opaque by design, so it is asked the only way it can be: by running it
 * on a throwaway request and reading the header it sets.
 */
async function resolveAuthorization(auth: Middleware | undefined, httpUrl: string): Promise<string | undefined> {
  if (!auth?.onRequest) return undefined;
  const probe = new Request(httpUrl);
  const result = (await auth.onRequest({
    request: probe,
    schemaPath: "/ws",
    params: {},
    id: "insert-session",
    options: {},
  } as unknown as Parameters<NonNullable<Middleware["onRequest"]>>[0])) as unknown;
  const request = result instanceof Request ? result : probe;
  return request.headers.get("Authorization") ?? undefined;
}

function decodeFrame(data: unknown): string | undefined {
  if (typeof data === "string") return data;
  if (data instanceof ArrayBuffer) return new TextDecoder().decode(data);
  if (ArrayBuffer.isView(data)) return new TextDecoder().decode(data);
  return undefined;
}

type Frame = Record<string, unknown>;

interface Waiter {
  resolve: (frame: Frame) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

/**
 * A duplex insert session on the server's `/ws` endpoint, opened with `db.insertSession()`.
 *
 * The caller sees the acknowledgement of chunk n and only then decides what to send next,
 * including whether to `commit()` or `rollback()` at all - which `batchLoad`'s fixed commit policy
 * cannot offer.
 *
 * NOT concurrency safe: one session belongs to one caller. The protocol would let a client
 * pipeline frames, which this class deliberately does not do; a second call made while a frame is
 * in flight is refused rather than interleaved.
 *
 * Every failure is an `ArcadeDBError` with `status` 0 (a frame has no HTTP status); `error`,
 * `detail` and `exception` carry what the server's `error` frame said.
 */
export class InsertSession {
  /** The id the session is known by on the server: generated by it unless the caller chose one. */
  readonly sessionId: string;
  readonly database: string | undefined;
  /** The commit policy the server echoed in `started`, which is what is actually in force. */
  readonly transactionMode: string | undefined;
  /** The HTTP transaction this session joined, or `undefined` when it manages its own. */
  readonly transactionId: string | undefined;

  private chunkSeq = 0;
  private isOpen = true;
  private busy = false;
  private closing: Promise<void> | undefined;
  private readonly queue: Frame[] = [];
  private waiter: Waiter | undefined;
  private terminal: Error | undefined;
  private socketClosed = false;
  private readonly closeWaiters: (() => void)[] = [];

  /** @internal Use `db.insertSession()`. */
  constructor(
    private readonly socket: WebSocketLike,
    started: Frame,
    private readonly timeoutMs: number,
    private readonly onBatchAck: ((ack: BatchAck) => void) | undefined,
    pending: Frame[],
    terminal: Error | undefined,
    closed: boolean,
  ) {
    this.sessionId = String(started.sessionId);
    this.database = typeof started.database === "string" ? started.database : undefined;
    this.transactionMode = typeof started.transactionMode === "string" ? started.transactionMode : undefined;
    this.transactionId = typeof started.transactionId === "string" ? started.transactionId : undefined;
    this.queue.push(...pending);
    this.terminal = terminal;
    this.socketClosed = closed;
  }

  /** How many chunks the server has acknowledged. The next one goes out as this plus one. */
  get lastChunkSeq(): number {
    return this.chunkSeq;
  }

  /** False once the session has been committed, rolled back, closed, or has failed. */
  get open(): boolean {
    return this.isOpen;
  }

  /** @internal Called by the opener for every event on the socket after the handshake. */
  push(frame: Frame): void {
    if (this.waiter) {
      const w = this.waiter;
      this.waiter = undefined;
      clearTimeout(w.timer);
      w.resolve(frame);
    } else {
      this.queue.push(frame);
    }
  }

  /** @internal */
  fail(err: Error, closed: boolean): void {
    this.terminal ??= err;
    if (closed) {
      this.socketClosed = true;
      for (const w of this.closeWaiters.splice(0)) w();
    }
    if (this.waiter) {
      const w = this.waiter;
      this.waiter = undefined;
      clearTimeout(w.timer);
      w.reject(err);
    }
  }

  /**
   * Sends one chunk and returns the `batchAck` the server answered it with, after handing it to
   * `onBatchAck` if one was given.
   *
   * The sequence number is managed here, from 1, and advanced only once the server has
   * acknowledged the chunk. A chunk the server refuses with an "Insert session error" frame - too
   * many rows (`wsMaxInsertChunkRows`), a sequence that skips ahead, bad options or data - rejects
   * with `ArcadeDBError` and leaves the session open with the sequence where it was, so the caller can split the batch and resend it
   * under the same number. A chunk whose own transaction fails is acknowledged with
   * `wholeChunkFailed: true` (`per_batch` only) and likewise leaves the sequence where it was.
   * These `error` frames END the session (`open` becomes false): "Security error" (grant
   * revoked or principal invalid), "Insert session expired" (idle sweep), "Internal error", and an
   * "Insert session error" saying the session is "not found or expired" or "is closed". An
   * unrecognised title leaves it open, as in the Go and Python clients. A row the server
   * cannot apply is NOT a refusal: it comes back counted in `failed` and described in `errors`.
   *
   * A frame larger than `wsMaxInsertFrameSize` is different: the server answers no frame at all
   * and closes the connection (1009), so the call rejects and the SESSION IS GONE - its uncommitted
   * rows are rolled back server-side. Keep chunks well under that size; a split cannot be replayed
   * into the same session.
   */
  async sendChunk(records: readonly InsertRecord[]): Promise<BatchAck> {
    this.checkOpen();
    const seq = this.chunkSeq + 1;
    const ack = (await this.exchange({ action: "chunk", sessionId: this.sessionId, chunkSeq: seq, records }, "batchAck")) as unknown as BatchAck;
    // A whole-chunk failure (the chunk's own transaction failed; reported as an error at rowIndex
    // -1) is acknowledged but does NOT advance the server's watermark: the chunk must be replayed
    // under the same sequence number, so ours stays put too.
    ack.wholeChunkFailed = Array.isArray(ack.errors) && ack.errors.some((e) => e?.rowIndex === -1);
    if (!ack.wholeChunkFailed) this.chunkSeq = seq;
    this.onBatchAck?.(ack);
    return ack;
  }

  /**
   * Ends the session and commits what it wrote, returning the `committed` frame.
   *
   * A session that joined a transaction commits nothing here: `outcome` is `"detached"` and the
   * rows become durable only when that transaction commits over HTTP.
   */
  commit(): Promise<CommittedFrame> {
    return this.finish("commit");
  }

  /**
   * Ends the session and discards what it wrote, returning the `committed` frame. Only a
   * `per_stream` session can undo chunks it has already had acknowledged; `summary.partialCommit`
   * says whether this one could. A session on a joined transaction discards nothing here either.
   */
  rollback(): Promise<CommittedFrame> {
    return this.finish("rollback");
  }

  /**
   * Rolls the session back if it is still open, then closes the connection. Idempotent, and safe
   * to call after `commit()`. Never throws: a rollback that fails here is swallowed because the
   * connection is being dropped anyway, and the server rolls back whatever a closed connection
   * left behind.
   */
  close(): Promise<void> {
    this.closing ??= this.doClose();
    return this.closing;
  }

  async [Symbol.asyncDispose](): Promise<void> {
    await this.close();
  }

  private async doClose(): Promise<void> {
    if (this.isOpen && !this.busy) {
      try {
        await this.finish("rollback");
      } catch {
        // See close(): the connection is going away regardless.
      }
    }
    this.isOpen = false;
    if (this.socketClosed) return;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, this.timeoutMs);
      this.closeWaiters.push(() => {
        clearTimeout(timer);
        resolve();
      });
      try {
        this.socket.close(1000);
      } catch {
        clearTimeout(timer);
        resolve();
      }
    });
  }

  private async finish(action: "commit" | "rollback"): Promise<CommittedFrame> {
    this.checkOpen();
    try {
      return (await this.exchange({ action, sessionId: this.sessionId }, "committed")) as unknown as CommittedFrame;
    } finally {
      // Closed whatever the server said: a commit the engine refused has already rolled the
      // session back, and a second frame on it would only be answered "session is closed".
      this.isOpen = false;
    }
  }

  private checkOpen(): void {
    if (!this.isOpen) throw sessionError(`The /ws insert session '${this.sessionId}' is closed`);
    if (this.busy) throw sessionError(`The /ws insert session '${this.sessionId}' already has a frame in flight; a session is not concurrency safe`);
  }

  /**
   * Writes one frame and reads the one answer to it. Every frame sent is answered by exactly one
   * frame, so anything already waiting before the send is an unsolicited `error` - the idle sweep
   * having given up on the session - and is reported rather than skipped: whatever the answer
   * would have said, the session is gone. An `error` that IS the awaited answer ends the session
   * too unless it is a usable refusal; see `endsSession`.
   */
  private async exchange(frame: Frame, expected: "batchAck" | "committed"): Promise<Frame> {
    this.busy = true;
    try {
      if (this.queue.length > 0) {
        this.isOpen = false;
        return this.checkAnswer(this.queue.shift() as Frame, expected);
      }
      if (this.terminal) {
        this.isOpen = false;
        throw this.terminal;
      }
      try {
        this.socket.send(JSON.stringify(frame));
      } catch (err) {
        this.isOpen = false;
        throw sessionError(`Error on sending a /ws insert frame for session '${this.sessionId}'`, errorText(err), err);
      }
      const answer = await this.nextFrame();
      return this.checkAnswer(answer, expected);
    } finally {
      this.busy = false;
    }
  }

  private checkAnswer(answer: Frame, expected: string): Frame {
    if (answer.result === "error" || answer.action === "error") {
      if (endsSession(answer)) this.isOpen = false;
      throw frameError(answer, this.sessionId);
    }
    if (answer.action !== expected) {
      this.isOpen = false;
      throw sessionError(
        `Unexpected frame '${String(answer.action)}' on /ws insert session '${this.sessionId}', expected '${expected}'`,
      );
    }
    return answer;
  }

  private nextFrame(): Promise<Frame> {
    return new Promise<Frame>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiter = undefined;
        this.isOpen = false;
        reject(sessionError(`Timeout of ${this.timeoutMs}ms waiting for the answer to a frame of /ws insert session '${this.sessionId}'`));
        try {
          this.socket.close(1000);
        } catch {
          // already gone
        }
      }, this.timeoutMs);
      this.waiter = {
        resolve,
        reject: (err) => {
          this.isOpen = false;
          reject(err);
        },
        timer,
      };
    });
  }
}

/**
 * Whether an `error` frame means the server no longer holds the session. Only an
 * "Insert session error" refusal - the row cap, a chunk that skips ahead, bad options or data -
 * leaves it usable; and not even that kind when its detail says the session is gone ("not found
 * or expired", "' is closed"). "Security error" (a revoked grant has already rolled the session
 * back; an invalid principal closes the connection), "Insert session expired" (the idle sweep),
 * and "Internal error" end it. An unrecognised title does NOT, the same default the Go and Python
 * clients take: a session marked closed is never rolled back by `close()`, so wrongly giving up
 * on one leaves the server holding it until the idle sweep, while wrongly keeping it costs one
 * more frame, answered "not found or expired", which does end it.
 */
function endsSession(frame: Frame): boolean {
  if (frame.error === "Insert session expired" || frame.error === "Security error" || frame.error === "Internal error")
    return true;
  if (frame.error !== "Insert session error") return false;
  const detail = typeof frame.detail === "string" ? frame.detail : "";
  return detail.includes("not found or expired") || detail.includes("' is closed");
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function startFrame(database: string, transactionId: string | undefined, opts: InsertSessionOptions, transactionMode: string | undefined): Frame {
  const options: Frame = {};
  if (opts.targetType !== undefined) options.targetType = opts.targetType;
  if (transactionMode !== undefined) options.transactionMode = transactionMode;
  if (opts.conflictMode !== undefined) options.conflictMode = opts.conflictMode;
  if (opts.keyColumns !== undefined) options.keyColumns = opts.keyColumns;
  if (opts.updateColumnsOnConflict !== undefined) options.updateColumnsOnConflict = opts.updateColumnsOnConflict;
  if (opts.validateOnly) options.validateOnly = true;
  const frame: Frame = { action: "start", database, options };
  if (opts.sessionId !== undefined) frame.sessionId = opts.sessionId;
  if (transactionId !== undefined) frame.transactionId = transactionId;
  return frame;
}

/**
 * Connects, sends `start` and resolves with the session once the server has answered `started`.
 * Behind `db.insertSession()`; see `InsertSession` and the README for the contract.
 */
export async function openInsertSession(
  ctx: InsertSessionContext | undefined,
  database: string,
  txSessionId: string | undefined,
  opts: InsertSessionOptions,
): Promise<InsertSession> {
  if (!ctx) {
    throw sessionError("This ArcadeDBServer was not built by createClient(), so it has no base URL to open a /ws connection on");
  }
  let transactionMode = opts.transactionMode;
  if (opts.joinTransaction) {
    if (txSessionId === undefined) {
      throw sessionError(
        "There is no open transaction to join: call insertSession({ joinTransaction: true }) on the handle passed to db.transaction()",
      );
    }
    if (transactionMode !== undefined && transactionMode !== "none") {
      throw sessionError(`joinTransaction requires transactionMode "none", not "${transactionMode}"`);
    }
    transactionMode = "none";
  }
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const Ctor =
    opts.WebSocket ?? ctx.WebSocket ?? (globalThis as { WebSocket?: WebSocketConstructor }).WebSocket;
  if (!Ctor) {
    throw sessionError(
      "No WebSocket implementation is available: this runtime has no global WebSocket (Node < 22). Pass the `ws` package's class as the `WebSocket` option",
    );
  }

  const url = toWebSocketUrl(ctx.baseUrl);
  const authorization = await resolveAuthorization(ctx.auth, ctx.baseUrl);
  let socket: WebSocketLike;
  try {
    socket = authorization ? new Ctor(url, { headers: { Authorization: authorization } }) : new Ctor(url);
  } catch (err) {
    throw sessionError(`Error on opening the /ws insert session on ${url}`, errorText(err), err);
  }

  // Frames and failures that arrive before the session object exists are buffered here and handed
  // to it; afterwards they are forwarded straight to it.
  const early: Frame[] = [];
  let earlyTerminal: Error | undefined;
  let earlyClosed = false;
  let session: InsertSession | undefined;
  let onOpen: (() => void) | undefined;
  let onHandshakeEvent: (() => void) | undefined;

  socket.addEventListener("open", () => onOpen?.());
  socket.addEventListener("message", (event) => {
    const text = decodeFrame(event.data);
    let frame: Frame;
    try {
      if (text === undefined) throw new Error("not a text frame");
      frame = JSON.parse(text) as Frame;
    } catch (err) {
      const e = sessionError("The server sent a /ws frame that is not JSON", errorText(err));
      if (session) session.fail(e, false);
      else earlyTerminal ??= e;
      onHandshakeEvent?.();
      return;
    }
    if (session) session.push(frame);
    else early.push(frame);
    onHandshakeEvent?.();
  });
  socket.addEventListener("error", (event) => {
    const detail = event.message ?? (event.error === undefined ? undefined : errorText(event.error));
    const e = sessionError(`The /ws connection to ${url} failed`, detail, event.error);
    if (session) session.fail(e, false);
    else earlyTerminal ??= e;
    onHandshakeEvent?.();
    onOpen?.();
  });
  socket.addEventListener("close", (event) => {
    const e = sessionError(`The server closed the /ws connection to ${url}`, event.reason ? `${event.code ?? ""} ${event.reason}`.trim() : undefined);
    if (session) session.fail(e, true);
    else {
      earlyTerminal ??= e;
      earlyClosed = true;
    }
    onHandshakeEvent?.();
    onOpen?.();
  });

  const abort = (): void => {
    try {
      socket.close(1000);
    } catch {
      // already gone
    }
  };
  const wait = (arm: (done: () => void) => void, what: string): Promise<void> =>
    new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(sessionError(`Timeout of ${timeoutMs}ms ${what}`));
      }, timeoutMs);
      arm(() => {
        clearTimeout(timer);
        resolve();
      });
    });

  try {
    let opened = false;
    await wait((done) => {
      onOpen = () => {
        opened = true;
        done();
      };
    }, `opening the /ws connection to ${url}`);
    if (!opened || earlyTerminal) throw earlyTerminal ?? sessionError(`The /ws connection to ${url} failed`);
    onOpen = undefined;

    socket.send(JSON.stringify(startFrame(database, opts.joinTransaction ? txSessionId : undefined, opts, transactionMode)));
    await wait((done) => {
      onHandshakeEvent = () => {
        if (early.length > 0 || earlyTerminal) done();
      };
      onHandshakeEvent();
    }, "waiting for the answer to the start frame of a /ws insert session");
    onHandshakeEvent = undefined;

    const answer = early.shift();
    if (!answer) throw earlyTerminal ?? sessionError("The /ws connection closed before the server answered `start`");
    if (answer.result === "error" || answer.action === "error") {
      throw frameError(answer, opts.sessionId ?? "<pending>");
    }
    if (answer.action !== "started") {
      throw sessionError(`Unexpected frame '${String(answer.action)}' answering \`start\`, expected 'started'`);
    }
    session = new InsertSession(socket, answer, timeoutMs, opts.onBatchAck, early, earlyTerminal, earlyClosed);
    return session;
  } catch (err) {
    onOpen = undefined;
    onHandshakeEvent = undefined;
    abort();
    throw err;
  }
}
