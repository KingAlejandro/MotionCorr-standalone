# Issue #97 — port onto current main, Linux validation

Raw log: `port_validation.log`. Harness: `port_validation.sh`, which runs
`port_assertion_margins.py` and `port_option_off_control.py` from the candidate tree and
hashes both before running them. Second platform: `port_validation_darwin.log`.

## Identity

Both trees are real clones checked out from the remote — the base at the merge base, the
candidate at the PR branch — so nothing in the trust chain depends on a patch file that is
not in the repository. Builds are Release, out of tree, with differing
`CMAKE_HOME_DIRECTORY`; a copied build tree caches an absolute source path and would
rebuild the original sources.

| | |
|---|---|
| base | `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38`, tree `9f5dd916…`, clean |
| candidate | `b8505dde04cfea68e78f8bee9d6d12210f19ce5e`, tree `59836c09…`, clean |
| binaries | base `ce9b97d1…`, candidate `789171c3…` |
| host | cpu64 (`small-refmac-machine`), CPUs 40-55 on NUMA node 1, `membind=1`, `flock /tmp/motioncorr-issue96-cpu-validation.lock`, `-j16` |

The log prints `git diff --stat` over the whole tree and `diff -r` over the whole of `src/`.
The only production delta is the fix. No timing is measured or claimed: `ctffind` was
running on the same box throughout.

The prose in this file and in the PR body was written after the run; nothing else in the
candidate tree changed, so the validated tree is the PR head minus those edits.

## Results

| Check | base | candidate |
|---|---|---|
| `ctest` | 18/18 pass | **20/20 pass** |
| `ctest -R RunnerInterpolate -N` | 0 — both cases are new | 2 |
| `validate_test_collection.py`, candidate validator on both builds | FAIL: 18 < 20, both names missing | PASS at 20 |
| `runner_numerics interpolate_recenter` | absent | pass — 4 witnesses and the empty-input guard |
| `test_runner_contract.py --case interpolate_shifts` | **fail, exit 1** | pass, exit 0 |
| option-off MRC pixel payload, 65 536 B | **identical** | |
| option-off per-movie STAR | **0 of 119 lines differ** | |
| option-on MRC pixel payload | differs — the intended correction | |
| option-on per-movie STAR | 90 of 155 lines differ | |

The MRC comparison is of the pixel payload from byte 1024, not the whole file: the header
carries a creation timestamp. The STAR denominators are whole-file line counts, so no line
is excluded from the comparison before it is made.

## Which assertions reject the unfixed binary, and by how much

9 patches × 2 axes = 18 observations.

| assertion | base | candidate |
|---|---|---|
| serialized frame numbers `[2..8]` | 0/9 violations | 0/9 |
| option-off group layout `[3,5,7]` | 0/9 | 0/9 |
| value at the first selected frame is 0 | 0/9 | 0/9 |
| **cross-arm anchor, frame 3, exact** | **18/18** | 0/18 |
| **cross-arm anchor, frame 5, ≤ 3e-5** | **18/18** | 0/18 |
| **segment linearity, ≤ 3e-5** | **18/18** | 0/18 |

The first three hold on the unfixed binary. They are the `--first_frame_sum > 1` and
unequal-final-group coverage the case was added for, not defect detectors, and the test
says so where they are asserted. The value at the first selected frame is the number the
original code manufactures.

**The margin is a range, and the weak end is the one that matters.** Each detector is
violated by between **0.000444 px and 0.068627 px**, which is **15× to 2288×** the 3e-5
tolerance. The 15× observation is the weakest thing the detectors are asked to resolve; it
is a Y-axis patch whose local motion is nearly flat. On the candidate the cross-arm anchors
agree to 0.000000 and the linearity residual is at most 0.000010, inside the 2e-5 analytic
rounding bound (four values, each `%12.5f`/`%12.6f`, so 5e-6 apiece —
`src/metadata_table.cpp`).

The step floor is calibration, not decoration. `alignPatch` leaves the first group shift at
exactly `+0.0` and the first group centre is frame 1, so the correct field has
`interp(1) = 0` and the first-segment step equals the discarded origin exactly. 9 of 9
patches in X and 6 of 9 in Y clear 100× the tolerance; the test requires at least 3 per
axis. On the unfixed binary every step is 0.000000, which is the kink itself.

## Not run

No GPU. The recentering is backend-shared host code with no device-side copy, so a CUDA
build compiles the identical arithmetic; what a native run would add is that the CUDA
patch-alignment path feeds its own group shifts into it. No slot is assigned to this issue.
CI's `cuda-compile` job covers compilation only.

No downstream scientific claim. One synthetic fixture on this port; the full-size real
movie is in the retained `README.md` evidence against the earlier base `4c952b3`. Defect
frequency across the 24-movie set is unmeasured. No timing.
