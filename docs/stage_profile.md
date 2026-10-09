# Built-in stage profile (`--profile`)

## Why

Recent profiling needed hand-patched builds (`tools/nsys_analysis/patch_nvtx.py`),
sudo-only Nsight sampling, and ad-hoc probes. It still missed about 44% of each movie: two untagged
windows between existing stage markers were serial first-touch page faults on
fresh full-frame host buffers (~45 ms each per movie), with the GPU idle. A
single-GPU run cannot see this from per-stage tables, and for multi-GPU scaling
the serial host fraction is the quantity that matters.

## What

`--profile <file.jsonl>` makes every release binary record, per movie and per
stage, on the main thread:

| field | source | meaning |
|---|---|---|
| `wall_ms` | `CLOCK_MONOTONIC` | elapsed |
| `cpu_ms` | `CLOCK_THREAD_CPUTIME_ID` | main-thread CPU (wall − cpu ≈ blocked/waiting) |
| `minflt`, `majflt` | `getrusage(RUSAGE_THREAD)` | page faults on the main thread |
| `vcsw`, `ivcsw` | same | voluntary (blocking) / involuntary (preempted) switches |

Ranges are contiguous: closing one stage opens the next, so every microsecond of
a movie is charged to exactly one named stage. That tiling holds by construction
and proves nothing by itself. What makes gaps like the ones above visible is that
the boundaries are placed around the work they name. `tests/test_stage_profile.py`
therefore checks attribution: each substantial stage must contain its own
sub-stage as most of its wall, and the catch-all stages must stay small. A
deleted or misplaced boundary fails that check (verified with compiled mutants). The existing `RCTIC/RCTOC` markers are reused as
nested sub-stages. The same ranges are emitted as NVTX ranges when the binary is
built with CUDA. Nsight Systems therefore lines them up with kernels and copies,
with no source patching and no sudo.

Process-level records (`process` line) add run wall, process CPU (all threads),
peak RSS, total faults, writer-thread time and drain wait.

Off by default. When off, each probe is one branch on a cached bool; no syscalls,
no allocation, no output, and no product changes. When on, the cost is two
`clock_gettime` plus one `getrusage` per boundary (~45 boundaries/movie).

## Output safety

- `--profile` creates its file exclusively (`O_EXCL`). An existing file, or a
  symlink at that path, is refused before anything is written, because the
  option is parsed before inputs are validated.
- Write, flush and close failures are reported once on stderr. The run and
  its products are unaffected.
- Stage calls from non-owner threads return before touching owner-only state
  (`tests/test_stage_profile_threads.cpp`).

## Device timing (`--profile_device_timing`)

`--profile` also turns on CUDA event timing for the per-step lines of the
alignment and dose-weighting log blocks. Each timed step waits for the device,
so a profiled run synchronises more often than production, and an Nsight trace
of it overstates the sync counts and device idle of those stages.

`--profile_device_timing 0` (with `--profile`) keeps everything else: the
stage records, the sub-stages and the NVTX ranges. The CUDA code then takes its
unprofiled shape, and the log blocks print the unprofiled "not measured" lines.
The default is 1, the previous behaviour. The process record states the mode as
`"device_timing":"on"` or `"off"`. Without `--profile` the option has no effect.
The profiling kit's trace passes use 0 by default.

## Reading sub-stages

Sub-stages come from the existing `RCTIC/RCTOC` markers and are recorded on the
main thread only. Markers inside OpenMP regions (`CCF_CALC`, `CLIP_PATCH`,
`PATCH_FFT`, ...) therefore count only the master thread's iterations: with
`--j 4` they cover roughly a quarter of the work. Treat their wall and counts as
a share, not a total. Top-level stages are unaffected.

A movie's `ok` reflects computation. A product write that fails later on the
writer thread is reported by the existing failure path, not in that record.

## Not in scope

GPU kernel timing remains Nsight's job; CUPTI inside the binary would perturb
what it measures. The existing `Total GPU alignment time` log lines are unchanged.

## Analysis

`tools/stage_profile.py run.jsonl [other.jsonl]` prints the per-stage table
(median/sum, CPU share, faults) and, given two files, the paired per-stage
difference. It also reports the serial host fraction that bounds multi-GPU scaling.
