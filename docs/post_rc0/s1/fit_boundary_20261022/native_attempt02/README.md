# Native attempt 02

This is the single new host-only attempt authorized after the parent admission
state change at 16:35:54 UTC. Historical attempt PID3032254 and its exit75,
original result.json/evidence archive and frozen expectations remain unchanged.

Source is the git archive of `5c8f6b4f9242510545f852c15065bd93e762a2a1`.
`prelaunch-source.json`, `frozen-launch-plan.json`, `launch-command.py.txt`
and `transport.json` retain the prelaunch binding, exact launcher, environment,
and detached launch receipt. `run_remote.py` is used byte-unchanged from that
source. The archived oracle and CMake equal implementation `135ee09e`.
`archive-source-manifest.json` binds every archived regular file; the remote
source receipt additionally binds the unpacked tree actually compiled.

Resources: 4-gpu-vm via `ssh -J ccp4-gateway 4GPUs`; fresh scratch
`/mnt/clathrin/alex-motioncorr-fit-boundary-native-attempt02-20261022-5c8f6b4f`.
CPUs8–9 only, build parallel 2, runtime CPU 8, numeric threads 1; no CUDA context
or GPU allocation. The unchanged driver records optional read-only GPU health.
Both locks use nonblocking acquisition. No retry is authorized on a busy lock.

The focused build targets runner_numerics and motioncorr. The targeted runnable
collection comprises the four new registrations; all generated required names
and the four drop-one controls are checked separately. Full-suite runnable
qualification is UNRUN because unrelated helper binaries remain unbuilt.
No placeholder binaries, requirement waiver or full suite execution is planned.

Process-credential redactions cover irrelevant access tokens in process command
lines only; full raw receipt hashes and locations remain indexed. Numeric
outputs, source identities, PIDs, CPU occupancy and command exits are unchanged.

## Actual attempt02 result

**BLOCKED / attempt FAIL, exit1; native oracle UNRUN.** Detached PID 3036046
launched at 2026-10-22 16:39:43.774146 UTC and released all owned locks at
16:41:50.515566 UTC. Read-only reconciliation at 16:42:41.044491 UTC found
the PID absent, no matching task processes and both locks FREE.

Release CPU configure/build of runner_numerics and motioncorr **PASS**, exit0.
All 7,475 archived regular files match the unpacked source before and after
build. The compiled test source matches oracle commit 135ee09e; the generated
adapter contains the unchanged production matA/solve body verbatim.
`result.json` retains archive, test, adapter, executable and expectation hashes.
Object/dependency identities and actual compiler/link commands are archived.

CTest JSON collection succeeds with 84 entries, including the four new real
commands. The following unmodified driver step fails before any test runs:

```
/home/alex/.mc-venv/bin/python3 \
  <source>/docs/post_rc0/s1/fit_boundary_20261022/check_registration.py \
  <source> <build> <receipts>
# exit1, AssertionError at check_registration.py:30
```

CMake 3.28.3 emits `add_test([=[RunnerFitBoundary]=] ...)`; the helper's shlex
parser returns literal `[=[RunnerFitBoundary]=]`, while CTest returns
`RunnerFitBoundary`. All 84 names therefore fail equality, despite 84 actual
registrations. `CTestTestfile.cmake`, original stderr and the full name diff
are retained. This is a declaration-helper portability defect. No helper,
production math, input, mask, policy, bound or tolerance was changed.

Targeted runnable validation, required/four-drop-one validation, focused
recenter/model controls, seven native oracle cases, three direct mutant modes
and CI drop-one controls are **UNRUN** because the driver stopped first.
No native coefficient, field, rank, condition or mutant-kill result exists.
Full runnable collection remains **UNRUN**: 33 unrelated helpers have no
command in this focused build. Full suite, GPU execution, corpus,
reconstruction, scientific and performance qualification are **UNRUN**.
No retry or additional native execution was made after the failure.

`evidence.tar.gz` contains compact raw receipts (no binaries or large products),
with per-member sizes/SHA256 in `evidence-index.json`. Read-only optional GPU
queries in the unchanged driver are resource provenance only. Parent owns any
subsequent helper repair, fresh authorization, independent review and publication.
