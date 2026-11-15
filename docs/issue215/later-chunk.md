# Later-chunk identity control follow-up

Base: live PR #248 head `06386874f5fc4f1069fee53ea269ff4d95219064`.
The fresh worktree fast-forwarded from `c8844894` to that exact head; no drift
was observed. Issue #215, its comment, the PR body, merged discussion timeline,
review submissions and inline threads were read live before edits. The latest
review requests this control after accepting the guard's source/retained evidence.

## Test design and acceptance

The existing nine-row `CudaNvcompTiffIdentity` and historical evidence remain
intact. The new `CudaNvcompTiffIdentityLaterChunk` uses the same valid 48x40x6
uint16 Deflate fixture with two-frame chunks, one reader and no gain. It adds
two compact references, healthy fixed/mutant runs, and append/atomic-rename
rows on each binary (eight rows total).

Only test executables compile `cuda_tiff_identity_probe.cu`, which includes the
unchanged session source and exports the exact conversion kernel's host stub
address. The shim wraps `cudaLaunchKernel`; it recognizes this address rather
than guessing from block dimensions. After the real first conversion launch,
it checks successful stream synchronization and reads **all** 3,840 first-chunk
`d_Iframes` pixels and 1,920 `d_Isum` pixels. Both must exactly equal the
independent Python fixture oracle (vertical flip, no gain, two-frame sum).
Launch, synchronization or copy failure cannot emit the consumption witness.
No synthetic callback or launch-count marker is accepted as consumption.
The extra synchronization/readbacks change scheduling only in these test binaries;
this is a correctness control with no performance claim.

The pipeline reads chunks 0 and 1 before converting chunk 0. After the readback
witness, the fifth frame-span read (zero-based index 4, frame 4 in chunk 2)
triggers mutation before that read, through either `pread` or `__pread_chk`.
The shim requires exactly four previous span reads. Conversion, later-read and
mutation witnesses must each occur once in that order. Append preserves the
valid TIFF; rename replaces the pathname with a separately encoded valid TIFF
whose pixels differ by one. Open reader handles retain the original inode.

Fixed rows require the named production identity decline, compact routing,
successful completion, exact MRC payloads and complete MRC/STAR identity against
the appropriate compact reference. The existing strict product comparator
checks inventory, MRC geometry/header/extended-header/pixels and STAR content;
only its established output-root and MRC writer-timestamp normalization applies.
Logs and PDFs are outside this product identity comparison.

CMake generates a test-only first-chunk-only session copy by wrapping exactly
the per-chunk path/descriptor checks with `if (k == 0)`. Missing/nonunique match
is fatal at configure. Tag-scan capture, fresh-reader checks and every other
operation remain in the mutant. Each mutant mutation row must fail the **same
fixed acceptance predicate**, recorded as `fixed_acceptance: false`, while also
witnessing the completed first conversion and actual later mutation, completing
successfully on `nvcomp`, emitting no identity decline, and matching all original
host-reference MRC/STAR products. A generic fallback, failed decode, missing
witness, crash or missing products cannot satisfy this negative control.

Normal `motioncorr_core`/`motioncorr` receive no hook, symbol, environment policy
or production source change. The immutable/trusted Deflate-input policy and all
numerical gates remain unchanged. These valid-body controls provide no arbitrary
corrupt-Deflate safety guarantee.

## Local checks, 2026-10-22

Venue: this Mac worktree, arm64, AppleClang 21.0.0, C++17, LibTIFF 4.7.2,
Python 3.13.7 with NumPy. Occupancy was checked using `uptime` and
`ps -Ao pid,pcpu,comm -r | head -12`; other browser/Bandicoot/security processes
were active and untouched. About 35 GiB was free. These are not benchmark runs.
Build/test concurrency was capped at two; Python/BLAS worker counts were capped.

Commands from the worktree root:

```sh
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 \
  cmake -S . -B build-issue215-local -DCMAKE_BUILD_TYPE=Release \
  -DCUDA=OFF -DBUILD_TESTING=ON \
  -DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 \
  cmake --build build-issue215-local --target tiff_identity_host_control --parallel 2
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 \
  ctest --test-dir build-issue215-local \
  -R 'TiffIdentityLaterChunkHostControls|NvcompAcceptanceDiagnostics|NvcompGuards|OutputTreeComparator' \
  --output-on-failure -j2
git diff --check
/usr/bin/c++ -std=c++17 -I/opt/homebrew/include -fsyntax-only \
  tests/cuda_tiff_identity_shim.cpp
```

Configure/build: **PASS**. Focused CTest: **4/4 PASS**. Diff whitespace and
original shim configuration C++17 syntax: **PASS**. The CTest log remains at
`build-issue215-local/Testing/Temporary/LastTest.log` in this worktree.
The new host test runs 18 cases against an explicitly fake CUDA API: append and
rename through each read wrapper; launch/sync/copy errors; either destination
mismatch; absent consumption; wrong kernel. It also rejects missing/duplicate/
misordered witnesses and unchanged identity. This is host interposition and
control validation, **not native decoding or accumulation evidence**.
The full CPU suite and historical nine-row/native/tutorial checks were not rerun.
The configure warning for absent `pbzip2` concerns existing compressed-MRC tests,
which were outside this focused run.

## Native command plan — UNRUN

CUDA compilation, actual GPU conversion/readback, later-chunk fixed fallback,
and first-chunk-only mutant discrimination are **UNRUN** here. No remote/GPU
job was started. Parent owns live resource preflight and publication.

In an isolated Linux source/scratch directory at the resulting commit, after
parent checks occupancy/capacity and the current allocation/lock rules:

```sh
cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
  -DUSE_NVCOMP=ON -DNVCOMP_ROOT="$NVCOMP_ROOT" -DBUILD_TESTING=ON \
  -DPython3_EXECUTABLE="$PYTHON_WITH_NUMPY"
cmake --build "$BUILD" --parallel 2 --target \
  motioncorr_tiff_identity_later motioncorr_tiff_identity_first_chunk
# Hold the current per-GPU correctness lock; use one preflight-approved UUID.
CUDA_VISIBLE_DEVICES="$GPU_UUID" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  taskset -c "$TWO_CPUS" "$PYTHON_WITH_NUMPY" \
  "$SRC/tests/run_tiff_identity_later_chunk_controls.py" \
  --binary "$BUILD/motioncorr_tiff_identity_later" \
  --mutant-binary "$BUILD/motioncorr_tiff_identity_first_chunk" \
  --workdir "$NEW_EMPTY_EVIDENCE_DIR" --cpus "$TWO_CPUS"
```

Bound: one GPU, two allocated CPUs maximum, sequential subprocesses, one reader,
one OpenMP thread, 180 seconds per subprocess (eight rows; registered CTest
timeout 1,500 seconds). Each movie is only 48x40x6; the existing production
pinned-pool cap remains in force. Record actual CPU list, GPU UUID, software
versions, source/binary hashes, commands/exits, occupancy and lock ownership.
Retain `result.json`, `manifest.json`, fixture/oracle files, process/movie logs,
route witnesses and product-identity reports. Expect fixed mutation acceptance
`true` and mutant mutation acceptance `false`; all eight row verdicts must pass
before claiming native discrimination. Preserve old evidence separately.
