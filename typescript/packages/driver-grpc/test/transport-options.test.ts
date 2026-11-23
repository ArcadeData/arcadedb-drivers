import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GrpcTransportOptions } from "@connectrpc/connect-node";
import type { Interceptor } from "@connectrpc/connect";

/**
 * `createClient`'s `transport` option (issue #200). `createGrpcTransport` is replaced by a spy that
 * still builds the real transport, so these tests read exactly the options `createClient` handed
 * it, and the client they return is still a working one.
 */
const captured: GrpcTransportOptions[] = [];
vi.mock("@connectrpc/connect-node", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@connectrpc/connect-node")>();
  return {
    ...actual,
    createGrpcTransport: (options: GrpcTransportOptions) => {
      captured.push(options);
      return actual.createGrpcTransport(options);
    },
  };
});

const { Http2SessionManager } = await import("@connectrpc/connect-node");
const { bearerAuth, createClient, passwordAuth } = await import("../src/index.js");

const passthrough: Interceptor = (next) => (req) => next(req);

beforeEach(() => {
  captured.length = 0;
});

describe("createClient transport options", () => {
  it("builds the transport exactly as before when transport is omitted", () => {
    createClient({ baseUrl: "https://example.com:50051" });

    expect(captured).toEqual([{ baseUrl: "https://example.com:50051", interceptors: [] }]);
  });

  it("passes nodeOptions, timeouts and limits through to createGrpcTransport", () => {
    const ca = "-----BEGIN CERTIFICATE-----\n...";
    createClient({
      baseUrl: "https://example.com:50051",
      transport: { nodeOptions: { ca }, defaultTimeoutMs: 5_000, idleConnectionTimeoutMs: 1_000, readMaxBytes: 1024 },
    });

    expect(captured[0]).toMatchObject({
      baseUrl: "https://example.com:50051",
      nodeOptions: { ca },
      defaultTimeoutMs: 5_000,
      idleConnectionTimeoutMs: 1_000,
      readMaxBytes: 1024,
    });
  });

  it("adds the caller's interceptors before auth, so auth stays and runs innermost", () => {
    const auth = bearerAuth("AU-x");
    createClient({ baseUrl: "https://example.com:50051", auth, transport: { interceptors: [passthrough] } });

    expect(captured[0].interceptors).toEqual([passthrough, auth]);
  });

  it("keeps the caller's interceptors when there is no auth", () => {
    createClient({ baseUrl: "https://example.com:50051", transport: { interceptors: [passthrough] } });

    expect(captured[0].interceptors).toEqual([passthrough]);
  });

  it("ignores a baseUrl or sessionManager smuggled past the type at run time", () => {
    const sessionManager = new Http2SessionManager("http://elsewhere.example:50051");
    createClient({
      baseUrl: "https://example.com:50051",
      transport: { baseUrl: "http://elsewhere.example:50051", sessionManager } as never,
    });

    expect(captured[0].baseUrl).toBe("https://example.com:50051");
    expect(captured[0]).not.toHaveProperty("sessionManager");
    sessionManager.abort();
  });

  it("does not let transport options weaken the plaintext-password guard", () => {
    expect(() =>
      createClient({
        baseUrl: "http://example.com:50051",
        auth: passwordAuth("root", "pw"),
        transport: { nodeOptions: {} },
      }),
    ).toThrow(/insecure/i);
  });

  it("does not let transport options unlock rawAdmin over a non-TLS baseUrl", () => {
    const client = createClient({ baseUrl: "http://example.com:50051", transport: { defaultTimeoutMs: 1 } });

    expect(() => client.rawAdmin).toThrow(/insecure/i);
  });
});
