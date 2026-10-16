import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ArcadeDBError, basicAuth, createClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";
import { unwrap } from "../packages/driver/src/internal/unwrap.js";

// Mirrors `Issue7403RemoteInsertSessionIT` in ArcadeData/arcadedb, the Java client's own IT: the same
// scenarios against the same server setting (`wsMaxInsertChunkRows` = 4, low enough that a whole-chunk
// refusal is reachable without sending 100,000 rows). Uses the runtime's global `WebSocket`, which is
// why this suite needs Node >= 22 (it already needs >= 22.22 for testcontainers).
//
// Image pin and override: see `data-plane.test.ts`.
const ARCADEDB_IMAGE = process.env.ARCADEDB_DOCKER_IMAGE ?? "arcadedata/arcadedb:26.11.1-SNAPSHOT";
const ROOT_PASSWORD = "playwithdata";
const DB_NAME = "wsinsert";
const MAX_ROWS = 4;

let container: StartedTestContainer;
let server: ArcadeDBServer;

const people = (...names: string[]) => names.map((name) => ({ name }));

async function countPeople(): Promise<number> {
  const { result } = await server.db(DB_NAME).query<{ c: number }>({ language: "sql", command: "SELECT count(*) AS c FROM Person" });
  return result[0].c;
}

beforeAll(async () => {
  container = await new GenericContainer(ARCADEDB_IMAGE)
    .withEnvironment({
      JAVA_OPTS: `-Darcadedb.server.rootPassword=${ROOT_PASSWORD} -Darcadedb.server.wsMaxInsertChunkRows=${MAX_ROWS}`,
    })
    .withExposedPorts(2480)
    .withWaitStrategy(Wait.forHttp("/api/v1/ready", 2480).forStatusCodeMatching((statusCode) => statusCode === 204))
    .withStartupTimeout(60_000)
    .start();

  server = createClient({
    baseUrl: `http://${container.getHost()}:${container.getMappedPort(2480)}`,
    auth: basicAuth("root", ROOT_PASSWORD),
  });
  await unwrap(server.raw.POST("/api/v1/server", { body: { command: `create database ${DB_NAME}`, language: "sql" } }));
  await server.db(DB_NAME).command({ language: "sql", command: "CREATE DOCUMENT TYPE Person IF NOT EXISTS" });
}, 90_000);

afterAll(async () => {
  await container?.stop();
});

describe("the /ws insert session against a real server", () => {
  it("the caller commits after seeing the acknowledgements", async () => {
    const before = await countPeople();
    const seen: number[] = [];
    const session = await server.db(DB_NAME).insertSession({ targetType: "Person", onBatchAck: (a) => seen.push(a.chunkSeq) });
    try {
      expect(session.sessionId).toBeTruthy();
      expect(session.transactionMode).toBe("per_stream");
      expect((await session.sendChunk(people("a", "b"))).inserted).toBe(2);
      expect((await session.sendChunk(people("c"))).inserted).toBe(1);
      expect(seen).toEqual([1, 2]);
      // Nothing is durable until the caller says so.
      expect(await countPeople()).toBe(before);

      const committed = await session.commit();
      expect(committed.outcome).toBe("commit");
      expect(committed.summary.inserted).toBe(3);
    } finally {
      await session.close();
    }
    expect(await countPeople()).toBe(before + 3);
  });

  it("the caller can roll back after seeing the acknowledgements", async () => {
    const before = await countPeople();
    const session = await server.db(DB_NAME).insertSession({ targetType: "Person" });
    try {
      expect((await session.sendChunk(people("a", "b"))).inserted).toBe(2);
      expect((await session.rollback()).outcome).toBe("rollback");
    } finally {
      await session.close();
    }
    expect(await countPeople()).toBe(before);
  });

  it("closing without committing rolls the session back", async () => {
    const before = await countPeople();
    const session = await server.db(DB_NAME).insertSession({ targetType: "Person" });
    await session.sendChunk(people("a"));
    await session.close();
    await session.close();
    expect(await countPeople()).toBe(before);
  });

  it("joins the HTTP transaction: commit answers detached, the transaction's own commit makes the rows durable", async () => {
    const before = await countPeople();
    await server.db(DB_NAME).transaction(async (tx) => {
      const session = await tx.insertSession({ targetType: "Person", joinTransaction: true });
      try {
        expect(session.transactionMode).toBe("none");
        expect(session.transactionId).toBeTruthy();
        expect((await session.sendChunk(people("a", "b"))).inserted).toBe(2);
        const committed = await session.commit();
        expect(committed.outcome).toBe("detached");
        expect(committed.summary.externalTransaction).toBe(true);
      } finally {
        await session.close();
      }
      // The session committed nothing: only the transaction's own commit, below, does.
      expect(await countPeople()).toBe(before);
    });
    expect(await countPeople()).toBe(before + 2);
  });

  it("the transaction's rollback undoes what the joined session wrote", async () => {
    const before = await countPeople();
    await expect(
      server.db(DB_NAME).transaction(async (tx) => {
        const session = await tx.insertSession({ targetType: "Person", joinTransaction: true });
        try {
          await session.sendChunk(people("a", "b"));
          await session.commit();
        } finally {
          await session.close();
        }
        throw new Error("caller changed its mind");
      }),
    ).rejects.toThrow("caller changed its mind");
    expect(await countPeople()).toBe(before);
  });

  it("joining without an open transaction is refused", async () => {
    await expect(server.db(DB_NAME).insertSession({ joinTransaction: true })).rejects.toThrow(/no open transaction/);
  });

  it("a chunk refused as a whole is reported and the retry reuses its sequence number", async () => {
    const before = await countPeople();
    const session = await server.db(DB_NAME).insertSession({ targetType: "Person" });
    try {
      const err = await session.sendChunk(people("a", "b", "c", "d", "e")).catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ArcadeDBError);
      expect((err as ArcadeDBError).message).toContain(`more than the ${MAX_ROWS}`);
      expect(session.lastChunkSeq, "a refused chunk must not consume a sequence number").toBe(0);

      // A row the server cannot apply, by contrast, is tallied rather than refused.
      const ack = await session.sendChunk([{ name: "a" }, { "@class": "NoSuchType" }]);
      expect(ack.chunkSeq).toBe(1);
      expect(ack.inserted).toBe(1);
      expect(ack.failed).toBe(1);
      await session.commit();
    } finally {
      await session.close();
    }
    expect(await countPeople()).toBe(before + 1);
  });

  it("a per_batch chunk whose transaction fails is acknowledged as a whole-chunk failure, and replays under the same sequence", async () => {
    const db = server.db(DB_NAME);
    await db.command({ language: "sql", command: "CREATE DOCUMENT TYPE Uniq IF NOT EXISTS" });
    await db.command({ language: "sql", command: "CREATE PROPERTY Uniq.name IF NOT EXISTS STRING" });
    await db.command({ language: "sql", command: "CREATE INDEX IF NOT EXISTS ON Uniq (name) UNIQUE" });
    await db.command({ language: "sql", command: "INSERT INTO Uniq SET name = 'taken'" });

    const session = await db.insertSession({ targetType: "Uniq", transactionMode: "per_batch" });
    try {
      const failed = await session.sendChunk([{ name: "taken" }]);
      expect(failed.wholeChunkFailed).toBe(true);
      expect(failed.received).toBe(1);
      expect(failed.failed).toBe(1);
      expect(failed.errors?.[0]?.rowIndex).toBe(-1);
      expect(session.lastChunkSeq).toBe(0);
      expect(session.open).toBe(true);

      const replay = await session.sendChunk([{ name: "fresh" }]);
      expect(replay.wholeChunkFailed).toBe(false);
      expect(replay.chunkSeq).toBe(1);
      expect(replay.inserted).toBe(1);
      expect(session.lastChunkSeq).toBe(1);
      await session.commit();
    } finally {
      await session.close();
    }
    const { result } = await db.query<{ c: number }>({ language: "sql", command: "SELECT count(*) AS c FROM Uniq" });
    expect(result[0].c).toBe(2);
  });

  it("a wrong password is refused at the handshake", async () => {
    const wrong = createClient({ baseUrl: `http://${container.getHost()}:${container.getMappedPort(2480)}`, auth: basicAuth("root", "nope-nope") });
    await expect(wrong.db(DB_NAME).insertSession({ timeoutMs: 5_000 })).rejects.toBeInstanceOf(ArcadeDBError);
  });
});
