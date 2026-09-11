import { describe, expect, it } from "vitest";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { basename } from "node:path";

/**
 * The fixture only imports `createClient` and calls `db.query()` - the data plane. It must never
 * gain a static import of `facade/dashboards.ts` (Grafana/PromQL), `facade/timeseries.ts`, or
 * `facade/vector.ts` - see `test/fixtures/data-plane-entry.ts`.
 */
const FIXTURE = fileURLToPath(new URL("./fixtures/data-plane-entry.ts", import.meta.url));

/**
 * Markers unique to each lazily-loaded module, chosen to survive minification. Each is a string
 * literal passed as a URL path to `client.GET`/`client.POST` (see `queryGrafana`, `queryPromQL`,
 * `queryRangePromQL`, `labelsPromQL`, `seriesPromQL` in `src/facade/dashboards.ts`,
 * `writeTimeSeries`/`queryTimeSeries` in `src/facade/timeseries.ts`, and `vectorSearch` in
 * `src/facade/vector.ts`) - not identifiers. A minifier renames local identifiers (classes,
 * functions, variables) to short names like `a`/`o`, but never rewrites the contents of a string
 * literal, so these survive where an exported class or function NAME would not. None of the four
 * substrings occurs in any data-plane route (`/api/v1/query`, `/api/v1/command`, `/api/v1/begin`,
 * `/api/v1/commit`, `/api/v1/rollback`) or anywhere in the openapi-fetch runtime.
 */
const GRAFANA_MARKER = "grafana/query";
const PROMQL_MARKER = "prom/api/v1";
const TIMESERIES_MARKER = "/api/v1/ts/{database}/write";
const VECTOR_MARKER = "/api/v1/vector/{database}/search";

/**
 * The fixture's whole eagerly-loaded chunk set, openapi-fetch runtime included, is ~11KB
 * minified today. The ceiling is close to that, not the previous 50,000: a ceiling generous
 * enough to fit a whole extra lazily-loaded module (timeseries.js alone is a few KB) would not
 * fail if `db.ts` regressed to a static import the way the missing TIMESERIES_MARKER check
 * wouldn't have caught it either - see the README's "excludes the time-series, Grafana and
 * PromQL modules" claim this test exists to keep honest.
 */
const SIZE_CEILING_BYTES = 20_000;

interface EagerBundle {
  /** Concatenated text of every output chunk reachable from the entry via STATIC imports only. */
  text: string;
  bytes: number;
}

/**
 * Bundles the fixture the way a consumer's own bundler would: minified ESM, tree-shaking on, with
 * code-splitting enabled. Splitting matters here specifically because `db.grafana`/`db.promql`/
 * `db.ts` are loaded via a dynamic `import()` inside `ArcadeDBDatabase` (see `src/index.ts`) so
 * that a bundler CAN place them in their own chunk. Without `splitting`, esbuild inlines every
 * dynamically-imported module into the single output file regardless of whether the dynamic
 * import is ever reached at runtime - confirmed empirically while writing this test: the same
 * fixture, bundled with `--bundle --minify --format=esm` but no `--splitting`, contains both
 * markers below even though nothing in the fixture ever touches `.grafana` or `.promql`. That
 * would make this assertion fail for a reason that has nothing to do with what a real
 * code-splitting-aware consumer's bundle actually ships up front.
 *
 * `metafile` records, per output chunk, which other chunks it reaches and by what kind of edge:
 * `"import-statement"` (static, always loaded) or `"dynamic-import"` (loaded on demand, a separate
 * chunk under `splitting`). Walking only the static edges from the entry chunk gives exactly the
 * set of chunks a consumer's own bundler would ship in the part of the bundle it loads up front -
 * which is the only part the acceptance criterion ("importing the data plane must not drag in
 * PromQL/Grafana") is about.
 */
async function bundleDataPlaneEntryEagerChunks(): Promise<EagerBundle> {
  const result = await build({
    entryPoints: [FIXTURE],
    bundle: true,
    minify: true,
    format: "esm",
    platform: "neutral",
    treeShaking: true,
    splitting: true,
    outdir: "treeshake-out",
    write: false,
    metafile: true,
  });

  const outputs = result.metafile.outputs;
  const entryKey = Object.keys(outputs).find((key) => outputs[key].entryPoint?.endsWith("data-plane-entry.ts"));
  if (entryKey === undefined) {
    throw new Error('esbuild\'s metafile has no output whose entryPoint matches "data-plane-entry.ts"; cannot locate the entry chunk');
  }

  const eagerKeys = new Set<string>();
  const queue: string[] = [entryKey];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    if (eagerKeys.has(current)) continue;
    eagerKeys.add(current);
    for (const imp of outputs[current].imports) {
      if (imp.kind === "import-statement") queue.push(imp.path);
    }
  }

  const filesByBasename = new Map(result.outputFiles.map((file) => [basename(file.path), file]));
  let text = "";
  let bytes = 0;
  for (const key of eagerKeys) {
    const file = filesByBasename.get(basename(key));
    if (file === undefined) {
      throw new Error(`esbuild's metafile lists output "${key}" but produced no matching output file`);
    }
    text += file.text;
    bytes += file.contents.byteLength;
  }
  return { text, bytes };
}

describe("tree-shaking: the data plane excludes the dashboard, time-series, and vector modules", () => {
  it("does not statically pull PromQL, Grafana, time-series, or vector routes into the eagerly-loaded chunk", async () => {
    const { text, bytes } = await bundleDataPlaneEntryEagerChunks();

    expect(text).not.toContain(PROMQL_MARKER);
    expect(text).not.toContain(GRAFANA_MARKER);
    expect(text).not.toContain(TIMESERIES_MARKER);
    expect(text).not.toContain(VECTOR_MARKER);
    expect(bytes).toBeLessThan(SIZE_CEILING_BYTES);
  });
});
