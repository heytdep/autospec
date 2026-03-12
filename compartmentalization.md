# Compartmentalization Algorithm

## Purpose

Split a formal specification into compartments that can be improved independently and in parallel. The quality of this split determines the entire system's effectiveness. A bad split means agents fight over entangled state; a good split means genuine parallel progress.

---

## Step 1: Variable-Action Mapping

Extract from the spec:

- **V**: set of all state variables
- **A**: set of all actions (TLA+ actions, Lean definitions, ProVerif processes)
- **P**: set of all properties (invariants, temporal, security)

Build the mapping:
- For each action a in A: `reads(a)` and `writes(a)` subsets of V
- For each property p in P: `vars(p)` = variables referenced in p, `actions(p)` = actions whose execution can affect p

This mapping is mechanical for TLA+ (parse UNCHANGED clauses, primed variables). For Lean/ProVerif it requires more analysis but the principle is the same: which state does each definition touch?

---

## Step 2: Coupling Analysis

Build a coupling graph:
- Nodes = actions
- Edge between a1 and a2 with weight = |writes(a1) ∩ (reads(a2) ∪ writes(a2))| + |writes(a2) ∩ (reads(a1) ∪ writes(a1))|

High weight = tightly coupled (both write to each other's variables).
Zero weight = no direct coupling.

---

## Step 3: Clustering

Partition the action graph into clusters where:
- **Intra-cluster coupling is high**: actions within a cluster have high-weight edges between them.
- **Inter-cluster coupling is low**: edges between clusters have low weight.

This is a graph partitioning problem. The agent uses the coupling graph + the following heuristics:

### Heuristic 1: Property coherence
If all actions referenced by a property are in one cluster, that property is local to that compartment. Prefer partitions that maximize the number of local properties (minimize spanning properties).

### Heuristic 2: Functional coherence
Actions that together implement a recognizable protocol phase (e.g. "leader election", "log replication", "view change") should be in the same compartment, even if coupling analysis alone might split them.

### Heuristic 3: Interface minimality
The set of variables that cross cluster boundaries should be small and have clear directionality (one cluster writes, another reads, not both writing).

### Conflict resolution
When heuristics conflict (coupling says split, functional coherence says keep together), the agent produces both options and a triad decides.

---

## Step 4: Intersection Identification

For each pair of compartments (C_i, C_j):

1. Find shared variables: `shared = (writes(C_i) ∩ reads(C_j)) ∪ (writes(C_j) ∩ reads(C_i))`
2. If `shared` is empty, no intersection exists.
3. If `shared` is non-empty, create an intersection record:
   - `compartments`: [C_i, C_j]
   - `shared_vars`: the shared variable set
   - `directionality`: analyze who writes and who reads
   - `spanning_properties`: properties whose `vars(p)` intersects both C_i's and C_j's variable sets
   - `coupling_strength`:
     - **weak**: one side only reads the shared vars
     - **medium**: one side writes, other reads
     - **strong**: both sides write to shared vars

---

## Step 5: Validation

Before accepting the compartmentalization, verify:

### 5.1 No orphaned properties
Every property must be either local to a compartment or covered by a spanning property in an intersection. If a property falls through the cracks, the compartmentalization is invalid.

### 5.2 One intersection per compartment pair
If a pair has multiple distinct sets of shared variables with different directionality, attempt to merge into one intersection. If not possible, re-cluster.

### 5.3 No fully connected topology
If every compartment has an intersection with every other, the spec is too entangled. Options:
- Merge the two most coupled compartments and re-analyze.
- Repeat until topology is manageable (each compartment intersects with at most 2-3 others).
- If merging collapses everything into one compartment, accept single-compartment mode.

### 5.4 Minimum compartment size
A compartment with fewer than 2 actions is probably not worth the overhead. Merge it with its most-coupled neighbor.

---

## Step 6: Output

The compartmentalization agent outputs:

```
{
  compartments: [
    {
      id: "C1",
      name: "leader_election",
      actions: ["ElectLeader", "HandleVote", "DeclareLeader"],
      local_vars: ["votes", "leader", "election_round"],
      local_properties: ["LeaderUniqueness", "ElectionTermination"],
      rationale: "these actions form a closed loop over election state with
                  minimal external coupling (only leader var is read externally)"
    },
    ...
  ],
  intersections: [
    {
      id: "I1",
      compartments: ["C1", "C2"],
      shared_vars: ["leader"],
      directionality: "C1 writes, C2 reads",
      spanning_properties: ["LeaderConsistency"],
      coupling_strength: "medium"
    },
    ...
  ],
  topology_summary: "3 compartments, 2 intersections, max degree 2, no strong coupling",
  fallback_triggered: false
}
```

---

## Re-compartmentalization

The compartmentalization is NOT fixed for the entire run. If structural changes alter the variable-action coupling significantly (e.g. a technique merges two protocol phases, or removes a variable entirely), the orchestrator may trigger re-compartmentalization. Criteria:

- A compartment's action set changed by more than 50% from original.
- An intersection's coupling strength changed category (weak->strong or vice versa).
- A compartment has had P consecutive FAIL steps where failure traces to intersection issues.

Re-compartmentalization runs the full algorithm again on the current spec state. Existing journals and checkpoints are remapped to new compartments by the checkpoint agent.
