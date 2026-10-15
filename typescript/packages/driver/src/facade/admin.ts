import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/** One server user, as `listUsers` returns it. The password hash is never returned. */
export type ServerUser = components["schemas"]["UserList"]["result"][number];

/** One security group's definition, as `listGroups` returns it. */
export type GroupDefinition = components["schemas"]["GroupDefinition"];

/**
 * Database assignments: a database name, or `"*"` for every database, mapped to the groups the
 * user holds there.
 */
export type UserDatabases = Record<string, string[]>;

/** Options for `createUser`. */
export interface CreateUserOptions {
  /** Database assignments. Omitted, no assignment is sent. */
  databases?: UserDatabases;
}

/** What `updateUser` changes. An omitted field is not sent, and the server keeps that value. */
export interface UpdateUserOptions {
  password?: string;
  /** Replaces the user's assignments. An empty object is sent, and removes them all. */
  databases?: UserDatabases;
}

/** What `saveGroup` sets on the group. An omitted field is not sent. */
export type SaveGroupOptions = Omit<components["schemas"]["SaveGroupRequest"], "database" | "name">;

/**
 * Throws `RangeError` for a name the server would silently change: it trims the name it reads out
 * of `create database <name>`, so " db" would create or drop "db" rather than the database named.
 * An empty name is refused too.
 */
function checkDatabaseName(name: string): void {
  if (name === "" || name.trim() !== name) {
    throw new RangeError(`database name ${JSON.stringify(name)} is empty or has leading or trailing white space`);
  }
}

export async function serverCommand(client: RawClient, command: string): Promise<Record<string, unknown>> {
  // "language" is required by the contract's CommandRequest; the server ignores it here. The 200
  // body is typed as QueryResponse, which an administrative command's {"result": "ok"} does not
  // match - openapi-fetch does not validate, so the parsed body is returned as what it is.
  const data: unknown = await unwrap(client.POST("/api/v1/server", { body: { command, language: "sql" } }));
  return data as Record<string, unknown>;
}

export async function databaseCommand(client: RawClient, verb: "create" | "drop", name: string): Promise<void> {
  checkDatabaseName(name);
  await serverCommand(client, `${verb} database ${name}`);
}

export async function createUser(
  client: RawClient,
  name: string,
  password: string,
  opts: CreateUserOptions,
): Promise<void> {
  await unwrap(
    client.POST("/api/v1/server/users", {
      body: { name, password, ...(opts.databases !== undefined ? { databases: opts.databases } : {}) },
    }),
  );
}

export async function updateUser(client: RawClient, name: string, opts: UpdateUserOptions): Promise<void> {
  const body: components["schemas"]["UpdateUserRequest"] = {};
  if (opts.password !== undefined) body.password = opts.password;
  if (opts.databases !== undefined) body.databases = opts.databases;
  await unwrap(client.PUT("/api/v1/server/users", { params: { query: { name } }, body }));
}

export async function dropUser(client: RawClient, name: string): Promise<void> {
  await unwrap(client.DELETE("/api/v1/server/users", { params: { query: { name } } }));
}

export async function listUsers(client: RawClient): Promise<ServerUser[]> {
  const data = await unwrap(client.GET("/api/v1/server/users", {}));
  return data.result ?? [];
}

export async function saveGroup(
  client: RawClient,
  database: string,
  name: string,
  opts: SaveGroupOptions,
): Promise<void> {
  const body: components["schemas"]["SaveGroupRequest"] = { database, name };
  for (const [key, value] of Object.entries(opts) as [keyof SaveGroupOptions, unknown][]) {
    if (value !== undefined) (body as Record<string, unknown>)[key] = value;
  }
  await unwrap(client.POST("/api/v1/server/groups", { body }));
}

export async function deleteGroup(client: RawClient, database: string, name: string): Promise<void> {
  await unwrap(client.DELETE("/api/v1/server/groups", { params: { query: { database, name } } }));
}

export async function listGroups(client: RawClient): Promise<Record<string, Record<string, GroupDefinition>>> {
  const data = await unwrap(client.GET("/api/v1/server/groups", {}));
  const groups: Record<string, Record<string, GroupDefinition>> = {};
  for (const [db, entry] of Object.entries(data.result?.databases ?? {})) {
    groups[db] = entry.groups;
  }
  return groups;
}
