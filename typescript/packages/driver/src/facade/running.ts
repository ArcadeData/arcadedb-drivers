import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/**
 * What a terminate command answers for one statement or transaction. `"terminated"`: it stopped
 * and what it wrote was rolled back. `"completed"`: it ended on its own before it noticed, so what
 * it did stands. `"terminating"`: not stopped yet within the wait. `"not found"`: no such statement
 * on this server, or another user's.
 */
export type QueryStatus = "terminated" | "completed" | "terminating" | "not found";

/**
 * One statement as `listQueries` returns it, passed through as the server sends it. The contract
 * does not describe this shape; it is what a 26.11.1-SNAPSHOT server sends. `sessionId` is absent
 * for a statement that does not run inside a transaction, and `tag` for one sent without a
 * `queryTag`. `startedAt` is epoch milliseconds.
 */
export interface RunningQuery {
  id: string;
  database: string;
  user: string;
  protocol: string;
  language: string;
  text: string;
  startedAt: number;
  elapsedMs: number;
  terminating: boolean;
  sessionId?: string;
  tag?: string;
  clientAddress?: string;
  server: string;
}

/**
 * The answer for one statement or transaction. `sessionId` and `sessionOpen` are present only for a
 * statement that ran inside a transaction: a command terminated there ends the transaction too
 * (`sessionOpen` false), a terminated read leaves it open. For a `"terminating"` statement
 * `sessionOpen` is only the state at the time of the answer, since a command ends its session as
 * it stops.
 */
export interface TerminateResult {
  id: string;
  status: QueryStatus;
  sessionId?: string;
  sessionOpen?: boolean;
}

/**
 * One transaction session as `listTransactions` returns it. `runningQueries` holds the ids of the
 * statements running in it, which `terminateQuery` takes.
 */
export interface OpenTransaction {
  id: string;
  user: string;
  database: string;
  idleMs: number;
  busy: boolean;
  runningQueries: string[];
  server: string;
}

/** Narrows `listQueries`. An omitted or empty field is no filter. */
export interface ListQueriesOptions {
  database?: string;
  tag?: string;
}

/** Bounds how long a terminate command waits for the statements to stop. */
export interface TerminateOptions {
  /**
   * Milliseconds. Omitted or zero leaves the server's default, 5000; the server caps it at 10000.
   * A statement still running when the wait ends is answered `"terminating"`.
   */
  waitMs?: number;
}

/** `GET /api/v1/progress/{database}`'s answer: the in-progress maintenance operations. */
export type ProgressResponse = components["schemas"]["ProgressResponse"];

/**
 * What the server, in Java, trims and splits on: every character at or below U+0020. Not `\s` or
 * `trim()`, which would refuse a no-break space the server keeps. The Go and Python clients use the
 * same rule.
 */
function spaceOrControl(c: string): boolean {
  return c.charCodeAt(0) <= 0x20;
}

/**
 * Throws `RangeError` for a value the server would split: it reads a database name, a query id and
 * a session id as one word.
 */
function checkWord(what: string, value: string): void {
  if (value === "" || Array.from(value).some(spaceOrControl)) {
    throw new RangeError(`${what} ${JSON.stringify(value)} is empty or contains a space or control character`);
  }
}

/**
 * Throws `RangeError` for a tag the server would silently change: it takes the rest of the command
 * as the tag, trimmed, so " a" would match "a" rather than the tag named.
 */
function checkTag(tag: string): void {
  if (tag !== "" && (spaceOrControl(tag.charAt(0)) || spaceOrControl(tag.charAt(tag.length - 1)))) {
    throw new RangeError(`tag ${JSON.stringify(tag)} starts or ends with a space or control character`);
  }
}

/**
 * Sends `command` through `POST /api/v1/server` and returns the body's `result`. Not through
 * `serverCommand`: the contract's `CommandRequest` has no `wait`, although the server reads one.
 * A positive wait under a millisecond is rounded up rather than sent as 0, which the server reads
 * as "do not wait".
 */
async function running<T>(client: RawClient, command: string, waitMs?: number): Promise<T> {
  const body: Record<string, unknown> = { command, language: "sql" };
  if (waitMs !== undefined && !Number.isFinite(waitMs)) {
    // JSON.stringify would send Infinity as null and drop NaN's meaning silently.
    throw new RangeError(`waitMs ${waitMs} is not a finite number`);
  }
  if (waitMs !== undefined && waitMs > 0) body.wait = Math.max(1, Math.ceil(waitMs));
  const data: unknown = await unwrap(
    client.POST("/api/v1/server", { body: body as components["schemas"]["CommandRequest"] }),
  );
  const result = (data as { result?: unknown } | undefined)?.result;
  if (result === undefined || result === null) {
    throw new TypeError(`POST /api/v1/server answered with no result for "${command.split(" ", 2).join(" ")}"`);
  }
  return result as T;
}

export async function listQueries(client: RawClient, opts: ListQueriesOptions): Promise<RunningQuery[]> {
  let command = "list queries";
  if (opts.database) {
    checkWord("database name", opts.database);
    command += ` database ${opts.database}`;
  }
  if (opts.tag) {
    checkTag(opts.tag);
    command += ` tag ${opts.tag}`;
  }
  return running<RunningQuery[]>(client, command);
}

export async function terminateQuery(client: RawClient, id: string, opts: TerminateOptions): Promise<TerminateResult> {
  checkWord("query id", id);
  return running<TerminateResult>(client, `terminate query ${id}`, opts.waitMs);
}

export async function terminateQueriesByTag(
  client: RawClient,
  tag: string,
  opts: TerminateOptions,
): Promise<TerminateResult[]> {
  if (tag === "") throw new RangeError("tag is empty");
  checkTag(tag);
  return running<TerminateResult[]>(client, `terminate queries tag ${tag}`, opts.waitMs);
}

export async function listTransactions(client: RawClient): Promise<OpenTransaction[]> {
  return running<OpenTransaction[]>(client, "list transactions");
}

export async function terminateTransaction(
  client: RawClient,
  sessionId: string,
  opts: TerminateOptions,
): Promise<TerminateResult> {
  checkWord("session id", sessionId);
  return running<TerminateResult>(client, `terminate transaction ${sessionId}`, opts.waitMs);
}

export async function progress(client: RawClient, database: string): Promise<ProgressResponse> {
  return unwrap(client.GET("/api/v1/progress/{database}", { params: { path: { database } } }));
}
