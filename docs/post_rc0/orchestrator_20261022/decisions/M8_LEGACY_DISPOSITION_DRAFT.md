# M8 legacy PR disposition — unapproved decision brief

Fresh 22 October REST snapshots of each PR, all conversation comments and reviews
are retained beside this draft. This is scope/evidence triage, not a new full
source audit, native test, performance measurement, or permission to close/merge.
All four PRs remain open. Preserve heads and linked historical evidence regardless
of the maintainer's eventual open/park/close decision.

| PR and pinned head | Evidence to retain | Proposed M8 disposition and reason |
| --- | --- | --- |
| [#64](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64), 401a810ff7bbb100bff84b14c3cc3c536eb9cc9f | Corrected INCONCLUSIVE calibration; withdrawn blocking limits; leaked/unblinded holdout and no unacceptable cells on the movie holdout; warning-tier result at 10 Å²; original controls and failures. | Park as an archived research branch, or close without merge after pinning links. It establishes no replacement blocking gate, and its own body says not for merge. Keep warning evidence as well as withdrawn claims. |
| [#138](https://github.com/KingAlejandro/MotionCorr-standalone/pull/138), 875857f1ba3390c53cdf97f68afaa2a1f1e4832b | Historical nvCOMP 8-bit/multi-row widening experiments and format matrix; narrow checksum/status fixes were separated. Tutorial re-encodes and repeated frames are not fresh deposited-collection or current-pipeline performance evidence. | Park/close historical stack without importing it into C1. Latest discussion says later #206 port is parked under T1. D1 already selected a trusted immutable-input precondition; do not describe that policy as unresolved or as malformed-input safety proof. Any future widening starts on current source with actual-beneficiary justification and qualification. |
| [#46](https://github.com/KingAlejandro/MotionCorr-standalone/pull/46), 2ef82b0279d0db7403daf9ba6c2943888f3a0321 | Historical Metal feasibility assumptions, runtime/build scope, and later #52/#119 evidence. Projected 10–14× speedup is not measured qualification. | Park/close historical implementation/design stack, retain the ADR with a clear superseded/historical status if narrowly extracted. Do not merge as implementation approval or close #35 via its stale wording. Metal is excluded from the active C1/C2 scope. |
| [#52](https://github.com/KingAlejandro/MotionCorr-standalone/pull/52), edb57b5d91ec0719d7285a16a4771b886d979e65 | Real tutorial relaxed-profile FAIL (relative RMSE 0.01322–0.01323), two-run exploratory 1.04× ratio, component probe limits and tested source637b8117. | Park/close the historical stack after evidence links are pinned; optional narrow documentation extraction later. The current backend diagnostic profile does not retroactively pass the historical run. Component timing is not application speedup or backend acceptance. |

This proposal changes no issue state, PR state, support class, gate, default,
D1/T1 disposition or licence. A maintainer may keep any branch open instead.
If closure is selected, retain exact commit links and evidence references first,
and record that closure is administrative, not a successful scientific or native
acceptance. No branch deletion is proposed.
