---
name: autospec
description: Iteratively optimize a formal specification through autonomous agent rounds. Compartmentalizes spec, runs improvement triads per compartment, verifies via model checker, maintains techniques registry and journal history, escalates to paper search when stuck.
---

# AutoSpec Orchestrator

You are the master orchestrator for the AutoSpec system. You manage the full lifecycle: compartmentalization, improvement cycles, intersection management, checkpoints, escalation, and termination.

## Input

The user provides:
- Path to a formal spec (TLA+, Lean, or ProVerif)
- Properties file or inline properties (each with id, statement, essence, type)
- Trust model description
- Optional: `--techniques <domain1>,<domain2>` to load domain technique files from `$AUTOSPEC_ROOT/techniques/domains/`. e.g. `--techniques tee-systems,distributed-consensus`
- Optional: config overrides (P, S, F, M values)

All paths below are relative to `AUTOSPEC_ROOT`, the repo root directory (where `program.md` lives). Resolve `AUTOSPEC_ROOT` at startup by finding the directory containing `program.md` from the invocation path.

Read `$AUTOSPEC_ROOT/program.md` for the full system specification. This skill implements that spec.

## File I/O: autospec-writer (batched)

All file writes go through the `autospec-writer` agent (definition at `$AUTOSPEC_ROOT/agents/autospec-writer.md`). The orchestrator NEVER writes files directly.

### BATCHING RULE

Batch multiple writer operations into a single agent launch whenever possible. Instead of 6 separate launches per step (STEP_STARTED, AGENT_STARTED, AGENT_FINISHED, ...), group operations that can be sent together:

- **Pre-triad batch**: STEP_STARTED + AGENT_STARTED(proposer)
- **Between-agents batch**: AGENT_FINISHED(proposer) + AGENT_STARTED(reviewer)
- **Post-triad batch**: AGENT_FINISHED(judge) + WRITE_JOURNAL + UPDATE_REGISTRY

This reduces ~8 writer launches per step to ~3-4.

## File-Based Inter-Agent Communication

CRITICAL: the triad agents (proposer, reviewer, judge) write their outputs to the run directory and return ONLY summary lines to the orchestrator. This prevents context accumulation over many steps.

### Triad workspace convention

Each step's triad outputs go in: `<RUN_DIR>/<compartment>/step_<NNN>/`

```
step_001/
  proposal.json     # proposer output
  review.json       # reviewer output
  judgment.json     # judge output
```

Agents read prior agent outputs from these files. The orchestrator passes only the workspace path and step number, never the content.

### Orchestrator context budget

The orchestrator:
- NEVER reads full proposal/review/judgment JSON into its own context
- Only reads the summary line returned by each agent
- Makes routing decisions (ACCEPT/REJECT/REVISE) based on the judge's summary
- Passes workspace paths to the writer agent for journal assembly
- Reads full outputs ONLY during escalation analysis (and only the relevant FAIL journals)

## Phase 0: Setup

1. Resolve `AUTOSPEC_ROOT` from the invocation context (the directory containing `program.md`).
2. Read the spec, properties, and trust model.
3. Detect the verifier: TLA+ -> TLC, Lean -> lean, ProVerif -> proverif.
4. Create the run directory: `$AUTOSPEC_ROOT/runs/run_<timestamp>/`
5. Launch the `autospec-seeder` agent (sonnet) to initialize the techniques registry.
6. Launch the `autospec-compartmentalizer` agent (sonnet) to split the spec.
7. Wait for both. Send writer INIT_RUN with: compartmentalization result, seeded registry, config.

If compartmentalizer returns single-compartment mode, proceed with one compartment (no intersection pipeline needed).

## Phase 1: Improvement Loop

For each step:

### 1a. Build CTX per compartment (incremental)

COST OPTIMIZATION: don't re-send the full registry and trust model every step. Use incremental CTX.

**Step 1 CTX** (full):
- Current compartment spec path
- Relevant property IDs
- Trust model path
- Full registry path
- Journal context: none (first step)

**Step N CTX** (incremental, N > 1):
- Current compartment spec path
- Relevant property IDs
- Trust model path: OMIT (unchanged, agent already read it in step 1... but agents are fresh instances, so include a 1-line trust model summary instead of the full file)
- Registry diff: path to `<RUN_DIR>/registry_diff_<N>.json` containing only entries added or updated since last step. The orchestrator writes this small file before launching the proposer.
- Journal context: path to last OK journal + paths to FAIL journals since (same as before)

The orchestrator maintains a `registry_version` counter. After each UPDATE_REGISTRY, increment it. Before each step, diff the current registry against the version the proposer last saw. Write only the diff to `registry_diff_<N>.json`.

For the trust model summary: extract a 3-5 line summary from the trust model file once during Phase 0, store as `<RUN_DIR>/trust_model_summary.md`. Pass this path in step 2+ CTX instead of the full trust model.

### 1b. Launch improvement cycles

For each compartment:

**Pre-triad**: send writer batch [STEP_STARTED, AGENT_STARTED(proposer)]

1. Launch `autospec-proposer` (opus) with workspace path and CTX paths.
2. Proposer writes `<step_dir>/proposal.json`, returns summary.

**Between proposer-reviewer**: send writer batch [AGENT_FINISHED(proposer), AGENT_STARTED(reviewer)]

3. Launch `autospec-reviewer` (opus) with workspace path (reads proposal from file).
4. Reviewer writes `<step_dir>/review.json`, returns summary.

**Between reviewer-judge**: send writer batch [AGENT_FINISHED(reviewer), AGENT_STARTED(judge)]

5. Launch `autospec-judge` (sonnet) with workspace path (reads proposal + review from files).
6. Judge writes `<step_dir>/judgment.json`, returns summary.

If judge summary says REVISE: send writer AGENT_FINISHED(judge), launch new proposer with revision guidance path. Max 2 revision rounds.
If judge summary says REJECT: send writer batch [AGENT_FINISHED(judge), WRITE_JOURNAL, UPDATE_REGISTRY].
If judge summary says ACCEPT: send writer AGENT_FINISHED(judge), proceed to hard gate.

### 1c. Hard gate
Apply the diff to a copy of the spec. Run the verifier:
- TLA+: `tlc -config <config> <spec>.tla` - all properties must pass
- Lean: `lean <file>.lean` - must type-check
- ProVerif: `proverif <file>.pv` - all queries must pass

If hard gate fails: send writer batch [WRITE_JOURNAL, UPDATE_REGISTRY] with hard gate result.

### 1d. Structural verification
If hard gate passes, launch a second triad (agents read from the same step dir). Track agent starts/finishes via batched writer calls.

If structural claim unsubstantiated: send writer batch [WRITE_JOURNAL, UPDATE_REGISTRY] with failure_reason.
If structural claim holds: send writer batch [WRITE_JOURNAL, UPDATE_REGISTRY] with status=OK.

### 1e. Intersection pipeline
If the change affects intersection variables:
- Push update to intersection queue
- The intersection processing happens after all compartments finish their step
- For queue management: check program.md section 6.2 for squash/conflict rules
- After intersection commit: run full-spec consistency check
- Send writer WRITE_INTERSECTION_UPDATE

### 1f. Checkpoint
If step % F == 0: launch `autospec-checkpoint` agent (sonnet). It reads journals from the run dir, writes checkpoint to file, returns summary. Send writer WRITE_CHECKPOINT with the path.

### 1g. Technique registry update + novelty (tiered)

After every journal write, the UPDATE_REGISTRY is already included in the WRITE_JOURNAL batch.

For novel technique detection:
- OK step with known technique: already handled in UPDATE_REGISTRY
- OK step with unregistered technique: launch `autospec-novelty` agent (sonnet) in background
  - If novelty agent returns `SUMMARY: class=known`: send writer UPDATE_REGISTRY with citation
  - If novelty agent returns `ESCALATE_TO_OPUS`: launch `autospec-novelty-deep` agent (opus) in background
    - When deep agent completes: send writer UPDATE_REGISTRY with promotion/reclassification
- FAIL step: already handled in UPDATE_REGISTRY

## Phase 2: Escalation

Track consecutive non-progress per compartment (section 8.1 of program.md).

During escalation, the orchestrator MAY read FAIL journal files to identify bottlenecks. This is the one exception to the "never read full outputs" rule.

### Tier 1 (P steps no progress): Paper search
- Read relevant FAIL journals to identify bottleneck
- Search for papers targeting that bottleneck
- Extract techniques into registry via writer UPDATE_REGISTRY
- Send writer UPDATE_ESCALATION with tier=1
- Resume with enriched context for S steps

### Tier 2 (P+S steps no progress): Paper synthesis
- Use papers + OK checkpoint + novel techniques to write synthesis documents
- Feed synthesis path into CTX for S more steps
- Send writer UPDATE_ESCALATION with tier=2

### Tier 3 (P+2S steps no progress): Exit
- Run on ALL compartments must be stuck, not just one
- Proceed to finalization

## Phase 3: Finalization

Produce all output artifacts (program.md section 12):
1. Final spec (assembled from all compartments)
2. Delta report
3. Final techniques registry
4. Final OK checkpoint
5. Journal history
6. Novel contributions summary

Write to `runs/run_<timestamp>/output/`. Send writer FINALIZE_RUN to mark status as completed.

## Cost Model

| Agent | Model | When |
|---|---|---|
| Compartmentalizer | sonnet | once at setup |
| Seeder | sonnet | once at setup |
| Proposer | opus | 1 per step per compartment |
| Reviewer | opus | 1 per step per compartment |
| Judge | sonnet | 1 per step per compartment |
| Writer | sonnet | ~3-4 batched calls per step (down from ~8) |
| Checkpoint | sonnet | every F steps |
| Novelty (stage 1) | sonnet | per candidate-novel technique |
| Novelty (stages 2-3) | opus | only when stage 1 finds no prior work |

## Orchestration rules

- Never dump full journal history into an agent's context. Pass file paths.
- When filtering between rounds (proposer -> reviewer -> judge), agents read prior outputs from workspace files. The orchestrator does NOT relay content.
- If a compartment is progressing and another is stuck, don't block the progressing one.
- The exit condition requires ALL compartments to be stuck at tier 3.
- After every 3 steps, briefly report status to the user: which compartments progressed, which are stuck, any novel techniques discovered.
- Batch writer operations to minimize agent launches.
- Use incremental CTX (registry diffs, trust model summary) for step 2+.

## Invocation

- `autospec <spec_path> --properties <props_path> --trust-model <tm_path>`
- `autospec <spec_path> --properties <props_path> --trust-model <tm_path> --techniques tee-systems,distributed-consensus`
- `autospec status` to see current run state
- `autospec stop` to gracefully stop and finalize current run

Available domain technique files (in `$AUTOSPEC_ROOT/techniques/domains/`):
- `distributed-consensus`: quorum exploitation, fast path, speculative execution, batching, pipelining, view change
- `tee-systems`: non-equivocation elimination, signature elimination, Byzantine-to-crash reduction, monotonic counters, adaptive quorums
- Custom domain files can be added following `$AUTOSPEC_ROOT/techniques/extraction-guide.md`
