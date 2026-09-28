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

<!-- filled in when the run completes -->
