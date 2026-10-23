# Parent checkpoint after v2.2 R3

Independent R3 found no material source/local-control blocker at exact
`593c9e2cc53663655a1628ab7500fadddee5d261` for consideration of one bounded
read-only CPU13 regrade. The tested code remains `dd38b6ad`; this checkpoint
only retains review and packaging records. It changes no native source,
grader, test, plan, gate or historical result.

Selected review files in `review-r3-v2.2/` were checked against the original
whitelist and copied byte-exact. The main reviewer campaign exited0; its
separate supplemental index-isolation harness exited1 because the bypass
mutant was rejected before the planned injection. That failed harness is
retained and is not described as a fully passing mutant campaign. The
review's local/source verdict is not a Linux or remote-runtime result.

The parent generated a 122,880-byte package from exact reviewed commit
`593c9e2c`, byte-identical to the reviewer's final-head package. Its receipt,
tar and launch record are under `parent-package-v2.2/`. Attempt1 correctly
refused the non-canonical macOS `/tmp` parent; a subsequent copy found no
package. Both errors are recorded. A distinct attempt2 used canonical
`/private/tmp`, unchanged code and a new output namespace; it exited0.
These are local packaging operations, not attempts at the remote regrade.

At 13:10–13:11 UTC on 23 October, a separate bounded connection diagnosis
could not establish a TCP connection to the configured gateway, before
authentication or target forwarding. It ran no remote command. Raw network
diagnostics remain local, outside this repository. Target occupancy and the
current status of previously launched C1/DC jobs are unknown; no restart,
route override, credential or service change was made.

**Remote regrade remains HELD/UNRUN.** No transfer, extraction, driver or
native invocation ran. Restore the established access path and reconcile
live resources before scheduling; CPU13 must be used serially with W4's
separately reviewed capture. The reviewed per-operation lease, identity
checks, bounds and no-retry rule remain prerequisites. GPU work stays
paused. This note itself is not execution authorization.

Original subset **FAIL** (24 CPU row PASS, 3 pair PASS / 5 FAIL, N4 PASS),
16 CUDA rows **UNRUN**, and aggregate **INCOMPLETE** remain unchanged.
The local retained tar gives STAR PASS / FULL UNRUN; genuine MRC payload
regrading is still missing. No full-precision, production-guard safety,
science, performance, parity adoption or merge recommendation follows.
