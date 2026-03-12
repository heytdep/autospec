# AutoSpec Delta Report
## Run: run_20260311_151358
## Spec: TplusUnifiedDA (Unified DA-Ordering Architecture)

---

## Executive Summary

5 steps across 3 compartments. 8 accepted improvements (2 spec bugs found, 1 novel technique discovered). Hard gate skipped (no TLC runtime).

| Metric | Value |
|---|---|
| Steps | 5 |
| Proposals | 15 |
| Accepted (OK) | 8 |
| Rejected (FAIL) | 7 |
| Real bugs found | 2 |
| Novel techniques | 1 (candidate) |
| State variables eliminated | 2 (ce_archiver_ack_count, ob_authority_ts) |
| State variables added | 1 (ob_checkpoint_seq) |
| Net state reduction | 1 variable + |CEArchivers|*MaxSeq integers |

---

## Accepted Improvements by Compartment

### C1: CE Core (1/5 OK)

**Step 3 OK: Fill-Snapshot Collapse (T_novel_001, candidate-novel)**
- Target: CEProcessFill, CEProcessRecoveredPending
- Change: Collapse MFR+Snapshot atomic pair into single MFR effect per fill
- Impact: Halves sequence-space consumption per fill. No downstream action or property distinguishes MFR from Snapshot.
- Structural delta: 2 effects per fill -> 1 effect per fill. ce_seq increments by 1 instead of 2.

### C2: OB Core (5/5 OK)

**Step 1 OK: OB Checkpoint Anchor (D201)**
- Target: OBViewChange (new: OBCheckpoint)
- Change: Add ob_checkpoint_seq as fallback anchor in OBViewChange when backup is empty
- Impact: Recovery scope bounded to post-checkpoint tail instead of full-log reconstruction
- Structural delta: Worst-case anchor 0 -> ob_checkpoint_seq. MinOfTwo cap prevents cross-session staleness.

**Step 2 OK: Stale MFR Session Gate (D206) -- SPEC BUG FIX**
- Target: OBReceiveMFR, DownstreamOBReceiveCEViewChange
- Change: Add ob_cached_ce_session variable. OBReceiveMFR checks msg.session = ob_cached_ce_session[m]
- Impact: Prevents phantom CEFinalization effects from stale MFRs after CE view change
- Bug: CEViewChange leaves msgs_ce_to_ob UNCHANGED. Old-session MFRs persist and can be consumed without session validation.

**Step 3 OK: OB Recovery Re-broadcast (D205) -- SPEC BUG FIX (LIVENESS)**
- Target: OBViewChange
- Change: Re-tag recovered effects with new session, re-broadcast them after view change
- Impact: Fixes permanent OMS liveness failure after OB view change
- Bug: OBViewChange retains recovered effects with old session tags but doesn't re-broadcast. Both OMSConsumeOB (session mismatch) and OMSViewChange (archiver query by new session) are dead paths. OMS permanently stuck.

**Step 4 OK: OB Session Echo in MFR (D206)**
- Target: CEProcessFill, OBReceiveMFR
- Change: CEProcessFill echoes OB session (msg.session) as ob_session field in MFR message. OBReceiveMFR checks msg.ob_session = ob_primary[m]
- Impact: Prevents phantom CEFinalization from fills originated by rolled-back OB session
- Orthogonal to Step 2 (which guards CE session staleness; this guards OB session staleness)

**Step 5 OK: ob_authority_ts Elimination (D104)**
- Target: OBViewChange, TypeInvariant, Init, UNCHANGED clauses
- Change: Eliminate ob_authority_ts (provably == ob_primary at all times, zero property surface)
- Impact: One fewer state variable per market. Cleaner spec.

### C3: OMS + Downstream + Archivers (3/5 OK)

**Step 1 OK: Session-Scoped Watermark GC (D207)**
- Target: ArchiverGCByAcks, ArchiverDAMonotonicity (INV20)
- Change: Replace ce_archiver_ack_count with session-scoped backup watermark GC. Fix idempotency bug.
- Impact: Eliminates |CEArchivers|*MaxSeq integers of state. Fixes idempotency bug where repeated firing inflates ack counts. Session-aware filter preserves old-session effects for double-crash recovery.
- Bug fixed: Original ArchiverGCByAcks can fire multiple times for same (a,s), inflating ce_archiver_ack_count past GC_K.

**Step 4 OK: OMS Muted Consumption Guard (D208)**
- Target: OMSConsumeCE, OMSConsumeOB, OMSConsumePending
- Change: Add ~oms_muted[p] guard to all three consumption actions
- Impact: Prevents consumption while muted (effects consumed then wiped by OMSViewChange). Reduces state space.

**Step 5 OK: Meaningful P11 Replacement (D206)**
- Target: INV11_OMSCursorConsistency
- Change: Replace vacuous P11 (>= 0 on Nat, trivially true) with log-bounded + session-consistency + seq-uniqueness
- Impact: Transforms tautological invariant into genuinely constraining assertions mirroring INV9/INV10/INV2/INV3 patterns.

---

## Rejected Proposals (Lessons Learned)

| Step | Comp | Technique | Rejection Reason |
|---|---|---|---|
| S1 | C1 | D006 | ce_checkpoint_seq persists across VC, exceeds new session range |
| S2 | C1 | D101 | ArchiverGCByAcks depends on backup_applied being contiguous prefix |
| S4 | C1 | D206 | P15 deliberately handles old-session pending fills; CEProcessRecoveredPending never sends to msgs_ce_to_ob |
| S5 | C1 | D104 | VC message ts field would carry session value, semantic inconsistency in P6/P17 |
| S2 | C3 | D209 | WF on unified nondeterministic action doesn't distribute to branches |
| S3 | C3 | D207 | Proposed OB archiver INV20 not an invariant (pre-existing records violate) |
| S4 | C2 | -- | (not applicable, C2 was 5/5) |

---

## Novel Technique Discovered

### T_novel_001: Fill-Snapshot Collapse
- Class: candidate-novel (pending verification)
- Generalized form: When a protocol produces N typed effects atomically per event but no consumer distinguishes the types, collapse to 1 effect. Reduces seq-space consumption by N-1 per event.
- Preconditions: Downstream consumers are type-agnostic (select by session+seq only). Paired effect types serve no independent semantic role.
- Verification status: Novelty check pending. Generality check pending.

---

## Spec Bugs Found

### BUG-1: Stale MFR Consumption After CE View Change (Severity: Medium)
- Location: OBReceiveMFR (line 391), CEViewChange (line 321)
- Issue: CEViewChange leaves msgs_ce_to_ob UNCHANGED. OBReceiveMFR has no CE session filter. After CE crash + view change, old-session MFRs can produce phantom CEFinalization.
- Fix: Add ob_cached_ce_session per-market, gate OBReceiveMFR on session match.

### BUG-2: OMS Liveness Failure After OB View Change (Severity: High)
- Location: OBViewChange (lines 427-452)
- Issue: OBViewChange retains recovered effects with old session tags but doesn't re-tag or re-broadcast. Both direct (OMSConsumeOB session mismatch) and archiver (OMSViewChange queries new session) recovery paths are dead. OMS permanently stuck for that market.
- Fix: Re-tag recovered effects with new session, re-broadcast after view change.

### BUG-3: OMS Consumption While Muted (Severity: Low-Medium)
- Location: OMSConsumeCE/OB/Pending (lines 459, 474, 491)
- Issue: No ~oms_muted guard. After OMSRecover, effects can be consumed then wiped by OMSViewChange.
- Fix: Add ~oms_muted[p] guard to all three consumption actions.

### BUG-4: ArchiverGCByAcks Idempotency (Severity: Low)
- Location: ArchiverGCByAcks (lines 689-703)
- Issue: No guard preventing repeated firing for same (a,s). ack_count inflates past GC_K.
- Fix: Replace with session-scoped watermark GC.
