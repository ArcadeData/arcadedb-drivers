import { describe, expect, it } from "vitest";
import type { CallOptions } from "@connectrpc/connect";
import type { MessageInitShape } from "@bufbuild/protobuf";
import type {
  BeginTransactionRequestSchema,
  BeginTransactionResponseSchema,
  CommitTransactionRequestSchema,
  CommitTransactionResponseSchema,
  ExecuteQueryRequestSchema,
  RollbackTransactionRequestSchema,
  RollbackTransactionResponseSchema,
} from "../src/gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";
import { createTransaction } from "../src/transaction.js";

type BeginRequest = MessageInitShape<typeof BeginTransactionRequestSchema>;
type BeginResponse = MessageInitShape<typeof BeginTransactionResponseSchema>;
type CommitRequest = MessageInitShape<typeof CommitTransactionRequestSchema>;
type CommitResponse = MessageInitShape<typeof CommitTransactionResponseSchema>;
type RollbackRequest = MessageInitShape<typeof RollbackTransactionRequestSchema>;
type RollbackResponse = MessageInitShape<typeof RollbackTransactionResponseSchema>;
type ExecuteQueryRequest = MessageInitShape<typeof ExecuteQueryRequestSchema>;

/** Records every call made through a fake `raw` client, mimicking the subset of
 * `Client<typeof ArcadeDbService>` the transaction wrapper touches. */
function mockRaw(
  opts: {
    transactionId?: string;
    commitFails?: boolean;
    committed?: boolean;
    commitMessage?: string;
    rollbackFails?: boolean;
  } = {},
) {
  const {
    transactionId = "tx-123",
    commitFails = false,
    committed = true,
    commitMessage = "",
    rollbackFails = false,
  } = opts;

  const calls: {
    begin: BeginRequest[];
    commit: CommitRequest[];
    rollback: RollbackRequest[];
    executeQuery: ExecuteQueryRequest[];
    executeQueryOptions: (CallOptions | undefined)[];
  } = { begin: [], commit: [], rollback: [], executeQuery: [], executeQueryOptions: [] };

  const raw = {
    beginTransaction: async (request: BeginRequest): Promise<BeginResponse> => {
      calls.begin.push(request);
      return { transactionId, timestamp: 0n };
    },
    commitTransaction: async (request: CommitRequest): Promise<CommitResponse> => {
      calls.commit.push(request);
      if (commitFails) throw new Error("commit failed");
      return { success: true, committed, message: commitMessage, timestamp: 0n };
    },
    rollbackTransaction: async (request: RollbackRequest): Promise<RollbackResponse> => {
      calls.rollback.push(request);
      if (rollbackFails) throw new Error("rollback failed");
      return { success: true, rolledBack: true, message: "" };
    },
    executeQuery: async (request: ExecuteQueryRequest, options?: CallOptions) => {
      calls.executeQuery.push(request);
      calls.executeQueryOptions.push(options);
      return { results: [], executionTimeMs: 0n, queryPlan: "" };
    },
    executeCommand: async (request: unknown) => {
      calls.executeQuery.push(request as ExecuteQueryRequest);
      return { success: true, message: "", affectedRecords: 0n, executionTimeMs: 0n, records: [], stats: undefined };
    },
    createRecord: async () => ({ rid: "" }),
    updateRecord: async () => ({ success: true, updated: true }),
    deleteRecord: async () => ({ success: true, deleted: true, message: "" }),
    lookupByRid: async () => ({ found: false, record: undefined }),
    bulkInsert: async () => ({
      received: 0n,
      inserted: 0n,
      updated: 0n,
      ignored: 0n,
      failed: 0n,
      errors: [],
      executionTimeMs: 0n,
      startedAt: undefined,
      finishedAt: undefined,
    }),
    streamQuery: async function* () {},
    insertStream: async () => ({
      received: 0n,
      inserted: 0n,
      updated: 0n,
      ignored: 0n,
      failed: 0n,
      errors: [],
      executionTimeMs: 0n,
      startedAt: undefined,
      finishedAt: undefined,
    }),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;

  return { raw, calls };
}

describe("transaction", () => {
  it("calls BeginTransaction first and threads its transaction_id into every subsequent request", async () => {
    const { raw, calls } = mockRaw({ transactionId: "tx-abc" });
    const transaction = createTransaction(raw);

    await transaction("mydb", async (tx) => {
      await tx.executeQuery({ query: "SELECT FROM V" });
      await tx.executeQuery({ query: "SELECT FROM E" });
    });

    expect(calls.begin).toHaveLength(1);
    expect(calls.begin[0]?.database).toBe("mydb");
    expect(calls.executeQuery).toHaveLength(2);
    for (const request of calls.executeQuery) {
      expect(request.transaction?.transactionId).toBe("tx-abc");
    }
  });

  it("binds the full transaction context - database on the request and on transaction.database, not only transactionId", async () => {
    const { raw, calls } = mockRaw({ transactionId: "tx-abc" });
    const transaction = createTransaction(raw);

    await transaction("mydb", async (tx) => {
      await tx.executeQuery({ query: "SELECT FROM V" });
    });

    expect(calls.executeQuery[0]?.database).toBe("mydb");
    expect(calls.executeQuery[0]?.transaction?.database).toBe("mydb");
    expect(calls.executeQuery[0]?.transaction?.transactionId).toBe("tx-abc");
  });

  it("overrides a caller-supplied database/transaction rather than trusting it (anti-hijack)", async () => {
    const { raw, calls } = mockRaw({ transactionId: "tx-abc" });
    const transaction = createTransaction(raw);

    await transaction("mydb", async (tx) => {
      await tx.executeQuery({
        query: "SELECT FROM V",
        database: "some-other-db",
        transaction: { transactionId: "hijacked-tx-id", database: "some-other-db" },
      });
    });

    expect(calls.executeQuery[0]?.database).toBe("mydb");
    expect(calls.executeQuery[0]?.transaction?.database).toBe("mydb");
    expect(calls.executeQuery[0]?.transaction?.transactionId).toBe("tx-abc");
  });

  it("passes CallOptions through to the underlying raw call unchanged", async () => {
    const { raw, calls } = mockRaw();
    const transaction = createTransaction(raw);
    const options: CallOptions = { timeoutMs: 5_000 };

    await transaction("mydb", async (tx) => {
      await tx.executeQuery({ query: "SELECT FROM V" }, options);
    });

    expect(calls.executeQueryOptions[0]).toBe(options);
  });

  it("commits on normal return and does not roll back", async () => {
    const { raw, calls } = mockRaw();
    const transaction = createTransaction(raw);

    const result = await transaction("mydb", async (tx) => {
      await tx.executeQuery({ query: "SELECT FROM V" });
      return 42;
    });

    expect(result).toBe(42);
    expect(calls.commit).toHaveLength(1);
    expect(calls.rollback).toHaveLength(0);
  });

  it("rolls back when the body rejects, does not commit, and propagates the original error", async () => {
    const { raw, calls } = mockRaw();
    const transaction = createTransaction(raw);
    const originalError = new Error("boom - async rejection");

    await expect(
      transaction("mydb", async () => {
        await Promise.resolve();
        throw originalError;
      }),
    ).rejects.toBe(originalError);

    expect(calls.rollback).toHaveLength(1);
    expect(calls.commit).toHaveLength(0);
  });

  it("rolls back when the body throws synchronously, not only on a rejected promise", async () => {
    const { raw, calls } = mockRaw();
    const transaction = createTransaction(raw);
    const originalError = new Error("boom - synchronous throw");

    await expect(
      transaction("mydb", (): never => {
        throw originalError;
      }),
    ).rejects.toBe(originalError);

    expect(calls.rollback).toHaveLength(1);
    expect(calls.commit).toHaveLength(0);
  });

  it("issues a best-effort rollback and surfaces the COMMIT error (not the rollback's) when both commit and rollback fail (T3)", async () => {
    // T3: mockRaw's rollback used to always resolve, so this test could not tell a real
    // best-effort rollback (try/catch around safeRollback's own call) from having no try/catch at
    // all - deleting safeRollback's try/catch left it green. Making rollback itself reject proves
    // the rollback failure is swallowed and the commit error still surfaces.
    const { raw, calls } = mockRaw({ commitFails: true, rollbackFails: true });
    const transaction = createTransaction(raw);

    await expect(
      transaction("mydb", async (tx) => {
        await tx.executeQuery({ query: "SELECT FROM V" });
      }),
    ).rejects.toThrow("commit failed");

    expect(calls.commit).toHaveLength(1);
    expect(calls.rollback).toHaveLength(1);
  });

  it("issues a best-effort rollback and surfaces the commit error when commit fails", async () => {
    const { raw, calls } = mockRaw({ commitFails: true });
    const transaction = createTransaction(raw);

    await expect(
      transaction("mydb", async (tx) => {
        await tx.executeQuery({ query: "SELECT FROM V" });
      }),
    ).rejects.toThrow("commit failed");

    expect(calls.commit).toHaveLength(1);
    expect(calls.rollback).toHaveLength(1);
  });

  it("throws when the server answers success with committed=false, including the server's message (C2)", async () => {
    // The server answers a stale/reaped transaction id with success=true, committed=false and NO
    // error status - a resolved commitTransaction() promise is not proof the transaction actually
    // committed. See ArcadeDbGrpcService.java:1660-1670.
    const { raw, calls } = mockRaw({ committed: false, commitMessage: "No active transaction for id=tx-123" });
    const transaction = createTransaction(raw);

    await expect(
      transaction("mydb", async (tx) => {
        await tx.executeQuery({ query: "SELECT FROM V" });
      }),
    ).rejects.toThrow(/No active transaction for id=tx-123/);

    expect(calls.commit).toHaveLength(1);
  });

  it("throws when beginTransaction returns a missing transaction id (I2)", async () => {
    const { raw } = mockRaw({ transactionId: "" });
    const transaction = createTransaction(raw);

    await expect(
      transaction("mydb", async (tx) => {
        await tx.executeQuery({ query: "SELECT FROM V" });
      }),
    ).rejects.toThrow(/transaction id/i);
  });

  it("throws when beginTransaction returns a blank (whitespace-only) transaction id (I2)", async () => {
    const { raw } = mockRaw({ transactionId: "   " });
    const transaction = createTransaction(raw);

    await expect(
      transaction("mydb", async (tx) => {
        await tx.executeQuery({ query: "SELECT FROM V" });
      }),
    ).rejects.toThrow(/transaction id/i);
  });

  describe("cause attachment when both the body throws and the rollback fails (I5)", () => {
    it("attaches the rollback failure as `cause` on the body's error", async () => {
      const { raw } = mockRaw({ rollbackFails: true });
      const transaction = createTransaction(raw);
      const originalError = new Error("the caller's real failure");

      let caught: unknown;
      try {
        await transaction("mydb", async () => {
          throw originalError;
        });
      } catch (err) {
        caught = err;
      }

      expect(caught).toBe(originalError);
      expect((caught as Error).cause).toBeInstanceOf(Error);
      expect(((caught as Error).cause as Error).message).toBe("rollback failed");
    });

    it("surfaces a frozen error as itself, not a TypeError, when the rollback also fails", async () => {
      // A frozen Error is non-extensible: `err.cause = rollbackErr` throws
      // `TypeError: Cannot add property cause, object is not extensible` in strict-mode ESM.
      const { raw } = mockRaw({ rollbackFails: true });
      const transaction = createTransaction(raw);
      const boom = Object.freeze(new Error("frozen sentinel failure"));

      let caught: unknown;
      try {
        await transaction("mydb", async () => {
          throw boom;
        });
      } catch (err) {
        caught = err;
      }

      expect(caught).toBe(boom);
      expect((caught as Error).message).toBe("frozen sentinel failure");
      expect((caught as Error).cause).toBeUndefined();
    });

    it("does not overwrite a caller-set cause when the rollback also fails", async () => {
      const { raw } = mockRaw({ rollbackFails: true });
      const transaction = createTransaction(raw);
      const originalCause = new Error("the caller's own causal chain");
      const boom = new Error("the caller's real failure", { cause: originalCause });

      let caught: unknown;
      try {
        await transaction("mydb", async () => {
          throw boom;
        });
      } catch (err) {
        caught = err;
      }

      expect(caught).toBe(boom);
      expect((caught as Error).cause).toBe(originalCause);
    });
  });
});
