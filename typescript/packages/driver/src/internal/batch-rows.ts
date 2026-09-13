/**
 * Turning structured rows into ArcadeDB's GraphBatch ndjson line format.
 *
 * The line format is NOT in the OpenAPI contract - all three request media types are declared
 * `{"type": "string"}` with a one-line description. It was established against a live
 * 26.10.1-SNAPSHOT server and reported upstream as ArcadeData/arcadedb#7570:
 *
 *     {"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}
 *     {"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}
 *
 * Two properties of this function are load-bearing rather than stylistic:
 *
 * 1. **Properties are flattened beside the control keys, never nested.** The gRPC sibling
 *    `GraphBatchRecord` has a `properties` map field, so nesting is the natural guess - and the
 *    server ACCEPTS it, answers 200 with correct counters, and stores a property literally named
 *    `properties` holding the map. Nothing fails until someone queries for a field that is not
 *    there. Taking `properties` as its own object in the row type and flattening it here means a
 *    caller cannot produce that payload.
 * 2. **Every vertex is emitted before any edge.** The server resolves an edge's `@from`/`@to`
 *    against temp ids declared earlier in the SAME payload only, and answers 400 otherwise. Since
 *    a batch is not atomic, that 400 can arrive after earlier chunks have durably committed, and
 *    retrying duplicates them. Vertices and edges arrive as separate arguments precisely so the
 *    wrong order cannot be expressed.
 *
 * The whole payload is materialized as one string. The request body is streamed to the server
 * either way, so this costs a caller memory only for the payload they already hold; a caller whose
 * payload does not fit in memory needs a different design, and should be told that rather than be
 * handed a client that pretends otherwise.
 */

/** A vertex to create. `properties` are the record's own fields; `id` is a temporary id an edge in the same call can reference. */
export interface VertexRow {
  /** The vertex type name, e.g. `"Person"`. Sent as `@class`. */
  type: string;
  /** Optional temporary id, referenced by an edge's `from`/`to` in the same call and returned in the summary's `idMapping`. Vertices without one are counted in `verticesWithoutId`. */
  id?: string;
  properties?: Record<string, unknown>;
}

/** An edge to create, referencing vertices by temporary id or by RID. */
export interface EdgeRow {
  /** The edge type name, e.g. `"Knows"`. Sent as `@class`. */
  type: string;
  /** Source: a temp id declared by a vertex in this same call, or a literal `#bucket:position` RID. */
  from: string;
  /** Target: same rules as `from`. */
  to: string;
  properties?: Record<string, unknown>;
}

function line(control: Record<string, string>, properties: Record<string, unknown> | undefined): string {
  return `${JSON.stringify({ ...control, ...properties })}\n`;
}

export function serializeRows(vertices: Iterable<VertexRow>, edges: Iterable<EdgeRow>): string {
  let out = "";
  for (const v of vertices) {
    const control: Record<string, string> = { "@type": "vertex", "@class": v.type };
    if (v.id !== undefined) control["@id"] = v.id;
    out += line(control, v.properties);
  }
  for (const e of edges) {
    out += line({ "@type": "edge", "@class": e.type, "@from": e.from, "@to": e.to }, e.properties);
  }
  return out;
}
