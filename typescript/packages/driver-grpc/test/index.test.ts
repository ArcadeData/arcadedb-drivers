import { describe, expect, it } from "vitest";
import { StreamQueryRequest_RetrievalMode, bearerAuth, createClient, passwordAuth } from "../src/index.js";

describe("createClient", () => {
  it("exposes the generated Connect client as raw", () => {
    const client = createClient({ baseUrl: "https://example.com:50051" });

    expect(typeof client.raw.executeCommand).toBe("function");
    expect(typeof client.raw.streamQuery).toBe("function");
  });

  it("exposes streamQuery, insertStream, and transaction on the client itself, not only via raw", () => {
    const client = createClient({ baseUrl: "https://example.com:50051" });

    expect(typeof client.streamQuery).toBe("function");
    expect(typeof client.insertStream).toBe("function");
    expect(typeof client.transaction).toBe("function");
  });

  it("re-exports RetrievalMode as a runtime value, so a caller never has to pass a bare number", () => {
    // The README tells callers to choose between CURSOR, MATERIALIZE_ALL and PAGED, and this is
    // an enum - a RUNTIME value, not a type. Without the re-export the only way to name one is a
    // deep import into the version-stamped generated file, which the package `exports` map
    // blocks. A `export type`-only re-export would compile and leave this undefined at runtime.
    expect(typeof StreamQueryRequest_RetrievalMode.CURSOR).toBe("number");
    expect(StreamQueryRequest_RetrievalMode.MATERIALIZE_ALL).not.toBe(StreamQueryRequest_RetrievalMode.CURSOR);
  });

  it("does not throw for an https:// baseUrl with passwordAuth", () => {
    expect(() => createClient({ baseUrl: "https://example.com:50051", auth: passwordAuth("root", "pw") })).not.toThrow();
  });

  it("does not throw for an http:// baseUrl with bearerAuth (not a plaintext password)", () => {
    expect(() => createClient({ baseUrl: "http://example.com:50051", auth: bearerAuth("AU-x") })).not.toThrow();
  });

  it("does not throw for an http:// baseUrl with no auth at all", () => {
    expect(() => createClient({ baseUrl: "http://example.com:50051" })).not.toThrow();
  });

  it("throws when passwordAuth is paired with an http:// baseUrl without opting in", () => {
    // Also pins that exposing `rawAdmin` did not move this #5048 guard. The guard runs
    // BEFORE any client (or transport) is constructed, so there is no `rawAdmin` for a
    // caller to fall back on when this throws - the only way to reach the admin service
    // insecurely would be building a second transport by hand, which is exactly the
    // hazard this task closes off.
    expect(() => createClient({ baseUrl: "http://example.com:50051", auth: passwordAuth("root", "pw") })).toThrow(/insecure/i);
  });

  it("permits an http:// baseUrl with passwordAuth when insecure: true is passed explicitly", () => {
    expect(() =>
      createClient({ baseUrl: "http://example.com:50051", auth: passwordAuth("root", "pw"), insecure: true }),
    ).not.toThrow();
  });

  it("throws for a schemeless baseUrl with passwordAuth (M7)", () => {
    // `new URL("localhost:50051")` parses successfully with protocol "localhost:", not "http:" -
    // a strict `=== "http:"` check would silently skip the refusal for exactly the kind of
    // schemeless baseUrl a caller who forgot the scheme would write. The guard must be
    // `!== "https:"`, which also refuses this.
    expect(() => createClient({ baseUrl: "localhost:50051", auth: passwordAuth("root", "pw") })).toThrow(/insecure/i);
  });
});
