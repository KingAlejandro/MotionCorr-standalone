# Lane B production A/B: does the pool change the application?

Source `a75f873`. Host `small-refmac-machine` (cpu64), Ubuntu 24.04, g++ 13.3,
LibTIFF 4.5.1, `-DCMAKE_BUILD_TYPE=Release`, built from scratch after a
staleness guard (`strings` on the test binary must contain a string only this
revision has) — an earlier attempt silently measured a stale binary because a
rebuild raced with the source sync.

All 24 RELION tutorial movies, `~/mc-issue26/data`, 3.04 GB on disk.

Common arguments, identical in every arm:

```
--i movies_all.star --o run_<arm> --use_own --j 8 --dose_weighting
--dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150
--gainref Movies/gain.mrc
```

Arms differ only by `--persistent_tiff_readers`: absent (`off`), `8` (matching
`--j`), and `16` (deliberately oversubscribing the budget).

**Fixed CPU budget.** Every arm runs under `taskset -c 0-7`, so the pool
cannot buy speed by taking more CPU than the baseline. This is the condition
the issue's stop rule is about: a faster reader that slows the whole
application under a fixed budget is a no-go.

**Controls.**
- Arm order alternates between pairs (`off on8 on16`, then `on16 on8 off`), so
  a monotonic drift in machine state cannot be read as an arm effect.
- The page cache is warmed identically before every arm (gain plus all 24
  movies).
- Each arm waits for the 1-minute load average to fall below 6.0 before
  starting, and the value it saw is recorded per arm.
- Runs are serialised against other MotionCorr work on the host through
  `flock /tmp/motioncorr-cpu64-bench.lock`.
- **Arm engagement is verified from the per-movie logs**, not assumed. An `on`
  arm whose logs lack `Persistent TIFF readers: N` silently ran the reference
  path; an earlier local A/B passed exactly that way because a shell had
  folded the flag and its value into one argv entry.

**Parity.** Every arm's 24 corrected images are compared against `off_p1` from
byte offset 1024 — the MRC header carries a build timestamp, so a whole-file
hash is not reproducible — plus byte comparison of the 24 per-movie STAR
files. The `off_p2`/`off_p3` arms serve as a same-arm control: they must match
too, or the comparison is measuring run-to-run noise rather than the flag.

Raw per-arm records: `production_ab.jsonl`.

## Results

Nine runs, 2026-09-28 16:18-17:00 UTC.

| arm | wall (s), in run order | median | mean | peak RSS (GiB) |
|---|---|---:|---:|---:|
| off | 242.7, 229.7, 230.1 | 230.1 | 234.2 | 3.177 |
| 8 readers | 240.9, 235.6, 227.1 | 235.6 | 234.5 | 3.176 |
| 16 readers | 238.7, 240.2, 221.9 | 238.7 | 233.6 | 3.177 |

**No detectable effect on the application.** The three arm means lie within
0.4% of each other (234.2 / 234.5 / 233.6 s). The medians differ by more
(+2.4% and +3.7%) but with three runs per arm a median is just the middle
value, and the spread *within the `off` arm alone* is 13.0 s — 5.7% of its
own median, larger than any between-arm difference. Across all nine runs the
spread is 20.9 s (8.9%). The right reading is that this experiment moves the
application wall by less than the run-to-run noise of the host.

Peak RSS is 3.177 GiB in every arm, identical to three decimals. Sixteen
readers on eight CPUs costs nothing in memory: a worker's extra state is one
`TIFF*` and one strip buffer, 7,420 bytes at this geometry.

**The oversubscribed arm is not a regression.** 16 readers against a fixed
8-CPU budget is the case the issue's stop rule is aimed at, and it is
indistinguishable from the baseline.

### Engagement

| arm | movie logs reporting a pool |
|---|---|
| `off` x3 | 0 of 24 |
| `on8` x3 | 24 of 24, `Persistent TIFF readers: 8` |
| `on16` x3 | 24 of 24, `Persistent TIFF readers: 16` |

### Output parity

Every one of the eight non-reference arms against `off_p1`:

```
24 images compared, 0 image mismatches; 24 STARs compared, 0 STAR mismatches
```

That includes `off_p2` and `off_p3`, the same-arm control: the comparison
would have flagged ordinary run-to-run variation if there were any, so the
zero for the `on` arms is a statement about the flag and not about the
comparison being insensitive. The comparator's sensitivity is shown separately
in `output_parity.md`, where a 20-of-24-frame run produces a different hash.

## What this does not settle

This is the CPU regime. Issue #85 measured TIFF reading at 2.7% of a CPU-regime
run and estimates roughly 25% of a native-CUDA run, because CUDA offloads the
stages that dominate here while the host-side read cost is unchanged. So this
venue dilutes lane B's effect by roughly an order of magnitude, and a GPU-regime
run would be the sharper test.

It would not change the verdict, though, and the microbenchmark bounds why: the
pool removes 1.7% of a movie read by stage attribution, and 5-10% end to end at
16-24 readers *with 64 CPUs available*. Taking the optimistic 10% against a 25%
ingest share caps the benefit at about 2.5% of GPU-regime wall — and shared work
on the GPU host is capped at eight logical CPUs, where 16-24 readers
oversubscribe and that 5-10% would not survive.

The GPU host was also not available for a clean timed run: load 17.5, three
resident compute processes, two holding 61 GB of device memory each.

