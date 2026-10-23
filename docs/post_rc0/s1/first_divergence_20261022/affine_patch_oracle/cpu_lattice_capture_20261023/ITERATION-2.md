# Frozen iteration 2: source-overlay archive binding

Iteration 1 used driver `f73eb930` and exited1 in admission before creating a
campaign directory or launching any MotionCorr process. The failed namespace is
retained at `/mnt/clathrin/alex-motioncorr-w4-affine-cpu-lattice-20261023-f73eb930`.
Its source/input/archive hashes passed; the erroneous extra check expected a
`diagnostic.patch` member inside `mc-residual-overlay.tar.gz`.

Read-only inspection shows that archive contains exactly four already-patched
source files, with names and hashes matching `overlay-binding.json`. It contains
no patch member. The patch itself is retained in Git at PR275 head `6ae48678`;
the parent checked its sha256 `061c5c5b...1a787e4` separately. The first failure
does not question the native binary or an observed numerical result: no native
process ran. It is retained as an admission FAIL, not changed to PASS.

This new iteration keeps the original protocol, resources, eight selectors,
argv, neutrality rules and amendment1. Replace only the archive-member check:
require exactly the four regular files named in the frozen overlay binding,
each at most1MiB and with the pinned patched-source hash. Reject missing, extra,
duplicate, nonregular or wrong-content members. Continue checking the entire
archive hash and the four live patched-source hashes before and after each run.
No patch extraction, application, source change or rebuild is performed.

Use a separately committed `capture_cpu_v2.py` and new scratch namespace. Retain
the old driver, bootstrap/log/exit archive and diagnosis. Before any new native
launch run data-only positive and wrong-inventory/content controls for the
archive binding, plus the existing neutrality/selector controls against v2.
The first attempt spent zero of its native budget; this distinct iteration
authorizes at most eight serial CPU applications, no retry, CUDA still HELD.

Freeze this note before implementing or running v2. A later result/evidence
commit records what actually ran and its exact status. No old truth, fit,
science or native qualification result is relabelled.
