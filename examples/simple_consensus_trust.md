# Trust Model: Simple Consensus with TEE

## Assumptions

- All replicas run inside a TEE (Trusted Execution Environment)
- TEE provides:
  - **Non-equivocation**: a replica cannot send conflicting messages in the same round (e.g. vote for two different values)
  - **Attestation**: any replica can verify that a message came from a genuine TEE-protected replica
  - **Liveness attestation**: the system can query which replicas are currently attested as live
- Authenticated channels between all replica pairs (provided by TEE attestation)
- At most f < n/2 replicas may crash (crash-fault, not Byzantine, due to TEE)
- Network is asynchronous but eventually delivers messages (fair lossy links)

## What TEE does NOT provide

- TEE does not prevent crash failures
- TEE does not guarantee message ordering or timing
- TEE does not prevent a compromised host from dropping messages (only from forging them)
