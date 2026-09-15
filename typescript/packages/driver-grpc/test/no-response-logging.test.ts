import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = fileURLToPath(new URL("../src", import.meta.url));

/**
 * Repository-level backstop for arcadedb#7309: no hand-written source file in this package may
 * call `console.*` or write to `process.stdout`/`process.stderr` directly. This is the blunt half
 * of the response-isolation guard - `test/auth.test.ts`'s "response isolation" describe block
 * proves the two auth interceptors specifically never touch a response object; this test instead
 * proves a wider, cruder claim: NOTHING in `src/` (any file, any function, today or after an
 * unrelated edit) logs anything at all. A future change that starts logging a `CreateApiToken`
 * response from `transaction.ts` or `stream.ts` - nowhere near the interceptors - would slip past
 * the interceptor-level test but fails this one.
 *
 * What this does NOT prove: it cannot see a logging call built by string concatenation
 * (`globalThis["con" + "sole"]`), a call routed through a variable alias (`const log = console;
 * log.info(...)`), or a call to a third-party logger this package doesn't depend on today. It is
 * a net, not a data-flow analysis - a clean run is evidence of "no literal console/stdout/stderr
 * call exists", not "no response ever reaches a log sink by any means".
 */

function tsFilesUnder(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "gen") continue; // generated code is never hand-edited and is not this test's concern
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...tsFilesUnder(path));
    } else if (entry.name.endsWith(".ts")) {
      files.push(path);
    }
  }
  return files;
}

const LOGGING_PATTERNS = [/\bconsole\s*\./, /\bprocess\.stdout\.write\s*\(/, /\bprocess\.stderr\.write\s*\(/];

describe("no logging exists in src/", () => {
  it("contains no console.*, process.stdout.write, or process.stderr.write call", () => {
    const offenders: string[] = [];
    for (const file of tsFilesUnder(SRC_DIR)) {
      const content = readFileSync(file, "utf8");
      for (const pattern of LOGGING_PATTERNS) {
        if (pattern.test(content)) offenders.push(`${file} matches ${pattern}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
