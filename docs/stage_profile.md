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

Ranges are contiguous and **exhaustive**: closing one stage opens the next, so
every microsecond of a movie belongs to exactly one named stage, and gaps such as
the ones above become visible. The existing `RCTIC/RCTOC` markers are reused as
nested sub-stages. The same ranges are emitted as NVTX ranges when the binary is
built with CUDA. Nsight Systems therefore lines them up with kernels and copies,
with no source patching and no sudo.

Process-level records (`process` line) add run wall, process CPU (all threads),
peak RSS, total faults, writer-thread time and drain wait.

Off by default. When off, each probe is one branch on a cached bool; no syscalls,
no allocation, no output, and no product changes. When on, the cost is two
`clock_gettime` plus one `getrusage` per boundary (~45 boundaries/movie).

## Not in scope

GPU kernel timing remains Nsight's job; CUPTI inside the binary would perturb
what it measures. The existing `Total GPU alignment time` log lines are unchanged.

## Analysis

`tools/stage_profile.py run.jsonl [other.jsonl]` prints the per-stage table
(median/sum, CPU share, faults) and, given two files, the paired per-stage
difference. It also reports the serial host fraction that bounds multi-GPU scaling.
