import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import { decodeNdJson } from "../internal/ndjson.js";
import { type EdgeRow, serializeRows, type VertexRow } from "../internal/batch-rows.js";

type RawClient = Client<paths>;

/**
 * The contract's `NdJsonBatchEvent.error` object, widened by one field the schema does not
 * declare.
 *
 * The generated `error` object carries only `commitIndex`, `status` and `statusMapped` - but the
 * server sends `error` (the message) and `exception` on it too, the same fields the BUFFERED
 * encoding declares on `BatchError`. Established against a live 26.10.1-SNAPSHOT server and
 * reported upstream alongside ArcadeData/arcadedb#7570 (the `idMappingStreamed` gap `BatchSummary`
 * works around below is the same contract, the same endpoint, the same kind of gap). Without this
 * widening, the one thing a caller needs from an in-band failure - what went wrong - is
 * unreachable through the generated type.
 *
 * Narrow this back to the generated type once the contract declares the fields.
 */
type BatchErrorEvent = NonNullable<components["schemas"]["NdJsonBatchEvent"]["error"]> & {
  error?: string;
  exception?: string;
};

export type NdJsonBatchEvent = Omit<components["schemas"]["NdJsonBatchEvent"], "error"> & {
  error?: BatchErrorEvent;
};

/**
 * The buffered summary, plus one field the contract does not declare.
 *
 * `BatchResponse` declares `idMapping`, `idMappingOmitted` and `idMappingSize`. On a STREAMED
 * load the server sends `idMappingStreamed: true` instead - a field in no schema, reported
 * upstream as a comment on ArcadeData/arcadedb#7570. It is a genuinely different condition from
 * `idMappingOmitted`: *omitted* means too large to return, *streamed* means already delivered in
 * the progress lines. Without this widening, the one signal telling a caller which of those
 * happened is unreachable through the generated type.
 *
 * Narrow this back to the generated type once the contract declares the field.
 */
export type BatchSummary = components["schemas"]["BatchResponse"] & { idMappingStreamed?: boolean };

/** The 17 tuning parameters, named exactly as the contract names them. */
export interface BatchOptions {
  batchSize?: number;
  lightEdges?: boolean;
  wal?: boolean;
  parallelFlush?: boolean;
  preAllocateEdgeChunks?: boolean;
  edgeListInitialSize?: number;
  bidirectional?: boolean;
  commitEvery?: number;
  expectedEdgeCount?: number;
  commitRetries?: number;
  commitRetryDelayMs?: number;
  vertexBatchSize?: number;
  expectedVertexCount?: number;
  expectedRecords?: number;
  ordinalBase?: number;
  idMapping?: string;
  refMode?: string;
}

export interface BatchLoadArgs {
  vertices?: Iterable<VertexRow>;
  edges?: Iterable<EdgeRow>;
  options?: BatchOptions;
}

const PATH = "/api/v1/batch/{database}" as const;

/**
 * openapi-fetch JSON-serializes a request body by default (`JSON.stringify`), which would quote
 * the already-serialized ndjson payload as a single JSON string instead of sending it verbatim.
 * `bodySerializer` overrides that per-request, so the body reaches `fetch` (and the wire) exactly
 * as `serializeRows` produced it, while everything else about the request - base URL, auth
 * middleware, `ArcadeDBError` mapping - keeps riding the same generated client. See
 * `facade/stream.ts`'s doc comment for why a second transport is not the alternative.
 */
function requestInit(args: BatchLoadArgs, database: string, accept?: string) {
  return {
    params: { path: { database }, query: (args.options ?? {}) as Record<string, never> },
    body: serializeRows(args.vertices ?? [], args.edges ?? []) as unknown as never,
    bodySerializer: (body: unknown) => body as BodyInit,
    headers: { "Content-Type": "application/x-ndjson", ...(accept ? { Accept: accept } : {}) },
  };
}

export async function batchLoad(client: RawClient, database: string, args: BatchLoadArgs): Promise<BatchSummary> {
  const { data, error, response } = await client.POST(PATH, requestInit(args, database));
  if (!response.ok) throw ArcadeDBError.fromResponse(response, error);
  return data as BatchSummary;
}

/**
 * D6: the two error channels collapse into one throw.
 *
 * A load that fails BEFORE the first acknowledgement answers with a real HTTP status and the
 * buffered error body, because the status line has not been sent yet. A load that fails AFTER
 * the first progress line cannot do that - the status line is already on the wire and cannot be
 * taken back - so the failure arrives in band, under a 200, carrying the status the buffered
 * encoding would have used. Both raise `ArcadeDBError` here, so a caller's `for await` fails
 * identically whichever channel the failure used; when the failure happened is the only
 * difference between them, and it is not something a caller can act on.
 *
 * `statusMapped: false` means `status` is an unclassified 500 fallback rather than the status the
 * buffered encoding would have chosen - the contract says to key on `exception` there, so the
 * thrown error carries it and `detail` records why.
 */
async function* raiseOnErrorEvent(events: AsyncGenerator<NdJsonBatchEvent>): AsyncGenerator<NdJsonBatchEvent> {
  for await (const event of events) {
    if (event.error !== undefined) {
      const { status, statusMapped, error: message, exception } = event.error;
      throw new ArcadeDBError(status ?? 500, {
        error: message ?? "the batch load reported an error",
        exception,
        detail: statusMapped === false ? "status is an unclassified fallback; key on exception" : undefined,
      });
    }
    yield event;
  }
}

export async function* batchLoadStream(
  client: RawClient,
  database: string,
  args: BatchLoadArgs,
): AsyncGenerator<NdJsonBatchEvent> {
  const { error, data, response } = await client.POST(PATH, {
    ...requestInit(args, database, "application/x-ndjson"),
    parseAs: "stream",
  });
  if (!response.ok) throw ArcadeDBError.fromResponse(response, error);
  if (data == null) return;
  yield* raiseOnErrorEvent(decodeNdJson<NdJsonBatchEvent>(data));
}
