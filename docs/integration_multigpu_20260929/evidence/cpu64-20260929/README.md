# CPU validation of the composed candidate — cpu64, 29 Sep 2026

Two runs are retained. The first is the authoritative build-and-test at
`1793e7e`; the second re-runs everything after the independent review's fixes,
at `d8dbf75`, including the CMake change that removed a duplicate test.

| | |
|---|---|
| Host | `small-refmac-machine`, 64 logical CPUs |
| CPUs | `taskset -c 32-47` (16, within the 32-63 validation range), `numactl --membind=1` |
| Lock | `/tmp/motioncorr-issue96-cpu-validation.lock`, `flock -w 3600` |
| Build | Release, `-DCUDA=OFF`, `-DBUILD_TESTING=ON`, `-j16`, `Python3_EXECUTABLE=~/.mc-venv/bin/python` |
| Untouched | ctffind PIDs 1156942 and 1635429 |

## Results

| Check | `1793e7e` | `d8dbf75` (post-review) |
|---|---|---|
| Configure + build | PASS | PASS |
| Required-test collection gate, `--min-count 23` | 23/23 | 23/23 |
| CPU CTest | **23/23** | **23/23** |
| PR117 mutation harness on the composed tree | **83/83 detected, 0 skipped** | — |
| `verify_composition.py` provenance oracle | — | PASS, 3 declared reconciliations, 0 unsourced |
| `test_aggregate_sampler.py` | — | **8/8** |

The mutation harness is the load-bearing CPU check. 83 targeted source mutations
are applied one at a time to a scratch copy and the cases that should then fail
are re-run; a mutation whose case still passes is a check that cannot observe
what it asserts. Zero skipped, so no mutation was excused for a missing
executable. Among those detected on the composed tree are PR117's two frozen P1
fixes — `merge accepts an empty required-product list` and `launcher mistakes
zombie-only groups for live survivors`.

## A failure worth keeping

The very first attempt reported 22/23: `CiFailClosedControls` control 2 shells
out to `cmake`, and the driver's `PATH` did not include `~/.mc-venv/bin`, where
cmake and ctest live on this host. The source was not involved. Both runs above
have the toolchain on `PATH`. Retained because "one test failed, then passed on
re-run" is exactly the shape a real flake takes, and the distinction is the
recorded cause.

## Files

`source.txt`, `source-status.txt`, `toolchain.txt`, `achieved-mask.txt` —
provenance, including the mask read back from `/proc/self/status` rather than
restated · `status.txt` — exit codes · `ctest.log`, `ctest2.log` ·
`validate-collection.log`, `validate2.log` · `negative-controls.log`,
`negative-controls.json` — the full 83-mutation matrix ·
`occupancy-before/after.txt` — what else was running ·
`recheck-after-review-fixes.log` — the complete post-review driver output.
