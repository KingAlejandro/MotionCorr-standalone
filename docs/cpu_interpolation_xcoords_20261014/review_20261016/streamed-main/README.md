# Current verification after #178 merged

Baseline: `1db869025507ac801845b4001b84e6bc0e77a645`.
Merged/tested revision: `d22c4569160a6d88eb73b754c2cbaa5edd9f452b`.
This supersedes the parent directory's d7171b81 verification for current-head claims.
Subsequent evidence commits change no src/tests/CMake/driver bytes.

The merge retains #178's `frame_offset` and `model_frame = iframe + frame_offset`.
The added test compares one-frame calls at offsets 0..nf-1 against the frozen
full-stack reference in every existing configuration, with nonzero destinations.
The cache builder depends only on nx, not time. Both methods construct it once
before their frame loop, never in row/pixel loops. The new streamed unweighted
caller invokes interpolation separately for each frame, so that path now builds
nx coordinates **per frame**, not once per movie (24 × 3710 for the tutorial).
This is the explicitly permitted per-call scope; hoisting across calls would
expand ownership/interface changes and is left out. It remains far fewer divisions
than the original per-pixel expression, but establishes no speed benefit.

## Commands and results

Same macOS environment, cpu64 host, input hashes and flags as the parent report.
No gate relaxations or timing runs. All remote commands now inherit
`taskset -c 44-49` with `OMP_NUM_THREADS=6` (4 for products), no flock; build -j6.
No CPUs 0–31 used after the allocation change.

macOS, checkout at d22c4569:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
 -DPython3_EXECUTABLE=$HOME/.venvs/global/bin/python3 # rc 0
cmake --build build -j4                            # rc 0
ctest --test-dir build --output-on-failure           # rc 8
```

57 pass, 2 fail, 1 skip / 60. Only SyntheticRegression and MultiGpuScheduling
fail; NativeMovieStaging skips. Independently archived main 1db86902 to
`/tmp/fix181-local-20261016/streamed/main`, configured identically and built
motioncorr (-j4, rc 0 each), then ran `ctest --test-dir .../build -R
'^(SyntheticRegression|MultiGpuScheduling)$' --output-on-failure` (rc 8): same
23.649856567382812 pixel difference and healthy-tree tomography validator failure.

Linux trees shipped with `git archive d22c4569` and `git archive 1db86902` piped
to `ssh cpu64 'taskset -c 44-49 tar -x -C DIR'` (rc 0 both), where DIR is
`/home/ubuntu/fix181-20261016/streamed-candidate` or `streamed-base`.
Imported exact Git metadata to candidate with a bundle, as in the parent report.
Under pinned shell with PATH including ~/.mc-venv/bin:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
 -DPython3_EXECUTABLE=$HOME/.mc-venv/bin/python3 # rc 0 each tree
cmake --build build -j6                       # candidate rc 0
cmake --build build -j6 --target motioncorr   # baseline rc 0
ctest --test-dir build --output-on-failure    # candidate rc 8 first; rc 0 full rerun
```

Full rerun **60/60 pass**. First run had ProfilingKit's two mock-CLI controls hit
their existing 30-second subprocess timeout on this shared host; retained in
`linux/ctest.log`. No timeout, test, or code change preceded the successful full
rerun (`linux/ctest-rerun.log`). This transient remains a limitation, not an ignored
failure. CpuUnweightedStream and the coordinate/offset test pass on both hosts.

On both hosts, apply `mutant.patch` changing the production builder to reciprocal
multiplication, build target cpu_interpolation_xcoords (rc 0), then focused CTest
`-R '^CpuInterpolationXcoords$' --output-on-failure` (rc 8): nx=65, ix=33 macOS;
nx=65, ix=35 Linux. Restore source/rebuild (rc 0); direct test rc 0: 57,922
coordinates, 480 configurations including streamed offsets. All logs retained.

Product verification from remote `/home/ubuntu/fix181-20261016`:

```sh
taskset -c 44-49 env OMP_NUM_THREADS=4 ~/.mc-venv/bin/python3 \
 streamed-candidate/docs/cpu_interpolation_xcoords_20261014/review_20261016/check_products.py \
 --base /home/ubuntu/fix181-20261016/streamed-base/build/motioncorr \
 --candidate /home/ubuntu/fix181-20261016/streamed-candidate/build/motioncorr \
 --base-source-sha 1db869025507ac801845b4001b84e6bc0e77a645 \
 --candidate-source-sha d22c4569160a6d88eb73b754c2cbaa5edd9f452b \
 --data /home/ubuntu/fix181-20261016/data \
 --out /home/ubuntu/fix181-20261016/products-streamed # rc 0
```

All four binary invocations rc 0; tutorial/synthetic 5x5 local-patch strict trees
match. 8 MRC payload and canonical-file hashes + 4 canonical STAR hashes match.
This includes streamed noDW/even-odd outputs and the DW sum path. Polynomial fits
are confirmed by the per-movie logs (`polynomial-path.txt`, `product-logs.tar.gz`).
Payload XOR-one negative control is rejected at offset 1024 and restored.
`products.json` records commands, binary/source/input identities, SHA-256s,
comparisons and negative result. Header timestamp/root normalizations are
unchanged; no numerical tolerance. Main and candidate build hashes are separate.

Limitations: same-backend fixture identity only, no new timing, speed or native
GPU claim. Separate corpus timing/performance decision remains unresolved; keep draft.
