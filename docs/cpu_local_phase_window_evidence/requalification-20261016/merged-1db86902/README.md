# Current acceptance: main 1db86902 merged

This section supersedes the earlier d7171b81 qualification. Base `1db869025507ac801845b4001b84e6bc0e77a645` includes #178 streamed unweighted reconstruction. Candidate merge `e48b59ca2e6070ba6ac53e5fd4161e18b978219c` merges main without conflicts, rebase, or force-push. No additional production changes were needed. All review findings remain addressed; no numerical gate changed.

## Results and commands

All cpu64 payloads inherited **taskset -c 56-61**, no flock, `OMP_NUM_THREADS=6`, `OMP_THREAD_LIMIT=6`, builds `-j4`; movie commands use j1/j4. No timing measurements. Work remains entirely under `/home/ubuntu/fix183-20261016/`. Trees shipped via `git archive <sha> | ssh cpu64 'tar -x -C DIR'`; exact Git metadata restored to support git-dependent test controls. Binary/input/product hashes are in `linux/exact-results.json`, `linux/witnesses.log`, `linux/restored-binary-sha256.txt`.

| Verification at e48b59ca | Command (full commands in scripts/logs) | Exit | Result |
|---|---|---:|---|
| Linux Release | `cmake -S . -B build-release -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=/home/ubuntu/.mc-venv/bin/python3`; `cmake --build build-release -j4` | 0 | built |
| Linux full Release | `ctest --test-dir build-release --output-on-failure` | 0 | **60/60**, no skips |
| Linux Debug | same with `build-debug`, `-DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS_DEBUG="-O0 -g"` | 0 | built |
| Linux full Debug | `ctest --test-dir build-debug --output-on-failure` | 0 | **60/60**, no skips |
| Plain 1db86902 Release | configure/build `base-178/build` | 0 | reference built |
| Focused, both configs | `build-{release,debug}/cpu_patch_phase_window` | 0 | positive trig witness, 300 geometries, 108 alignments, **36 cropped multi-iteration** |
| Exact products | `python3 exact.py` | 0 | four strict 5x5 tutorial/synthetic j1/j4 pairs vs **1db86902** |
| Product negative control | same driver, flip first MRC payload byte | **1 comparator**, 0 driver | exactly one payload mismatch, identical inventories |
| Linux mutants | `python3 linux-mutants.py` | 0 driver | three builds exit 0; each mutated test **1**; restored build/tests 0 |
| macOS Release | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=$HOME/.venvs/global/bin/python3`; `cmake --build build -j4` | 0 | built |
| macOS full CTest | `ctest --test-dir build --output-on-failure` | **8** | **57 pass / 2 fail / 1 skip**, 60 total |
| Plain 1db86902 macOS control | same build; `ctest -R '^(SyntheticRegression|MultiGpuScheduling)$' --output-on-failure` | **8** | same two inherited failures |
| macOS mutants | `python3 mac-mutants.py` | 0 driver | both build 0 / test **1**; restored check 0 |

MRC payload SHA-256, full headers with only the known first-label writer timestamp masked, and root-normalized STAR SHA-256 match: **16 MRC + 8 STAR pairs**, 48 deterministic files across four full inventories. Inputs: independently downloaded/verified release tutorial 00021 and gain; generated standard 512x512x16 seed 20260923. Every pair uses 5x5, group_frames=5, DW/save_noDW/even_odd_split. See `exact.py` for complete run commands and the existing log/PDF exclusions. Negative control differs only at MRC byte 1024.

Mutants prove discrimination: omit fallback sine count in Debug; restore full local support; restore dead-final update; skip needed local updates; restrict rows to iteration limit 1. First three fail count assertions, fourth fails exact trajectory/log comparison, fifth fails mandatory cropped >=2-iteration coverage. Production code is restored after each.

macOS inherited failures are identical to plain main: SyntheticRegression max pixel difference **23.649856567382812**, MultiGpuScheduling tomography healthy-tree assertion. NativeMovieStaging explicitly skips on macOS. Only the two user-authorized inherited failures are ignored; nothing else is waived.

CI [38953626025](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38953626025) passes at e48b59ca (Linux build/full CTest/smoke and CUDA compilation). Code/base blob manifests are retained. Final evidence commit changes documentation only; final pushed-head results are reported in the PR closing comment.

## Prior attempt retained

`linux/final-head.log` belongs to the preceding **91a73577** recheck against d7171b81, not this merge: StageProfile failed its patch-stage containment assertion (9.413 ms substage / 18.878 ms stage) with products identical, exit 8/driver 2. Earlier e48b59ca checks pass that assertion in both configurations unchanged. The old archive/no-Git and short-ref failures remain retained as historical setup failures; they are not current passes.

## Limits

No wall-time/RSS measurement or native GPU execution; exact same-backend products are not scientific equivalence. Benefit is calculated: 6.52% retained complex support for the representative geometry, then I-1 rather than I local updates (half for I=2, none for I=1). Separate corpus timing/benefit decision remains unresolved; keep draft. Do not infer current benefit from old container helper ratios or unexplained movie gap.
