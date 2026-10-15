import type { Client, Middleware } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { NotSessionTokenError } from "../errors.js";
import { resolveAuthorization } from "../internal/authorization.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/** Starts every token `POST /api/v1/login` issues ("AU-<server name>-<uuid>"). An API token starts with "at-". */
const SESSION_TOKEN_PREFIX = "AU-";

const TOKEN_HASH = /^[0-9a-f]{64}$/;

/**
 * What `login` and `loginAs` return. `token` is the session token, prefixed `AU-`; present it with
 * `withToken`. It is a credential: anyone holding it acts as `user` until it is logged out or
 * expires.
 */
export interface LoginResult {
  token: string;
  user: string;
}

/**
 * One authentication session as `listSessions` returns it. These are the server's login sessions,
 * not the transaction sessions `transaction()` opens.
 */
export interface Session {
  /** The session's live bearer token, a credential in its own right. */
  token: string;
  user: string;
  /**
   * The cluster node that issued the session when this node holds a copy of it; `undefined` for a
   * session this node issued.
   */
  issuer: string | undefined;
  createdAt: Date;
  lastUpdate: Date;
  /** Milliseconds since the session was last used, as the server measured it. */
  elapsedMs: number;
  /** `null` when the server has none. */
  sourceIp: string | null;
  userAgent: string | null;
  /** `country` and `city` are only known behind a proxy that reports them; `null` otherwise. */
  country: string | null;
  city: string | null;
}

/** Options for `createAPIToken`. */
export interface CreateAPITokenOptions {
  /** Scopes the token to one database. Omitted, the token covers `"*"`, every database. */
  database?: string;
  /**
   * When the token stops authenticating. Omitted, it never expires. It must be a valid date after
   * the Unix epoch: the server reads an expiry of 0 as "never".
   */
  expiresAt?: Date;
  /** Takes the shape a group's `types` map takes (see `saveGroup`). Omitted, none is granted. */
  permissions?: Record<string, unknown>;
}

/** One issued API token, as metadata: the server keeps only the hash, so the token itself is never listed. */
export interface APIToken {
  name: string;
  database: string;
  createdAt: Date;
  /** `null` for a token that never expires. */
  expiresAt: Date | null;
  /**
   * Only reported by `listAPITokens`; `createAPIToken` always returns `false`. An expired token
   * authenticates nobody, but stays listed until the next token change retires it.
   */
  expired: boolean;
  permissions: Record<string, unknown>;
  /** The SHA-256 hex of the token, and the argument `deleteAPIToken` takes. */
  tokenHash: string;
  /** The token's last characters, to tell two entries apart. */
  tokenSuffix: string;
}

/** What `createAPIToken` returns: the token's metadata and, this once, the token itself. */
export interface CreatedAPIToken extends APIToken {
  /**
   * The plaintext token, prefixed `at-`. The server stores only its hash, so this is the only time
   * it can be read: store it before dropping this value. This client never logs or keeps it.
   */
  token: string;
}

type TokenFields = components["schemas"]["ApiTokenList"]["result"][number];

function apiToken(t: TokenFields): APIToken {
  return {
    name: t.name,
    database: t.database,
    createdAt: new Date(t.createdAt),
    expiresAt: t.expiresAt ? new Date(t.expiresAt) : null,
    expired: t.expired === true,
    permissions: t.permissions ?? {},
    tokenHash: t.tokenHash,
    tokenSuffix: t.tokenSuffix,
  };
}

export async function login(client: RawClient): Promise<LoginResult> {
  const data = await unwrap(client.POST("/api/v1/login", {}));
  return { token: data.token, user: data.user };
}

/** Throws `NotSessionTokenError`, unsent, unless `auth` presents a session token from `login`. */
export async function logout(client: RawClient, auth: Middleware | undefined, baseUrl: string): Promise<void> {
  const authorization = await resolveAuthorization(auth, baseUrl, "/api/v1/logout", "logout");
  if (!authorization?.startsWith(`Bearer ${SESSION_TOKEN_PREFIX}`)) {
    throw new NotSessionTokenError();
  }
  await unwrap(client.POST("/api/v1/logout", {}));
}

export async function listSessions(client: RawClient): Promise<Session[]> {
  const data = await unwrap(client.GET("/api/v1/sessions", {}));
  return (data?.result ?? []).map((s) => ({
    token: s.token,
    user: s.user,
    issuer: s.issuer,
    createdAt: new Date(s.createdAt),
    lastUpdate: new Date(s.lastUpdate),
    elapsedMs: s.elapsedMs,
    sourceIp: s.sourceIp ?? null,
    userAgent: s.userAgent ?? null,
    country: s.country ?? null,
    city: s.city ?? null,
  }));
}

/** Throws `RangeError`, unsent, for an `expiresAt` that is not a valid date after the Unix epoch. */
export async function createAPIToken(
  client: RawClient,
  name: string,
  opts: CreateAPITokenOptions,
): Promise<CreatedAPIToken> {
  const body: components["schemas"]["CreateApiTokenRequest"] = { name };
  if (opts.database !== undefined) body.database = opts.database;
  if (opts.expiresAt !== undefined) {
    const ms = opts.expiresAt.getTime();
    if (!(ms > 0)) {
      throw new RangeError("expiresAt must be a valid date after the Unix epoch");
    }
    body.expiresAt = ms;
  }
  if (opts.permissions !== undefined) body.permissions = opts.permissions;
  const data = await unwrap(client.POST("/api/v1/server/api-tokens", { body }));
  return { ...apiToken(data.result), token: data.result.token };
}

export async function listAPITokens(client: RawClient): Promise<APIToken[]> {
  const data = await unwrap(client.GET("/api/v1/server/api-tokens", {}));
  return (data?.result ?? []).map(apiToken);
}

/**
 * Throws `RangeError`, unsent, unless `tokenHash` is 64 lowercase hexadecimal characters. The
 * argument travels in the query string, which proxies and access logs record, and the likeliest
 * mistake is passing the plaintext token itself, so the error does not repeat it.
 */
export async function deleteAPIToken(client: RawClient, tokenHash: string): Promise<void> {
  if (typeof tokenHash !== "string" || !TOKEN_HASH.test(tokenHash)) {
    throw new RangeError("not an API token hash: want the 64-character SHA-256 hex tokenHash, never the token itself");
  }
  await unwrap(client.DELETE("/api/v1/server/api-tokens", { params: { query: { token: tokenHash } } }));
}
