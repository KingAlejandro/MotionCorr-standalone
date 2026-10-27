# Parent verification: cpu1d T24 CPU global, 22 October 2026

Read-only snapshot at **22:59:43 UTC**, after the one cpu1d launch. Tested native source remains `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; this checkpoint changes evidence only. No native command, comparison or experiment was rerun to collect it.

**Bounded engineering PASS for T24 CPU G only:** the candidate and same-host frozen-F CPU native runs exited 0, and the unchanged products comparator exited 0 with a complete IDENTICAL report: 24 movies, 24 MRCs and 25 STARs on both sides, no differing files/products. All 24 MRC header/extended-header/payload hash triples agree. STAR identity uses the comparator's documented output-root normalization; this is not an assertion that all raw tree bytes match.

The parent checked report/class/invocation hash bindings, exact source cleanliness, candidate CPU binary `5692c6dc…dc3c`, frozen-F CPU binary `43cab2b7…b42`, frozen F RUN hash, input STAR hash, CPU mask 8–9 and OMP threads 2. Native G PID 3311888 was gone. Raw commands, exits, start/finish receipts, reports and native RUN records are embedded in `readback.json`; `verify-parent-G.py` is the exact parent collector/verifier used. It ran over SSH through ccp4-gateway, with the remote readback pinned to CPU13 while the independent analysis occupied that core; no timing is qualified.

The same snapshot retains the completed K267 comparison: all eight C1 field/status rows equal same-host F, with **1 PASS / 5 FAIL / 2 UNIDENTIFIABLE**. This is field/status compatibility, not image/signal or scientific qualification. Historic ABORT reports remain separately retained; no old outcome is rewritten.

At the snapshot, the CPU local stage was reserved with no exit, the wrapper and chain were live, and no chain stop existed. Local, census and image qualification remain incomplete. All pending GPU rows, individual-fix CUDA MRC attribution, downstream science and performance remain outside this result. No C1 aggregate PASS or merge recommendation follows.

The verifier's claims are limited to the stored reports/receipts and stated bindings; it does not rehash the entire raw movie collection or rerun the comparator. No gate, tolerance, production source, test, build, dependency or CI file changes.
