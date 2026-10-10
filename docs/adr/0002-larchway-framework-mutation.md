# ADR 0002: Larchway, a third suite on a new framework

Status: accepted
Date: 2026-10-10

## Context

ADR 0001 added the mutant suite (`modelbay/`) so a scanner could not score by
recognising the langfail corpus. In practice the mutations barely bit. Rowan,
hand-adjudicated, found 50 of 82 vulnerabilities on langfail and 48 of 82 on
modelbay. Renaming symbols, wrapping API calls, and moving sinks between files
still left a Flask app with the same request model, the same guard shapes, and
the same layering, so analysis that worked on one transferred to the other
almost unchanged.

The same run exposed a scoring problem. Automated, symbol-anchored matching of
findings to manifest entries undercounted the mutant findings substantially: a
reviewer describes the real defect but anchors it at a different hop, a wrapper,
or the renamed symbol, and the matcher misses it. A recall number from
auto-scoring on a mutant suite is therefore a lower bound, not a score.

We want a suite where the vulnerability semantics stay fixed but the framework,
the domain, and the way taint is carried all change, so a tool has to model the
framework rather than pattern-match one it already knows.

## Decision

Add a **larchway suite**: a third vulnerable app (`larchway/`) carrying the
langfail vulnerabilities, ported to FastAPI/Starlette with async handlers, in a
different domain (an evaluation and annotation workbench rather than a model
registry). It is scored by the same tooling, under the same schema and ids, with
the same public-corpus/held-out-key policy as ADR 0001.

### Hand adjudication is mandatory

Every scored larchway run is adjudicated by hand: each finding is mapped to a
`V`, `D`, or `~` id in writing in the result file, exactly as `score.py`'s
docstring describes. Auto-scoring may be used to draft a mapping, never to
publish a number.

### Mutation axes

ADR 0001's six mutations (rename, rewrap, relocate, guard rewrite, safe twin,
held-out key) apply to every entry. Larchway adds eleven more, applied where
they fit and recorded per entry in the held-out key so each port is auditable:

- **A7 framework swap.** Flask to an ASGI framework with an async lifespan.
- **A8 typed sources.** Taint arrives through declared, typed request parameters
  and body models rather than a raw request object, typed loosely enough that no
  coercion sanitises it.
- **A9 dependency-injected receivers.** The object that reaches the sink is
  supplied by the framework's dependency injection, often behind an abstract
  type, so the concrete class is only known from the provider.
- **A10 async hops.** Await chains, thread-pool offloading, and concurrent
  gathers between source and sink.
- **A11 deferred hops.** Background tasks, an in-process event bus, a worker
  draining a persisted queue, and startup hooks.
- **A12 guards in the framework.** Authentication and authorisation live in
  dependencies, router configuration, and middleware, and fail in framework
  shapes rather than in an `if` statement.
- **A13 class dispatch.** Service classes, decorator-filled registries, and
  name-built method lookup.
- **A14 model round-trips.** Taint carried through validation, serialisation,
  and copy-with-update of data models.
- **A15 response-class sinks.** The dangerous operation is the construction of a
  response, a template render, a redirect, a file response, or a cookie.
- **A16 alternate transports.** Entry points other than plain HTTP request and
  response.
- **A17 framework-native twins.** Extra decoys whose fix is the framework
  itself, so a correct report has to know what the framework guarantees.

Library-facing surfaces whose names are fixed by a third-party API are not
renamed; their composition is mutated instead.

### Domain shift

The domain, vocabulary, route layout, seed data, and literals are new. Before
any name ships it is checked against both earlier corpora: a reused module,
function, route, or payload literal is a diffable leak.

### Chains and kill chains

Langfail's composed `chains:` are ported where their members are. Larchway adds
**kill chains** (`kill_chains:`): paths from an attacker with no credentials, or
only a self-service account, to critical impact through several links that are
each modest alone. Kill chains reuse existing vulnerability ids rather than
adding new ones. Each has:

- an end-to-end PoC driving every link against the running app;
- a **broken-chain twin**: the same path with exactly one link replaced by its
  existing safe twin, plus a PoC proving the chain then fails.

`score.py` reports every chain as **full** (every member found), **partial**
(n of m), or **none**, with a summary line. A tool that flags a kill chain's
broken-twin decoy is reported as over-claiming that chain; the flag is already
counted once as a decoy false positive.

### Not-ported ids

A suite manifest may carry a top-level `not_ported:` list. Those ids leave every
recall denominator, since a defect absent from the corpus cannot be found.

### Held-out answer key

Unchanged from ADR 0001:

- **Public / committed:** `larchway/` (the corpus),
  `benchmarks/suites/larchway/README.md`, `benchmarks/suites/larchway/scan_prompt.md`,
  the harness changes, this ADR.
- **Held out / git-ignored, local until release:** the answer key
  (`ground_truth.yaml`, with per-entry `mutation:` blocks and the kill chains),
  the PoCs (`tests/`), build notes, raw scan output, and scored results.

## Scope

Larchway v1 ports the web, ML, and data tiers of langfail: identity, object
authorisation, files and storage, deserialisation and formats, query and serving
privacy, outbound requests and jobs, and rendering. The agent and assistant tier
is **not ported** in v1. Its ids, and any chain that depends only on them, are
listed in the held-out key's `not_ported:` list and nowhere public. Recall on
larchway is therefore over a smaller denominator than langfail's and is compared
per id, not as a headline percentage.

## Consequences

- Langfail and mutant scoring are unchanged: the same numbers from the same
  commands. Chain lines are added to the per-tool text summary only; the public
  scoreboard and README chart are untouched.
- A tool run on all three suites gives two deltas per id: langfail minus mutant
  (memorisation of names and paths) and langfail minus larchway (dependence on a
  familiar framework and domain).
- Larchway does not publish to `SCOREBOARD.md` or the README chart while its key
  is held out.
- Cost: a third app to keep runnable, every port backed by a PoC, and a manual
  adjudication pass for every scored run.
- The agent tier remains a gap in larchway until a later version ports it.
