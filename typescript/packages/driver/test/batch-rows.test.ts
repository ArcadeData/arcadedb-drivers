import { describe, expect, it } from "vitest";
import { serializeRows } from "../src/internal/batch-rows.js";

const lines = (s: string) => s.split("\n").filter((l) => l !== "").map((l) => JSON.parse(l));

describe("serializeRows", () => {
  it("flattens properties beside the control keys, never nested", () => {
    // The whole point of the structured row type. The server ACCEPTS a nested
    // `properties` object and stores a property literally called "properties",
    // answering 200 with correct counters - silent data corruption. See the spec's
    // section 3 and ArcadeData/arcadedb#7570.
    const [row] = lines(serializeRows([{ type: "Person", id: "p1", properties: { name: "Alice" } }], []));
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", "@id": "p1", name: "Alice" });
    expect(row).not.toHaveProperty("properties");
  });

  it("emits every vertex before any edge", () => {
    // Not cosmetic: the server resolves an edge's @from/@to only against temp ids
    // declared EARLIER in the same payload, and answers 400 otherwise - possibly
    // after earlier chunks have already committed.
    const out = lines(
      serializeRows(
        [{ type: "Person", id: "a" }, { type: "Person", id: "b" }],
        [{ type: "Knows", from: "a", to: "b" }],
      ),
    );
    expect(out.map((r) => r["@type"])).toEqual(["vertex", "vertex", "edge"]);
  });

  it("omits @id when a vertex has no id", () => {
    const [row] = lines(serializeRows([{ type: "Person", properties: { name: "Anon" } }], []));
    expect(row).not.toHaveProperty("@id");
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", name: "Anon" });
  });

  it("omits @id when a vertex's id is explicitly undefined", () => {
    // Sibling parity: `_internal/batch_rows.py` tests `if "id" in vertex`, so a row spelled
    // `{"id": None}` there emits `"@id": null` unless it treats an explicit None as absent too.
    // Pin the TypeScript side of that parity here: `{ id: undefined }` must behave exactly like
    // an omitted `id` key, not like an empty string.
    const [row] = lines(serializeRows([{ type: "Person", id: undefined, properties: { name: "Anon" } }], []));
    expect(row).not.toHaveProperty("@id");
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", name: "Anon" });
  });

  it("serializes edge endpoints and properties", () => {
    const [row] = lines(serializeRows([], [{ type: "Knows", from: "a", to: "#1:7", properties: { since: 2020 } }]));
    expect(row).toEqual({ "@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7", since: 2020 });
  });

  it("terminates every line with a newline, including the last", () => {
    // A body whose final line has no terminator is a body that ends before its
    // announced length: the server answers 408, never a 200 with a short count.
    const out = serializeRows([{ type: "Person" }], [{ type: "Knows", from: "a", to: "b" }]);
    expect(out.endsWith("\n")).toBe(true);
    expect(out.split("\n").filter((l) => l !== "")).toHaveLength(2);
  });

  it("produces an empty string for no rows", () => {
    expect(serializeRows([], [])).toBe("");
  });

  it("lets a property named like a control key through untouched", () => {
    // Properties live in their own object in our type, so a property called
    // "type" or "from" cannot collide with a control field. This is the second
    // reason for the structured row shape (spec D2).
    const [row] = lines(serializeRows([{ type: "Person", properties: { type: "civilian", from: "Rome" } }], []));
    expect(row).toEqual({ "@type": "vertex", "@class": "Person", type: "civilian", from: "Rome" });
  });
});
