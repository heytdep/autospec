# Novel Contributions

## T_novel_001: Fill-Snapshot Collapse

**Status**: candidate-novel (pending verification pipeline)

**Discovery**: Run run_20260311_151358, Step 3, Compartment C1 (ce_core)

**Description**: When a protocol produces multiple typed effects atomically per event (e.g., MFR+Snapshot pair per fill), but no downstream consumer branches on the individual types (all consumers select by session+seq only), the multiple effects can be collapsed into a single effect. This reduces sequence-space consumption proportionally.

**Generalized Form**: For a protocol event E that atomically produces effects {e_1, ..., e_N} with distinct types but identical (session, seq_base+i) structure, if no consumer C in the protocol discriminates on type (i.e., all guards and invariants reference only session and seq fields), then E can produce a single effect e_1 with seq = seq_base. The remaining N-1 types become dead members of the type set.

**Preconditions**:
1. Downstream consumers are type-agnostic for the specific types being collapsed
2. The paired types serve no independent semantic role in guards, invariants, or branching logic
3. The protocol's seq-space is the bottleneck being optimized (finite MaxSeq)

**Applicability Beyond This Spec**: Any protocol with atomic multi-effect production where types are informational rather than control-flow-relevant. Common in financial systems (trade + settlement as paired effects), distributed databases (write + WAL entry as paired effects), event sourcing (command + event pairs).

**Evidence Trail**:
- Proposer traced all 6 references to "Snapshot" in the spec: zero type-discriminating guards
- Reviewer independently verified all downstream consumers (CEBackupApply, OMSConsumeCE, ArchiverIngestCE, ArchiverIngestCEFromBackup, CEViewChange) are type-agnostic
- Judge confirmed: no disputed claims, structural delta verified

**Verification Needed**:
- Novelty check: search for prior work on "effect type collapse" or "atomic pair reduction" in formal methods / protocol optimization literature
- Generality check: does the generalized form hold beyond this specific spec?
- Triad review of the generalized form
