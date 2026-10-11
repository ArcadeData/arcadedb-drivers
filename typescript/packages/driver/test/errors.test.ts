import { describe, expect, it } from "vitest";
import { ArcadeDBError, TimeSeriesWriteError } from "../src/errors.js";
import * as publicSurface from "../src/index.js";

describe("ArcadeDBError", () => {
  it("carries status, error, exception, and detail from a parsed JSON body", () => {
    const err = new ArcadeDBError(404, {
      error: "Database not found",
      exception: "com.arcadedb.exception.DatabaseOperationException",
      detail: "Database 'foo' was not found",
    });

    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
    expect(err.error).toBe("Database not found");
    expect(err.exception).toBe("com.arcadedb.exception.DatabaseOperationException");
    expect(err.detail).toBe("Database 'foo' was not found");
  });

  it("carries help and exceptionArgs from a parsed JSON body", () => {
    const err = new ArcadeDBError(400, {
      error: "Invalid parameter",
      help: "See the SQL reference for valid syntax",
      exceptionArgs: "arg0, arg1",
    });

    expect(err.help).toBe("See the SQL reference for valid syntax");
    expect(err.exceptionArgs).toBe("arg0, arg1");
  });

  it("leaves help and exceptionArgs undefined when the body does not carry them", () => {
    const err = new ArcadeDBError(404, { error: "Database not found" });

    expect(err.help).toBeUndefined();
    expect(err.exceptionArgs).toBeUndefined();
  });

  it("carries requestId when supplied out of band (from the X-Request-Id response header)", () => {
    const err = new ArcadeDBError(404, { error: "Database not found" }, "req-abc-123");

    expect(err.requestId).toBe("req-abc-123");
  });

  it("falls back to a body-supplied requestId when none is passed explicitly", () => {
    const err = new ArcadeDBError(404, { error: "Database not found", requestId: "body-req-456" });

    expect(err.requestId).toBe("body-req-456");
  });

  it("tolerates an absent body without throwing", () => {
    const err = new ArcadeDBError(500);

    expect(err.status).toBe(500);
    expect(err.error).toBeUndefined();
    expect(err.exception).toBeUndefined();
    expect(err.detail).toBeUndefined();
    expect(err.requestId).toBeUndefined();
    expect(err.message).toContain("500");
  });

  it("discards a non-JSON (string) body entirely, falling back to the default message", () => {
    // A string body is not "object", so parseBody's `typeof body !== "object"` guard drops it
    // wholesale rather than reading properties off it. This assertion does NOT prove the guard
    // is load-bearing, though: none of the six fields parseBody extracts (error, exception,
    // detail, requestId, help, exceptionArgs) collides with a name on String.prototype, so
    // reading `body.error` off the raw string primitive - which is exactly what happens when a
    // property is read on a primitive; JS auto-boxes it rather than throwing - would also come
    // back `undefined` for every field. Removing the guard entirely leaves this test byte-for-byte
    // green. It is kept for defensive clarity (and to avoid running six property reads against a
    // primitive), not because this test demonstrates it changes the outcome.
    const err = new ArcadeDBError(502, "Bad Gateway from upstream proxy");

    expect(err.status).toBe(502);
    expect(err.error).toBeUndefined();
    expect(err.exception).toBeUndefined();
    expect(err.detail).toBeUndefined();
    expect(err.requestId).toBeUndefined();
    expect(err.message).toBe("ArcadeDB request failed with status 502");
  });

  it("tolerates a null body without throwing", () => {
    const err = new ArcadeDBError(503, null);

    expect(err.status).toBe(503);
    expect(err.error).toBeUndefined();
  });

  it("is named ArcadeDBError and survives instanceof checks through a throw/catch round trip", () => {
    try {
      throw new ArcadeDBError(400, { error: "Bad request" });
    } catch (caught) {
      expect(caught).toBeInstanceOf(ArcadeDBError);
      expect((caught as ArcadeDBError).name).toBe("ArcadeDBError");
    }
  });
});

/** A non-2xx `Response` carrying `headers`; its body is irrelevant to `fromResponse`'s header reads. */
function failedResponse(status: number, headers: Record<string, string>): Response {
  return new Response(null, { status, headers });
}

describe("ArcadeDBError.retryAfter / commitIndex (issue #117)", () => {
  it("reads Retry-After and X-ArcadeDB-Commit-Index off the response", () => {
    const err = ArcadeDBError.fromResponse(
      failedResponse(503, { "Retry-After": "5", "X-ArcadeDB-Commit-Index": "42" }),
      { error: "not ready" },
    );

    expect(err.retryAfter).toBe(5);
    expect(err.commitIndex).toBe(42);
  });

  it("trims whitespace around a header value before parsing it", () => {
    const err = ArcadeDBError.fromResponse(
      failedResponse(409, { "Retry-After": "  7 ", "X-ArcadeDB-Commit-Index": " 9" }),
      undefined,
    );

    expect(err.retryAfter).toBe(7);
    expect(err.commitIndex).toBe(9);
  });

  it("accepts Retry-After: 0, a valid 'retry now'", () => {
    const err = ArcadeDBError.fromResponse(failedResponse(503, { "Retry-After": "0" }), undefined);

    expect(err.retryAfter).toBe(0);
  });

  it("leaves both absent when the response carries neither header", () => {
    const err = ArcadeDBError.fromResponse(failedResponse(500, {}), { error: "boom" });

    expect(err.retryAfter).toBeUndefined();
    expect(err.commitIndex).toBeUndefined();
  });

  it.each([
    ["an HTTP-date", "Wed, 21 Oct 2026 07:28:00 GMT"],
    ["garbage", "soon"],
    ["a negative number", "-3"],
    ["a fraction", "1.5"],
    ["an empty value", ""],
    ["a number with trailing junk", "5s"],
    ["a value past Number.MAX_SAFE_INTEGER", "9007199254740993"],
  ])("yields absent, without throwing, for %s", (_label, value) => {
    const err = ArcadeDBError.fromResponse(
      failedResponse(503, { "Retry-After": value, "X-ArcadeDB-Commit-Index": value }),
      undefined,
    );

    expect(err.retryAfter).toBeUndefined();
    expect(err.commitIndex).toBeUndefined();
  });

  it("takes both from the constructor's extras for an error built out of band", () => {
    const err = new ArcadeDBError(503, { error: "busy" }, undefined, { retryAfter: 3, commitIndex: 11 });

    expect(err.retryAfter).toBe(3);
    expect(err.commitIndex).toBe(11);
  });
});

describe("TimeSeriesWriteError (issue #117)", () => {
  it("is an ArcadeDBError carrying written, dropped and the four reason lists", () => {
    const err = new TimeSeriesWriteError(
      400,
      {
        error: "Some samples were dropped",
        written: 3,
        dropped: 2,
        unknownTypes: ["nope"],
        nonTimeSeriesTypes: ["Person"],
        unavailableTypes: ["broken"],
        undeclaredKeys: ["humidity"],
      },
      "req-1",
    );

    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect(err).toBeInstanceOf(TimeSeriesWriteError);
    expect(err.name).toBe("TimeSeriesWriteError");
    expect(err.status).toBe(400);
    expect(err.error).toBe("Some samples were dropped");
    expect(err.requestId).toBe("req-1");
    expect(err.written).toBe(3);
    expect(err.dropped).toBe(2);
    expect(err.unknownTypes).toEqual(["nope"]);
    expect(err.nonTimeSeriesTypes).toEqual(["Person"]);
    expect(err.unavailableTypes).toEqual(["broken"]);
    expect(err.undeclaredKeys).toEqual(["humidity"]);
  });

  it("defaults an absent reason list to empty and drops non-string elements", () => {
    const err = new TimeSeriesWriteError(400, { error: "x", written: 0, dropped: 1, unknownTypes: ["a", 7, null, "b"] });

    expect(err.unknownTypes).toEqual(["a", "b"]);
    expect(err.nonTimeSeriesTypes).toEqual([]);
    expect(err.unavailableTypes).toEqual([]);
    expect(err.undeclaredKeys).toEqual([]);
  });

  it("leaves written and dropped undefined when the body does not carry them as numbers", () => {
    const err = new TimeSeriesWriteError(400, { error: "x", written: "3" });

    expect(err.written).toBeUndefined();
    expect(err.dropped).toBeUndefined();
  });

  it("reads Retry-After and X-ArcadeDB-Commit-Index through fromResponse, like its parent", () => {
    const err = TimeSeriesWriteError.fromResponse(
      failedResponse(400, { "X-Request-Id": "req-h", "X-ArcadeDB-Commit-Index": "12" }),
      { error: "x", written: 1, dropped: 1 },
    );

    expect(err).toBeInstanceOf(TimeSeriesWriteError);
    expect(err.requestId).toBe("req-h");
    expect(err.commitIndex).toBe(12);
    expect(err.written).toBe(1);
  });

  it("is exported from the package entry point", () => {
    expect(publicSurface.TimeSeriesWriteError).toBe(TimeSeriesWriteError);
  });
});
