# Parent verification: cpu1d T24 CPU local, 22 October 2026

Read-only snapshot at **23:24:59 UTC**, after the one cpu1d launch. Native tested source remains `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; this commit adds evidence only. No native run, comparator or experiment was repeated to collect it.

**Bounded engineering PASS for T24 CPU L only:** the 24-movie candidate 5×5 local run and same-host frozen-F baseline exited0. The unchanged products comparator returned a complete IDENTICAL report/exit0:24 movies,24MRC,25STAR each side, no differing files/products. All24 MRC header/extended-header/payload hash triples agree; STAR identity uses the documented output-root normalization, not raw-tree byte equality.

The parent checked source cleanliness, both binary identities, input STAR, original F-L RUN hash `4b2ffd1f…7cb`, CPU8–9/OMP2, stage exits and comparator/class/report/invocation hash bindings. The candidate's cleanup receipt has no remaining process and no SIGTERM/SIGKILL. This is receipt verification rather than a new independent live-process census of that already completed native invocation. `readback.json` retains all reports, native RUNs and stage commands/exits; `verify-parent-L.py` is the exact collector/verifier. The metadata read ran pinned to CPU13 after the separate DC analysis had completed. Timings are unqualified under shared-host concurrency.

Together with the separate `../parent-G-20261022/` snapshot, both CPU tutorial configurations match49 expected products each. These results do not validate the dataset launcher or pending CUDA tutorial attribution. K267 field/status compatibility remains1 PASS/5 FAIL/2 UNIDENTIFIABLE on CPU; historical truth failures and old ABORT reports are retained separately.

No stop file was present at the snapshot. Remaining census/image/recovery/GPU rows and final C1 qualification remain incomplete. No science, performance, support-class or merge recommendation follows. No production source, test, build, CI, gate, tolerance or dependency changed; raw movie payloads were not rehashed by this collector.
