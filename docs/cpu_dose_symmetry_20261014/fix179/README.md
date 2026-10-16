# PR #179 current-main verification, 16 October 2026

**Result:** exact CPU products against main `1db869025507ac801845b4001b84e6bc0e77a645`, including FMA-enabled builds; Linux 60/60 CTests. No whole-job performance conclusion. This supersedes the old `116eb04a` validation for the current code, not its retained historical measurements.

## Revisions and fixes

- Original PR head: `b469e1f651fa0b9d09cbf85750c7d382f00c29f1`.
- Merge `77007ed1102ba7bfcbcfb24643d774c584e42813` incorporates main `d7171b810dc97003784339d7bad1c279903f3bba`, including the FFTW plan cache and destructive CPU DW inverse FFT.
- Fix `b302c08c998afc46832d5a6336b6458705661802`: default-OFF `BUILD_CPU_DOSE_BENCH` avoids building a second test executable by default; NaN messages explicitly identify their applicability to the mirrored negative-ly row. The numerical loop is unchanged.
- **Verified code head: `bcc77dee40856a0302700e7d39c00c83ca010eee`**, merge of updated main `1db86902` (#178 streamed unweighted reconstruction). The sole merge conflict was adjacent CMake test registrations; both tests are retained. Subsequent evidence-only commits do not change tested code.
- All review findings accepted. Codex reported no major issue. The performance review's clean-host paired comparison is intentionally deferred to the separate corpus screen; this task does not establish a merge recommendation.

## Current results and exit statuses

Every current candidate run below uses `bcc77dee`; every current baseline uses `1db86902`. Logs and commands are retained alongside this report.

| Check | Exit | Result |
|---|---:|---|
| macOS configure / build | 0 / 0 | Release CPU-only build |
| macOS full CTest | 8 | 57 passed, 2 failed, 1 skipped of 60 |
| macOS plain-main configure / build | 0 / 0 | Fresh archive of `1db86902` |
| macOS plain-main two failure controls | 8 | Same two failures and assertions |
| cpu64 baseline + candidate Release configure / build | 0 each | GCC 13.3, FFTW 3.3.10 |
| cpu64 full CTest | 0 | **60/60**, including GNU exp-call witness |
| cpu64 direct dose control | 0 | **1,680 exact-bit + exp-call-bound cases** |
| cpu64 Release product harness | 0 | **4/4** strict tree comparisons, 16 MRC product pairs |
| cpu64 both FMA configure / builds | 0 each | `-ffp-contract=fast -march=native` |
| cpu64 FMA CpuDoseSymmetry CTest / direct control | 0 / 0 | **1,680 cases pass** |
| cpu64 FMA product harness | 0 | **4/4** strict tree comparisons, 16 MRC product pairs |
| Release / FMA mutated-payload comparisons | 1 / 1 | Required failure: exactly one MRC payload differs at byte 1024 |
| Benchmark opt-in configure / target build / reset OFF | 0 / 0 / 0 | Builds when requested; absent from default target list |

The macOS failures are `SyntheticRegression` (pixel diff 23.649856567382812 instead of zero) and `MultiGpuScheduling` (validator rejects healthy published tree, 73/74 subcases pass). Both reproduce with the same assertions on plain main; only these two are set aside as instructed. `NativeMovieStaging` is an explicit platform skip. No tests or gates were modified.

## Commands and resources

Local Apple arm64 commands (logs `macos-final-*`):

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
  -DPython3_EXECUTABLE=$HOME/.venvs/global/bin/python3
cmake --build build -j 4
ctest --test-dir build --output-on-failure
# Plain-main control: git archive 1db86902 | tar -x -C /tmp/fix179-macos-main
# Same configure/build, with that source/build directory; then:
ctest --test-dir /tmp/fix179-macos-main/build \
  -R '^(SyntheticRegression|MultiGpuScheduling)$' --output-on-failure
```

cpu64 is a shared AMD EPYC 7763 VM. All final builds, suites and products are confined to `/home/ubuntu/fix179-20261016`, **taskset CPUs 38-43**, build parallelism 6, inherited `OMP_NUM_THREADS=6`; product jobs request j4 and set `OMP_NUM_THREADS=4`. No CPUs 0-31, GPUs, `/mnt`, corpus or screen files were used. Host/compiler, flags, binary/source hashes and affinity: `linux/environment.txt`. This is correctness verification, not a timing-isolated environment.

Trees shipped using `git archive <sha> | ssh cpu64 'tar -x -C DIR'`. Candidate Git metadata was fetched separately for the Git-backed CI fail-closed control; `git reset --mixed FETCH_HEAD` did not replace the archived working tree. Commands inside `taskset -c 38-43 bash -c '...'`:

```sh
export PATH=$HOME/.mc-venv/bin:$PATH OMP_NUM_THREADS=6
cd /home/ubuntu/fix179-20261016
for arm in base candidate; do
  cmake -S $arm -B $arm/build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
    -DPython3_EXECUTABLE=$HOME/.mc-venv/bin/python
  cmake --build $arm/build -j 6
done
ctest --test-dir candidate/build --output-on-failure
candidate/build/cpu_dose_symmetry
python run_products.py --root /home/ubuntu/fix179-20261016 --variant release
for arm in base candidate; do
  cmake -S $arm -B $arm/build-fma -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
    -DCMAKE_CXX_FLAGS="-ffp-contract=fast -march=native" \
    -DPython3_EXECUTABLE=$HOME/.mc-venv/bin/python
  cmake --build $arm/build-fma -j 6
done
ctest --test-dir candidate/build-fma -R CpuDoseSymmetry --output-on-failure
candidate/build-fma/cpu_dose_symmetry
python run_products.py --root /home/ubuntu/fix179-20261016 --variant fma
# Opt-in compilation only, never execute a timed benchmark:
cmake -S candidate -B candidate/build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
  -DBUILD_CPU_DOSE_BENCH=ON -DPython3_EXECUTABLE=$HOME/.mc-venv/bin/python
cmake --build candidate/build --target cpu_dose_bench -j 6
cmake -S candidate -B candidate/build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF \
  -DBUILD_CPU_DOSE_BENCH=OFF -DPython3_EXECUTABLE=$HOME/.mc-venv/bin/python
```

`linux/fma-target.txt` records `-mfma [enabled]`; both `*-fma-instructions.txt` files record emitted FMA instructions in the production runner object. This checks each build mode against matching main, **not** equality between Release and FMA builds.

## Product checks and inputs

`run_products.py` is an untimed harness over the unchanged `tools/profiling/lib/identity.py`. For **both** synthetic 512x512x16 and tutorial 3710x3838x24, run global 1x1 and local 5x5 with dose weighting, save_noDW, even/odd, j4, seed 1, dose/frame 1.277, voltage 300, B-factor 150; apix 1 / 0.885 respectively, tutorial gain applied. Exact invocation, exit and binary SHA-256 for every job: `linux/products-{release,fma}.json`.

Each of eight comparisons requires exactly four MRC products and identical file inventories; 12 non-excluded files per tree compare exactly. SHA-256 includes raw MRC payloads, complete files with only the existing first-label clock mask, and root-normalized STAR. Complete MRC headers and extended headers are also checked, not discarded. Existing log timing and PDF-byte exclusions remain unchanged; PDF inventory is checked. Each negative control flips one byte of the primary DW MRC payload and requires exactly that payload difference. No tolerance or normalization was added.

Inputs downloaded independently from release `spa-tutorial-data-v1` (`test-data/README.md` recipe), checked against its SHA256SUMS; synthetic generated with `candidate/test-data/generate_synthetic_fixture.py --profile standard --outdir inputs` (exit 0):

- tutorial TIFF: `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`
- gain MRC: `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`
- synthetic MRCS: `36e1a91b25a54d958e0ff78be87e55fa9777aebbd36d145d415bbc7837b8c8a1`

## CI and limitations

Code-head CI [38954420178](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38954420178) is green on `bcc77dee`: Ubuntu build/smoke + CUDA compile-only. `ci-code-head.json` records its exact revision/status. Final evidence-head CI is linked in the PR body after it completes.

No native GPU execution, timing samples, speedup claim or scientific-equivalence claim. Same-backend exact identity covers these fixtures/settings only. The original whole-job performance objection remains unresolved and is for the separate corpus screen to decide; keep the PR experimental.

Superseded attempts are retained, not pooled: initial macOS `b302c08c` logs, and `linux/superseded-d7171b81/` (58/59 initial CTests because the archive lacked Git metadata and `cmake` was not on PATH; 59/59 after environment correction; one completed global synthetic product pair). A waiting own flock command and its harness were cancelled when the orchestrator reassigned CPUs 38-43 and removed the lock rule. Final checks above use no flock. No failed numerical gate was waived to obtain a pass.
