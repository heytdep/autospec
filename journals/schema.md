# Journal and Checkpoint Schema

## Journal Entry

Written after every improvement step, regardless of outcome.

```json
{
  "run_id": "run_001",
  "step": 14,
  "compartment": "C2",
  "timestamp": "2026-03-10T14:23:00Z",
  "status": "OK | FAIL",

  "proposal": {
    "technique": "T003 or 'novel'",
    "technique_name": "human-readable name",
    "target_actions": ["ActionA", "ActionB"],
    "claim": "falsifiable statement about what improves and why",
    "preconditions": "why this technique applies here",
    "structural_delta": "free-form: what dimension improves",
    "diff": "the actual spec changes (unified diff format)"
  },

  "review": {
    "verdict": "APPROVE | REJECT",
    "argument": "the reviewer's core argument",
    "counterexample": "if REJECT, the specific counter",
    "property_concerns": ["any property essences potentially affected"]
  },

  "judgment": {
    "ruling": "ACCEPT | REJECT | REVISE",
    "reasoning": "judge's reasoning, referencing specific claims from proposal and review",
    "revision_round": "0 | 1 | 2 (if REVISE was used)"
  },

  "hard_gate": {
    "ran": true,
    "passed": true,
    "verifier": "TLC | Lean | ProVerif",
    "state_space_before": 142857,
    "state_space_after": 98304,
    "properties_checked": ["P1", "P2", "P3"],
    "counterexample": "null or the counterexample if failed"
  },

  "structural_verification": {
    "ran": true,
    "claim_substantiated": true,
    "evidence": "spec-level evidence supporting or refuting the structural claim"
  },

  "failure_reason": "null if OK. specific reason if FAIL: triad_rejected | hard_gate_failed | structural_claim_unsubstantiated",

  "technique_registry_update": {
    "action": "none | added | updated | failure_recorded",
    "technique_id": "T003 or new ID if added"
  }
}
```

## Journal File Organization

```
journals/
  run_001/
    C1/
      step_001.json
      step_002.json
      ...
      checkpoint_005.md        # full checkpoint at step 5
      checkpoint_005_ok.md     # OK-only checkpoint at step 5
      checkpoint_010.md
      checkpoint_010_ok.md
    C2/
      ...
    intersections/
      I1/
        update_001.json
        update_002.json
    full_spec/
      consistency_check_001.json
      consistency_check_002.json
```

## Checkpoint Format

### Full Checkpoint (every F steps)

Written by the checkpoint agent as a coherent narrative, not raw concatenation.

```markdown
# Checkpoint: C1, Step 10

## Previous checkpoint: Step 5

## Progress since last checkpoint
- Steps 6-10: 3 OK, 2 FAIL
- Techniques attempted: aggregate signatures (OK), threshold encryption (FAIL), ...
- State space trajectory: 142857 -> 130000 -> 98304

## Structural improvements achieved
- Communication per round: O(n^2) -> O(n) (step 7, aggregate signatures)
- Removed redundant authentication layer (step 9, TEE trust exploitation)

## Failed attempts and lessons
- Threshold encryption (step 8): precondition not met, requires honest majority > 2/3 but trust model only guarantees > 1/2
- ...

## Stalled areas
- Round complexity: 3 attempts, no improvement. Current: 4 rounds. Bottleneck appears to be leader election phase requiring 2 rounds minimum.

## Techniques registry updates
- T003 (aggregate signatures): new successful application recorded
- T_new_001 (candidate-novel): "lazy view change propagation" - discovered in step 9, pending verification
```

### OK Checkpoint

Same structure but only includes OK steps. This is the "successful research findings" document. It reads as a cumulative record of everything that worked, suitable for feeding into paper synthesis during escalation.
