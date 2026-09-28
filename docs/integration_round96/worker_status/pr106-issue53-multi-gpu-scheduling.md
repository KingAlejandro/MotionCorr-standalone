# Issue #53 / PR #106 — static multi-GPU whole-movie workers, ported to current main

**Status:** ported and validated; awaiting final-source review. Not merged, nothing closed.
**Branch:** `integrate/pr106-issue53-static-workers`
**Base:** `origin/main` `5ada983cfd1d6d8ef411120286402e380bdd4747`
**Source of the port:** PR #106 `round96/53-claude-opus-5` at `a52e967`, which branched from
the pre-PR110 main `4c952b3`. The old branch is untouched.

## Why this is a port and not a merge

PR106 predates the PR110 correctness foundation. Only two files are touched by both
(`git diff --name-only` intersection): `CMakeLists.txt` and `src/motioncorr_runner.cpp`.
Neither is a textual conflict — main's own edits to the runner are at `:104`, `:121` and
`:306`, leaving the `--gpu` block untouched — so the risk was never Git. It was semantics.

## Semantic overlap that had to be resolved

**Test registration is pinned in three places on current main, not one.** Adding
`MultiGpuScheduling` to `CMakeLists.txt` alone leaves it collected but not required.
Adding it to `tools/validate_test_collection.py` alone breaks
`tools/test_ci_fail_closed.py`, whose `INTEGRATED_SUITE` asserts that a 17-name
collection *passes*. All three move together, and the new name is added to that file's
drop-one loop so the required test has a control proving the guard can see its absence.

**`isMovieComplete()` is option-dependent, and PR110 made it frame-count dependent**
(`src/motioncorr_runner.cpp:596-620`). `merge_workers.py --aggregate-with` runs the stock
binary with `--only_do_unfinished` to regenerate the dataset STAR, so mismatched
`--aggregate-args` now reprocess movies the merge has just certified, overwriting the
staged products in place. The merge digests every staged product before that pass and
requires them to survive.

**PR110 changed nothing else the tooling depends on.** It added no per-movie product and
removed none; `tools/compare_motioncorr.py` is byte-identical between `4c952b3` and
`5ada983` (blob `f9124ae`), so `compare24.py`'s dependency is intact.

**`/WORKER_STATUS.md` is gitignored on main** (`.gitignore:20`, added by #98), so PR106's
root-level status file is not carried over. This file replaces it.

## Findings closed during the port

Five findings filed on PR106's own head were never implemented, and all five are
reproducible false PASSes: launcher-owned `--i`/`--o`/`--gpu` overridable in worker
arguments; `--status` not bound to the run being merged; a movie named twice in one shard;
a stale comparison report rebound to new inputs; the comparator pinned by path but not by
contents.

An independent oracle audit of the ported tree found a sixth, larger one: **no test
executed the launcher's witness-to-verdict wiring**. Replacing it with an unconditional
`status["verdict"] = "PASS"` left the whole suite green. Harm class (d) — wrongly
witnessed work — was the only one of the four with no dedicated control. It now has
`case_launcher_verdict_follows_the_device_witness`, which drives `run_multi_gpu.main()`
in-process against a faked `nvidia-smi` across six scenarios, plus seven mutation entries.

The audit also found a reachable PASS the guard's own comment disclaimed: the sampler
caught only `WitnessError`, so any other exception killed the thread silently, `join()`
succeeded, and a run that stopped being observed after two seconds certified itself.

## Validation

**cpu64** (`small-refmac-machine`), cores 32-63, build `-j 16`, Release `-O3 -DNDEBUG`,
g++ 13.3.0, cmake 4.4.3, Python 3.12 + numpy 2.5.3, under
`flock /tmp/motioncorr-issue96-cpu-validation.lock`. Two colleague `ctffind` jobs left
untouched. Commands and full log: `docs/multi_gpu/port_validation/`.

**4GPUs**, two arms. A CUDA build was required rather than optional: the ported hunk
splits on `#if defined _CUDA_ENABLED` and every CPU build compiles the other side, so the
live path had never been compiled on this branch. nvcc 12.8.61, sm80, `CUDA_BUILD_RC=0`.
Then a native two-worker two-GPU run on GPU2/GPU3, selected by UUID and asserted idle
first, on disjoint masks 96-103 / 104-111: `verdict: PASS`, two distinct physical UUIDs,
69 witness samples, merge PASS over 96 files, and **24/24 exact** against the retained
serial CUDA baseline. Separately, the tooling was revalidated over the retained outputs
with no GPU compute at all.

The native arm was budgeted as a four-movie smoke check and ran all 24: the STAR
subsetter looked for a column this dataset does not have and silently wrote the input
back unchanged. The expected-count assertion caught it, and the subsetter now uses
`star_io.render_with_rows` with the row count asserted.

## Superseding the round-96 integration counts

`docs/integration_round96/OVERLAP.md:44-46` and `MERGE_EVIDENCE.md:24` are PR110's
retained evidence and are correct as of PR110. They are superseded here, not edited:
the suite is now **18 required names, `--min-count 18`, 18 CTests**.

## Not established

No timing, throughput or scaling figure — none measured, none claimed. #26 owns the
measurement matrix; `docs/multi_gpu/SCALING_EXPERIMENT.md` specifies the arms and names
the six per-worker quantities that are not recordable today.

More than two devices, `--grouping_for_ps`, `--even_odd_split`, EER, gain rotation/flip
and other geometries are unrun. `logfile.pdf` equivalence is excluded by construction.
CPU/RELION Gate 2 is untouched and still separately failing. The C++ device-list guard
cannot be mutation-tested, because mutating it needs a rebuild; its control is the
recorded unpatched-main binary in `docs/multi_gpu/gpu_evidence/a0_device_list_witness.log`.
