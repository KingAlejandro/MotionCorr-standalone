# MotionCorr compare: base vs candidate

## Provenance

- kit: `5ac83a4ab4384f514a1ec2062f98c449576f01be`
- arm `base`: `/workspace/scratch/28038873ca11/build-reference/motioncorr` sha256 `b9f8912d65c79b57`; source `116eb04ad359cd5bf789b28809fc2047ea155b9b` (git in /workspace/scratch/28038873ca11/reference); --profile present
  - linked: libfftw3f.so.3=/workspace/scratch/4d99fce6c5db/build-deps/usr/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `candidate`: `/workspace/scratch/28038873ca11/build-candidate/motioncorr` sha256 `abd3db17aaf6a94a`; source `5ac83a4ab4384f514a1ec2062f98c449576f01be` (git in /workspace/scratch/28038873ca11/MotionCorr-standalone); --profile present
  - linked: libfftw3f.so.3=/workspace/scratch/4d99fce6c5db/build-deps/usr/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 442a2f5ea6ec, INTEL(R) XEON(R) PLATINUM 8573C, 9 CPUs, lane 0-3, load1 1.9, clocksource tsc, THP always [madvise] never
- locks: /tmp/motioncorr-bench.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 1 run, 0 clean, target 1 clean, at most 1 (TARGET NOT REACHED)
- input: `synthetic_512x512_16frames.star` in `/workspace/scratch/28038873ca11/data`, 1 movies, STAR sha256 `35c92d95f191f095`
- payload options: `--use_own --j 4 --angpix 1 --voltage 300 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1`
- command: `tools/profiling/mcprof.py compare base=/workspace/scratch/28038873ca11/build-reference/motioncorr candidate=/workspace/scratch/28038873ca11/build-candidate/motioncorr --data /workspace/scratch/28038873ca11/data --star synthetic_512x512_16frames.star --work /workspace/scratch/28038873ca11/kit-namespace-check --cpus 0-3 --runner-cpus 8 --pairs 1 --warmup 0 --lane-wait 5 --settle-timeout 5 --source base=/workspace/scratch/28038873ca11/reference --source candidate=/workspace/scratch/28038873ca11/MotionCorr-standalone --keep-outputs -- --use_own --j 4 --angpix 1 --voltage 300 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | - | - | - | - | - | - | - | - | - |
| candidate | 0 | - | - | - | - | - | - | - | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

Rounds: 1 planned, 0 retained, 1 discarded (a discard removes the whole round, every arm). Discards triggered by: `base` 1 (alone 0), `candidate` 1 (alone 0).

Discarded rounds:
- round 1 (AB): base: payload affinity [8] != lane | candidate: payload affinity [8] != lane

Lane wait before round: r1 1 s.

### `candidate` vs `base`: **not resolved (0 retained pairs, 6 needed)**

Reason: no retained pairs.

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| candidate | PASS | 9 | 1 | 5 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
