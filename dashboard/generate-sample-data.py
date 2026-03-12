#!/usr/bin/env python3
"""Generate sample data for dashboard testing."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "runs" / "sample_run"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def main():
    # compartments
    compartments = {
        "mode": "multi-compartment",
        "compartments": [
            {
                "id": "C1", "name": "leader_election",
                "actions": ["ElectLeader", "HandleVote", "DeclareLeader", "TimeoutElection"],
                "local_vars": ["votes", "leader", "election_round", "candidates"],
                "local_properties": ["LeaderUniqueness", "ElectionTermination"],
                "rationale": "closed loop over election state, only leader var read externally"
            },
            {
                "id": "C2", "name": "log_replication",
                "actions": ["AppendEntry", "ReplicateEntry", "AckEntry", "CommitEntry", "TruncateLog"],
                "local_vars": ["log", "commit_index", "match_index", "next_index"],
                "local_properties": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"],
                "rationale": "core replication logic, reads leader from C1, log shared with C3 for view change"
            },
            {
                "id": "C3", "name": "view_change",
                "actions": ["InitiateViewChange", "CollectViewChangeMessages", "InstallNewView", "RollbackActions"],
                "local_vars": ["view_number", "vc_messages", "new_view_proof", "rollback_set"],
                "local_properties": ["ViewMonotonicity", "RollbackSafety"],
                "rationale": "view change protocol, reads log from C2 for rollback decisions"
            }
        ],
        "intersections": [
            {
                "id": "I1", "compartments": ["C1", "C2"],
                "shared_vars": ["leader"],
                "directionality": "C1 writes, C2 reads",
                "spanning_properties": ["LeaderConsistency"],
                "coupling_strength": "medium"
            },
            {
                "id": "I2", "compartments": ["C2", "C3"],
                "shared_vars": ["log"],
                "directionality": "bidirectional",
                "spanning_properties": ["ViewChangeLogIntegrity"],
                "coupling_strength": "strong"
            }
        ],
        "topology_summary": "3 compartments, 2 intersections, linear chain C1-C2-C3, one strong coupling (C2-C3)"
    }
    write_json(RUN_DIR / "compartments.json", compartments)

    # techniques registry
    registry = [
        {
            "id": "T001", "name": "signature aggregation", "class": "known",
            "source": {"type": "paper", "ref": "Boneh et al. 2003"},
            "description": "replace individual signatures with aggregate signature",
            "optimizes": ["communication complexity", "message size"],
            "preconditions": ["signature scheme supports aggregation", "distinct signers"],
            "generalized_form": "when n signatures needed, replace with 1 aggregate",
            "applications": [
                {"run": "sample_run", "step": 3, "compartment": "C2", "outcome": "OK", "notes": "applied to AckEntry, reduced ack size from O(n) sigs to O(1)"},
                {"run": "sample_run", "step": 9, "compartment": "C3", "outcome": "OK", "notes": "applied to view change proof messages"}
            ],
            "known_failures": [],
            "verification_trail": None
        },
        {
            "id": "T002", "name": "round collapsing", "class": "known",
            "source": {"type": "paper", "ref": "various consensus literature"},
            "description": "merge consecutive communication rounds when second doesn't depend on full first-round results",
            "optimizes": ["latency", "round complexity"],
            "preconditions": ["consecutive rounds where R2 messages depend only on local R1 result"],
            "generalized_form": "if R2 can begin before R1 completes, pipeline or merge",
            "applications": [
                {"run": "sample_run", "step": 5, "compartment": "C1", "outcome": "FAIL", "notes": "election requires all votes before declaring"},
                {"run": "sample_run", "step": 11, "compartment": "C2", "outcome": "OK", "notes": "pipelined append+replicate"}
            ],
            "known_failures": [
                {"run": "sample_run", "step": 5, "compartment": "C1", "reason": "precondition not met: DeclareLeader needs full vote count"}
            ],
            "verification_trail": None
        },
        {
            "id": "T003", "name": "trust assumption exploitation (TEE)", "class": "known",
            "source": {"type": "paper", "ref": "TEE-based consensus literature"},
            "description": "remove protocol mechanisms redundant under TEE guarantees",
            "optimizes": ["protocol complexity", "round count", "message count"],
            "preconditions": ["TEE trust model provides equivalent guarantees"],
            "generalized_form": "for each mechanism M, if TEE already excludes the threat M mitigates, remove M",
            "applications": [
                {"run": "sample_run", "step": 7, "compartment": "C1", "outcome": "OK", "notes": "removed vote authentication round"},
                {"run": "sample_run", "step": 13, "compartment": "C3", "outcome": "OK", "notes": "simplified view change proof"}
            ],
            "known_failures": [],
            "verification_trail": None
        },
        {
            "id": "T004", "name": "redundant mechanism elimination", "class": "known",
            "source": {"type": "paper", "ref": "standard formal methods practice"},
            "description": "remove mechanisms whose guarantees are subsumed by others",
            "optimizes": ["spec simplicity", "protocol complexity"],
            "preconditions": ["another mechanism or trust assumption provides the same guarantee"],
            "generalized_form": "if mechanism M guarantees property P and P is already guaranteed elsewhere, remove M",
            "applications": [
                {"run": "sample_run", "step": 2, "compartment": "C2", "outcome": "FAIL", "notes": "tried to remove TruncateLog"},
                {"run": "sample_run", "step": 8, "compartment": "C2", "outcome": "OK", "notes": "removed duplicate commit confirmation"}
            ],
            "known_failures": [
                {"run": "sample_run", "step": 2, "compartment": "C2", "reason": "TruncateLog not redundant, needed by C3 for surgical rollback"}
            ],
            "verification_trail": None
        },
        {
            "id": "T005", "name": "state variable elimination", "class": "known",
            "source": {"type": "paper", "ref": "standard formal methods practice"},
            "description": "remove derived state variables, replace reads with derivation",
            "optimizes": ["state space size", "spec simplicity"],
            "preconditions": ["variable is a function of other variables at all reachable states"],
            "generalized_form": "if v = f(v1,...,vn) is invariant, eliminate v and inline f",
            "applications": [
                {"run": "sample_run", "step": 4, "compartment": "C2", "outcome": "OK", "notes": "eliminated next_index, derivable from match_index + 1"}
            ],
            "known_failures": [],
            "verification_trail": None
        },
        {
            "id": "T006", "name": "lazy view change propagation", "class": "candidate-novel",
            "source": {"type": "agent-discovered", "ref": "sample_run/step_10/C3"},
            "description": "delay view change message propagation until new leader pulls on demand instead of eager broadcast",
            "optimizes": ["communication complexity during view change", "view change latency"],
            "preconditions": ["new leader can reconstruct state from quorum subset", "TEE prevents equivocation during delay"],
            "generalized_form": "when a protocol phase broadcasts state that the next phase only partially reads, defer broadcast and pull on demand. requires consistent pull (TEE or quorum intersection).",
            "applications": [
                {"run": "sample_run", "step": 10, "compartment": "C3", "outcome": "OK", "notes": "reduced VC broadcast from O(n^2) to O(n)"}
            ],
            "known_failures": [],
            "verification_trail": {
                "novelty_check": "no_prior_work_found",
                "generality_check": "generalizable",
                "triad_review": "pending",
                "prior_work_ref": None
            }
        },
        {
            "id": "T007", "name": "action merging", "class": "known",
            "source": {"type": "paper", "ref": "Lamport, Specifying Systems, 2002"},
            "description": "merge fine-grained actions into coarser one when intermediate states are unobservable",
            "optimizes": ["state space size", "spec simplicity"],
            "preconditions": ["intermediate state not referenced by any property", "merged action atomic in execution model"],
            "generalized_form": "if A1;A2 always sequential and no property references intermediate state, replace with A12",
            "applications": [
                {"run": "sample_run", "step": 6, "compartment": "C1", "outcome": "FAIL", "notes": "HandleVote+DeclareLeader not always sequential"},
                {"run": "sample_run", "step": 12, "compartment": "C2", "outcome": "OK", "notes": "merged local replicate+ack"}
            ],
            "known_failures": [
                {"run": "sample_run", "step": 6, "compartment": "C1", "reason": "DeclareLeader guarded by quorum, not always sequential after HandleVote"}
            ],
            "verification_trail": None
        },
        {
            "id": "T008", "name": "quorum-adaptive leader election", "class": "novel",
            "source": {"type": "agent-discovered", "ref": "sample_run/step_14/C1"},
            "description": "adapt election quorum size based on TEE-attested liveness of replicas",
            "optimizes": ["election latency", "fault tolerance flexibility"],
            "preconditions": ["TEE can attest replica liveness", "quorum intersection property holds at minimum quorum"],
            "generalized_form": "when trust model provides liveness attestation, dynamically adjust quorum thresholds while preserving quorum intersection for safety.",
            "applications": [
                {"run": "sample_run", "step": 14, "compartment": "C1", "outcome": "OK", "notes": "reduced expected election latency ~40% in high-availability scenarios"}
            ],
            "known_failures": [],
            "verification_trail": {
                "novelty_check": "confirmed_novel",
                "generality_check": "generalizable",
                "triad_review": "approved",
                "prior_work_ref": None
            }
        }
    ]
    write_json(RUN_DIR / "registry.json", registry)

    # journals
    journals_data = [
        {"run_id": "sample_run", "step": 1, "compartment": "C1", "timestamp": "2026-03-10T10:00:00Z", "status": "OK",
         "proposal": {"technique": "U001", "technique_name": "symmetry reduction", "target_actions": ["ElectLeader", "HandleVote"],
                       "claim": "replicas are interchangeable in election, symmetry reduces state space by ~6x for 3 replicas",
                       "structural_delta": "state space reduction via replica symmetry: 3! = 6x reduction",
                       "diff": "--- a/leader_election.tla\n+++ b/leader_election.tla\n@@ -5,3 +5,4 @@\n CONSTANT Replicas\n+SYMMETRY ReplicaSymmetry\n+ReplicaSymmetry == Permutations(Replicas)"},
         "review": {"verdict": "APPROVE", "argument": "replicas are indeed symmetric in election, no replica-specific logic"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "symmetry holds, replicas have identical behavior in election actions"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 142857, "state_space_after": 23809,
                       "properties_checked": ["LeaderUniqueness", "ElectionTermination"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "state space reduced from 142857 to 23809, ratio 6.0x matching 3! prediction"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "U001"}},

        {"run_id": "sample_run", "step": 2, "compartment": "C2", "timestamp": "2026-03-10T10:05:00Z", "status": "FAIL",
         "proposal": {"technique": "T004", "technique_name": "redundant mechanism elimination", "target_actions": ["TruncateLog"],
                       "claim": "TruncateLog is redundant because CommitEntry already manages log consistency",
                       "structural_delta": "remove one action, simplify log management",
                       "diff": "--- a/log_replication.tla\n+++ b/log_replication.tla\n@@ -30,8 +30,0 @@\n-TruncateLog(replica, index) ==\n-  /\\ log' = [log EXCEPT ![replica] = SubSeq(log[replica], 1, index)]"},
         "review": {"verdict": "REJECT", "argument": "TruncateLog is used by C3 for surgical rollback. removing it breaks ViewChangeLogIntegrity.", "counterexample": "view change needs to truncate divergent entries from old leader"},
         "judgment": {"ruling": "REJECT", "reasoning": "TruncateLog is not redundant, needed by C3 for rollback"},
         "hard_gate": {"ran": False, "passed": False, "verifier": "TLC", "state_space_before": 98304, "state_space_after": None,
                       "properties_checked": [], "counterexample": None},
         "structural_verification": {"ran": False, "claim_substantiated": False, "evidence": None},
         "failure_reason": "triad_rejected",
         "technique_registry_update": {"action": "failure_recorded", "technique_id": "T004"}},

        {"run_id": "sample_run", "step": 3, "compartment": "C2", "timestamp": "2026-03-10T10:10:00Z", "status": "OK",
         "proposal": {"technique": "T001", "technique_name": "signature aggregation", "target_actions": ["AckEntry"],
                       "claim": "aggregate ack signatures: O(n) individual sigs to O(1) aggregate",
                       "structural_delta": "communication complexity: ack messages shrink from O(n) sigs to O(1)",
                       "diff": "--- a/log_replication.tla\n+++ b/log_replication.tla\n@@ -20,5 +20,5 @@\n AckEntry(replica, entry_id) ==\n-  /\\ acks' = [acks EXCEPT ![entry_id] = acks[entry_id] \\cup {<<replica, Sign(replica, entry_id)>>}]\n+  /\\ acks' = [acks EXCEPT ![entry_id] = AggregateSig(acks[entry_id], replica, entry_id)]"},
         "review": {"verdict": "APPROVE", "argument": "aggregation applies cleanly, distinct signers on same entry_id"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "preconditions met, straightforward application"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 98304, "state_space_after": 87210,
                       "properties_checked": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "AckEntry produces single aggregate instead of set of individual sigs"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T001"}},

        {"run_id": "sample_run", "step": 4, "compartment": "C2", "timestamp": "2026-03-10T10:15:00Z", "status": "OK",
         "proposal": {"technique": "T005", "technique_name": "state variable elimination", "target_actions": ["ReplicateEntry", "AppendEntry"],
                       "claim": "next_index is always match_index + 1, eliminating it reduces state space",
                       "structural_delta": "state space: remove one variable, reduce by factor of domain(next_index)",
                       "diff": "--- a/log_replication.tla\n+++ b/log_replication.tla\n VARIABLES log, commit_index, match_index\n-VARIABLES next_index"},
         "review": {"verdict": "APPROVE", "argument": "next_index = match_index + 1 is invariant in all reachable states"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "derivability confirmed"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 87210, "state_space_after": 54120,
                       "properties_checked": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "state space reduced from 87210 to 54120"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T005"}},

        {"run_id": "sample_run", "step": 5, "compartment": "C1", "timestamp": "2026-03-10T10:20:00Z", "status": "FAIL",
         "proposal": {"technique": "T002", "technique_name": "round collapsing", "target_actions": ["HandleVote", "DeclareLeader"],
                       "claim": "collapse vote collection and leader declaration into single round",
                       "structural_delta": "round complexity: 2 rounds -> 1",
                       "diff": "...collapsed election..."},
         "review": {"verdict": "REJECT", "argument": "DeclareLeader requires quorum observation, can't collapse", "counterexample": "with 5 replicas, partial vote count leads to premature declaration"},
         "judgment": {"ruling": "REJECT", "reasoning": "election inherently needs separate collection and declaration phases"},
         "hard_gate": {"ran": False, "passed": False, "verifier": "TLC", "state_space_before": 23809, "state_space_after": None,
                       "properties_checked": [], "counterexample": None},
         "structural_verification": {"ran": False, "claim_substantiated": False, "evidence": None},
         "failure_reason": "triad_rejected",
         "technique_registry_update": {"action": "failure_recorded", "technique_id": "T002"}},

        {"run_id": "sample_run", "step": 6, "compartment": "C1", "timestamp": "2026-03-10T10:25:00Z", "status": "FAIL",
         "proposal": {"technique": "T007", "technique_name": "action merging", "target_actions": ["HandleVote", "DeclareLeader"],
                       "claim": "merge HandleVote and DeclareLeader since they always execute sequentially",
                       "structural_delta": "spec simplicity: 2 actions -> 1",
                       "diff": "...merged actions..."},
         "review": {"verdict": "REJECT", "argument": "HandleVote fires many times before DeclareLeader fires once. Not always sequential."},
         "judgment": {"ruling": "REJECT", "reasoning": "precondition violated: different firing patterns"},
         "hard_gate": {"ran": False, "passed": False, "verifier": "TLC", "state_space_before": 23809, "state_space_after": None,
                       "properties_checked": [], "counterexample": None},
         "structural_verification": {"ran": False, "claim_substantiated": False, "evidence": None},
         "failure_reason": "triad_rejected",
         "technique_registry_update": {"action": "failure_recorded", "technique_id": "T007"}},

        {"run_id": "sample_run", "step": 7, "compartment": "C1", "timestamp": "2026-03-10T10:30:00Z", "status": "OK",
         "proposal": {"technique": "T003", "technique_name": "trust assumption exploitation (TEE)", "target_actions": ["HandleVote", "ElectLeader"],
                       "claim": "TEE non-equivocation makes vote signatures redundant",
                       "structural_delta": "message size: remove sig from votes. protocol complexity: remove verification step",
                       "diff": "--- a/leader_election.tla\n+++ b/leader_election.tla\n HandleVote(replica, candidate) ==\n-  /\\ VerifySignature(replica, <<\"vote\", candidate>>)\n-  /\\ votes' = [votes EXCEPT ![candidate] = votes[candidate] \\cup {<<replica, Sign(...)>>}]\n+  /\\ votes' = [votes EXCEPT ![candidate] = votes[candidate] \\cup {replica}]"},
         "review": {"verdict": "APPROVE", "argument": "TEE non-equivocation prevents conflicting votes. signature was only for authenticity, which TEE provides."},
         "judgment": {"ruling": "ACCEPT", "reasoning": "trust model explicitly includes TEE non-equivocation"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 23809, "state_space_after": 18500,
                       "properties_checked": ["LeaderUniqueness", "ElectionTermination"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "vote messages no longer carry signatures"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T003"}},

        {"run_id": "sample_run", "step": 8, "compartment": "C2", "timestamp": "2026-03-10T10:35:00Z", "status": "OK",
         "proposal": {"technique": "T004", "technique_name": "redundant mechanism elimination", "target_actions": ["CommitEntry"],
                       "claim": "commit broadcast redundant: replicas infer commit from ack quorum + aggregate sig",
                       "structural_delta": "communication: remove one O(n) broadcast round per commit",
                       "diff": "--- a/log_replication.tla\n+++ b/log_replication.tla\n CommitEntry(leader, entry_id) ==\n   /\\ Cardinality(acks[entry_id]) * 2 > Cardinality(Replicas)\n   /\\ commit_index' = [commit_index EXCEPT ![leader] = entry_id]\n-  /\\ BroadcastCommit(leader, entry_id)"},
         "review": {"verdict": "APPROVE", "argument": "replicas can verify quorum from aggregate sig (step 3 synergy)"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "synergy with aggregate sigs confirmed"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 54120, "state_space_after": 41200,
                       "properties_checked": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "BroadcastCommit removed, one fewer O(n) round"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T004"}},

        {"run_id": "sample_run", "step": 9, "compartment": "C3", "timestamp": "2026-03-10T10:40:00Z", "status": "OK",
         "proposal": {"technique": "T001", "technique_name": "signature aggregation", "target_actions": ["CollectViewChangeMessages"],
                       "claim": "aggregate VC message signatures: O(n) to O(1)",
                       "structural_delta": "message size: VC proof shrinks from O(n) sigs to O(1) aggregate",
                       "diff": "--- a/view_change.tla\n+++ b/view_change.tla\n CollectViewChangeMessages(new_leader, sender, msg) ==\n-  /\\ vc_messages' = [...\\cup {<<sender, Sign(sender, msg)>>}]\n+  /\\ vc_messages' = [... AggregateSig(...)]"},
         "review": {"verdict": "APPROVE", "argument": "same pattern as step 3, distinct signers"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "clean reapplication"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 67000, "state_space_after": 58100,
                       "properties_checked": ["ViewMonotonicity", "RollbackSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "VC proof now O(1)"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T001"}},

        {"run_id": "sample_run", "step": 10, "compartment": "C3", "timestamp": "2026-03-10T10:45:00Z", "status": "OK",
         "proposal": {"technique": "novel", "technique_name": "lazy view change propagation", "target_actions": ["InitiateViewChange", "CollectViewChangeMessages", "InstallNewView"],
                       "claim": "defer VC broadcast, new leader pulls from quorum. O(n^2) -> O(n) communication",
                       "structural_delta": "communication complexity during view change: O(n^2) -> O(n)",
                       "diff": "--- a/view_change.tla\n+++ b/view_change.tla\n InitiateViewChange(replica) ==\n-  /\\ Broadcast(replica, <<\"vc\", view_number[replica] + 1, log[replica]>>)\n+  /\\ vc_pending' = [vc_pending EXCEPT ![replica] = <<view_number[replica]+1, log[replica]>>]\n+PullViewChangeState(new_leader, replica) ==\n+  /\\ vc_pending[replica] # <<>>\n+  /\\ vc_messages' = ...",
                       "novel_technique_description": "defer broadcast when next phase only partially reads, pull on demand with TEE/quorum consistency"},
         "review": {"verdict": "APPROVE", "argument": "pull-based works: quorum suffices, TEE prevents equivocation on pulled state"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "novel and sound. TEE + quorum intersection guarantee consistency."},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 58100, "state_space_after": 52400,
                       "properties_checked": ["ViewMonotonicity", "RollbackSafety", "ViewChangeLogIntegrity"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "n*(n-1) messages -> n/2+1 messages"},
         "failure_reason": None,
         "technique_registry_update": {"action": "added", "technique_id": "T006"}},

        {"run_id": "sample_run", "step": 11, "compartment": "C2", "timestamp": "2026-03-10T10:50:00Z", "status": "OK",
         "proposal": {"technique": "T002", "technique_name": "round collapsing", "target_actions": ["AppendEntry", "ReplicateEntry"],
                       "claim": "pipeline append+replicate: leader replicates entry while appending next",
                       "structural_delta": "latency: pipelined replication, 2 -> 1 effective round in steady state",
                       "diff": "--- a/log_replication.tla\n+++ b/log_replication.tla\n-AppendEntry(leader, entry) == ...\n-ReplicateEntry(leader, replica, entry) == ...\n+AppendAndReplicate(leader, entry) ==\n+  /\\ log' = [log EXCEPT ![leader] = Append(log[leader], entry)]\n+  /\\ Send to all replicas"},
         "review": {"verdict": "APPROVE", "argument": "replication depends on entry content, not full post-append state"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "confirmed: safe to pipeline"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 41200, "state_space_after": 35800,
                       "properties_checked": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "append+replicate merged, one fewer sequential round"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T002"}},

        {"run_id": "sample_run", "step": 12, "compartment": "C2", "timestamp": "2026-03-10T10:55:00Z", "status": "OK",
         "proposal": {"technique": "T007", "technique_name": "action merging", "target_actions": ["ReplicateEntry", "AckEntry"],
                       "claim": "local self-replication is instantaneous, merge replicate+ack for local case",
                       "structural_delta": "state space: remove intermediate state for local self-replication",
                       "diff": "...merged local case..."},
         "review": {"verdict": "APPROVE", "argument": "local path has no network delay, intermediate state unobservable"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "clear merge candidate for local case"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 35800, "state_space_after": 31200,
                       "properties_checked": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "local self-replication now atomic"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T007"}},

        {"run_id": "sample_run", "step": 13, "compartment": "C3", "timestamp": "2026-03-10T11:00:00Z", "status": "OK",
         "proposal": {"technique": "T003", "technique_name": "trust assumption exploitation (TEE)", "target_actions": ["InstallNewView"],
                       "claim": "TEE attestation makes per-message VC proof verification redundant",
                       "structural_delta": "protocol complexity: remove per-message verification in InstallNewView",
                       "diff": "--- a/view_change.tla\n+++ b/view_change.tla\n InstallNewView(new_leader) ==\n-  /\\ \\A msg \\in vc_messages[new_leader]: VerifyVCProof(msg)\n   /\\ Cardinality(vc_messages[new_leader]) * 2 > Cardinality(Replicas)"},
         "review": {"verdict": "APPROVE", "argument": "TEE attestation makes message forgery impossible"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "trust model covers this"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 52400, "state_space_after": 47100,
                       "properties_checked": ["ViewMonotonicity", "RollbackSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "VerifyVCProof loop removed"},
         "failure_reason": None,
         "technique_registry_update": {"action": "updated", "technique_id": "T003"}},

        {"run_id": "sample_run", "step": 14, "compartment": "C1", "timestamp": "2026-03-10T11:05:00Z", "status": "OK",
         "proposal": {"technique": "novel", "technique_name": "quorum-adaptive leader election", "target_actions": ["ElectLeader", "DeclareLeader"],
                       "claim": "TEE liveness attestation enables dynamic election quorum, ~40% latency reduction when all live",
                       "structural_delta": "election latency: ~40% reduction in high-availability. fault tolerance: adaptive quorum",
                       "diff": "--- a/leader_election.tla\n+++ b/leader_election.tla\n+AttestedLive == {r \\in Replicas : TEE_Attested(r)}\n+ElectionQuorum == (Cardinality(AttestedLive) + 1) \\div 2 + 1\n DeclareLeader(candidate) ==\n-  /\\ Cardinality(votes[candidate]) * 2 > Cardinality(Replicas)\n+  /\\ Cardinality(votes[candidate]) >= ElectionQuorum",
                       "novel_technique_description": "dynamically adjust quorum thresholds based on TEE liveness attestation while preserving quorum intersection"},
         "review": {"verdict": "APPROVE", "argument": "quorum intersection holds: any two quorums overlap by at least 1"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "novel and correct. TEE liveness lets you shrink quorum safely."},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 18500, "state_space_after": 16200,
                       "properties_checked": ["LeaderUniqueness", "ElectionTermination"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": True, "evidence": "election quorum now adaptive based on attested liveness"},
         "failure_reason": None,
         "technique_registry_update": {"action": "added", "technique_id": "T008"}},

        {"run_id": "sample_run", "step": 15, "compartment": "C2", "timestamp": "2026-03-10T11:10:00Z", "status": "FAIL",
         "proposal": {"technique": "U004", "technique_name": "invariant strengthening", "target_actions": ["CommitEntry"],
                       "claim": "stronger LogMatching invariant enables future optimizations",
                       "structural_delta": "provability: stronger invariant for future use",
                       "diff": "...strengthened invariant..."},
         "review": {"verdict": "APPROVE", "argument": "strengthened invariant is valid"},
         "judgment": {"ruling": "ACCEPT", "reasoning": "valid but speculative"},
         "hard_gate": {"ran": True, "passed": True, "verifier": "TLC", "state_space_before": 31200, "state_space_after": 31200,
                       "properties_checked": ["LogMatching", "LeaderCompleteness", "StateMachineSafety"], "counterexample": None},
         "structural_verification": {"ran": True, "claim_substantiated": False, "evidence": "no structural improvement, state space unchanged, lateral move"},
         "failure_reason": "hard gate passed but structural claim unsubstantiated",
         "technique_registry_update": {"action": "none", "technique_id": None}},
    ]

    for j in journals_data:
        comp = j["compartment"]
        step = j["step"]
        write_json(RUN_DIR / comp / f"step_{step:03d}.json", j)

    # checkpoints
    write_text(RUN_DIR / "C1" / "checkpoint_005.md", """# Checkpoint: C1, Step 5

## Previous checkpoint: none

## Progress since start
- Steps 1, 5, 6 for C1: 1 OK, 2 FAIL
- State space trajectory: 142857 -> 23809

## Structural improvements achieved
- Symmetry reduction (step 1): 6x state space reduction

## Failed attempts
- Round collapsing (step 5): election requires full quorum observation
- Action merging (step 6): HandleVote and DeclareLeader have different firing patterns

## Stalled areas
- Election round/latency optimization: 2 consecutive failures
""")

    write_text(RUN_DIR / "C1" / "checkpoint_005_ok.md", """# OK Checkpoint: C1, Step 5

## Successful findings

### Step 1: Symmetry Reduction
- Replicas fully interchangeable in election
- State space: 142857 -> 23809 (6x reduction)
""")

    write_text(RUN_DIR / "C2" / "checkpoint_010.md", """# Checkpoint: C2, Step 10

## Previous checkpoint: none

## Progress: 5 OK, 1 FAIL
- State space trajectory: 98304 -> 87210 -> 54120 -> 41200 -> 35800 -> 31200

## Structural improvements
- Sig aggregation on acks (step 3): O(n) -> O(1) ack size
- next_index elimination (step 4): derived variable removed, ~38% state space reduction
- Commit broadcast removal (step 8): O(n) messages eliminated per commit
- Pipelined replication (step 11): append+replicate merged
- Local self-replication merge (step 12): atomic local path

## Failed attempts
- TruncateLog removal (step 2): needed by C3 for surgical rollback

## Overall: 68% state space reduction from original
""")

    write_text(RUN_DIR / "C2" / "checkpoint_010_ok.md", """# OK Checkpoint: C2, Step 10

## Successful findings

### Step 3: Signature Aggregation
- Ack size: O(n) -> O(1) aggregate

### Step 4: State Variable Elimination
- next_index = match_index + 1 invariant, eliminated

### Step 8: Commit Broadcast Removal
- Synergy with step 3 aggregate sigs

### Step 11: Pipelined Replication
- append+replicate merged

### Step 12: Local Self-Replication
- Atomic local replicate+ack
""")

    # intersection updates
    write_json(RUN_DIR / "intersections" / "I1" / "update_001.json", {
        "step": 7, "source_compartment": "C1", "type": "variable_simplification",
        "description": "leader election votes no longer carry signatures (TEE exploitation)",
        "affected_vars": ["leader"], "status": "committed"
    })
    write_json(RUN_DIR / "intersections" / "I2" / "update_001.json", {
        "step": 10, "source_compartment": "C3", "type": "protocol_restructure",
        "description": "view change now pull-based instead of broadcast",
        "affected_vars": ["log"], "status": "committed"
    })
    write_json(RUN_DIR / "intersections" / "I2" / "update_002.json", {
        "step": 11, "source_compartment": "C2", "type": "action_merge",
        "description": "append+replicate pipelined, log write pattern unchanged",
        "affected_vars": ["log"], "status": "committed"
    })

    # status
    write_json(RUN_DIR / "status.json", {
        "state": "running",
        "current_step": 16,
        "started": "2026-03-10T10:00:00Z",
        "config": {"P": 5, "S": 3, "F": 5, "M": 3},
        "active_agents": [
            {"name": "autospec-proposer", "role": "proposer", "compartment": "C1", "technique": "exploring registry", "started": "2026-03-10T11:15:00Z"},
            {"name": "autospec-proposer", "role": "proposer", "compartment": "C3", "technique": "trust assumption exploitation", "started": "2026-03-10T11:14:00Z"},
            {"name": "autospec-novelty", "role": "novelty verification", "compartment": "C3", "technique": "lazy view change propagation (T006)", "started": "2026-03-10T11:10:00Z"}
        ],
        "escalation": {
            "C1": {"consecutive_no_progress": 2, "tier": 0},
            "C2": {"consecutive_no_progress": 1, "tier": 0},
            "C3": {"consecutive_no_progress": 0, "tier": 0}
        }
    })

    print(f"sample data written to {RUN_DIR}")


if __name__ == "__main__":
    main()
