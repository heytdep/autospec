# MFS Language Specification v0.3

**Mechanism Flow Specification** — a formal language for specifying distributed protocol mechanisms, their effects, and composition as a directed acyclic graph.

## 1. Design Philosophy

MFS sits between English protocol specifications and state-machine formalisms (TLA+, Quint). It describes **what mechanisms do and how their effects flow**, not **how internal state transitions work**.

### Borrowed Concepts

| Source | Concept Borrowed | How Used in MFS |
|---|---|---|
| Event structures (Winskel) | Events with causal ordering | Effects as first-class typed events with causal flow |
| Choreography calculi | Global interaction types | Multi-party flow declarations from a global view |
| CSP / pi-calculus | Typed channels | Channel declarations with transport/ordering/reliability annotations |
| Alloy | Relational signatures, facts, assertions | Type declarations, guarantee syntax |
| Event-B | Events with guards and actions | Mechanism blocks: trigger, guard, effect structure |

### Execution Model

MFS's semantic domain is **effect traces**: ordered sequences of effect emission and delivery events over the flow DAG. A trace records which mechanism produced which effect, when it was delivered to which consumer, and over which channel. Temporal operators in guarantee properties (`eventually`, `always`, `before`) are interpreted over these traces. Specifically:

- `delivered(e)`: effect `e` has been received by a consumer
- `before(e1, e2)`: `e1` appears earlier in the trace than `e2` at the consumer
- `eventually P`: there exists a trace suffix in which `P` holds
- `always P`: `P` holds at every point in every valid trace
- `stored(a, e)`: archiver `a` has recorded effect `e`
- `confirmed(e)`: effect `e` has been delivered and not subsequently invalidated by a rollback signal
- `rolled_back(e)`: effect `e` was delivered but later invalidated by a rollback signal (i.e., a recovery mechanism determined `e` was not part of the recovered prefix)

This trace model does **not** require modeling internal mechanism state — it only observes the externally visible effect events.

### Derived Values

Recovery and guarantee declarations may reference **derived values** — values computed from the effect trace rather than from internal state. Derived values are grounded in observable effects:

- `last_recovered_seq`: the highest sequence number in the contiguous prefix recovered from archivers during a view change. Derived from the recovery mechanism's `maximal_contiguous_prefix` strategy applied to the archiver response.
- `last_applied`: the sequence number of the last effect applied by the previous primary before failure. Observable as the highest `seq` in the effect trace at the point of crash.
- `checkpoint_seq`: the sequence number of the most recent endorsed checkpoint. Derived from the most recent `checkpoint_endorsed` event in the trace.
- `anchor_seq`: the starting point for recovery, defined as `last_applied` (primary-only failure) or `checkpoint_seq` (full-cluster failure).

These values must be expressible as functions over the effect trace. They do not require internal state — they are properties of the observable effect history.

### Well-formedness

A valid MFS specification must satisfy:
- **Acyclicity**: the effect-flow graph formed by mechanism dissemination rules and flow declarations must be a DAG. Cycles are a specification error. Feedback loops must be modeled as separate mechanisms with distinct effect types at each stage.
- **Consistency**: flow declarations must be consistent with mechanism dissemination rules. If both describe the same edge, their channel, filter, and target must agree. Inconsistency is a specification error (dissemination rules take precedence per Section 7).
- **Type closure**: every type referenced in effect payloads must be either a built-in type (Section 14), declared via `type` (Section 14), or explicitly marked `@opaque`.

### Non-goals

MFS does **not** describe:
- Internal state variables or transitions (use TLA+/Quint)
- Implementation details (data structures, algorithms)
- Timing constraints beyond relative ordering (use timed automata)

---

## 2. Top-Level Structure

An MFS specification is a sequence of top-level declarations:

```
<spec> ::= <declaration>*

<declaration> ::= <scope-decl>
               | <type-decl>
               | <effect-type-decl>
               | <channel-decl>
               | <mechanism-decl>
               | <flow-decl>
               | <guarantee-decl>
               | <recovery-decl>
               | <gc-decl>
               | <module-decl>
               | <import-decl>
```

All declarations are order-independent (the spec is declarative, not procedural). Forward references are allowed.

---

## 3. Scope Declarations

Scopes define the domains over which mechanisms operate. They can be parameterized.

```
<scope-decl> ::= "scope" <id> [ "(" <param-list> ")" ] "{" <scope-body> "}"

<scope-body> ::= <scope-field>*

<scope-field> ::= "domain" ":" <description>
               | "parameter" <id> ":" <type> [ "=" <default> ]
               | "instances" ":" <cardinality-expr>
```

### Examples

```mfs
scope global_inventory {
  domain: "all user inventories, confirmations, checkpoints"
  instances: 1
}

scope per_market(m: MarketId) {
  domain: "order book state for market m"
  instances: |markets|
}

scope per_partition(u: PartitionId) {
  domain: "order/trade state for users in partition u"
  parameter users: Set<UserId>
  instances: |partitions|
}
```

---

## 4. Effect Type Declarations

Effects are the observable outputs of mechanisms. They are typed, carry metadata, and flow between mechanisms via channels.

```
<effect-type-decl> ::= "effect" <id> [ "(" <param-list> ")" ] "{"
                          <effect-field>*
                       "}"

<effect-field> ::= "payload" ":" <type-expr>
                | "metadata" ":" "{" <field-list> "}"
                | "ordering" ":" <ordering-constraint>
                | "attestation" ":" <attestation-spec>
                | "scope" ":" <scope-ref>
```

### Ordering Constraints (Effect-Level)

Effect ordering describes a **producer-side invariant** on the sequence numbers assigned to effects. This is distinct from channel ordering (Section 5), which describes the **transport-layer delivery guarantee**.

**Interaction rule**: When a channel with `ordering: none` carries an effect with `strictly_monotonic` ordering, the consumer is responsible for buffering and reordering received effects by sequence number before processing. The effect's ordering constraint is a property of the effect stream, not a promise about delivery order.

```
<ordering-constraint> ::= <id> ":" "strictly_monotonic" "within" <scope-ref>
                       | <id> ":" "monotonic" "within" <scope-ref>
                       | "unordered"
```

### Attestation

```
<attestation-spec> ::= "tee_signed" "(" <field-list> ")"
                     | "unsigned"
                     | "encrypted" "(" <key-spec> ")"
```

### Examples

```mfs
effect ce_effect {
  payload: MatchFinalizationResult | SharedUserAssetSnapshot | ChainEvent | InterestApplied
  metadata: {
    seq: SeqNum
    session: SessionId
  }
  ordering: seq strictly_monotonic within global_inventory
  attestation: tee_signed(seq, session, hash(payload))
  scope: global_inventory
}

effect ob_effect(m: MarketId) {
  payload: OrderbookEvent | FillResult
  metadata: {
    seq: SeqNum
    session: SessionId
  }
  ordering: seq strictly_monotonic within per_market(m)
  attestation: tee_signed(seq, session, hash(payload))
  scope: per_market(m)
}

effect ob_pending_action(m: MarketId) {
  payload: PendingMatch
  metadata: {
    pending_seq: SeqNum
    session: SessionId
  }
  ordering: pending_seq strictly_monotonic within per_market(m)
  attestation: tee_signed(pending_seq, session, hash(payload))
  scope: per_market(m)
  -- separate namespace from ob_effect to avoid ambiguity on recovery
}

effect oms_derived_effect(u: PartitionId) {
  payload: FilteredUpstreamEffect
  metadata: {
    local_seq: SeqNum
    session: SessionId
    source_ref: SourceCursor
  }
  ordering: local_seq strictly_monotonic within per_partition(u)
  attestation: tee_signed(local_seq, session, hash(payload))
  scope: per_partition(u)
}
```

---

## 5. Channel Declarations

Channels describe how effects are physically transported between mechanisms. They are first-class objects with full annotations.

```
<channel-decl> ::= "channel" <id> "{"
                      <channel-field>*
                   "}"

<channel-field> ::= "transport" ":" <transport-type>
                 | "pattern" ":" <pattern-type>
                 | "fan" ":" <fan-spec>
                 | "ordering" ":" <channel-ordering>
                 | "reliability" ":" <reliability-spec>
                 | "complexity" ":" <complexity-class>
```

### Transport Types

```
<transport-type> ::= "memory"
                  | "overlay_pubsub" "(" "topic" ":" <string> ")"
                  | "overlay_directed" [ "(" <directed-opts> ")" ]
                  | "request_response"
```

### Pattern Types

```
<pattern-type> ::= "fire_and_forget"
                | "broadcast_then_filter"
                | "pull_on_demand"
                | "push_with_ack"
```

### Fan Specifications

```
<fan-spec> ::= <nat> ":" <nat>          -- e.g., 1:1
            | <nat> ":" <id>            -- e.g., 1:N
            | <id> ":" <id>             -- e.g., N:N
            | <nat> ":" <nat> "per" <scope-ref>  -- e.g., 1:1 per partition
```

### Channel Ordering

```
<channel-ordering> ::= "fifo_per_source"
                     | "causal"
                     | "total"
                     | "none"
```

### Reliability

```
<reliability-spec> ::= "at_most_once"
                     | "at_least_once"
                     | "exactly_once"
```

### Complexity Class

The `complexity` field describes the **message complexity per effect emission** — the number of overlay messages produced when the mechanism emits a single effect over this channel. The free variable in the `O(...)` expression is bound to the channel's `fan` parameter: if `fan: 1:B`, then `B` in `O(B)` refers to the fan-out count (number of recipients). `O(1)` indicates point-to-point communication.

```
<complexity-class> ::= "O(" <expr> ")"
```

### Examples

```mfs
channel ce_to_backup {
  transport: overlay_pubsub(topic: "ce-effects")
  pattern: fire_and_forget
  fan: 1:B
  ordering: fifo_per_source
  reliability: at_most_once
  complexity: O(B)
}

channel ce_to_archive {
  transport: overlay_pubsub(topic: "ce-archive")
  pattern: fire_and_forget
  fan: 1:A
  ordering: none
  reliability: at_most_once
  complexity: O(A)
}

channel ce_broadcast {
  transport: overlay_pubsub(topic: "ce-effects")
  pattern: broadcast_then_filter
  fan: 1:U
  ordering: fifo_per_source
  reliability: at_most_once
  complexity: O(U)
}

channel archiver_retrieval {
  transport: request_response
  pattern: pull_on_demand
  fan: 1:1
  ordering: none
  reliability: at_least_once
  complexity: O(1)
}
```

---

## 6. Mechanism Declarations

Mechanisms are the primary building blocks. Each mechanism has triggers, optional guards, effects it produces, and dissemination rules.

```
<mechanism-decl> ::= "mechanism" <qualified-id> "{"
                        <mechanism-body>
                     "}"

<qualified-id> ::= <id-or-param> [ "." <id-or-param> ]*
<id-or-param>  ::= <id> [ "[" <param-list> "]" ]

<mechanism-body> ::= <mechanism-field>*

<mechanism-field> ::= "scope" ":" <scope-ref>
                   | "triggers" ":" "[" <trigger-list> "]"
                   | "guard" ":" <predicate>
                   | "produces" ":" <effect-ref> [ "(" <binding-list> ")" ]
                   | "consumes" ":" <effect-ref> [ "(" <binding-list> ")" ]
                   | "dissemination" "{" <dissemination-rule>* "}"
```

### Triggers

Triggers are what activate a mechanism. They can be external inputs, upstream effects, or predicates over the received effect history.

```
<trigger> ::= <effect-ref>              -- triggered by receiving an effect
           | <external-event>            -- triggered by external input
           | <effect-predicate>          -- triggered by a predicate over received effect history
```

An `<effect-predicate>` is a boolean expression evaluated over the stream of effects a mechanism has consumed (e.g., `CE.is_down` meaning "no ce_effect received within timeout"). It does **not** reference internal state variables — it is defined over the observable effect trace only, consistent with MFS's non-state-machine philosophy.

### Produces vs Consumes

- `produces`: declares that this mechanism **creates new effects** of the given type and is responsible for disseminating them.
- `consumes`: declares that this mechanism **receives and processes effects** of the given type from upstream. Consumption is non-destructive — multiple mechanisms can consume the same effect (broadcast semantics). `consumes` declares an input dependency, while `triggers` declares what activates the mechanism. A mechanism may be triggered by receiving an effect it consumes, but these are separate concepts: `triggers` defines activation, `consumes` defines the effect types in the mechanism's input set.

For mechanisms that filter and re-sequence upstream effects (e.g., OMS deriving a local log from CE + OB effects), use both `consumes` (for the upstream effect types) and `produces` (for the derived effect type).

### Dissemination Rules

Dissemination rules define where produced effects go and over which channel.

```
<dissemination-rule> ::= "->" <target> ":" <channel-ref>
                       [ "filter" ":" <predicate> ]
                       [ "alternative" "{" <dissemination-rule> "}" ]
```

The `alternative` clause specifies a fallback dissemination path. It activates when the primary channel is unavailable or when an explicit precondition is not met (e.g., the producer lacks required routing information). The alternative is a complete dissemination rule with its own target, channel, and optional filter. Alternatives are evaluated in order; the first viable path is used. Alternatives are a specification-level construct documenting design options — they do not imply runtime failover logic.

### Examples

```mfs
mechanism CE.produce {
  scope: global_inventory
  triggers: [user_action, chain_event, ob_fill_result]

  produces: ce_effect(seq, session, payload)

  dissemination {
    -> CE.backup: ce_to_backup
    -> Archiver[CE]: ce_to_archive
    -> OMS[u]: ce_broadcast
    -> OB[m]: ce_broadcast
      filter: payload is MatchFinalizationResult
  }
}
```

---

## 7. Flow Declarations

Flows define the DAG edges explicitly. Dissemination rules inside mechanisms and top-level flow declarations both describe effect routing. Their relationship:

- **Dissemination rules** (inside mechanisms) are the **authoritative source** for where a mechanism sends its effects and over which channel.
- **Flow declarations** (top-level) are **derived documentation** that make the DAG explicit for cross-cutting analysis (redundant paths, guarantees over flows). They must be consistent with the dissemination rules they describe.
- If a flow declaration contradicts a dissemination rule, the dissemination rule takes precedence.

Flow declarations add value by naming edges (for use in guarantee `over` clauses), declaring redundant paths, and providing a single place to see the full DAG without reading every mechanism.

```
<flow-decl> ::= "flow" <id> "{"
                   "from" ":" <mechanism-ref>
                   "to" ":" <mechanism-ref>
                   "carries" ":" <effect-ref>
                   "via" ":" <channel-ref>
                   [ "filter" ":" <predicate> ]
                   [ "redundant_paths" ":" "[" <path-list> "]" ]
                "}"
```

### Examples

```mfs
flow ce_to_oms {
  from: CE.produce
  to: OMS.consume
  carries: ce_effect
  via: ce_broadcast
  redundant_paths: [
    CE.backup -> Archiver[CE] -> OMS.consume,
    CE.produce -> Archiver[CE] -> OMS.consume
  ]
}
```

---

## 8. Guarantee Declarations

Guarantees are properties that must hold over effects and flows. They are expressed over effect sequences and flow paths, not over state variables.

```
<guarantee-decl> ::= "guarantee" <id> "{"
                        "over" ":" <scope-or-flow-ref>
                        "property" ":" <property-expr>
                        [ "assumes" ":" <assumption-list> ]
                        [ "degradation" ":" <degradation-spec> ]
                     "}"
```

### Property Expressions

```
<property-expr> ::= "forall" <var> "in" <set> ":" <predicate>
                 | "exists" <var> "in" <set> ":" <predicate>
                 | <predicate> "=>" <predicate>
                 | <predicate> "and" <predicate>
                 | <predicate> "or" <predicate>
                 | "eventually" <predicate>
                 | "always" <predicate>
                 | "prefix_contiguous" "(" <effect-ref> "," <scope-ref> ")"
                 | "no_gaps" "(" <effect-ref> "," <scope-ref> ")"
                 | "causally_ordered" "(" <effect-ref> "," <effect-ref> ")"
```

### Degradation Specs

Degradation describes how a guarantee weakens under partial failure.

```
<degradation-spec> ::= "on" <failure-condition> ":" <weakened-property>
```

### Examples

```mfs
guarantee sequential_consistency_ce {
  over: global_inventory
  property: forall e1 e2 in ce_effect:
    e1.seq < e2.seq => delivered(e1) before delivered(e2)
  assumes: [single_leader(CE), tee_integrity]
}

guarantee data_availability_ce {
  over: flow(CE.produce -> Archiver[CE])
  property: forall e in ce_effect:
    eventually exists a in Archiver[CE]: stored(a, e)
  assumes: [at_least_one_honest_archiver]
  degradation:
    on all_archivers_down: property weakens to "recovery depends on backup state"
}

guarantee surgical_rollback {
  over: CE.view_change
  property: forall e in ce_effect:
    e.seq <= last_recovered_seq => confirmed(e)
    and e.seq > last_recovered_seq => rolled_back(e)
}
```

---

## 9. Recovery Declarations

Recovery blocks specify what happens when a mechanism's primary fails and a new leader takes over.

```
<recovery-decl> ::= "recovery" <id> "{"
                       "for" ":" <mechanism-ref>
                       "trigger" ":" <recovery-trigger>
                       "source" ":" <recovery-source>
                       "strategy" ":" <recovery-strategy>
                       [ "window" ":" <duration> ]
                       [ "anchor" ":" <anchor-expr> ]
                       [ "post_recovery" ":" <post-recovery-action> ]
                    "}"
```

### Recovery Strategies

```
<recovery-strategy> ::= "maximal_contiguous_prefix" "(" "from" ":" <anchor-ref> ")"
                      | "cursor_based_catchup" "(" <cursor-list> ")"
                      | "snapshot_then_replay" "(" "snapshot" ":" <source> "," "replay" ":" <source> ")"
```

### Examples

```mfs
recovery ce_view_change {
  for: CE.produce
  trigger: authority_endorsement(new_leader, sig, ts)
    where ts > downstream.cached_ts
  source: Archiver[CE]
  strategy: maximal_contiguous_prefix(from: anchor_seq)
  window: Delta
  anchor: primary_only_failure ? last_applied : checkpoint_seq
  post_recovery: broadcast(last_recovered_seq)
    then downstream: surgical_rollback(seq > last_recovered_seq)
}

recovery oms_view_change {
  for: OMS[u].consume
  trigger: authority_endorsement(new_leader_oms, sig, ts)
  source: Archiver[OMS] | Archiver[CE] + Archiver[OB]
  strategy: cursor_based_catchup(ob_cursor[m] for all m, ce_cursor)
  window: Delta
  post_recovery: broadcast(view_change_partition(u, cursors))
}
```

---

## 10. Garbage Collection Rules

Archiver garbage collection is specified as rules with triggers and conditions.

```
<gc-decl> ::= "gc" <id> "{"
                 "for" ":" <archiver-ref>
                 <gc-rule>*
                 [ "guard" ":" <predicate> ]
              "}"

<gc-rule> ::= "rule" <id> "{"
                 "trigger" ":" <gc-trigger>
                 "condition" ":" <predicate>
                 "action" ":" "prune" "(" <prune-spec> ")"
                 [ "applies_to" ":" "[" <service-list> "]" ]
              "}"
```

### Examples

```mfs
gc archiver_partial {
  for: Archiver[svc]

  rule backup_ack_gc {
    trigger: backup_ack(source_id, seq)
    condition: distinct_sources(seq) >= k_of_n
    action: prune(effects where effect.seq <= seq)
  }

  rule checkpoint_gc {
    trigger: checkpoint_endorsed(seq_c)
    condition: checkpoint_endorsed_at(seq_c)
    action: prune(effects where effect.seq <= seq_c)
    applies_to: [CE]
  }

  guard: no_reingest_below_checkpoint
}

gc archiver_history {
  for: Archiver[svc]
  -- no pruning rules; retains everything for audit
}
```

---

## 11. Comments and Annotations

```
-- single line comment

{- multi-line
   comment -}

@annotation_name(args)   -- metadata annotation on next declaration
```

### Standard Annotations

```
@deprecated("reason")
@todo("description")
@see("reference")
@complexity(O(N))
@trust_assumption("description")
```

---

## 12. Module System

Large specs can be split across files. Each file declares at most one module.

```
<module-decl> ::= "module" <id> [ "(" <param-list> ")" ]

<import-decl> ::= "import" <module-id> [ "as" <alias> ]
               | "from" <module-id> "import" <id-list>
```

### Scoping Rules

- All top-level declarations within a module are **public** by default. There is no private visibility modifier (MFS prioritizes readability over encapsulation).
- `import M` brings all declarations from module `M` into scope, prefixed by `M.` (or the alias if `as` is used).
- `from M import X, Y` brings only `X` and `Y` into scope without prefix.
- Name collisions between imported declarations are a static error. Use aliasing (`as`) to resolve.
- Parameterized modules (`module M(x: T)`) bind `x` throughout the module body. Importing a parameterized module requires providing arguments: `import M(concrete_value)`.
- Circular imports are not allowed.

---

## 13. Formal Grammar Summary (EBNF)

```ebnf
spec          = { declaration } ;
declaration   = scope_decl | type_decl | effect_decl | channel_decl
              | mechanism_decl | flow_decl | guarantee_decl
              | recovery_decl | gc_decl | module_decl | import_decl ;

type_decl     = "type" , id , [ "{" , { field_decl } , "}" ]
              | "@opaque" , "type" , id ;

scope_decl    = "scope" , id , [ "(", param_list, ")" ] , "{" , { scope_field } , "}" ;
scope_field   = "domain" , ":" , string
              | "parameter" , id , ":" , type_expr , [ "=" , expr ]
              | "instances" , ":" , expr ;

effect_decl   = "effect" , id , [ "(", param_list, ")" ] , "{" , { effect_field } , "}" ;
effect_field  = "payload" , ":" , type_expr
              | "metadata" , ":" , "{" , { field_decl } , "}"
              | "ordering" , ":" , effect_ordering
              | "attestation" , ":" , attestation_spec
              | "scope" , ":" , scope_ref ;
effect_ordering = id , ":" , ( "strictly_monotonic" | "monotonic" ) , "within" , scope_ref
              | "unordered" ;

channel_decl  = "channel" , id , "{" , { channel_field } , "}" ;
channel_field = "transport" , ":" , transport_spec
              | "pattern" , ":" , pattern_spec
              | "fan" , ":" , fan_spec
              | "ordering" , ":" , channel_ordering
              | "reliability" , ":" , reliability_spec
              | "complexity" , ":" , complexity_spec ;
channel_ordering = "fifo_per_source" | "causal" | "total" | "none" ;

mechanism_decl = "mechanism" , qual_id , "{" , { mech_field } , "}" ;
qual_id        = id_or_param , { "." , id_or_param } ;
id_or_param    = id , [ "[" , param_list , "]" ] ;
mech_field     = "scope" , ":" , scope_ref
              | "triggers" , ":" , "[" , trigger_list , "]"
              | "guard" , ":" , predicate
              | "produces" , ":" , effect_ref
              | "consumes" , ":" , effect_ref
              | "dissemination" , "{" , { dissem_rule } , "}" ;
dissem_rule    = "->" , target , ":" , channel_ref
              , [ "filter" , ":" , predicate ]
              , [ "alternative" , "{" , dissem_rule , "}" ] ;

flow_decl     = "flow" , id , "{" ,
                  "from" , ":" , mech_ref ,
                  "to" , ":" , mech_ref ,
                  "carries" , ":" , effect_ref ,
                  "via" , ":" , channel_ref ,
                  [ "filter" , ":" , predicate ] ,
                  [ "redundant_paths" , ":" , "[" , { path } , "]" ] ,
                "}" ;

guarantee_decl = "guarantee" , id , "{" ,
                    "over" , ":" , scope_or_flow_ref ,
                    "property" , ":" , property_expr ,
                    [ "assumes" , ":" , "[" , { id } , "]" ] ,
                    [ "degradation" , ":" , degradation_spec ] ,
                 "}" ;

recovery_decl = "recovery" , id , "{" ,
                   "for" , ":" , mech_ref ,
                   "trigger" , ":" , trigger_spec ,
                   "source" , ":" , source_spec ,
                   "strategy" , ":" , strategy_spec ,
                   [ "window" , ":" , duration ] ,
                   [ "anchor" , ":" , expr ] ,
                   [ "post_recovery" , ":" , action_spec ] ,
                "}" ;

gc_decl       = "gc" , id , "{" ,
                   "for" , ":" , archiver_ref ,
                   { gc_rule } ,
                   [ "guard" , ":" , predicate ] ,
                "}" ;
gc_rule       = "rule" , id , "{" ,
                   "trigger" , ":" , trigger_spec ,
                   "condition" , ":" , predicate ,
                   "action" , ":" , "prune" , "(" , prune_spec , ")" ,
                   [ "applies_to" , ":" , "[" , { id } , "]" ] ,
                "}" ;

(* Predicates and expressions *)
predicate     = comparison
              | predicate , ( "and" | "or" | "=>" ) , predicate
              | "not" , predicate
              | "(" , predicate , ")"
              | id , "(" , { expr } , ")"          (* named predicate application *)
              | expr , "is" , type_ref ;            (* type test *)
comparison    = expr , ( "==" | "!=" | "<" | "<=" | ">" | ">=" ) , expr ;
expr          = id | nat | string
              | expr , "." , id                     (* field access *)
              | id , "(" , { expr } , ")"           (* function application *)
              | expr , ( "+" | "-" | "*" ) , expr
              | "(" , expr , ")" ;

(* Trigger specs for recovery and GC *)
trigger_spec  = id , "(" , { id } , ")"             (* event pattern *)
              , [ "where" , predicate ] ;

(* Source specs for recovery *)
source_spec   = source_atom , { "|" , source_atom }  ;  (* disjunction: any suffices *)
source_atom   = mech_ref
              | source_atom , "+" , source_atom ;       (* conjunction: all required *)

(* Lexical *)
id            = letter , { letter | digit | "_" } ;
string        = '"' , { char } , '"' ;
nat           = digit , { digit } ;
letter        = "a".."z" | "A".."Z" ;
digit         = "0".."9" ;
```

---

## 14. Type System

MFS has a simple structural type system for effect payloads and metadata.

### Built-in Types

| Type | Description |
|---|---|
| `SeqNum` | Monotonically increasing sequence number |
| `SessionId` | Leader instance identifier |
| `MarketId` | Market identifier |
| `PartitionId` | User partition identifier |
| `UserId` | User identifier |
| `Signature` | TEE attestation signature |
| `Hash` | Cryptographic hash |
| `Timestamp` | ISO 8601 timestamp |
| `Duration` | Time duration (e.g., `Delta`) |

### Type Constructors

```
Set<T>          -- unordered collection
Seq<T>          -- ordered sequence
Map<K, V>       -- key-value mapping
T | U           -- union type (effect payload variants)
Optional<T>     -- nullable type
```

### User-Defined Types

Domain-specific payload types are declared with `type`. Types can be opaque (no fields, treated as abstract) or structural (with named fields).

```
<type-decl> ::= "type" <id> [ "{" <field-list> "}" ]
             | "@opaque" "type" <id>
```

**Examples:**

```mfs
type MatchFinalizationResult {
  fill_id: FillId
  status: Confirmed | Rollback
  affected_users: Set<UserId>
}

type SharedUserAssetSnapshot {
  user: UserId
  balances: Map<AssetId, Amount>
}

@opaque type ChainEvent
@opaque type InterestApplied
@opaque type PendingMatch
@opaque type FilteredUpstreamEffect
```

`@opaque` types are used for domain types whose internal structure is irrelevant to the mechanism specification. They participate in union types and effect payloads but their fields are not inspectable in MFS predicates.

---

## 15. Conventions

- **Identifiers**: `snake_case` for values and fields, `PascalCase` for types, `UPPER_CASE` for constants.
- **Qualified names**: `Service.mechanism` or `Service[param].mechanism` for parameterized services.
- **Scope references**: use the scope name directly, with parameters if needed: `per_market(m)`, `global_inventory`.
- **Effect references**: use the effect type name, optionally with parameters: `ce_effect`, `ob_effect(m)`.
- **Channel references**: use the channel name directly.
- **Indentation**: 2-space indent, no tabs.
- **File extension**: `.mfs`
