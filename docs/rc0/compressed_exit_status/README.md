# #214: compressed MRC stream-status rejection

Source/test head: `39aca256c248e6209c6cbf8edc183b7400551b43`, based on main
`c8844894c7c6366abf297699b5312e4b775eb5b0`. Later commits in this PR record
release documentation/evidence only. Baseline is unmodified `c8844894`.
Issue: https://github.com/KingAlejandro/MotionCorr-standalone/issues/214.
Historical reproduction: [#204 record](../qual_mrc_staging/README.md), especially
its 24 damaged-stream records (six accepted decoder failures).

## Change and subset policy

`CompressedMRCReader::finish()` drains to EOF, checks `ferror` and `pclose`, and
clears the pipe pointer before reporting failure. The runner calls it after the
serial frame-error checks, before alignment or product publication, only when
all header-declared frames are selected. This applies to both CPU and CUDA's
shared host compressed reader. A nonzero status (including signal termination
or `pclose` failure) or pipe read error uses the existing movie-level exception
path: exit 1, no completion STAR for that movie, no joint STAR; subsequent
healthy movies continue. No numerical gates, dependencies or tolerances change.
The intended change to inherited behavior is rejection of these damaged full
reads; #214 explicitly requests that change.

Header-only reads and selections omitting any frame retain early close and
ignore decoder exit status, because SIGPIPE is legitimate. This includes a
subset beginning after frame 1 that reaches the last frame. Explicit first=1,
last=N is still a full read. Selected-frame short reads still fail. Subsets do
not certify whole-stream integrity: validate independently before processing.
The destructor remains nonthrowing and reaps early-closed decoders. Status validation is explicit because a throwing destructor could terminate during stack unwinding or run after publication.

## Measured local results (2026-10-19)

Venue: macOS arm64 `SCMAC-7L9P2F`, Darwin 25.6.0; Apple clang 21.0.0;
CMake Release; NumPy 2.5.4 in `/tmp/motioncorr-214-venv`; xz 5.8.4 and zstd 1.5.7.
`pbzip2` absent. Shared host under substantial build load; no timing inference.
Both configure/build chains exited **0**, using `-j 4`. Sources for the baseline
were copied with `git archive HEAD | tar -x`, before edits.

| Check | Result | Evidence |
|---|---|---|
| Unfixed xz discriminating test | exit 1, four failed assertions: missing last byte, index CRC, exit-3, explicit-all exit-3 incorrectly publish | `unfixed-xz.log` |
| Unfixed zstd discriminating test | exit 1, two failed assertions: exit-3 and explicit-all exit-3 incorrectly publish | `unfixed-zst.log` |
| Fixed xz | exit 0, 16 runs, zero failed assertions | `fixed-xz.log` |
| Fixed zstd | exit 0, 16 runs, zero failed assertions | `fixed-zst.log` |
| Healthy products vs unfixed binary | 8/8 trees identical (full and three subsets per codec) | `identity` objects in fixed logs |
| bz2 | exit 77, visibly SKIP; native and shim cases UNRUN | `bz2-skip.log` |
| Collection | PASS, 77 tests collected, all three new names required | `collection.log` |
| Fail-closed controls | 8/8 PASS (also exercised by full CTest) | `fail-closed.log` |
| Full local CTest | 74 passed, 2 skipped, 1 failed (`SyntheticRegression`, documented macOS difference); exit 8 | `ctest.log` |

The native damage cases are missing-last-byte, integrity-field corruption
(xz index CRC; other codecs' trailer/checksum), and midstream truncation. Each
first checks that the native decoder exits nonzero. Logs record delivered-byte
counts; not every codec delivers the complete movie on every kind of damage.
The xz tail/index cases delivered all 263168 bytes; zstd's tail/checksum cases
already reject on the baseline through short reads. These existing rejections
are retained controls, not newly discriminating results.

For **every installed codec**, a separate test-only decoder emits the complete
movie plus one MiB trailing data, then exits 0 or 3. The exit-0 control requires
a drain to avoid SIGPIPE; the exit-3 control demonstrates late-error rejection.
Damaged-stream batches check the failed movie has no MRC/completion STAR, the
healthy next movie completes, the process exits 1, and the joint STAR is absent.
CLI initialization also exercises header-only reader destruction on these runs.

The comparator is `tools/profiling/lib/identity.py`: entire MRC header (including
labels), extended header and every payload byte, masking only the recognized
first-label writer clock; all other products including STAR are byte-identical
after output-root replacement, except `.log`/`.pdf` (inventory only). No whitespace
normalization. Inputs have identical names across baseline/fix. Input/product
hashes are in `products_inputs.json`; normalized MRC and STAR hashes are retained
alongside raw hashes. Scratch with full outputs is `/tmp/motioncorr-214-{negative,fixed}-{xz,zst}`.

Binaries (SHA-256):

- baseline `/tmp/motioncorr-214-base-build/motioncorr`: `284215193aeda5991185f7760b046b4c384dcf0de320a8a40432eb90d52ff2a8`
- fixed `/tmp/motioncorr-214-build/motioncorr`: `3ff8802579d906df21d002e58d6cd0b003f6cf571cf4fec2aa57e70a8a785957`

## Commands

```sh
cmake -S /tmp/motioncorr-214-base-src -B /tmp/motioncorr-214-base-build \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build /tmp/motioncorr-214-base-build -j 4
cmake -S . -B /tmp/motioncorr-214-build -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/tmp/motioncorr-214-venv/bin/python
cmake --build /tmp/motioncorr-214-build -j 4
# Repeat for xz and zst. Unfixed command must exit nonzero.
python tests/test_compressed_mrc_status.py --codec xz \
  --binary /tmp/motioncorr-214-base-build/motioncorr --work /tmp/motioncorr-214-negative-xz
python tests/test_compressed_mrc_status.py --codec xz \
  --binary /tmp/motioncorr-214-build/motioncorr \
  --baseline-binary /tmp/motioncorr-214-base-build/motioncorr --work /tmp/motioncorr-214-fixed-xz
ctest --test-dir /tmp/motioncorr-214-build --output-on-failure -j 2
python tools/validate_test_collection.py --test-dir /tmp/motioncorr-214-build
```

## Real compressed movie: cpu64 overhead measurement

Source/test head and baseline as above; both Linux CPU Release builds exited 0
(`cpu64/logs/`), GCC 13.3.0, CMake 4.4.3, xz 5.4.5. Venue `small-refmac-machine`, AMD EPYC 7763, taskset CPUs 8-15,
`--j 8`, `OMP_NUM_THREADS=8`, `OPENBLAS_NUM_THREADS=1`, THP madvise. The
`motioncorr-cpu64-bench.lock` was held for the timing campaign and released at
completion. Two unrelated single-thread ctffind processes remained running;
this is a shared-host measurement, not an exclusive-host claim.

Real EMPIAR-10028 `031_movie.mrcs` (4096 x 4096 x 16 float32), original SHA-256
`8ce479649ec00abf46b290aee2b43343d0ba0dc67f239f0e3fd0c6875b3c7213`, was
compressed with `xz -1 -c`, checked with `xz -t`, and read as `movie.mrc.xz`.
Compressed SHA-256: `d7d05f093f8bbce99b4e36194efb7ab5a51d2b017eb2f0f98b5be5502091fe26`.
Commands and binary hashes are in `cpu64/bench/summary.json`; binary hashes
before/after the campaign match. `bench.py` is the retained driver.

The campaign command was:

```sh
OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 \
flock -n /tmp/motioncorr-cpu64-bench.lock taskset -c 8-15 \
  /home/ubuntu/.mc-venv/bin/python /tmp/motioncorr-214/bench.py \
  --source /tmp/motioncorr-214/src \
  --baseline /tmp/motioncorr-214/build-baseline/motioncorr \
  --fixed /tmp/motioncorr-214/build-src/motioncorr \
  --input /tmp/motioncorr-214/real.mrc.xz --work /tmp/motioncorr-214/bench --reps 7
```

One warm-up pair excluded from statistics, then **seven interleaved pairs**,
order alternating baseline/fix and fix/baseline. All 16 processes exited 0; all
8 pairs' output trees were identical under the strict comparator described
above. Every run is retained; no outlier was discarded.

| End-to-end process wall | Median (s) | IQR (s) | Min-max (s) |
|---|---:|---:|---:|
| Baseline | 53.829 | 0.110 | 53.534-54.118 |
| Fixed | 53.734 | 0.271 | 53.488-55.657 |
| Paired fixed minus baseline | -0.110 | 0.480 | -0.317 to +1.848 |

This estimates net whole-process cost on this real compressed movie, including
decoding, alignment and writing. It does **not** isolate `finish()` latency;
the variation is larger than the median difference. No speedup or stable
"no regression" conclusion is asserted. Native GPU timing, other real compressed
movies/codecs, soak and Tier D science were not measured.

## Shared-source re-entry

All Linux builds passed (Release, GCC 13.3.0, CUDA 12.8, nvCOMP 5.3). Sources and
binaries are pinned in `gpu/logs/driver-build.log`; the hashes after native
execution match the build hashes (`gpu/logs/binaries-native-after.sha256`).

| Configuration | Full CTest result |
|---|---|
| CPU | 77/77 PASS, no skips |
| CUDA | 110/111 passed; `ProfilingKit` hit the two #246 CLI timeouts; one unchanged-test retry reproduced only those errors |
| CUDA+nvCOMP | 114/114 PASS, no skips |

The CUDA failure and targeted retry contain exactly the two import-subset
`TimeoutExpired` errors attributed to independent issue [#246](https://github.com/KingAlejandro/MotionCorr-standalone/issues/246). Those CLI tests wait up to
300 seconds for any host compiler, inside a 30-second test timeout. The
`cc1plus` occupancy observation is retained in `gpu/compiler-observation-13h39.txt`.
No timeout or gate was changed. The parent directed that these two errors alone
be recorded under #246 without further retries; every other test must pass.

Native compressed checks used GPU0 A100 80 GB PCIe
`GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, CPUs 88-95, selected by UUID and
protected by `/tmp/motioncorr-gpu0-correctness.lock` (mapping confirmed in QF
README lines 33, 47-48). `extra_native.sh` retains the commands and assertions.

- **48 native fixed/baseline runs PASS** across native pbzip2 1.1.13, xz and zstd;
  **12/12 healthy output trees identical** to the frozen QF nvCOMP binary.
  Its SHA-256 was checked against QF's committed `raw/binaries.sha256` before
  use: `2e00e0e8fb75aafaf23f15a3c2a142c7d35b6e30477d594244ecba495a5bb6b3`.
  `git diff 6d68e2d6 c8844894 -- src CMakeLists.txt tests` is empty, so F and
  the unfixed baseline have identical program/test source.
- Unfixed native controls fail as required for **all three codecs**: full-stream
  exit-3 and explicit-all-frame exit-3 publish incorrectly. xz additionally
  publishes missing-last-byte and index-CRC damage. Native bz2/zstd tail damage
  already fails on the baseline; delivered-byte counts are retained rather than
  calling those newly discriminating cases.
- Successful fixed compressed runs each have the actual per-movie
  `Computing full-frame Fourier transforms (CUDA in-VRAM)` witness; the driver
  checks it. An ingest flag alone is not the native execution evidence.
- **#204 compressed replay: 49/49 PASS**, including 25 compressed/route/refusal
  records and all 24 damage records (the six historical accepted failures now
  reject). The retained patch only relocates the harness source root and changes
  native-bz2's expected result to success because pbzip2 is now installed in task
  scratch. No tolerance changes. This historical harness collapses horizontal
  whitespace in text comparisons; the 12 direct baseline comparisons above do
  not. MRC comparison is strict in both, apart from the writer clock.

External decompression runs on the host, followed by native CUDA in-VRAM transforms/alignment.

Native inputs/products remain in `/mnt/clathrin/alex-motioncorr-214`; hashes are
retained in `gpu/native_sha256.json`. The real-movie timing products remain in
`/tmp/motioncorr-214/bench`; hashes are in `cpu64/bench/products_sha256.json`.
Mac inputs/products have their separate `products_inputs.json` manifest.

`native_driver.sh` records initial preparation, builds and CPU CTest. The first
GPU3 CUDA attempt was interrupted when the parent reassigned the lane; its
partial host-test log is retained as `ctest-cuda-gpu3-aborted.log`, not counted as
a completed suite. Owned remnants of that attempt were stopped; unrelated jobs
were untouched. `gpu0_suites.sh` records the full CUDA attempt, and
`finish_suites.sh` records its targeted retry (which reproduced #246); `nvcomp_suite.sh` records the complete passing nvCOMP suite. Direct SSH and
initial bulk transfers failed; sources were fetched at exact commit `39aca256`
through `ssh -J ccp4-gateway` and exported with `git archive` on the host.

Not rerun: the full frozen-QF campaign beyond these affected format rows,
real-corpus EER campaigns, multi-GPU dataset endpoints, soak, other real-movie
performance rows and Tier D science. QF on frozen F `6d68e2d6` remains historical
evidence of F; no QF row is relabelled as a pass on this candidate. Supported
configurations and numerical gates are unchanged. Independent review and
current-head CI are required before merge.
