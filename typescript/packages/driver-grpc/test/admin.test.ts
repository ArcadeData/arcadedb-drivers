import { describe, expect, it, vi } from "vitest";
import { createClient as createConnectClient } from "@connectrpc/connect";
import type { Interceptor } from "@connectrpc/connect";
import { createGrpcTransport } from "@connectrpc/connect-node";
import { bearerAuth, createClient, passwordAuth } from "../src/index.js";

// `createClient` (from `@connectrpc/connect`) and `createGrpcTransport` (from
// `@connectrpc/connect-node`) are wrapped in `vi.fn(actual)` rather than stubbed out:
// every call still runs the real implementation, so the rest of this file's assertions
// exercise real behaviour. Only the call COUNT and call ARGUMENTS are inspected - the
// property under test is "how many transports/clients did `createClient` build and from
// what", which cannot be observed by asking a `Client` object what transport it was
// built from (Connect exposes no such introspection).
vi.mock("@connectrpc/connect", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@connectrpc/connect")>();
  return { ...actual, createClient: vi.fn(actual.createClient) };
});

vi.mock("@connectrpc/connect-node", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@connectrpc/connect-node")>();
  return { ...actual, createGrpcTransport: vi.fn(actual.createGrpcTransport) };
});

describe("rawAdmin", () => {
  it("throws for a plaintext-password auth over a non-TLS baseUrl, exactly as it did before rawAdmin existed", () => {
    // Pins that exposing a second stub did not move the #5048 guard. The guard runs
    // BEFORE any client (or transport) is constructed, so there is no `rawAdmin` for a
    // caller to fall back on when this throws - the only way to reach the admin service
    // insecurely would be building a second transport by hand, which is exactly the
    // hazard this task closes off.
    expect(() =>
      createClient({ baseUrl: "http://example.com:50051", auth: passwordAuth("root", "pw") }),
    ).toThrow(/insecure/i);
  });

  it("exposes the generated Connect client for the admin service, distinct from raw", () => {
    const client = createClient({ baseUrl: "https://example.com:50051" });

    expect(typeof client.rawAdmin.ping).toBe("function");
    expect(typeof client.rawAdmin.createApiToken).toBe("function");
    expect(client.rawAdmin).not.toBe(client.raw);
  });

  it("builds raw and rawAdmin from exactly one transport, not two", () => {
    // The property that matters: a test only checking that both `raw` and `rawAdmin`
    // exist would pass just as well against an implementation that built a SECOND
    // transport for `rawAdmin` - which is precisely the #5048 bypass this task exists to
    // rule out. Asserting `createGrpcTransport` ran once, and that both `createClient`
    // calls received the SAME transport argument, is what actually rules that out.
    vi.mocked(createConnectClient).mockClear();
    vi.mocked(createGrpcTransport).mockClear();

    const client = createClient({ baseUrl: "https://example.com:50051" });

    expect(createGrpcTransport).toHaveBeenCalledTimes(1);
    expect(createConnectClient).toHaveBeenCalledTimes(2);

    const transportArgs = vi.mocked(createConnectClient).mock.calls.map((call) => call[1]);
    expect(transportArgs[0]).toBe(transportArgs[1]);
    expect(transportArgs[0]).toBe(vi.mocked(createGrpcTransport).mock.results[0]?.value);

    // Sanity: the two returned clients are still the distinct objects the test above
    // already checked, built from that one shared transport.
    expect(client.raw).not.toBe(client.rawAdmin);
  });

  it("routes an auth interceptor's metadata to an admin RPC, not only a data-plane one", async () => {
    // `test/auth.test.ts` asserts `bearerAuth`/`passwordAuth` mutate `header` when run
    // directly against a fake `UnaryRequest`. This does the same thing one layer out:
    // it runs the SAME interceptor through the real transport's interceptor chain,
    // triggered by an admin-service call (`rawAdmin.ping`) rather than a data-plane one,
    // and confirms the header still gets set. The call itself is expected to reject -
    // there is no real server at this baseUrl - but the interceptor's synchronous header
    // mutation runs before the (failing) network attempt, which is all this needs.
    const seen: { url: string; authorization: string | null }[] = [];
    const spyAuth: Interceptor = (next) => async (req) => {
      const authed = bearerAuth("t0ken")(next);
      try {
        return await authed(req);
      } finally {
        seen.push({ url: req.url, authorization: req.header.get("authorization") });
      }
    };

    // `insecure: true`: this test is about interceptor wiring, not the insecure-channel
    // guard below - which would otherwise fire on this http:// baseUrl before `rawAdmin`
    // could even be read.
    const client = createClient({ baseUrl: "http://127.0.0.1:1", auth: spyAuth, insecure: true });

    await expect(client.rawAdmin.ping({})).rejects.toThrow();

    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toContain("ArcadeDbAdminService");
    expect(seen[0]?.authorization).toBe("Bearer t0ken");
  });
});

describe("rawAdmin's insecure-channel guard", () => {
  // 42 of ArcadeDbAdminService's 44 RPCs carry `DatabaseCredentials` inside the request
  // message rather than authenticating from the transport's interceptor metadata - so the
  // #5048-style hazard here is a request BODY travelling in cleartext, not anything the
  // auth interceptor does. This guard is therefore unconditional on `auth`: it fires (or
  // not) purely from `baseUrl`'s scheme and `insecure`, unlike the plaintext-password guard
  // above, which additionally requires `passwordAuth`.

  it("throws on ACCESS (not at createClient) for a non-TLS baseUrl without insecure: true", () => {
    const client = createClient({ baseUrl: "http://example.com:50051" });

    // Construction itself must not throw - see the "raw still works" test below for why.
    expect(() => client.rawAdmin).toThrow(/insecure/i);
  });

  it("names the remedy in the thrown message", () => {
    const client = createClient({ baseUrl: "http://example.com:50051" });

    expect(() => client.rawAdmin).toThrow(/https:\/\/ baseUrl|insecure: true/);
  });

  it("permits rawAdmin over a non-TLS baseUrl when insecure: true is passed explicitly", () => {
    const client = createClient({ baseUrl: "http://example.com:50051", insecure: true });

    expect(() => client.rawAdmin).not.toThrow();
    expect(typeof client.rawAdmin.ping).toBe("function");
  });

  it("permits rawAdmin over a TLS baseUrl without needing insecure: true", () => {
    const client = createClient({ baseUrl: "https://example.com:50051" });

    expect(() => client.rawAdmin).not.toThrow();
  });

  it("throws for a schemeless baseUrl (M7's protocol trap applies to rawAdmin too)", () => {
    // `new URL("localhost:50051").protocol` evaluates to "localhost:", not "https:" - see
    // `test/index.test.ts`'s twin test for the plaintext-password guard. `rawAdmin`'s guard
    // reuses the same `!== "https:"` comparison, so it fails closed here too.
    const client = createClient({ baseUrl: "localhost:50051" });

    expect(() => client.rawAdmin).toThrow(/insecure/i);
  });

  it("leaves raw working over an insecure channel with no auth at all - the over-guarding regression check", () => {
    // The guard above must be scoped to `rawAdmin` alone. A caller who never touches the
    // admin service must not start failing because they built a client over plain HTTP for
    // the data plane - that would be a worse regression than the gap this guard closes.
    const client = createClient({ baseUrl: "http://example.com:50051" });

    expect(() => client.raw).not.toThrow();
    expect(typeof client.raw.executeCommand).toBe("function");
  });
});
