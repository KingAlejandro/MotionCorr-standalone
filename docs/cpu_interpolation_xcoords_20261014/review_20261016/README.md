# PR #181 review fixes and correctness verification

Base: `d7171b810dc97003784339d7bad1c279903f3bba` (main).
Original PR: `a532b8a4371e0e6c732fb8149284a4887298c00d`.
Merge: `4fe5b00d9991c459f32862a74f0eb463b9a2368d` (no rebase/force push).
Tested code: `78df217a0792571e1f3f3e3ecb9583db6b028848`.
Later commits in this review only add evidence/docs; src/tests/CMake and both drivers
are unchanged from that tested commit.

## Fixes

- Both production polynomial paths use one private coordinate-cache builder.
  The test friend observes that actual builder, not a duplicate test expression.
  57,922 RFLOAT coordinates at widths 1, 3, 65, 3710, 3711, 3838, 3839, 4096,
  4097, 5760, 5761, 11520, 11521 must match `(RFLOAT)ix / nx - 0.5` bitwise.
  Existing 480 configurations / both float-output paths remain unchanged.
  This routine extraction makes the production arithmetic directly testable; cache
  lifetime/ownership and interpolation arithmetic are unchanged.
- `run_products.py` requires `--base-source-sha` and `--candidate-source-sha`;
  `run_kernel.py` requires `--source-sha`. Both reject missing/non-full SHAs before
  venue checks/output/launch. Receipts distinguish `driver_source` from each
  binary's hash and caller-attested build source. They do not assert that a given
  SHA proves a clean build. `test_driver_sources.py` mocks all measurement launches
  and verifies distinct driver/base/candidate revisions survive into receipts.
- Accepted all substantive findings. Used a merge rather than the review's suggested
  rebase, as requested. No performance finding is disputed or claimed resolved.

## Commands and exit statuses

All candidate execution below is code `78df217a`; main controls are `d7171b81`.
Logs are retained in `macos/` and `linux/`; build output includes flags/compiler.

### macOS ARM64, AppleClang 17, CMake 4.4.4

From the PR checkout:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
  -DPython3_EXECUTABLE=$HOME/.venvs/global/bin/python3   # rc 0
cmake --build build -j4                              # rc 0
ctest --test-dir build --output-on-failure             # rc 8
```

56 pass, 2 fail, 1 skip / 59: only SyntheticRegression and MultiGpuScheduling fail;
NativeMovieStaging skips its Linux-only path. No other failures ignored.

Plain-main control used `git archive d7171b81 | tar -x -C
/tmp/fix181-local-20261016/main`, configured identically, built `--target motioncorr`
(rc 0 each), then:

```sh
ctest --test-dir /tmp/fix181-local-20261016/main/build \
  -R '^(SyntheticRegression|MultiGpuScheduling)$' --output-on-failure # rc 8
```

Both fail identically: SyntheticRegression max pixel difference 23.649856567382812;
MultiGpuScheduling's tomography validator rejects the healthy published tree.
See `main-known-failures.log` and candidate `ctest.log`.

Mutant patch `macos/reciprocal-mutant.patch` changes the sole production cache
expression to `(RFLOAT)ix * (1.0 / nx) - 0.5`. Build of target
`cpu_interpolation_xcoords` rc 0; `ctest --test-dir build -R
'^CpuInterpolationXcoords$' --output-on-failure` rc 8, failing coordinate bits at
nx=65, ix=33. Restored source, rebuilt rc 0, direct `build/cpu_interpolation_xcoords`
rc 0: 57,922 coordinate checks and 480 output configurations pass.

```sh
$HOME/.venvs/global/bin/python3 \
  docs/cpu_interpolation_xcoords_20261014/review_20261016/test_driver_sources.py # rc 0, 2 tests
```

Initial mock-test setup failures (missing venue args, platform probe intercepted)
are retained in `driver-sources*.log`; fixed only the mock test, not production gates.

### cpu64 Linux x86_64, GCC 13.3.0, Release

All files/work are under `/home/ubuntu/fix181-20261016/`. Trees shipped via:

```sh
git archive 78df217a | ssh cpu64 'tar -x -C /home/ubuntu/fix181-20261016/candidate' # rc 0
git archive d7171b81 | ssh cpu64 'tar -x -C /home/ubuntu/fix181-20261016/base'      # rc 0
```

Initial build/test/product steps followed the then-current rule:
`flock -w 3600 /tmp/motioncorr-cpu64-bench.lock -c 'COMMAND'`, -j4, no affinity
constraint. After the orchestrator allocated CPUs 44–49, all remaining work ran
without flock, under `taskset -c 44-49 bash -c 'export OMP_NUM_THREADS=6; COMMAND'`,
build -j6 or less. Final full CTest and product checks were repeated in that lane.
No waiting flock jobs remained. Neither timing nor performance comparisons were run.
Host is an AMD EPYC 7763 VM, shared; environment/occupancy retained. No GPU used.

For each source (base builds motioncorr only; candidate builds all targets):

```sh
~/.mc-venv/bin/cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
  -DPython3_EXECUTABLE=$HOME/.mc-venv/bin/python3 # rc 0 each
~/.mc-venv/bin/cmake --build build -j4           # candidate rc 0
~/.mc-venv/bin/cmake --build build -j4 --target motioncorr # base rc 0
```

Initial candidate `~/.mc-venv/bin/ctest --test-dir build --output-on-failure` rc 8:
CiFailClosedControls requires `cmake` on PATH and Git metadata for its invalid-ref
assertion. Preserved the failure, exported `PATH=$HOME/.mc-venv/bin:$PATH`, and
imported an exact local Git bundle (`git init; git fetch ../source.bundle HEAD;
git reset --mixed FETCH_HEAD`) without changing tracked source. Rerun rc 0, 59/59.
Final pinned run:

```sh
ssh cpu64 "taskset -c 44-49 bash -c 'export PATH=\$HOME/.mc-venv/bin:\$PATH OMP_NUM_THREADS=6;
 cd /home/ubuntu/fix181-20261016/candidate;
 ctest --test-dir build --output-on-failure'" # rc 0, 59/59
```

Linux reciprocal mutant (same patch; pinned lane): target rebuild rc 0, focused
CTest rc 8 with nx=65, ix=35. Restored source, target rebuild rc 0, direct test
rc 0 with 57,922 coordinate checks + 480 configurations. No gate was altered.
`linux/source-and-polynomial.txt` records clean tracked source and successful
polynomial fits in all four product runs.

### Current-main exact products (no timing)

Tutorial input copied read-only from the existing issue36 tutorial fixture into
our data directory (not the corpus-screen directories); synthetic input generated
with `~/.mc-venv/bin/python3 candidate/test-data/generate_synthetic_fixture.py
--profile standard --outdir data` (rc 0). Input hashes: `linux/inputs.sha256` and
`products-pinned.json`. Sizes: tutorial 3710×3838×24, synthetic 512×512×16.

From `/home/ubuntu/fix181-20261016` on cpu64:

```sh
taskset -c 44-49 env OMP_NUM_THREADS=4 ~/.mc-venv/bin/python3 \
 candidate/docs/cpu_interpolation_xcoords_20261014/review_20261016/check_products.py \
 --base /home/ubuntu/fix181-20261016/base/build/motioncorr \
 --candidate /home/ubuntu/fix181-20261016/candidate/build/motioncorr \
 --base-source-sha d7171b810dc97003784339d7bad1c279903f3bba \
 --candidate-source-sha 78df217a0792571e1f3f3e3ecb9583db6b028848 \
 --data /home/ubuntu/fix181-20261016/data \
 --out /home/ubuntu/fix181-20261016/products-pinned # rc 0
```

The script records every binary invocation and exit status (all four rc 0): j4,
5x5 patches, fixed seed, DW/save-noDW/even-odd. Per-movie logs establish polynomial
fits, not a global-only bypass. Two strict tree comparisons pass: 8 MRCs,
4 STARs (12 hashed pairs). MRC payload SHA-256 excludes the complete header;
additionally, full-file canonical hashes compare every header byte except the
existing writer-timestamp mask. STAR hashes normalize only output roots. All
other strict comparator gates remain intact; PDFs inventoried, logs excluded.
`products-pinned.json` holds hashes and comparisons; `product-logs.tar.gz` retains
stdout and per-movie logs (these naturally include application log clocks, not
new timing measurements). The earlier locked run is retained in `products.json`.

Negative control: XOR 1 at the first synthetic MRC payload byte (offset 1024).
The same comparator rejects it, reporting `payload differs at byte 1024`;
script restores the byte. Comparator `identical=false` is the required rejection;
the enclosing verification command returns 0 only if rejection occurs.

## Limitations and next gate

This establishes same-backend exact output on these fixtures, not scientific
accuracy, speedup, native GPU execution, or a representative corpus result.
No wall-time runs were made; separate corpus-screen timing remains independent.
Historical container timing is not repaired by the new provenance flags. Keep the
PR draft pending the separate performance decision and final-head CI.
