# Final pilot report: native local full-width CCF weight pilot (cpu64, CPU only)

Supersedes the HELD wording of `pilot/README.md` and `FINAL_PACKET_INDEX.md` (kept as the historical record). A fresh independent result audit, not the author, is still required; nothing here is an acceptance, adoption, full100 or GPU claim.

## Terminal headline
The frozen 8-case pilot finished with **16 of 16 producers (1 old + 15 new), every exit 0, no timeout, no STOP in r2, driver rc 0 / lane rc 0**, and the frozen rules returned `prediction SUPPORTED`, `acceptance NOT_ACCEPTED_NO_AUTOMATIC_ACCEPTANCE`.
The global budget (16) is exhausted; no producer will be added. At 23:34:26Z no owned process remained and none of the 8 lock inodes carried a flock entry.

## How it got there (all records kept)
1. r1 (driver v5.1, 23:02Z): noisy OFF ran (exit 0); the pre-ON gate then stopped on `COMPARATOR` (the durable baseline path was passed as comparator root A over files embedding the original scratch root). **That STOP stays a STOP**, not a retrospective PASS (`native_r1/`, `DIAGNOSIS_r1.md`).
2. Saved-file diagnosis: only the two embedded-root lines differed; with root A = the original scratch root the unchanged comparator reports IDENTICAL. Raw OFF runtime and case STAR were byte-identical to the baseline; MRC header and payload equal.
3. Repair (v5.2, reviewed independently): baseline root metadata fix with a new ROOT_AUDIT, reuse of the one produced OFF by hash (never relaunched), a driver for the remaining 15; the parent wrote a new release (`release_v5_2/`).
4. r2 (driver v5.2, 23:31:37Z-23:32:19Z): REUSED event, pre-ON re-evaluation of the saved noisy OFF (comparator IDENTICAL), noisy ON, then the 7 other cases OFF/gate/ON.
Mixed provenance: the first OFF ran under v5.1, the 15 later launches under v5.2; launch, sampling, lease and cleanup code is identical. The parent's first release-writer attempt hit an existing directory by a literal slip and was refused by an exclusive `mkdir` before any write (`native_r2/PARENT_SETUP_ATTEMPTS.md`).

## Result under the frozen rules (the retained DECISION wording is quoted verbatim in `AUDIT_TABLES.md`)
- P1: affine, pedestal, zero, integer, fractional: PASS on runtime and actual STAR in both arms (.20/.40/.80 A).
- P2: noisy ON strictly lower than OFF in rms, p95 and max on both fields. Runtime 1.6454 -> 1.0954 (rms), 3.3373 -> 2.2402 (p95), 7.2840 -> 4.4692 (max) A; STAR 1.6454 -> 1.0954, 3.3373 -> 2.2403, 7.2838 -> 4.4693.
- The noisy raw gate remains **FAIL** on both fields; the improvement is bounded, not an accuracy acceptance. Increases list: empty. flat and repeated: UNIDENTIFIABLE, raw distances unchanged between arms (rms 2.1044 and 9.0126 A).
- Recomputation from the audit bundle with the pinned field operator matches DECISION.json to 6.2e-15 A. STAR vs runtime field roundtrip maximum: at most 5.5e-4 px (noisy ON), 0 to 1.9e-4 px elsewhere.

## Reported separately (records, no new gate; `AUDIT_TABLES.md`)
- Global pair equality: float64 bits and the serialised global STAR block equal OFF vs ON in all 8 cases; global DC and coupled counters equal pairwise; the five global-only pairs have identical runtime, case STAR and whole-product comparator output.
- `local_enabled`: True on the three 3x3 cases (witness 9 ON, 0 OFF), False on the five 1x1 cases. Local DC-eligible counts equal OFF/ON (noisy 115, affine and pedestal 55).
- Convergence/acceptance: global converged in all 16 runs. Patch convergence: noisy 8 of 9 converged and 1 not, in both OFF and ON; affine and pedestal 9 of 9 in both arms. Per-patch rejection counts are not recorded as such in the saved logs or receipts and are not derived here. Polynomial-fit RMSD is in the tables.
- Resource sampling: `OBSERVED` in all 16 runs, 7 samples each (stored all, none truncated), 0 read failures, 0 vanished reads, 0 missing children files, max Threads 2 and max tasks 2, mask `32-47` as the kernel reported it, 3 processes seen, span 0-123 ms, wall about 0.13 s. A record only; `--j 2` was not treated as proof.

## Evidence separation and limits
Native evidence: the 16 real-binary runs above. Synthetic evidence: the driver/consumer tests (fake child, crafted scores), which establish consumer and driver logic only (the "synthetic" wording in the DECISION scope refers to those tests). The noisy case is **one exposed realization**: no noise-origin causation, no p-values, no independent-seed claim.
Historical N5/9/13/20 and harm evidence is retained unchanged; no new qualification of those rows. Not established: full-field or real-movie accuracy, byte neutrality beyond the compared products, GPU behaviour, any default or adoption change. full100, GPU and adoption remain UNRUN/held. No evidence comment, watcher or merge was made.

## Where everything is
`FINAL_INDEX.json` (commits, durable archives with COPY_INDEX hashes, the namespace verification), `final_remote_verification_23_34Z.txt` (per-file hashes on cpu64), and the read-only audit bundle `~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1/` (258 files; `BUNDLE_MANIFEST.json` here is its manifest, sha256 `49698c7c...`). Bundle excludes MRC pixel payloads, EPS/PDF products and the large baseline trees (hash-bound in `products_inventory.json`); full products stay on cpu64 and in the durable run archive.
