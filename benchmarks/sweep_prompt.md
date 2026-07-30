# The partitioned-review prompt

The prompt used for a **region sweep**: instead of one reviewer reading the
whole blind copy, N reviewers each read one region of it, and their findings
are pooled.

## Provenance

The original 5-region Opus sweep (75/82, on SCOREBOARD.md) was run **without
saving its prompt**. What follows is reconstructed from the description that
survived — one region each, trace taint across file/DB/queue boundaries, check
that safe-looking helpers actually work, don't stop at one finding per
function. It is faithful in substance and is **not verbatim**.

Any run using this file is therefore not strictly comparable to that 75/82.
Record which prompt a run used in its `results/*.yaml` `notes:` field. Do not
delete or silently edit this file to match a new run — add a version below.

## Regions

Five regions, chosen so each is a coherent slice with its own bug flavour and
no region is much bigger than the others:

| Region | Paths |
|--------|-------|
| `api` | `langfail/api/` |
| `services` | `langfail/services/`, `langfail/workers/` |
| `ml` | `langfail/ml/` |
| `agent` | `langfail/agent/`, `langfail/mcp_server.py` |
| `core` | `langfail/core/`, `langfail/ui/`, `langfail/cli.py`, `langfail/models.py` |

A reviewer may **read** any file in the copy — cross-file taint is the point —
but only reports findings whose sink is in its own region, so the pooled
results don't double-count.

## Prompt (v1)

Substitute `{REGION}` and `{PATHS}`. Give the reviewer the blind copy only.

---

You are doing a security review of a self-hosted MLOps platform called
Langfail: a Flask app with a model registry, dataset ingestion, experiment
tracking, an inference API, and an LLM assistant.

Your assigned region is **{REGION}**: `{PATHS}`. Report only bugs whose
dangerous operation lives in your region. You may and should read any other
file in the tree to follow where data comes from.

Find real, exploitable security bugs. For each one, state: the entry point
where untrusted input arrives, the dangerous operation it reaches, the path
between them, and what an attacker gets. Be concrete about the file and
function.

Four things matter more than volume:

1. **Follow data across boundaries.** Input arrives in one module and does
   damage in another. Paths detour through a database write that is read back
   later, through a background job queue, through a serialize/deserialize
   round trip, or through the LLM's own context. A bug whose entry point and
   sink are in the same function is the easy case; most are not.

2. **Do not trust a helper because of what it is called or what its docstring
   claims.** Read what it does. Some validators and sanitizers in this
   codebase do not do what they appear to do — they normalize once when the
   input can be doubled up, they check a property that does not hold, they
   guard a value the caller can set first, or they are simply not applied on
   the path that matters. Equally, some functions that look dangerous are
   genuinely fine. Decide from the code.

3. **Do not stop at one finding per function.** A function can carry two
   unrelated bugs: a SQL problem and a missing authorization check, a
   parameterized query that still leaks another tenant's rows. Having found
   one, keep reading.

4. **Say when something is safe.** If you inspect a function that looks
   suspicious and conclude it is correct, say so and why. A wrong accusation
   costs as much as a miss here.

Consider the whole range: unsafe deserialization, injection of SQL and shell
and templates, path traversal and archive extraction, SSRF, access control
(can one user reach another's objects?), authentication and session handling,
cryptographic choices, and — for the assistant — prompt injection direct and
indirect, tool abuse, what the tools can reach, and what leaves the process.

Report as a numbered list. No preamble, no summary of the codebase, no
remediation advice unless it clarifies the bug. If you are unsure whether
something is exploitable, include it and say what you are unsure about.

---

## Running a sweep

```bash
git rev-parse --short HEAD                        # record this
python scripts/export_blind_copy.py /tmp/langfail-blind
```

Give each reviewer the blind copy and one region's prompt. Pool the findings,
map each to a manifest id, and write `benchmarks/results/<tool>.yaml` — see
[`results/README.md`](results/README.md). Note in `notes:` that the run was
partitioned, how many reviewers, and that it used `sweep_prompt.md` v1.

A partitioned run is **not** comparable to a single-pass run of the same
model. Keep them in separate rows.
