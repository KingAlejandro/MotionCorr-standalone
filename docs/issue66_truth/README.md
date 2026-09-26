# Issue 66: CPU known-motion evidence

On 2026-09-26, the repaired truth validator passed all four gate-role fixtures on
CPU candidate `2c27c7bcb8a697bcc78e17c224bc88f338f1b9ff`. The small noisy fixture
retains its **FAIL** characterization result. No thresholds were changed.

| Fixture | Role / result | Global RMS (Å) | Local RMS (Å) | Total interior RMS (Å) |
| --- | --- | ---: | ---: | ---: |
| `km_global_hisnr` | gate / PASS | 0.008294 | <1e-16 | 0.008294 |
| `km_local_hisnr` | gate / PASS | 0.007881 | 0.051685 | 0.053024 |
| `km_local_nonsquare` | gate / PASS | 0.007205 | 0.040292 | 0.042217 |
| `km_local_realscale` | gate / PASS | 0.053057 | 0.145134 | 0.154049 |
| `km_local_noisy` | characterization / **FAIL** | 0.260688 | 0.621738 | 0.659491 |

All five fixtures had **exactly zero** field difference between j1/j4 and dose
weighting off/on. All three defect-free fixtures passed the mandatory applied-image
witness: relative RMSE was `7.2154e-8`, `3.5252e-7` and `3.7518e-7` for global,
local and nonsquare respectively, against the existing `1e-4` limit. This witness
re-applies each candidate's own reported field; it is not CPU-versus-CUDA image RMSE.
The raw-movie witness is intentionally unavailable for the two fixtures whose hot
pixels are replaced before alignment; their field and invariance checks were run.

The original fixture self-validation and negative-control suite passed **27/27**.
The two new validator suites passed **16/16**, including rejecting wrong applied
pixels, NaN/Inf, incomplete arguments, missing requested cases, thread differences,
missing CUDA execution evidence and a failed characterization subprocess.

## Provenance and scope

- Host: SSH alias `cpu64`, actual hostname `small-refmac-machine`, AMD EPYC 7763,
  64 visible logical CPUs. Load before/after was approximately 2.1/2.8.
- A top-level `taskset -c 48-55` restricted the entire test tree to eight logical
  CPUs. The supervisor and descendants' affinity was inspected while running.
  `OMP_NUM_THREADS=8`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`; each candidate
  invocation explicitly used `--j 1` or `--j 4`. No other users' work was changed.
- Candidate: CPU-only Release build, GCC 13.3, `-O3 -DNDEBUG`, CUDA disabled.
  All 239 staged source/CMake files were checked against the named Git commit.
- Executable: `/home/ubuntu/mc-stabilize-20260926-cpu/build-candidate/motioncorr`.
  SHA256 before and after testing:
  `c68596ae62c029c06278854a19ccfb850e60fdc46a5f2cf20448ef84cc5696d2`.
- Checker, launcher, generator and control source:
  `0f203d4cc86a0042cd08af8ab24cd14145fdc4db`; all seven staged files were hashed.
  Python 3.12.3, NumPy 1.26.4. Fixture generation ran from a pinned archive rather
  than a Git checkout, so its `source_commit: unknown` is resolved by the source
  hashes and explicit commit in the run manifest.
- Run: 2026-09-26 11:45:15–11:46:17 UTC. Fixtures, full movie outputs and logs remain
  under `/home/ubuntu/mc-stabilize-20260926-truth-0f203d4` on cpu64. The committed
  evidence contains reports, provenance and hashes; movie arrays remain remote.
- These are CPU truth/validator results for this exact executable. They do not
  establish native CUDA correctness, CPU/RELION Gate 2 agreement or a performance
  improvement. Recorded per-command elapsed times are single diagnostic runs.

## Commands and artifacts

The top-level environment above ran these commands sequentially, using absolute
paths recorded verbatim in [run-manifest.json](cpu64-2c27c7b/run-manifest.json):

```sh
python3 tools/test_known_motion_verdicts.py -v
python3 tools/test_known_motion_runner.py -v
python3 tools/run_known_motion_gates.py --binary /absolute/path/to/candidate/motioncorr \
    --fixtures /absolute/path/to/known_motion --outdir /absolute/path/to/all-results \
    --include-heavy --json /absolute/path/to/known-motion-all.json
python3 tools/test_known_motion.py --binary /absolute/path/to/candidate/motioncorr \
    --fixtures /absolute/path/to/known_motion --keep /absolute/path/to/original-controls
```

[Aggregate results](cpu64-2c27c7b/known-motion-all.json) include every candidate
command, status, backend-selection record and invariant. [Per-case reports](cpu64-2c27c7b/gates)
retain all field metrics and failed noisy-case gates. The [original suite log](cpu64-2c27c7b/original-known-motion-controls.txt)
records the measured witness response and defect-detection sensitivity.
The [fixture manifest](cpu64-2c27c7b/fixture-manifest.json) identifies the generated
movie inputs; the run manifest additionally hashes every fixture and result file.

Copied log and per-case JSON hashes were verified against the remote run manifest.
Remote `.log` files are stored here with `.txt` suffixes, with unchanged contents.
