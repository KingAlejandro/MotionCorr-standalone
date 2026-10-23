# Commands and status

Venue: `ssh -J ccp4-gateway 4GPUs`, scratch
`/mnt/clathrin/alex-motioncorr-213`, CPUs 80–87, GPU2 UUID
`GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`.

Source staging used `git archive --format=tar.gz faba8961 CMakeLists.txt src tests
tools SOURCE_MANIFEST.txt README.md` (archive SHA-256
`6cb7ae89b43eb4699c297fae6af641232946d0582325e012a3a6eefc026e1b7c`),
transferred with rsync through the gateway and extracted with Linux tar to
`src-min`. The final driver was rsynced from `f25c9580`; its SHA-256 is
`2f9c6674858b73c5c89761201d3239d2b4495799735451d8c23fa3624a0e43ac`.
All **451** archived files were then verified against the local `f25c9580`
manifest in `source-sha256.json`; no mismatch. The earlier failed full-archive
transfer to `src` was not used for a build or execution.

Executed in scratch (each configure/build exit **0**):

```sh
taskset -c 80-87 cmake -S src-min -B build-cuda -DCMAKE_BUILD_TYPE=Release \
  -DCUDA=ON -DUSE_NVCOMP=OFF -DBUILD_TESTING=ON \
  -DMC_ENABLE_STICKY_CUDA_TEST=ON \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3
taskset -c 80-87 cmake --build build-cuda --target motioncorr_sticky_fault -j8
taskset -c 80-87 cmake -S src-min -B build-nvcomp -DCMAKE_BUILD_TYPE=Release \
  -DCUDA=ON -DUSE_NVCOMP=ON -DBUILD_TESTING=ON \
  -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive \
  -DMC_ENABLE_STICKY_CUDA_TEST=ON \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DPython3_EXECUTABLE=/home/alex/.mc-venv/bin/python3
taskset -c 80-87 cmake --build build-nvcomp --target motioncorr_sticky_fault -j8
```

Final controls, each exit **0**:

```sh
CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 \
  taskset -c 80-87 /home/alex/.mc-venv/bin/python3 src-min/tests/run_sticky_cuda_control.py \
  --binary build-cuda/motioncorr_sticky_fault --workdir control-cuda-final
CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 \
  taskset -c 80-87 /home/alex/.mc-venv/bin/python3 src-min/tests/run_sticky_cuda_control.py \
  --binary build-nvcomp/motioncorr_sticky_fault --workdir control-nvcomp-final
```

The driver acquires/releases the canonical GPU2 flock around every arm and its
health checks, verifies idle occupancy, and records the actual CPU affinity and
binary/input hashes. Every movie/worker invocation's full argv, cwd and return
code is in the arm's `*-command.json`; dataset workers additionally retain their
`command.json`, console log, status, process ownership and cleanup records.

Mutant: only `if (decision.verdict == CUDA_RETRY_FATAL)` at runner line 3703,
following `downloadPatchSpectra`, was changed to `if (false && ...)` in scratch.
The same CUDA target was rebuilt, then the same final driver ran with
`--workdir control-mutant-final`: exit **1**, expected attributed-refusal
assertion. Real fault and later product allocation both returned 700. Final GPU
health passed. `mutant-final.json` gives the exact command and source/binary
hashes. Restoring the source and rebuilding returned exit 0 and exactly the
original binary hash. Neither mutant source nor a mutant executable is committed.

The earlier `control-mutant` is the superseded health-sampling experiment; see
the README. Its GPU utilization sample was 3% after process exit. The final
driver waits for a bounded number of samples to reach the same required zero.

Production audit, each build exit **0**:

```sh
taskset -c 80-87 cmake --build build-cuda --target motioncorr -j8
taskset -c 80-87 cmake --build build-nvcomp --target motioncorr -j8
ctest --test-dir build-cuda --show-only=json-v1
ctest --test-dir build-nvcomp --show-only=json-v1
```

`nm -C` and binary-byte checks on both production binaries found no test kernel,
wrapped allocation/launch symbols, or `MC_STICKY_FAULT` string. The collection
commands collected 109/112 tests, including exactly one opted-in control, and
did **not** execute the full suites. Results are summarized in `summary.json`.
Raw build logs, original command/status JSON and console/health logs are retained;
healthy image products and temporary input stacks remain in scratch, with input
hashes recorded here. No timing comparison or scientific acceptance was run.
