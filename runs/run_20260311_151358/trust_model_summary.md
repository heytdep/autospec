CE/OB/OMS: TEE-attested, crash-only. TEE provides integrity, non-equivocation, message authenticity.
Archivers: non-TEE, availability-only faults. f+1 redundancy (one honest suffices). Cannot forge/reorder (TEE sigs + encryption).
Network: async, eventually reliable (partial synchrony). Messages can be lost/delayed.
Authority: external endorsement via sig+timestamp for leader transitions. L1 contract for checkpoint truth.
TEE guarantees available: non-equivocation (D101), attestation replacing sigs (D102), Byzantine-to-crash already applied (D103), single honest archiver (no quorum certs needed).
