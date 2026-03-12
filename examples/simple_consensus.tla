---- MODULE simple_consensus ----
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Replicas,       \* set of replica IDs
    Values,         \* set of proposable values
    MaxRound        \* bound for model checking

VARIABLES
    round,          \* current round number
    leader,         \* current leader (or None)
    votes,          \* votes[r] = the value replica r voted for in current round, or None
    proposed,       \* proposed[r] = value proposed by r if r is leader, or None
    decided,        \* decided[r] = decided value for replica r, or None
    msgs,           \* set of messages in transit
    acked,          \* acked[v] = set of replicas that acked value v
    sigs            \* sigs[r][m] = signature of replica r on message m

vars == <<round, leader, votes, proposed, decided, msgs, acked, sigs>>

None == CHOOSE n : n \notin Replicas \cup Values

\* --- types ---

TypeOK ==
    /\ round \in 0..MaxRound
    /\ leader \in Replicas \cup {None}
    /\ votes \in [Replicas -> Values \cup {None}]
    /\ proposed \in [Replicas -> Values \cup {None}]
    /\ decided \in [Replicas -> Values \cup {None}]
    /\ msgs \subseteq [type: {"propose", "vote", "ack", "decide"}, from: Replicas, val: Values]
    /\ acked \in [Values -> SUBSET Replicas]
    /\ sigs \in [Replicas -> [{"propose", "vote", "ack"} -> Values \cup {None}]]

\* --- init ---

Init ==
    /\ round = 0
    /\ leader = None
    /\ votes = [r \in Replicas |-> None]
    /\ proposed = [r \in Replicas |-> None]
    /\ decided = [r \in Replicas |-> None]
    /\ msgs = {}
    /\ acked = [v \in Values |-> {}]
    /\ sigs = [r \in Replicas |-> [t \in {"propose", "vote", "ack"} |-> None]]

\* --- leader election (round-robin for simplicity) ---

ElectLeader ==
    /\ leader = None
    /\ round < MaxRound
    /\ LET newLeader == CHOOSE r \in Replicas :
            \A r2 \in Replicas : r <= r2  \* deterministic pick
       IN leader' = newLeader
    /\ round' = round + 1
    /\ UNCHANGED <<votes, proposed, decided, msgs, acked, sigs>>

\* --- propose ---

Propose(l, v) ==
    /\ leader = l
    /\ proposed[l] = None
    /\ proposed' = [proposed EXCEPT ![l] = v]
    /\ sigs' = [sigs EXCEPT ![l]["propose"] = v]
    /\ msgs' = msgs \cup {[type |-> "propose", from |-> l, val |-> v]}
    /\ UNCHANGED <<round, leader, votes, decided, acked>>

\* --- vote ---

Vote(r, v) ==
    /\ [type |-> "propose", from |-> leader, val |-> v] \in msgs
    /\ votes[r] = None
    /\ votes' = [votes EXCEPT ![r] = v]
    /\ sigs' = [sigs EXCEPT ![r]["vote"] = v]
    /\ msgs' = msgs \cup {[type |-> "vote", from |-> r, val |-> v]}
    /\ UNCHANGED <<round, leader, proposed, decided, acked>>

\* --- ack (leader collects votes and broadcasts ack per replica) ---

AckVote(l, r, v) ==
    /\ leader = l
    /\ [type |-> "vote", from |-> r, val |-> v] \in msgs
    /\ r \notin acked[v]
    /\ acked' = [acked EXCEPT ![v] = acked[v] \cup {r}]
    /\ sigs' = [sigs EXCEPT ![l]["ack"] = v]
    /\ msgs' = msgs \cup {[type |-> "ack", from |-> l, val |-> v]}
    /\ UNCHANGED <<round, leader, votes, proposed, decided>>

\* --- decide (quorum reached) ---

Decide(r, v) ==
    /\ Cardinality(acked[v]) * 2 > Cardinality(Replicas)
    /\ decided[r] = None
    /\ [type |-> "ack", from |-> leader, val |-> v] \in msgs
    /\ decided' = [decided EXCEPT ![r] = v]
    /\ msgs' = msgs \cup {[type |-> "decide", from |-> r, val |-> v]}
    /\ UNCHANGED <<round, leader, votes, proposed, acked, sigs>>

\* --- reset for next round ---

NextRound ==
    /\ \E r \in Replicas : decided[r] # None
    /\ leader' = None
    /\ votes' = [r \in Replicas |-> None]
    /\ proposed' = [r \in Replicas |-> None]
    /\ acked' = [v \in Values |-> {}]
    /\ sigs' = [r \in Replicas |-> [t \in {"propose", "vote", "ack"} |-> None]]
    /\ UNCHANGED <<round, decided, msgs>>

\* --- spec ---

Next ==
    \/ ElectLeader
    \/ \E l \in Replicas, v \in Values : Propose(l, v)
    \/ \E r \in Replicas, v \in Values : Vote(r, v)
    \/ \E l \in Replicas, r \in Replicas, v \in Values : AckVote(l, r, v)
    \/ \E r \in Replicas, v \in Values : Decide(r, v)
    \/ NextRound

Spec == Init /\ [][Next]_vars

\* --- properties ---

\* agreement: no two replicas decide differently
Agreement ==
    \A r1, r2 \in Replicas :
        (decided[r1] # None /\ decided[r2] # None) => decided[r1] = decided[r2]

\* validity: decided value was proposed
Validity ==
    \A r \in Replicas :
        decided[r] # None => \E l \in Replicas : proposed[l] = decided[r]

\* no decision without quorum
QuorumRequired ==
    \A r \in Replicas, v \in Values :
        decided[r] = v => Cardinality(acked[v]) * 2 > Cardinality(Replicas)

\* all signatures are for values that were actually sent
SignatureIntegrity ==
    \A r \in Replicas :
        /\ (sigs[r]["vote"] # None => votes[r] = sigs[r]["vote"])
        /\ (sigs[r]["propose"] # None => proposed[r] = sigs[r]["propose"])

====
