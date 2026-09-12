import { describe, expect, it } from "vitest";
import { createContextValues } from "@connectrpc/connect";
import type { Interceptor, UnaryRequest, UnaryResponse } from "@connectrpc/connect";
import { bearerAuth, passwordAuth } from "../src/auth.js";

type Next = Parameters<Interceptor>[0];

/** `next` for these tests never needs to do anything: assertions read the mutated `header`
 * object directly, not `next`'s return value. */
const next: Next = async () => ({}) as unknown as UnaryResponse;

/** Minimal fake `UnaryRequest`: only `header` is exercised by `bearerAuth`/`passwordAuth`, so
 * every other field is an inert placeholder. */
function fakeRequest(header: Headers): UnaryRequest {
  return {
    stream: false,
    header,
    signal: new AbortController().signal,
    contextValues: createContextValues(),
  } as unknown as UnaryRequest;
}

describe("bearerAuth", () => {
  it("sets authorization to Bearer <token>", async () => {
    const header = new Headers();
    const interceptor = bearerAuth("AU-x");

    await interceptor(next)(fakeRequest(header));

    expect(header.get("authorization")).toBe("Bearer AU-x");
  });
});

describe("passwordAuth", () => {
  it("sets x-arcade-user, x-arcade-password and x-arcade-database", async () => {
    const header = new Headers();
    const interceptor = passwordAuth("root", "pw", "mydb");

    await interceptor(next)(fakeRequest(header));

    expect(header.get("x-arcade-user")).toBe("root");
    expect(header.get("x-arcade-password")).toBe("pw");
    expect(header.get("x-arcade-database")).toBe("mydb");
  });

  it("omits x-arcade-database when database is not passed", async () => {
    const header = new Headers();
    const interceptor = passwordAuth("root", "pw");

    await interceptor(next)(fakeRequest(header));

    expect(header.get("x-arcade-user")).toBe("root");
    expect(header.get("x-arcade-password")).toBe("pw");
    expect(header.has("x-arcade-database")).toBe(false);
  });
});

/**
 * arcadedb#7309 argues server-side that a token-bearing response (`CreateApiToken`'s, in
 * particular) must be proved not to reach a log sink. On the client, both interceptors are
 * `(next) => async (req) => { ...; return next(req); }` - neither is ever handed a reason to
 * look at what `next` resolves to. A test that only greps for `console.*` would keep passing if
 * a future edit started reading a field off the response (to log it, forward it, whatever) as
 * long as it didn't literally call `console.*` to do so; wrapping the resolved value in a `Proxy`
 * that records every property access proves the stronger claim directly, against the interceptor
 * functions themselves rather than against today's absence of a logging call.
 *
 * What this does NOT prove: it says nothing about code outside these two interceptors (e.g. a
 * hypothetical logger elsewhere in the package that reads a response through a different call
 * site). See `test/no-response-logging.test.ts` for a repository-wide backstop on that.
 */
describe("response isolation", () => {
  // "then" is deliberately excluded from what counts as a read. Every promise-resolution step
  // between `next()`'s return and this test's own `await` performs `Get(value, "then")` to check
  // thenability - that happens twice here purely because this test itself chains the proxy
  // through two async functions (the fake `next` and the interceptor's own `async (req) => ...`),
  // and it would happen just the same in front of a completely inert interceptor. It is a
  // property of the JS Promise machinery, not a read of response DATA, so counting it would make
  // this test fail for a reason that has nothing to do with the property it exists to pin.
  function proxyThatRecordsAccess<T extends object>(target: T): { proxy: T; accessed: PropertyKey[] } {
    const accessed: PropertyKey[] = [];
    const proxy = new Proxy(target, {
      get(t, prop, receiver) {
        if (prop !== "then") accessed.push(prop);
        return Reflect.get(t, prop, receiver);
      },
    });
    return { proxy, accessed };
  }

  it("bearerAuth never reads a property of the response next() resolves to", async () => {
    const { proxy, accessed } = proxyThatRecordsAccess({ token: "s3cr3t" } as unknown as UnaryResponse);
    const passthrough: Next = async () => proxy;

    const result = await bearerAuth("t0ken")(passthrough)(fakeRequest(new Headers()));

    expect(result).toBe(proxy);
    expect(accessed).toEqual([]);
  });

  it("passwordAuth never reads a property of the response next() resolves to", async () => {
    const { proxy, accessed } = proxyThatRecordsAccess({ token: "s3cr3t" } as unknown as UnaryResponse);
    const passthrough: Next = async () => proxy;

    const result = await passwordAuth("root", "pw")(passthrough)(fakeRequest(new Headers()));

    expect(result).toBe(proxy);
    expect(accessed).toEqual([]);
  });
});
