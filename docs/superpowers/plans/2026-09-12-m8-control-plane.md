# M8: The Control Plane — Reachable, Then Documented

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ArcadeDB's 44 admin RPCs callable from both gRPC clients without defeating a security control, then document them.

**Architecture:** One handle per package exposing the generated `ArcadeDbAdminService` stub, built from the **same** channel or transport that already carries auth and the insecure-channel refusal. Not a facade over 44 RPCs — the stub, exposed once, exactly as `raw` exposes the data plane. Then a README enumeration, machine-checked so it cannot fall behind a contract bump.

**Tech Stack:** `@connectrpc/connect`, `grpc`/`grpc.aio`, vitest, pytest, mypy, ruff, eslint.

**Spec:** `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4, M8) — **see Task 1: its premise is false and is corrected before anything is built on it.**

**Issue:** ArcadeData/arcadedb-drivers#40, whose premise was corrected on 2026-09-12 before work started. Upstream: arcadedb#7308, #7309, #7310.

## Global Constraints

- Generated code is **never** hand-edited. Do not touch `contracts/`; M8 changes no contract, so the drift gate must stay green with no regeneration.
- **No HTTP client changes.** Neither `@arcadedb/driver` nor `arcadedb-driver` is part of this milestone.
- Python's sync and async facades are hand-maintained in parallel (`unasync` is a non-goal). Every sync addition needs its `Async` twin, and the twins must carry the same *behavioural facts* in their docstrings — drift there is a defect, filed once already as #30 and found again in M5.
- Service name, verbatim: `ArcadeDbAdminService`. Handle name, verbatim: `rawAdmin` (TypeScript) / `raw_admin` (Python).
- Branch: `feat/m8-control-plane`, off `main`.

## Decisions

**D-M8-1 — expose the stub once; do not facade 44 RPCs.** The parity bar (design §3, D4) says a facade wraps what a bare stub drives badly. A unary admin RPC is a one-line stub call. Exposing the stub is not a facade and does not breach the bar — it is the same move `raw` already makes for the data plane, and it is what "raw-only but documented" was always supposed to mean.

**D-M8-2 — the handle must be built from the existing channel/transport. This is why M8 is code and not prose.** Today the admin service is unreachable without defeating something:

| | what reaching `ArcadeDbAdminService` costs today |
|---|---|
| Python | impossible through the public API — `client._channel` and `arcadedb_driver_grpc._generated.arcadedb_server_pb2_grpc` are both private |
| TypeScript | the descriptor is exported, but the transport is a local `const` inside `createClient`, so a caller builds their own with `createGrpcTransport(...)` — **bypassing the refusal to pair a plaintext-password interceptor with a non-TLS `baseUrl`** (arcadedb#5048) |

Documenting that workaround would publish instructions for defeating a credential-exposure control, on a service whose `CreateApiToken` returns secret material. Reusing the existing channel/transport means auth, TLS policy and that refusal all carry over unchanged, because there is only one of each.

**D-M8-3 — no facade for `Health` and `Ready`.** Their request messages are empty (`message HealthRequest {}`), so the entire difference is `rawAdmin.health({})` versus `health()`. An empty request makes them the easiest RPCs to call through the stub, not the hardest — the opposite of the case for an exception.

**D-M8-4 — the README enumeration is machine-checked.** A hand-maintained list of 44 RPC names goes stale on the next contract bump, silently, and a stale list is worse than none because a reader trusts it. A test compares the documented set against the generated stub's own method set, so the list cannot drift without a red test.

---

### Task 1: Correct the design doc's M8 section

**Files:** Modify `docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md` (§4 M8 only).

- [ ] **Step 1: Verify the premise is false before rewriting**

```bash
grep -rn 'AdminService' typescript/packages/driver-grpc/src python/packages/driver-grpc/src/arcadedb_driver_grpc --include='*.ts' --include='*.py' | grep -vE '/gen/|_generated'
grep -n 'ArcadeDbServiceStub\|createConnectClient' python/packages/driver-grpc/src/arcadedb_driver_grpc/__init__.py typescript/packages/driver-grpc/src/index.ts
```

Expected: the first prints nothing — `ArcadeDbAdminService` appears nowhere outside generated code. The second shows `raw` bound to the **data-plane** service in both. So "reachable on `raw` / the stub" is false.

- [ ] **Step 2: Rewrite the section**

It must state: that the admin service is not currently reachable and what reaching it costs in each language (D-M8-2's table); that M8 therefore exposes the stub once rather than only documenting; that this does not breach the parity bar and why; the `Health`/`Ready` decision with its reasoning; and the corrected count — `ArcadeDbAdminService` carries **44** RPCs, 41 unary and 3 server-streaming, of which 32 unary were new in this contract and nine pre-dated it.

Match the register of the M6 and M7 corrections already in this document.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-11-contract-26.10.1-migration-design.md
git commit -m "$(cat <<'EOF'
docs: correct M8's premise - the admin service is not reachable at all

§4 M8 said the control-plane RPCs "stay reachable on `raw` / the stub" and
needed only documenting. They are not reachable. `raw` is the data-plane
stub in both packages; ArcadeDbAdminService is exposed nowhere.

Reaching it today means private names in Python, and in TypeScript building
a transport by hand - which bypasses the refusal to pair a plaintext password
with a non-TLS baseUrl. Documenting that workaround would publish
instructions for defeating a credential-exposure control on a service whose
CreateApiToken returns secret material.

So M8 exposes the stub once per package, built from the channel or transport
that already carries auth, and documents what is then actually callable.

Refs #40
EOF
)"
```

---

### Task 2: Expose the admin stub in both packages

**Files:**
- Modify: `typescript/packages/driver-grpc/src/index.ts`; `python/packages/driver-grpc/src/arcadedb_driver_grpc/__init__.py`, `aio.py`
- Test: `typescript/packages/driver-grpc/test/`, `python/packages/driver-grpc/tests/` (including `tests/test_public_surface.py`, which pins the exported surface)

**Interfaces:**
- Consumes: the generated `ArcadeDbAdminService` descriptor (TypeScript) and `ArcadeDbAdminServiceStub` (Python), both already generated.
- Produces: `rawAdmin` on `ArcadeDBGrpcClient`; `raw_admin` on the sync and async Python clients.

- [ ] **Step 1: Write the failing tests**

The property that matters is not "the handle exists" — it is that the handle rides the **same** channel/transport, so the security guard and the auth interceptors apply to it too. Assert that:

- With a plaintext-password auth and a non-TLS `baseUrl`, `createClient` still throws — and therefore no `rawAdmin` exists to misuse. (The guard runs before construction; this pins that exposing a second stub did not move it.)
- An auth interceptor's metadata reaches an admin RPC, not only a data-plane one. In Python, drive a recording servicer registered for `ArcadeDbAdminService` and assert the auth metadata arrived. In TypeScript, assert through whatever mechanism `test/auth.test.ts` already uses for the data plane — read it first and match.
- `rawAdmin` and `raw` are distinct objects but share one channel/transport (Python: assert `client.raw_admin` is backed by the same channel object; TypeScript: assert both were created from one transport).
- Closing the client closes the shared channel once — not twice, and not leaving the admin stub usable afterwards.

- [ ] **Step 2: Run them and see them fail**

```bash
cd typescript && npx vitest run packages/driver-grpc/test/; cd ..
cd python && uv run pytest packages/driver-grpc/tests -v; cd ..
```

- [ ] **Step 3: Implement**

TypeScript: build `rawAdmin` from the *same* `transport` local that `raw` already uses, immediately after it. One line plus its type and doc comment. Do not create a second transport.

Python: `self.raw_admin = _pb2_grpc.ArcadeDbAdminServiceStub(channel)` beside the existing `raw`, in both the sync and async clients, using the same `channel`. Add `raw_admin` to the class docstrings on both sides with the same behavioural content.

The doc comment in each language must say what the handle is (the generated admin stub, no facade), that it shares the client's channel and therefore its auth and TLS policy, and that it is the control plane rather than the data plane.

- [ ] **Step 4: Update the pinned public surface**

`python/packages/driver-grpc/tests/test_public_surface.py` pins `__all__`. Adding a public attribute on the client is exactly the deliberate API change that guard exists to catch, so update it — and only it.

- [ ] **Step 5: Full gate**

```bash
cd typescript && npx vitest run packages/driver-grpc/test/ && npm run typecheck && npm run lint && npm test; cd ..
cd python && uv run pytest packages/driver-grpc/tests -v && uv run mypy && uv run ruff check . && uv run ruff format --check . && uv run pytest; cd ..
```

- [ ] **Step 6: Commit**

```bash
git add typescript/packages/driver-grpc python/packages/driver-grpc
git commit -m "$(cat <<'EOF'
feat(driver-grpc): expose the admin stub on the same channel as the data plane

ArcadeDbAdminService was reachable from neither client. In Python that meant
two private names; in TypeScript it meant building a transport by hand, which
bypasses the refusal to send a plaintext password over a non-TLS baseUrl.

`rawAdmin` / `raw_admin` is the generated stub, exposed once, built from the
channel or transport `raw` already uses - so auth, TLS policy and the
insecure-channel refusal apply to the control plane because there is only one
of each, not because anything re-implements them.

Not a facade: 44 admin RPCs stay one-line stub calls, which is what the
parity bar asks for.

Refs #40
EOF
)"
```

---

### Task 3: The two guards

**Files:**
- Test: `typescript/packages/driver-grpc/test/`, `python/packages/driver-grpc/tests/`

**Interfaces:** Consumes Task 2's handles. Produces no public surface.

- [ ] **Step 1: A test that no interceptor reads a response**

arcadedb#7309 argues server-side that a token-bearing response must be proved not to reach a log sink. `CreateApiToken` returns secret material, so the client owes the same proof.

The evidence today is strong and the test should pin it rather than restate it: both TypeScript interceptors set request headers and `return next(req)`; all four Python `intercept_*` methods `return continuation(_augment(details, extra), request)`. Neither reads a response, and **there is no logging anywhere in either package** — no `console.*`, no `logging`, no `print`.

Write a test that would fail if that changed. Options worth weighing, and the choice is yours: a test that drives a call through the interceptor chain with a sentinel response object and asserts it was never accessed (a `Proxy` in TypeScript, an object whose attribute access records in Python); or a repository-level assertion that no logging call exists in the package source. The first proves more; the second is blunter but catches a wider class. Say which you chose and why — and if you do both, say that too.

- [ ] **Step 2: A test that the README enumeration cannot go stale**

A hand-written list of 44 RPC names is exactly the kind of prose that rots silently on the next contract bump, and a stale list is worse than none because a reader trusts it.

Write a test per package that extracts the RPC names documented in that package's README and asserts the set equals the admin stub's own method set, derived from the generated code. Decide the extraction contract yourself — a fenced block, a marker comment, a table column — but make it something a human writing the README naturally produces, and make the failure message say which names are missing and which are extra, so a contract bump tells the author exactly what to add.

This guard is the same class as the one in `scripts/adopt-contract-version.sh` added for #44: cheap, and it fires precisely when a human would otherwise forget.

- [ ] **Step 3: Run and commit**

```bash
cd typescript && npm test && npm run typecheck && npm run lint; cd ..
cd python && uv run pytest && uv run mypy && uv run ruff check . && uv run ruff format --check .; cd ..
```

Expect the enumeration guard to **fail** at this point — the README sections do not exist yet. That is correct and it is Task 4's job to make it pass. Commit the guards with that stated, or sequence Task 4 first if you prefer a green tree at every commit; say which you did.

---

### Task 4: The README enumeration and the security note

**Files:** Modify `typescript/packages/driver-grpc/README.md`, `python/packages/driver-grpc/README.md`.

- [ ] **Step 1: Derive the RPC list from the contract, not by hand**

```bash
awk '/^service ArcadeDbAdminService \{/,/^\}/' contracts/arcadedb-server-26.10.1-SNAPSHOT.proto | grep -oE 'rpc [A-Za-z]+' | awk '{print $2}'
```

Expect 44 names. Group them for a reader rather than listing alphabetically — databases, discovery, security, settings, backup, profiler, server, and the three server-streaming restore/import RPCs.

- [ ] **Step 2: Write the sections**

Each README in its own voice, and each must state:
- what `rawAdmin` / `raw_admin` is: the generated admin stub, no facade, sharing the client's channel and therefore its auth and TLS policy;
- that the 41 unary RPCs are one-line stub calls, and why that is the design rather than an omission (the parity bar);
- that `RestoreBackup`, `RestoreDatabase` and `ImportDatabase` are **server-streaming** on purpose — a long restore reports progress and stays cancellable — and are the three the bare stub drives least comfortably;
- that `Health` and `Ready` take empty request messages, which is why they get no facade;
- **the security note**: `CreateApiToken` returns secret material, and this client neither reads nor logs any response — the interceptors are request-side by construction and the package contains no logging at all. Say it as the property it is, and point at the test that pins it.

- [ ] **Step 3: The enumeration guard must now pass**

```bash
cd typescript && npm test; cd ..
cd python && uv run pytest; cd ..
```

If it fails, the failure message should name exactly which RPCs are missing or extra — fix the README, not the guard.

- [ ] **Step 4: Full gate, then commit**

```bash
cd typescript && npm run lint && npm run typecheck && npm test; cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run python scripts/check_codegen_skips.py; cd ..
git status --short
```

---

### Task 5: Open the pull request

- [ ] **Step 1: Re-run everything from clean**

```bash
cd typescript && npm run lint && npm run typecheck && npm test && cd ..
cd python && uv run ruff check . && uv run ruff format --check . && uv run mypy \
  && uv run pytest && uv run python scripts/check_codegen_skips.py && cd ..
```

- [ ] **Step 2: Confirm the drift gate is untouched**

M8 changes no contract, so regeneration must produce no diff.

```bash
cd typescript && npm run generate && cd ..
cd python && ./scripts/generate.sh && ./scripts/generate-grpc.sh && cd ..
git status --short
```

Expected: only `?? .idea/`.

- [ ] **Step 3: Run the e2e suites**

Task 2 changes how the clients are constructed, which every e2e exercises.

```bash
cd typescript && npm run e2e; cd ..
cd python && uv run pytest e2e; cd ..
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/m8-control-plane
gh pr create --base main --milestone '0.2.0 — the 26.10.1 contract' \
  --label enhancement,grpc-driver,typescript,python,security \
  --title 'feat: reach the control plane without defeating a security control' \
  --body 'Closes #40.'
```

Expand that body before creating: the corrected premise, what reaching the admin service used to cost in each language, why exposing the stub is not a facade, the `Health`/`Ready` decision, and both guards.
