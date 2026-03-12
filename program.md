# AutoSpec: Formal Specification Auto-Research System

## Overview

AutoSpec takes a formal specification (TLA+, Lean, ProVerif) and iteratively improves it through autonomous agent rounds. Improvements span structural optimization, simplification, security hardening, and novel technique discovery. All changes are verified against a deterministic hard gate (model checker / proof assistant) and assessed by sycophancy-aware agent triads.

The system is not a simplicity seeker. It is a structural optimizer that discovers and applies techniques to improve safety, liveness, efficiency, communication complexity, cryptographic assumptions, and any other dimension it can find, including dimensions not anticipated at design time.

---

## 1. Inputs

- `spec`: the formal specification (TLA+/Lean/ProVerif source files)
- `properties`: a list of properties that MUST be preserved. Each property has:
  - `id`: unique identifier
  - `statement`: the formal property
  - `essence`: plain-language description of what the property protects. The essence is the invariant, not the exact formulation. Properties may be rewritten, split, merged, or strengthened, but the essence must survive.
  - `type`: safety | liveness | security
- `trust_model`: what the system can assume (e.g. TEE guarantees, authenticated channels, honest majority). This is critical because techniques that exploit trust assumptions need to know what's assumed.
- `config`:
  - `P`: steps without progress before escalation to paper search (default: 5)
  - `S`: steps with papers before next escalation tier (default: 3)
  - `F`: checkpoint frequency in steps (default: 5)
  - `M`: max historical journals to load on ambiguity (default: 3)

---

## 2. Master Loop

```
initialize:
  compartmentalize(spec) -> compartments[], intersections[]
  seed techniques registry from spec domain
  step = 0

loop:
  step += 1

  ctx = build_context(step)

  for each compartment in parallel:
    run_improvement_cycle(compartment, ctx)

  process_intersection_queues()

  if step % F == 0:
    write_checkpoint()

  if should_escalate():
    escalate()

  if exit_condition():
    finalize()
    break
```

---

## 3. Compartmentalization Algorithm

See `compartmentalization.md` for the full algorithm. Summary of decision criteria:

### 3.1 What makes a compartment

A compartment is a maximal group of spec actions (TLA+ actions, Lean definitions, ProVerif processes) that:

1. Share a **tightly coupled variable set**: the actions read AND write a common set of state variables, and removing any action from the group would break an invariant over those variables.
2. Have **minimal outgoing coupling**: the group's interaction with variables outside the group is limited to a well-defined interface (see intersections below).
3. Represent a **coherent functional unit**: the actions together implement a recognizable protocol phase, subsystem, or mechanism.

### 3.2 What makes an intersection

An intersection between compartments A and B exists when:

- A writes variable(s) that B reads, or vice versa.
- There exists at least one property whose verification requires reasoning about actions in both A and B.

An intersection is characterized by:
- `shared_vars`: the variables involved
- `directionality`: A->B, B->A, or bidirectional
- `spanning_properties`: properties that cross this intersection
- `coupling_strength`: weak (read-only sharing), medium (one-way write), strong (bidirectional write)

### 3.3 When NOT to compartmentalize

Fall back to single-compartment mode when:
- More than 60% of variables are touched by more than 60% of actions (spec is monolithic).
- The compartmentalization produces compartments where every compartment has intersections with every other compartment (fully connected graph).
- The spec is under 100 lines (overhead exceeds benefit).

The compartmentalizing agent MUST output its reasoning for the split, including variable-to-action mappings and coupling analysis. If uncertain, it flags ambiguity and a triad decides.

### 3.4 Target: one intersection per compartment pair

Ideally each compartment pair shares at most one intersection. If analysis reveals multiple intersections between the same pair, the agent must either:
- Merge them into a single intersection with a unified interface, or
- Re-split the compartments to achieve cleaner boundaries, or
- Flag for triad review if neither option works cleanly.

---

## 4. Context Building (CTX)

Context for step N of compartment C:

### 4.1 Base context (always included)
- Current spec for compartment C
- Properties relevant to compartment C (including spanning properties from intersections)
- Trust model
- Techniques registry (full)

### 4.2 Journal context (sliding window)
- Last OK journal for compartment C (the most recent successful step)
- All FAIL journals between that last OK and current step
- This gives the agent: "here's where we are, here's what didn't work since"

### 4.3 Extended context (loaded on demand)
During a step, if the improvement triad encounters ambiguity (proposer and reviewer disagree on whether a precondition holds, or the technique's applicability is unclear), the triad MAY request:
- Last M additional journals for compartment C not already in context
- Last journal checkpoint for compartment C

This is a pull, not a push. Context stays minimal unless agents need more.

### 4.4 Escalation context
When in paper-search escalation mode, context additionally includes:
- Extracted technique summaries from fetched papers
- The specific structural bottleneck that triggered escalation (from FAIL journal analysis)

---

## 5. Improvement Cycle (per compartment)

### 5.1 Proposal

The **proposer agent** receives the CTX and produces a proposal:

```
{
  technique: "<name from registry OR 'novel'>",
  target_actions: ["action1", "action2"],
  claim: "<falsifiable statement about what improves and why>",
  preconditions: "<why this technique applies here>",
  diff: "<the actual spec changes>",
  structural_delta: "<what dimension improves: communication complexity, round count,
                      cryptographic assumptions, redundancy removal, etc.>"
}
```

The `structural_delta` field is free-form. The proposer is not limited to predefined optimization dimensions. If it discovers something new to optimize, it names and describes it.

### 5.2 Review

The **reviewer agent** receives the proposal + CTX (independently, not the proposer's reasoning) and must:

1. Verify preconditions: does the technique actually apply? Do the trust model assumptions hold?
2. Attack the claim: find a counterexample, a case where the claimed improvement doesn't hold, or a hidden regression.
3. Check for property essence violations: does any property's essence get weakened?
4. Output: APPROVE with evidence, or REJECT with specific counterargument.

### 5.3 Judgment

The **judge agent** receives: the proposal, the review, and the CTX. It does NOT see internal reasoning of either agent. It rules:

- **ACCEPT**: the claim holds, the review's objections (if any) don't invalidate it. Proceed to hard gate.
- **REJECT**: the review found a real problem. Log as FAIL journal.
- **REVISE**: the core idea has merit but the specific implementation needs adjustment. Send back to proposer with the judge's guidance. Max 2 revision rounds, then force ACCEPT or REJECT.

### 5.4 Hard gate

If the triad ACCEPTs, apply the diff to the spec and run the deterministic verifier:

- **TLA+**: run TLC. All properties must pass. Record state space size.
- **Lean**: type-check the modified proof. All theorems must hold.
- **ProVerif**: verify all queries pass.

If the hard gate fails: FAIL journal, revert changes. The counterexample from the model checker goes into the journal (this is gold for future attempts).

### 5.5 Structural verification

If the hard gate passes, a second triad verifies the structural claim:

- The proposer claimed "communication reduced from O(n^2) to O(n)". Does the diff actually achieve this?
- The proposer claimed "TEE trust makes mechanism X redundant". Is X actually fully subsumed by the TEE guarantee?

This triad works from the diff + the claim + the spec. It must produce a verdict with spec-level evidence (action names, variable references, state counts).

If structural verification fails: the change still passed the hard gate, so correctness is fine, but the claimed improvement is bogus. Log as FAIL journal with "hard gate passed but structural claim unsubstantiated." This prevents the system from accumulating changes that don't actually improve anything.

### 5.6 Journal entry

After each step, write a journal entry:

```
{
  step: N,
  compartment: C,
  status: OK | FAIL,
  technique_used: "<name or 'novel'>",
  claim: "<the falsifiable claim>",
  structural_delta: "<what was claimed to improve>",
  diff: "<the changes, or attempted changes>",
  hard_gate_result: { passed: bool, state_space: int, counterexample: ... },
  structural_verification: { passed: bool, evidence: "..." },
  failure_reason: "<if FAIL, why specifically>",
  model_checker_output: "<if relevant, the TLC/Lean/ProVerif output>"
}
```

---

## 6. Intersection Pipeline

### 6.1 Flow

When a compartment improvement step produces an ACCEPT+hard-gate-pass result that affects intersection variables:

1. The compartment agent pushes an **intersection update** to the intersection's queue.
2. If the intersection agent is idle, it picks up the update immediately.
3. If the intersection agent is busy, the update is queued.

### 6.2 Queue management

When queue length > 1:
- **Compatible updates** (touch disjoint variables within the intersection, or are commutative): squash into a single update.
- **Conflicting updates** (both modify the same intersection variable in incompatible ways): launch a resolution triad. The proposer proposes a reconciliation, the reviewer checks it doesn't break either compartment's properties, the judge rules.

### 6.3 Intersection agent processing

For each update (or squashed batch):

1. Apply the intersection changes.
2. Run the hard gate on the FULL spec (all compartments + intersections) to verify no cross-compartment property breaks.
3. If it passes, commit. If it fails, the intersection agent determines which compartment's change is incompatible, reverts that change, and sends a FAIL signal back to that compartment with the cross-compartment counterexample.

### 6.4 Broader spec consistency

After every intersection commit, queue a **full-spec consistency check** in the outer orchestrator. If multiple intersection commits are pending, batch them. The full-spec check runs TLC/Lean/ProVerif on the entire assembled spec. This is the ultimate hard gate.

---

## 7. Techniques Registry

### 7.1 Schema

See `techniques/registry-schema.md`. Each entry:

```
{
  id: unique,
  name: "aggregate signatures",
  class: "known" | "candidate-novel" | "novel",
  source: { type: "paper" | "agent-discovered", ref: "..." },
  description: "replace individual signatures with aggregated signature to reduce message size",
  optimizes: "communication complexity, message size",
  preconditions: "signature scheme supports aggregation, messages are from distinct signers",
  known_failures: ["attempted in step X of run Y, failed because Z"],
  applicability_notes: "...",
  generalized_form: "when M independent signatures are required and the scheme supports aggregation,
                      replace M signatures with 1 aggregate. Reduces O(M) to O(1) in signature size."
}
```

### 7.2 Growth

Three sources:

1. **Paper extraction**: during escalation, papers are fetched and techniques are extracted into the registry with `class: "known"` and paper citation.
2. **Successful steps**: when a step gets OK status, the judge extracts the technique. If it matches a registry entry, annotate that entry with the new application. If it doesn't match any entry, add as `class: "candidate-novel"`.
3. **Failed steps (inverse learning)**: add to `known_failures` of the attempted technique. If the technique doesn't exist in the registry (agent tried something truly new and it failed), still add it with the failure record.

### 7.3 Novel technique verification

When an entry has `class: "candidate-novel"`:

1. **Novelty check**: an agent searches papers/prior work for the same technique. If found, reclassify to `class: "known"` with citation.
2. **Generality check**: can the technique be stated abstractly beyond this specific spec? The agent attempts to write a `generalized_form`. If the technique is inherently spec-specific, mark it as such (still valuable, but not a reusable contribution).
3. **Verification triad**: reviews the generalized form. Is the abstraction sound or overfitted?

If it survives all three: promote to `class: "novel"` with full provenance (run, step, compartment, original diff, generalized form, verification trail).

---

## 8. Escalation Ladder

### 8.1 Detecting "no progress"

No progress for compartment C means: the last P consecutive steps for C all have status FAIL, OR all have status OK but with no measurable structural improvement (changes are lateral moves).

"No measurable structural improvement" is determined by: state space didn't shrink, spec didn't get shorter, no structural claim was substantiated by the structural verification triad.

### 8.2 Tier 1: Paper search (P steps without progress)

1. Analyze the FAIL journals to identify the structural bottleneck: what were agents trying to improve? What kept failing?
2. Construct targeted search queries from: the bottleneck description + techniques that were tried and failed + the spec domain.
3. Fetch papers. Extract techniques into registry.
4. Resume improvement cycles with enriched registry for S steps.

### 8.3 Tier 2: Paper synthesis (P + S steps without progress)

1. Using fetched papers + the OK checkpoint (successful findings so far) + novel techniques discovered, write synthesis documents.
2. These are structured analyses: "given the current spec state and known techniques, here are unexplored directions."
3. Feed synthesis documents into CTX for the next S steps.

### 8.4 Tier 3: Exit (P + 2S steps without progress)

The system has exhausted its improvement capacity. Exit successfully.

Output:
- Final optimized spec
- Complete journal history
- Techniques registry (including novel discoveries)
- OK checkpoint (cumulative successful findings)
- Summary: what changed from the original spec, organized by structural dimension

---

## 9. Checkpoints

### 9.1 Frequency

Every F steps per compartment.

### 9.2 Structure

Two checkpoint files per compartment:

1. **Full checkpoint**: previous full checkpoint + all journals since last checkpoint (OK and FAIL). This is the complete picture.
2. **OK checkpoint**: previous OK checkpoint + only OK journals since last checkpoint. This is the "successful research findings" document, a cumulative record of what worked.

### 9.3 Checkpoint writing

A dedicated agent reads the previous checkpoint + new journals and produces a coherent summary, not just concatenation. It identifies themes, tracks which structural dimensions have seen the most progress, and flags areas that have stalled.

---

## 10. Dashboard

See `dashboard/` for implementation. The locally-served web UI provides:

1. **Journal browser**: navigate all journals and checkpoints, filter by compartment, status, technique.
2. **Spec evolution view**: interactive visualization showing compartments, their intersections, and the changes at each step. Click a step to see the diff, the claim, and the verification result.
3. **Techniques map**: all techniques in the registry. For each: source (paper/discovered), times applied, success rate. Known vs. candidate-novel vs. novel clearly distinguished.
4. **Novelty tracker**: for each technique flagged as candidate-novel or novel, show the verification status, the generalized form, and inspiration sources.
5. **Live agent view**: which agents are currently running, on which compartment/intersection, what technique they're attempting.
6. **Progress metrics**: per-compartment and global progress over time. State space trajectory, spec size trajectory, structural improvements timeline.

---

## 11. Decision Reference

Every decision point in the system and how to resolve it:

| Decision | Criteria | Fallback |
|---|---|---|
| How to split into compartments | Variable coupling analysis (see section 3) | Single-compartment mode |
| Whether a technique applies | Preconditions from registry checked against spec + trust model | Triad decides |
| Whether a structural claim holds | Spec-level evidence from diff + actions | Triad decides |
| Whether two intersection updates conflict | Do they modify same variable in incompatible ways? | Resolution triad |
| Whether progress was made | Hard gate pass + substantiated structural claim | Not progress |
| What papers to search for | FAIL journal analysis -> bottleneck identification -> query construction | Broaden search terms |
| Whether a technique is novel | Paper search finds no match | Novelty verification pipeline |
| Whether to compartmentalize at all | Coupling density analysis (section 3.3) | Don't compartmentalize |
| Whether to accept a revision | Judge rules after max 2 revision rounds | Force ACCEPT or REJECT |
| When to write checkpoint | Every F steps (configurable) | - |
| When to exit | P + 2S steps without progress on ALL compartments | - |

---

## 12. Output Artifacts

When the system completes (tier 3 exit or user interrupt):

1. **Final spec**: the optimized formal specification.
2. **Delta report**: what changed from the original, organized by structural dimension, with evidence and technique references.
3. **Techniques registry**: all known + novel techniques discovered during the run.
4. **OK checkpoint (final)**: the cumulative successful research findings.
5. **Full journal history**: every step, every compartment, every decision.
6. **Novel contributions**: techniques classified as novel, with generalized forms and verification trails. These are the system's genuine research output.
