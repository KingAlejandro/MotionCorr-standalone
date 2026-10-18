# RC0 D10: host EER memory safety (#221)

- **Base:** `71ab841e69869b615555bb02f8f393db59c22d73`.
- **Tested source:** `97fb9fda5902f4bd5c2aab7c40ae4064637b5125`. `src/`, `tools/` and
  `CMakeLists.txt` are unchanged since. Later commits touch only `docs/rc0/eer_memory_safety/`,
  except W-D10d, which adds two cases to `tests/test_eer_memory_safety.py` (see
  [Added test cases](#added-test-cases-w-d10d-review-findings-p2-1-and-p3-1)).
- **Status:** native evidence and D14 timing are recorded below. Independent review
  (#198) is in progress. There is no merge recommendation yet, and merging needs
  maintainer approval (D3).

## Design and preserved behavior

The host's paired 7-bit unpackers keep their bit operations and electron order.
Each loop starts only inside the fraction, counts consumed bits (including the
final run length), and rejects consumption past that fraction. `memcpy` replaces
unaligned 32-bit dereferences without changing the word's bits. Eight zero bytes
at the allocation end make speculative reads safe; bytes read ahead from the next
fraction cannot make an overrun acceptable. The 8-bit unpacker checks availability
of each consumed run/symbol. A pair-capacity check bounds electron-vector writes.
No partial fraction is rendered: an overrun/overshoot takes the inherited D6 warning
and skip path. Valid streams retain the same positions, symbols and accumulation.

Container errors are different: invalid strip sizes/ranges, failed directory
selection/read and missing mandatory tags fail the movie. Lazy reading records an
`exception_ptr` inside the critical section and rethrows outside it, where the
runner's existing per-frame capture and serial per-movie handler apply. TIFF/FILE
handles close with scope guards. Read-only input fixtures are never modified.

Legacy footer indexing validates remaining bytes and word counts before subtracting
or multiplying. Geometry-less legacy files are refused explicitly. Whole-IFD
truncation remains the inherited E-1 shorter-movie behavior without expected counts.
MRC byte-order magnitude tests use ordered comparisons, integer formatting uses an
unsigned magnitude for INT_MIN, and temporary MRC headers are freed on parse errors.

`EerMemorySafety` generates small TIFF/EER and MRC fixtures at test time. Its scalar
encoder and expected sparse image check valid pixels exactly, including grouping,
upsampling and terminal electrons. Corrupt fractions must equal an omitted fraction;
container/header failures must exit 1, complete movie 2, publish no failed-movie
products and withhold the joint completion STAR. The test is required by the existing
fail-closed collection validator.

## Provenance

Started from the Opus partial patch (SHA256
`f544d17693f24e610a9b3797107c65c22241a290cfac0e571717a112cee44be7`), reused
initialization, handle guards, legacy/footer checks, header/formatting fixes,
paired-loop bounds and helper modes. Corrected the 8+4 partial-symbol acceptance,
added physical strip-range validation and catch-all exception transport, and wrote
the generated regression and qualification evidence here. The original worktree
was read only and remains untouched.

## Native evidence (4GPUs)

Records are in [`raw/native/`](raw/native/), with summaries in
[`positive_controls_summary.json`](positive_controls_summary.json),
[`identity_summary.json`](identity_summary.json) and
[`binaries.sha256`](binaries.sha256).

**Toolchain:** GCC 13.3.0, CMake 3.28.3, CUDA 12.8 (sm80), nvCOMP 5.3.0.16, LibTIFF 4.5.1.

**Binaries and source.** The fix binaries were built from the W-D10 source tree:
- CPU at 00:26:35Z; CUDA, nvCOMP and ASan by 00:27Z.
- That was after `cac82f8c`, committed at 00:26:29Z, so the builds include it.
- `97fb9fda` changes only `tests/test_eer_memory_safety.py` and `native_controls.py`.
- At `97fb9fda` the source tree is clean, and `make -n motioncorr` in every
  `build-fix-*` tree reports nothing to compile or link.
- The binaries therefore correspond to the tested source. That holds for the CTest runs, the identity runs, the ASan valid-grouping run and the upsampling −1 control arms. It does not hold for the four control arms described in the table.

| Check | Result |
|---|---|
| CTest, fix | CPU 71/71, CUDA 104/104, CUDA+nvCOMP 107/107 (`ctest-fix-*.log`) |
| CTest, composed with main | Merge `8d6b14a9` = `adb32785` (tree of main `1afa03b5`) + `97fb9fda`. CPU 73/73, including `InputFormats`, `CutDownMovie` and `EerMemorySafety` (`ctest-composed-cpu.log`) |
| Damaged-input controls, fix | 37 V-EER fixture cases. All cases controlled, 0 sanitizer reports (`controls-fix-*.log`). Only the upsampling −1 arms (CPU and ASan+UBSan, 00:29–00:31Z) ran on the final binaries. The four upsampling 1 and 2 arms ran from 23:28Z to 00:23Z on earlier fix builds, before `cac82f8c`, so they do not test the final source. See the note below the table |
| Damaged-input controls, main (negative control) | Under ASan: sanitizer reports in 35 of 37 cases. CPU build: 27 of 37 cases controlled (`controls-main-*.log`) |
| Valid groupings under ASan | 28/28 pass (`asan-valid-groupings.log`) |
| Identity, main `71ab841e` vs fix | 24/24 byte-identical, on CPU and CUDA. Covers EMPIAR-12963 (with EER gain), 10474 Falcon 3 and 10474 Falcon 4, each at G and L and upsampling 1 and 2 (`identity-*.log`) |

**Note on the control arms.** Independent reviewer R-D10a found that four of the six control arms
predate the final build; the coordinator had missed this. During its first review, R-D10a rebuilt the exact head
`97fb9fda` and reran all 37 V-EER fixtures in all six arms (CPU and ASan+UBSan, upsampling −1, 1 and 2).

**Result:** 37/37 controlled, 37/37 publication-correct and 0 sanitizer reports in every arm
([review](https://github.com/KingAlejandro/MotionCorr-standalone/pull/231#issuecomment-6248101932)).

R-D10a's records are on 4GPUs under `/mnt/clathrin/alex-motioncorr-rc0/R-D10a/`:
- `controls.done`
- `controls-head-{cpu,asan}-up{-1,1,2}.log`

Copies are in [`raw/review-r-d10a/`](raw/review-r-d10a/).

The later test-only commit `9d8533a4` does not change `src/`.

## Added test cases (W-D10d, review findings P2-1 and P3-1)

The W-D10d commit adds two cases inside `EerMemorySafety`. No CTest name changes, and
`git diff 97fb9fda HEAD -- src tools CMakeLists.txt` is empty.

- **Borrowed neighbour (P2-1).** The case covers codecs 65000, 65001 and 65002, with k = 1…6.
  - **Fixture:** fraction 2 is a 2000-electron stream cut k bytes short. Fraction 3 is a valid
    stream whose first k bytes are exactly the removed tail, so a decoder that reads past the
    fraction end decodes fraction 2 completely.
  - **Fixture guard:** the decoder never reads the terminal symbol, so a cut could remove only
    unread bits. The fixture therefore asserts that the uncut stream's last byte holds a consumed
    run-length bit. Seed 65001 needed one electron dropped to meet this; without the guard, its
    k = 1 case is a valid stream that head correctly accepts.
  - **Required:** exactly one D6 skip, for frame 2. The `render_eer_groups` output must equal
    the image with frame 2 omitted and frame 3 rendered.
- **MRC dimension product (P3-1).**
  - **Fixture:** little- and big-endian `.mrcs` headers with nx = 65535, ny = nz = 2^31−1 and
    mode 2. nx = 65535 is the largest value that avoids a byte swap. x·y fits in `long`;
    x·y·n does not.
  - **Required:** the same per-movie failure as the INT_MIN cases (exit 1, healthy movie
    published, no failed-movie products, no joint STAR), plus
    `readMRC: invalid dimensions in header of image <name>`.

**Discrimination (4GPUs, CPU Release builds).**
[`w_d10d_discrimination.py`](w_d10d_discrimination.py) runs each new case separately. The
base build is `71ab841e` with the head's `tests/test_runner_numerics.cpp`. M2 removes
`if (pos + 2 >= pos_limit)` at `src/renderEER.cpp:642`, in a scratch copy only.

| Build | Borrow cases pass | MRC cases pass | `EerMemorySafety` |
|---|---|---|---|
| head | 18/18 | 2/2 | pass |
| base `71ab841e` | 4/18 (65000 k = 3–6). The other 14 are accepted without a skip | 0/2 | fails at the first new case, `(65000, 1)`, after passing every earlier 65000 case |
| M2 | 16/18 (65000 k = 1, 2 accepted) | 2/2 | fails at `(65000, 1)` |

**Base on the MRC cases:**
- Runs were capped at 16 GiB with `ulimit -v`. Base was not run uncapped, because it sizes
  buffers from the header.
- Under the cap, the header read throws `std::bad_alloc`. That ends the whole job with exit 1
  before the healthy movie is corrected.
- There is no per-movie failure report and no healthy products.

These counts differ from R-D10a's 13/18 because the fixture streams differ.

**CTest on `8932a83a`.** This is the pre-rebase SHA; its `src/`, `tests/`, `tools/` and
`CMakeLists.txt` are identical to the pushed W-D10d commit.
- **Sources:** git checkouts, not archives, so `CiFailClosedControls` can resolve git refs.
- **Results:**
  - CPU 71/71.
  - CUDA 104/104 and CUDA+nvCOMP 107/107, on GPU2 with `CUDA_VISIBLE_DEVICES=GPU-063e5232-…`
    and the GPU2 correctness lock held.
  - `EerMemorySafety` under ASan+UBSan: pass.
- **Composed check:** merge `e70c846b` of main `1afa03b5` and this head gives CPU 73/73.
- **Records:** binary SHA-256s, logs and the build and run scripts are in
  [`raw/native-w-d10d/`](raw/native-w-d10d/). `gpu-identity.txt` lists all four GPUs because
  `nvidia-smi` ignores `CUDA_VISIBLE_DEVICES`.

## Performance (D14)

**D14 rule, per workload:** the upper bound of the distribution-free CI of the median
paired difference (fix − main) must be ≤ +0.5 % of the median main wall time.

**Design (fixed before any run, then run once):**
- A pilot, excluded from the result.
- N = 32 balanced pairs (16 AB / 16 BA) plus at least 12 A/A' null pairs.
- Identical builds and conditions.

**Venues:**
- **CPU:** exclusive SCARF nodes. Both arms were built inside the allocation, from
  tarballs whose `src/`, `tests/`, `tools/` and `CMakeLists.txt` match `97fb9fda` and
  `71ab841e` file for file.
- **CUDA:** 4GPUs GPU2, pinned by UUID, with payload CPUs 112–119. The run held
  `/tmp/motioncorr-bench.lock`.

The CIs below are the tools' order-statistic intervals, with coverage of at least 95 %:
98.0 % for N = 32, 96.1 % for N = 12.

| Workload | Median main | Median fix − main | CI of median | Upper bound | Null median, CI | D14 |
|---|---|---|---|---|---|---|
| CPU whole job, 12963 L (`--j 16`) | 9.509 s | −0.025 s (−0.26 %) | −0.040 … −0.007 s | −0.07 % | −0.010 s, −0.043 … +0.022 s | D14 PASS (nulls sequential, not interleaved; deviation accepted by the maintainer 2026-10-18, #198) |
| CPU whole job, 10474 F3 L (`--j 16`) | 15.151 s | +0.002 s (+0.01 %) | −0.018 … +0.029 s | +0.19 % | +0.005 s, −0.018 … +0.061 s | D14 PASS (nulls sequential, not interleaved; deviation accepted by the maintainer 2026-10-18, #198) |
| Host decode, 12963 | 4.402 s | +0.0002 s (+0.00 %) | −0.0019 … +0.0029 s | +0.07 % | +0.0018 s, −0.0024 … +0.0058 s | pass |
| Host decode, 10474 F3 | 7.360 s | +0.0017 s (+0.02 %) | −0.0014 … +0.0070 s | +0.09 % | −0.0002 s, −0.0030 … +0.0045 s | pass |
| Host decode, 10474 F4 | — | — | — | — | — | **not yet measured.** Attempt 1 (job 3634352) hit the 1:30 limit at 24/32 pairs before any F4 statistic was written. Attempt 2 (job 3634495) uses the same declared design, F4 only, with a 4:00 limit |
| CUDA compact whole job, 12963 L (nvCOMP build, `--j 8`) | 4.833 s | −0.024 s (−0.49 %) | −0.059 … +0.014 s | +0.30 % | −0.004 s, −0.099 … +0.037 s (16 pairs) | pass |
| CPU whole job, 10474 F4 L (`--j 16`) | — | — | — | — | — | **declared, not run:** cancelled before any timed run following the maintainer decision (W-D10e; no SCARF job was submitted) |

**Integrity of the runs:**
- No pair was discarded in any workload.
- The CUDA run made 110 runs: 0 non-zero exits, 0 foreign GPU processes, 0 retries.
- Products from the first definitive AB pair are identical in every whole-job workload.

**Records:**
- CPU: [`raw/timing-scarf-cpu/`](raw/timing-scarf-cpu/).
  - Jobs 3634353 (12963) and 3634354 (F3) are the whole-job runs.
  - Job 3634352 is the decode run.
  - Jobs 3634321 and 3634331 are the earlier 8-pair pilots.
  - The per-run directories stay on SCARF in `/work4/scd/scarf1415/W-D10/`.
- CUDA: [`raw/timing-cuda-e12963L/`](raw/timing-cuda-e12963L/). Read `INCIDENT.txt`
  there: the coordinator killed an earlier, queued instance of the window by mistake.
  That instance had no timed runs, and the run reported here is the only result.
- W-D10e: [`raw/timing-scarf-cpu-interleaved/`](raw/timing-scarf-cpu-interleaved/) holds a
  declared design with interleaved nulls for the three CPU whole-job workloads, including the new
  10474 F4 L, and its driver. It was not run: after the maintainer accepted jobs 3634353 and
  3634354 as they stand, it was withdrawn before any job was submitted (`NOT-RUN.txt`).
- SCARF GPU job 3634351, a backup for the same CUDA workload, was cancelled before it
  started, so the result is not duplicated.
