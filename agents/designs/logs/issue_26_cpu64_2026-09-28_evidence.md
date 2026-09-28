# Issue 26 specification evidence — cpu64, 2026-09-28

Raw record for `agents/designs/issue_26_cpu_global_ifft_skip.md` §5, committed so
the digests in that document are checkable rather than merely asserted.

## Environment

| | |
| :-- | :-- |
| Host | `small-refmac-machine` (ssh alias `cpu64`), AMD EPYC 7763, 64 vCPU, 2 NUMA nodes |
| Lane | `taskset -c 32-63` on the top-level shell (children inherit); NUMA node 1 |
| Mutex | `flock -w 7200 /tmp/motioncorr-issue96-cpu-validation.lock` around every build and run |
| Parallelism | `make -j 16`; runtime `--j 4` (synthetic) or `--j 8` (tutorial) |
| Baseline | `origin/main` = `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Toolchain | gcc 13.3.0; cmake from `~/.mc-venv`; `-O3 -DNDEBUG -std=gnu++17 -fopenmp` (CUDA off) |
| Third-party load | two long-running `ctffind` processes, untouched; load1 2.2–16.7 across the session |

No timing claim is made from these runs. Wall values are recorded only as
context; the box was shared and load varied.

## Builds

Three trees, identical except the predicate at the global inverse FFT.

| tree | predicate | binary sha256 |
| :-- | :-- | :-- |
| `src-main-4c952b3…` | *(unmodified main)* | `83e8749a55626b3268983bf9733b4276749539e025034a90ae98afa1f25b75b6` |
| `src-pr57` | `do_local \|\| !do_dose_weighting \|\| save_noDW` | `95e1daf06e2fdb2b92c18b9ead0dd8a588955c33acb391ca111a9b8724450c03` |
| `src-fixed` | `do_local \|\| pre_dw_sum_needed`, the latter shared with the `:2340` guard | `7e05817719790906d0aae46c70370b8794b140c6774ecc0864411a0bf51adcf9` |

Branch head tree (`75fde5f` sources) built and tested separately: build rc=0,
`100% tests passed out of 2`.

## Inputs

| file | sha256 |
| :-- | :-- |
| `20170629_00021_frameImage.tiff` | `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0` |
| `gain.mrc` | `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1` |
| one-row `movies1.star` | `6a851ed446cdcca438fe1fe1fd2fbf759e6593395dcbf54bbb301a7f816c3e15` |
| in-repo `test-data/synthetic/synthetic_movie.tiff` (at main) | `95b5f0d37d481355b8abe30f7380c33d9ea173a87bec6e8fc3e567c057622bd4` |

Digests below are `sha256(bytes[1024:])` of each MRC — pixel payload only,
excluding the header whose label area at offset 224 carries a `strftime`
timestamp. First 24 hex characters shown.

## §5.1 — defect control, `--dose_weighting --even_odd_split --patch_x 1 --j 8`

| output | main | `pr57` | `fixed` |
| :-- | :-- | :-- | :-- |
| `20170629_00021_frameImage.mrc` | `ed33b6299dfc54782aa7f44c` | `ed33b6299dfc54782aa7f44c` | `ed33b6299dfc54782aa7f44c` |
| `20170629_00021_frameImage_EVN.mrc` | `6e006ae913033f1c050e1fda` | `117ad93bdd7b06e6b6080f64` | `6e006ae913033f1c050e1fda` |
| `20170629_00021_frameImage_ODD.mrc` | `62a9e0f978e254f3a6841ccb` | `117ad93bdd7b06e6b6080f64` | `62a9e0f978e254f3a6841ccb` |

Payload witness, sampled on the `motioncorr` process itself rather than a
launcher wrapper: `comm=motioncorr`, `Cpus_allowed_list=32-63`,
`Mems_allowed_list=0-1` (cpuset restricted, memory policy deliberately not),
`VmHWM≈2824016 kB`, resident pages node0=749 node1=705372.

Same control on the in-repo synthetic fixture, `--j 4`:

| output | main | `pr57` | `fixed` |
| :-- | :-- | :-- | :-- |
| `synthetic_movie.mrc` | `8936f180e52933be476413c8` | `8936f180e52933be476413c8` | `8936f180e52933be476413c8` |
| `synthetic_movie_EVN.mrc` | `53c04fbd1dcedea1c4365562` | `84021fd4db8799920eed0dd8` | `53c04fbd1dcedea1c4365562` |
| `synthetic_movie_ODD.mrc` | `3b8b243604d3c7c67bb973ad` | `30e14955ebf1352266dc2ff8` | `3b8b243604d3c7c67bb973ad` |

**Non-determinism.** A later run of the identical `pr57` binary on the identical
synthetic input and options produced `_EVN` = `7c8903dae9a0dd73bfcc914d`, not
`84021fd4db8799920eed0dd8` (`_ODD` was stable at `30e14955…` in both). The
elided path leaves a freshly `reshape`d, uninitialised buffer, so a single clean
run cannot demonstrate absence of this defect.

## §5.2 — CTests

`ctest -j 4` on each tree: `100% tests passed out of 13` for **all three**,
including `pr57`. The suite runs and does not observe the corruption.

## §5.3 — base `3e3a196` writes no EVN/ODD in that combination

`--dose_weighting --even_odd_split --patch_x 1` on the prototype base produced
`synthetic_movie.mrc` only; `_EVN.mrc`/`_ODD.mrc` count = 0. rc=0.

## §5.4 — reference-free oracle

`_EVN`/`_ODD` must not depend on `--dose_weighting` (they are unweighted sums):

| build | `_EVN` with vs without `--dose_weighting` | `_ODD` |
| :-- | :-- | :-- |
| main | `53c04fbd…` = `53c04fbd…` | `3b8b2436…` = `3b8b2436…` |
| `pr57` | `7c8903da…` ≠ `53c04fbd…` | `30e14955…` ≠ `3b8b2436…` |

Usable: true on correct code, false on the defect, no new fixture.

## §5.5 / §5.6 — elision control and peak RSS, `--j 8`, tutorial movie

| config | elides? | output | main | `pr57` | `fixed` |
| :-- | :-- | :-- | :-- | :-- | :-- |
| `--dose_weighting`, patch 1×1 | yes | `…_frameImage.mrc` | `ed33b6299dfc54782aa7f44c` | same | same |
| `+ --save_noDW` | no | `…_frameImage.mrc` | `ed33b6299dfc54782aa7f44c` | same | same |
| `+ --save_noDW` | no | `…_frameImage_noDW.mrc` | `40361e827e571d3d5966a7dd` | same | same |

Core header (bytes 0–223) also identical across all three builds in both configs.

Peak RSS (`/usr/bin/time -f %M`), and wall for context only:

| config | main | `pr57` | `fixed` | fixed − main |
| :-- | --: | --: | --: | --: |
| `--dose_weighting`, patch 1×1 | 3267840 kB (7.91 s) | 3101196 kB (5.92 s) | 3023924 kB (5.97 s) | −243916 kB (−7.46%) |
| `+ --save_noDW` | 4714344 kB (9.14 s) | 4714432 kB (9.06 s) | 4714164 kB (9.09 s) | −180 kB (−0.00%) |

Single run per cell.

## §5.7 — merge behaviour

`git merge-tree --write-tree origin/main <head>`:

| head | conflicts | merged predicate | outcome |
| :-- | :-- | :-- | :-- |
| `13845fb` | `CMakeLists.txt` only | `do_local \|\| !do_dose_weighting \|\| save_noDW` | corrupting |
| `75fde5f` | `CMakeLists.txt` only | `… \|\| save_noDW \|\| even_odd_split` | correct |

`src/motioncorr_runner.cpp` auto-merges cleanly in both cases.

## Not executed

See §6 of the specification. In particular: 5×5 local, non-square and binning
controls on main; the CUDA resident and `cudaInverseFFT2D` paths; and any
benchmark series.


---

# Port evidence — `perf/issue-26-global-ifft-elision-port`

Same lane and mutex as above. Recorded at 2026-09-28T08:18–08:25Z.

## Host witness (payload lane)

```
shell cpuset       : 32-63
shell mems         : 0-1
nproc visible      : 32
node1 cpulist      : 32-63
SMT siblings(cpu32): 32        core_id=0     (no sibling visible in the guest)
NUMA nodes         : 2
numactl --show     : policy default, cpubind 1, nodebind 1, membind 0 1
load1/5/15         : 3.08 / 2.69 / 3.36  (build)   3.58 / 3.49 / 3.60  (test)
ctffind            : 2 processes, untouched
build parallelism  : make -j 16        runtime: --j 1 (CTest) / --j 8 (controls)
```

## Builds

| tree | predicate | binary sha256 |
| :-- | :-- | :-- |
| `src-main-4c952b3…` | unmodified main | `83e8749a55626b3268983bf9733b4276749539e025034a90ae98afa1f25b75b6` |
| `src-port` | `do_local \|\| pre_dw_sum_needed` (shared) | `8ea55b8d289a77349300277bd79cc3c3af4094e30221e5c26a26f188ef42c1e2` |
| `src-neg` | pre-port predicate, no `even_odd_split` | `765a669cd7a8165e6ed98e2e4a94e56046c50b57b656860b026b437cdc8e2886` |
| `src-neg2` | always elide | `478a32f43d5c9a56…` |
| `src-neg3` | `do_local` dropped | `aa19af3f0f194739…` |

## Test outcomes

```
src-port   GlobalIfftElision  PASS      full suite: 100% tests passed out of 14
src-neg    GlobalIfftElision  FAIL  AssertionError: _EVN.mrc: 36767 of 36864 pixel
                                    bytes differ between no dose weighting and
                                    with dose weighting            [oracle A]
src-neg2   GlobalIfftElision  FAIL  AssertionError: _EVN.mrc: 35831 of 36864 pixel
                                    bytes differ                    [oracle A]
src-neg3   GlobalIfftElision  FAIL  AssertionError: patch 3x3 reproduced the patch
                                    1x1 result exactly on a movie that contains
                                    motion                          [oracle C]
src-neg3   SyntheticRegression FAIL Image Max Pixel Difference: 1.031577e+01
```

## Oracle C fixture validation

Unmodified main, generated motionless fixture: patch1 `af03af17642c38aff2bb5008`
= patch3 `af03af17642c38aff2bb5008` — identical, so an assertion there would be
a false positive. Unmodified main, repository `synthetic_movie.tiff`: patch1
`8936f180e52933be476413c8` vs patch3 `04c2a1d9349b3c090c26c49c`, 630499 of
1048576 pixel bytes differ — valid.

## Bounded controls, port vs unmodified main

```
arm           files  dims            pixels     core header
syn_5x5       1      512x512x1       identical  identical
syn_bin2      1      256x256x1       identical  identical
syn_bin_eo    3      256x256x1       identical  identical
syn_latebin   1      256x256x1       identical  identical
tut_5x5       1      3710x3838x1     identical  identical
tut_flat      1      3710x3838x1     identical  identical
compared 8 output files across 6 arms — all bit-identical
```

`tut_bin2` (non-square × binning 2) is **not** a control: main rejects the input
with *"The dimensions of the image after binning must be even"* (3710/2 and
3838/2 are both odd). Both builds fail identically; the only textual differences
are the reported source line, which the port shifts by the lines it adds, and
backtrace addresses.


## Overlap check against PR #110

```
git merge-tree --write-tree origin/pr110 HEAD   ->  8fed7e92b30c57dafdc17eb8f6d5d68a1a7be394
exit 0, no conflicted paths
```

Merged `CMakeLists.txt` contains 16 `add_test` entries: all of #110's
(`DefectParser`, `WriteFaults`, `CiFailClosedControls`, `ImageWriteFaults`),
the pre-existing ones, and `GlobalIfftElision`. Merged
`src/motioncorr_runner.cpp` contains `pre_dw_sum_needed` (5 occurrences) and
`effective_expected_frames` (5 occurrences), with
`const bool need_real_space_before_dw = do_local || pre_dw_sum_needed;`
intact. Nothing from #110's tree was imported into this branch.
