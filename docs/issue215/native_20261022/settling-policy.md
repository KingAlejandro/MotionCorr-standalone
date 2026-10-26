# Attempt04 post-run idle policy

This is an explicitly authorized experiment-driver change. Attempt03's
immediate post-run sample reported 6% utilization, no assigned-GPU compute
applications and 1 MiB memory; its recorded hardware fields passed. A later
locked read-only sample reported 0% utilization with the same memory and
healthy fields. These are observations, without an assumed hardware cause.
Attempt03 remains FAIL; its receipts and archive must never be rewritten.

The initial preflight still requires strict one-shot idle. After the native
subprocesses finish, while retaining the canonical GPU2 correctness lock,
the new driver takes read-only samples. It requires two consecutive samples
at 0% utilization, no assigned-GPU compute apps, memory at most 16 MiB,
correct index/UUID and all existing healthy hardware fields. Samples are
spaced by one second after completion. A monotonic deadline bounds the entire
settling window, including query execution, to at most ten seconds; completion
at the deadline fails. Each query receives only the remaining timeout budget.

Only nonzero utilization on an otherwise healthy, empty assigned GPU may
settle. Any missing/invalid health field, hardware error, incorrect UUID/index,
assigned-GPU compute app or unexpected memory immediately fails without another
sample or GPU workload. A nonzero-utilization sample resets the consecutive-idle
count. A single idle sample and persistent busy utilization both fail at timeout.
Raw initial/subsequent query logs and command receipts are retained separately;
completed validly parsed samples are also recorded before policy validation.
An XML parse/health failure retains its raw XML and a FAIL error receipt.

`test_postrun_idle.py` uses fake samples and a fake monotonic clock, including
failures at each sample position, deadline overrun and read failure. It also
calls the original `run_native.health` against a 6%-then-0% sequence and confirms
that its first one-shot assertion still fails. No old verdict is reclassified.

Attempt04 reuses the exact fc1c8e6f source and attempt01 binaries. All 7,260
archived source files and all three binary hashes are checked before and after.
Driver file hashes are recorded separately from compiled-source/binary hashes;
there is no rebuild. The unchanged eight later-chunk and nine early controls,
fixtures, conversion oracle, product comparator and acceptance predicates run
only after host checks, lock acquisition, bench-lock probe and strict preflight.
No numerical threshold, product gate or scientific/performance claim changes.
New scratch and a separate archive/index retain attempt04 independently.
