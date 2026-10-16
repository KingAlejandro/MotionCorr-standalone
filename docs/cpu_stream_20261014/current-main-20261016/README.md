# PR #178 qualification against current main

Baseline: `d7171b810dc97003784339d7bad1c279903f3bba`.
Candidate source: `06bea8173ad2b05f8faa1fed28bf108ea51ceb10` (merge
`3f3d5054` plus the non-Linux witness-message fix). Subsequent evidence-only
commits do not change the tested source. The merge has parents `e8f3eb8e` and
`d7171b81`; no rebase, force push, or #182 fusion.

## Changes and review disposition

- P1: merged origin/main; kept `s16_staging` and `s8_staging`, removed `Irefframes`.
- P2: added actual odd-frame end-to-end products, including seven selected frames
  with `--save_noDW --even_odd_split --bin_factor 2`; retained exact-product and
  paired full-geometry RSS results below.
- P3: non-Linux `CpuUnweightedStream` now explicitly reports the allocation witness
  skipped; Linux still requires the one-frame bound and N-frame positive control.
- No disagreement with Sonnet's correctness findings. Codex reported no findings
  on the previous head; that is not a review of this merged source.
- The old duplicated `run_unprofiled.py` is retained as historical evidence, not
  reused or expanded; this qualification uses the existing shared
  `tools/profiling/lib/identity.py` comparator.
- Fresh output trees are compared **on cpu64 where produced**, before any copy.
  All files, including dotfiles/temporaries, participate in inventory comparison.
  This does not prove the origin of #182's historical baseline-side partial file.

## Local Release build and full CTest

macOS 26.7.1, Apple arm64 Mac16,7, clang 21, 14 physical cores, 24 GiB RAM.
`macos-environment.txt` and `macos-commands.txt` retain exact commands.

| Revision | Check | Exit | Result |
|---|---|---:|---|
| `06bea817` | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=$HOME/.venvs/global/bin/python3` | 0 | configured |
| `06bea817` | `cmake --build build --parallel 4` | 0 | built |
| `06bea817` | `ctest --test-dir build --output-on-failure` | 8 | 56 passed, 2 failed, 1 skipped / 59 |
| `d7171b81` | same Release CPU configure/build, `/tmp/fix178-main` | 0 / 0 | built |
| `d7171b81` | full CTest, with baseline git metadata | 8 | 55 passed, 2 failed, 1 skipped / 58 |
| `06bea817` | `ctest --test-dir build -R '^CpuUnweightedStream$' -V` | 0 | pixel/model/split checks pass; bound explicitly **not witnessed** |

Only `SyntheticRegression` and `MultiGpuScheduling` fail in both full suites;
`NativeMovieStaging` skips on macOS. The numerical baseline failure is identical
(max pixel difference 23.649856567382812; no tolerance changed). The device-free
scheduling validator rejects its healthy tree in both. The initial archived main
suite also failed `CiFailClosedControls` because its git-ref error text differs
without git metadata. That attempt is retained as `macos-main-archive-ctest.log`;
restoring baseline git metadata makes the focused test and the entire remaining
suite pass. Neither extra archive failure nor skipped tests count as passes.

## Linux exact products, allocation witness, and RSS

Raw provenance and commands: `environment.txt`, `build-linux.sh`, `*-build.log`,
`*.exit`, `verify.py`, `results.json`, `*.stdout`, and `*.time`.
Initial Linux builds/runs used the requested cooperative flock on CPUs 8–11.
The orchestrator then explicitly changed allocation: no flock, exclusive CPUs
32–37 (NUMA node 1), build parallelism <=6, OMP_NUM_THREADS <=6. The sole waiting
flock (PID 2007928) and its own driver (1957218) were terminated; no other process
was touched. Initial evidence is retained under `locked-superseded/`, not pooled
with the final matrix. The complete final matrix runs without flock under
`taskset -c 32-37`; both builds were rechecked with parallelism 6 and the Linux
witness rerun there. Source shipped by `git archive <sha> | ssh cpu64
 'tar -x -C DIR'`. Work is confined to `/home/ubuntu/fix178-20261016/`.

Both Linux arms configured Release CPU-only with `~/.mc-venv/bin/cmake`,
`-DCUDA=OFF -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3`, built with
`--parallel 8`, exit 0. Candidate `ctest --test-dir candidate/build -R
CpuUnweightedStream -V`, exit 0: **scratch bound PASS**, including the retained
N-frame control. Full Linux CTest is left to current-head GitHub CI.

Matched final runs use taskset CPUs 32–37 on cpu64 (64-vCPU KVM AMD EPYC 7763), j4 for
RSS, with `GLIBC_TUNABLES=glibc.malloc.hugetlb=1` on both arms; host THP is
`madvise`, defrag `madvise`. OpenMP dynamic off, bind close, places cores,
OpenBLAS one thread. This is a shared host with six allocated CPUs, not an
isolated physical host. No physical-host isolation or wall-time
claim. `/usr/bin/time -v` logs include wall time but it is not analysed.

Tutorial input is 3710×3838×24, TIFF SHA-256
`df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`,
gain `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`.
Copied read-only inputs from `/home/ubuntu/mc51/tutorial/Movies/` into our scratch.
All synthetic identities and binary SHA-256 values are in `results.json`.

The comparator requires identical full inventories, every MRC header/extended
header/payload (only the known first-label writer clock masked), and all other
bytes after own-output-root normalization. Logs carry timings and are excluded;
PDFs are inventoried, not byte-compared (existing comparator policy). STAR and
EPS are compared; MRC payload and root-normalized STAR SHA-256 values are also
retained per tree. This is same-backend product identity, not scientific
validation against an independent implementation.

An initial, superseded tutorial odd+bin2 attempt failed on **main**, exit 1: dimensions 3710/2
and 3838/2 are odd, violating the existing even-output-size gate. It is retained
in `locked-superseded/verify-initial.log`, its `results.json` and `.stdout`/`.time`; the gate was
not changed. Use bin2 on the divisible-by-four synthetic dimensions; tutorial
odd selection uses 23 frames without binning. Seven-frame synthetic bin2 checks
were already clean before this failure.

Final driver command, exit **0**:

```
taskset -c 32-37 ~/.mc-venv/bin/python3 verify.py \
  --base-revision d7171b810dc97003784339d7bad1c279903f3bba \
  --candidate-revision 06bea817
```

**23/23 strict output-tree comparisons pass**, all 46 binary invocations exit 0.
64 MRC payload/header pairs and 46 STAR pairs match (248 compared files overall).
The 128×128×8 synthetic fixture covers global/5×5 × j1/j4 × default-dose,
`--save_noDW`, `--save_noDW --even_odd_split`, and seven-frame split + bin2
(16 cases), plus one no-dose local case. Tutorial 5×5 j4 covers the same first
three product modes, a 23-frame split, and two further split RSS pairs. Actual
polynomial fits and seven selected frames are visible in retained per-movie logs;
all per-movie logs are archived separately. Bin2 uses early binning (the default).
A flipped first payload byte makes the comparator subprocess exit **1**, exactly
as required, reporting `payload differs at byte 1024`; original byte restored.

Three full-geometry dose+noDW+even/odd pairs, alternating AB/BA/AB, same input,
binaries, CPU mask, allocator and THP settings:

| Pair | main peak KiB | candidate peak KiB | saving KiB | saving |
|---|---:|---:|---:|---:|
| 0 | 4,380,196 | 3,070,404 | 1,309,792 | 29.90% |
| 1 | 4,402,772 | 3,066,796 | 1,335,976 | 30.34% |
| 2 | 4,401,928 | 3,046,372 | 1,355,556 | 30.79% |

Median paired saving: **1,335,976 KiB (1.274 GiB)**. The peak-RSS benefit survives
composition with #187 on current main. The separate noDW-only pair is
4,404,368 → 3,069,396 KiB; consult `results.json` for the source of every value.
No wall-time conclusion, confidence interval, or additive historical RSS claim.

## Limitations

No 4GPUs or native GPU execution. Actual CUDA-to-CPU fallback execution is not
covered here: CPU-only execution and borrowed-alias lifetime controls are not a
substitute. CUDA compilation is checked by current-head CI separately. Reviewers'
requested native CUDA fallback qualification remains unresolved. This change
reduces unweighted reconstruction memory; dose-only jobs already skip that work.
No numerical gates, failure/publication behavior, or license/dependency changed.
