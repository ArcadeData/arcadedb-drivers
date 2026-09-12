import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ArcadeDbAdminService } from "../src/gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";

const README_PATH = fileURLToPath(new URL("../README.md", import.meta.url));
const MARKER_BEGIN = "<!-- admin-rpcs:begin -->";
const MARKER_END = "<!-- admin-rpcs:end -->";

/**
 * Every backtick-delimited token between the two markers in the README is one RPC name of
 * `ArcadeDbAdminService` (see the README's "The 44 RPCs" section) - group labels in the table's
 * first column are deliberately left unbackticked so this needs no Markdown table parser, just
 * this one regex.
 */
function documentedAdminRpcNames(): string[] {
  const readme = readFileSync(README_PATH, "utf8");
  const begin = readme.indexOf(MARKER_BEGIN);
  const end = readme.indexOf(MARKER_END);
  if (begin === -1 || end === -1 || end < begin) {
    throw new Error(`README.md is missing the admin-rpcs markers (${MARKER_BEGIN} / ${MARKER_END})`);
  }
  return [...readme.slice(begin, end).matchAll(/`([A-Za-z]+)`/g)].map((match) => match[1] as string);
}

/**
 * The admin stub's own RPC names, read from the GENERATED schema object rather than the `.proto`
 * contract: the point of this guard is that a contract bump regenerates `ArcadeDbAdminService`
 * and the README can then disagree with what actually got generated. Reading the `.proto` instead
 * would let the guard pass through a bump that changed the proto but, for whatever reason, never
 * reached the generated stub.
 */
function generatedAdminRpcNames(): string[] {
  return Object.values(ArcadeDbAdminService.method).map((method) => method.name);
}

describe("README's admin-rpcs enumeration", () => {
  it("documents exactly the generated stub's RPCs - no missing, no extra names", () => {
    const documented = documentedAdminRpcNames();
    const generated = generatedAdminRpcNames();
    const documentedSet = new Set(documented);
    const generatedSet = new Set(generated);

    const missing = generated.filter((name) => !documentedSet.has(name));
    const extra = documented.filter((name) => !generatedSet.has(name));

    expect(missing, `README is missing these RPCs: ${missing.join(", ") || "(none)"}`).toEqual([]);
    expect(extra, `README documents RPCs that don't exist on the generated stub: ${extra.join(", ") || "(none)"}`).toEqual(
      [],
    );
  });

  it("lists each RPC exactly once", () => {
    const documented = documentedAdminRpcNames();
    const duplicates = documented.filter((name, index) => documented.indexOf(name) !== index);
    expect(duplicates, `README lists these RPCs more than once: ${duplicates.join(", ")}`).toEqual([]);
  });

  it("documents all 44 RPCs (the count the README's own prose promises)", () => {
    expect(generatedAdminRpcNames()).toHaveLength(44);
  });
});
