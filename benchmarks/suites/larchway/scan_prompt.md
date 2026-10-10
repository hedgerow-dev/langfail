# The larchway-suite review prompt

The prompt for a **single-run review** of the `larchway` corpus: one reviewer
reads the whole blind copy in one context, which is the shape a scanner
invocation has and therefore the shape that compares against other tools on the
board.

Contains no answers, so this file is public. Record which prompt version a run
used in its `results/*.yaml` `notes:` field. Do not silently edit it to match a
new run; add a version below.

---

## Handover: what the reviewer must NOT see

This suite's value is that the reviewer cannot recognise the corpus. That is
worth more than any single prompt wording, and it is easy to destroy by
accident. Export with `scripts/export_blind_copy.py <dest> --suite larchway`,
which ships only `larchway/`, and then check the result against this list.

Withhold all of these:

| Must not ship | Why |
|---|---|
| `langfail/`, `modelbay/` | Sibling corpora with the same planted semantics; langfail's answer key is **public**. Anyone who maps one onto the other recovers the set. This is the single biggest leak. |
| `docs/` | The ADRs describe the mutation scheme and the suite design. A partial answer key. |
| `benchmarks/` | Answer keys (all suites), scoring tooling, this suite's README and this prompt. |
| `exploits/`, `tests/` | Runnable proofs against the sibling corpora. |
| `ARCHITECTURE.md`, `SCOREBOARD.md`, `SECURITY.md`, `README.md` | Narrate taint paths, index the findings, or state outright that the tree is planted-vulnerable. |
| `.gitignore`, `.gitleaksignore` | Name the held-out suites and the files holding planted secrets. |
| `.git` | The excluded files live in old commits; `git show <sha>:path` hands them over. Export with no history. |
| `CLAUDE.md` | Project instructions referencing the benchmark. |

Ship **only** the `larchway/` tree, in a fresh directory, with no git history.
Do not name the project "Langfail", do not say the corpus is ported, mutated,
derived, or a benchmark, and do not state how many defects exist or that any
do. A reviewer told "this is langfail on FastAPI" can fetch the public key and
map straight back.

---

## Prompt (v1)

Substitute `{PATH}`. Deliberately does not state how many defects are planted,
or that any are. Telling a reviewer "find N bugs" changes how long it looks and
how readily it reports marginal findings, and no scanner on the board gets that
hint.

---

You are performing a security code review of a Python web application. Review
it as you would a real codebase you had been asked to audit before it ships.

The application is at `{PATH}`. It is a self-hosted evaluation and annotation
workbench: member accounts, model checkpoints, data collections, labeling jobs,
evaluation runs, an assistant, a background worker, and server-rendered pages.
FastAPI plus SQLite.

Read whatever you need. Do not modify anything.

## What to look for

Everything you would in a real audit, but in particular:

- **Trace taint across boundaries.** Data that enters at an HTTP handler may
  reach its dangerous sink in a different module, or after a database
  round-trip, or via a background job or queue, or on a later request, or on
  the next process boot. A flow is still a flow if the source and sink are in
  different files, and some of these do not converge until two independently
  stored values are joined at the sink.
- **Check that safe-looking helpers actually work.** A function whose name or
  docstring promises validation, normalisation, escaping or scoping may be
  bypassable, may normalise once when it needs to loop, may check a property
  that does not hold, may guard a value the caller can set first, or may simply
  not be applied on the path that matters. Read the implementation; the name is
  not evidence.
- **Watch for controls that exist but are not wired up.** In several places a
  correct, strict variant of an operation sits beside a permissive one. Which
  one the caller actually reaches is the question.
- **Do not stop at one finding per function.** A single function can carry two
  unrelated defects, for example a query that is safe from injection but still
  returns another tenant's rows.
- **Consider the assistant surface.** Prompt injection direct and indirect,
  what the assistant can reach and with whose authority, unsafe handling of
  model-generated output, anything an attacker can influence in text the model
  reads, and what leaves the process.
- Config and deployment issues count if you find them, but the code is the
  focus.

Be discriminating. Some code here is deliberately fine and looks superficially
risky; reporting a safe function as broken is a real cost, not a free hedge.
Where two similar functions exist and only one is unsafe, say which and why.

## Output

Produce a findings list. For each finding, exactly:

- `file:line` of the **sink** (the place the damage happens)
- a one-line title
- 2-3 sentences: what the untrusted input is, how it reaches the sink, and why
  any apparent protection fails
- the CWE if you are confident of it

Order by severity. Aim for completeness over brevity: list everything you
genuinely believe is a defect, but do not pad with speculative or stylistic
issues. If you are unsure whether something is exploitable, include it and say
what you are unsure about.

Work steadily through the whole application rather than sampling it. There is
no time pressure.

---

## Running it

```bash
git rev-parse --short HEAD     # record this as blind_copy_commit
python scripts/export_blind_copy.py <dest> --suite larchway
```

Then map each finding to a manifest id (a `V*` id for a real defect, a `D*` id
when it claims a genuinely-safe function is broken, or `~` when it matches
nothing) and write `results/<tool>.yaml` per `benchmarks/score.py`'s docstring.
Score with:

```bash
python benchmarks/score.py --suite larchway results/<tool>.yaml
```

Adjudication is a human judgement made once, in writing, in the result file.
Do not let the reviewer self-score: it has not seen the key, and asking it to
grade itself reintroduces exactly the recognition this suite removes. Do not
publish an auto-matched score either: symbol-anchored matching undercounts a
mutated corpus.

### Comparing against the other corpora

A per-id recall gap between suites is the signal this benchmark exists to
measure, but it only means anything if **the same engine version, the same
prompt version and the same run shape** produced both numbers. Check that
before publishing a delta. Compare per id: larchway v1 does not port every
langfail id, so its headline recall is over a smaller denominator.
