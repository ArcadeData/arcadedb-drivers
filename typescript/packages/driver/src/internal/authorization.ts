import type { Middleware } from "openapi-fetch";

/**
 * The `Authorization` value the client's auth middleware would put on a request. `auth` is an
 * openapi-fetch middleware, opaque by design, so it is asked the only way it can be: by running it
 * on a throwaway request and reading the header it sets. Used by the `/ws` insert session, which
 * cannot run middleware, and by `logout`, which must know whether the client presents a session
 * token before it sends anything.
 */
export async function resolveAuthorization(
  auth: Middleware | undefined,
  httpUrl: string,
  schemaPath: string,
  id: string,
): Promise<string | undefined> {
  if (!auth?.onRequest) return undefined;
  const probe = new Request(httpUrl);
  const result = (await auth.onRequest({
    request: probe,
    schemaPath,
    params: {},
    id,
    options: {},
  } as unknown as Parameters<NonNullable<Middleware["onRequest"]>>[0])) as unknown;
  const request = result instanceof Request ? result : probe;
  return request.headers.get("Authorization") ?? undefined;
}
