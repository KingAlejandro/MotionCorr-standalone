**Parked — maintainer M8 selection, 23 October 2026 (Europe/London).**

This PR remains open at retained head [`401a810ff7bbb100bff84b14c3cc3c536eb9cc9f`](https://github.com/KingAlejandro/MotionCorr-standalone/commit/401a810ff7bbb100bff84b14c3cc3c536eb9cc9f). The corrected INCONCLUSIVE calibration, withdrawn blocking limits, exposed holdout and retained warning-tier result remain historical evidence; no replacement gate is established. No branch deletion or history rewrite is authorized.

The original PR description is retained below.

---

Evidence report and calibration tooling for #60.

> **Revised 28 September 2026 after two independent review rounds.** All three blocking limits this PR originally proposed are **withdrawn**. The headline figures in the first version of this description were computed on a leaked hold-out split and are superseded. Start at **§0** of the report.

**This PR changes no gate.** `tools/compare_motioncorr.py`, `docs/reference_gates.md`, `src/` and `test-data/` are untouched; the `0.001` relative-RMSE limit is unchanged and no recorded PASS/FAIL result is reclassified. Not for merge.

Report: [`docs/calibration/issue60_gate_calibration.md`](https://github.com/KingAlejandro/MotionCorr-standalone/blob/t3code/calibrate-motioncorr-gates/docs/calibration/issue60_gate_calibration.md)
Design record + addendum: [`agents/designs/issue_60_gate_calibration.md`](https://github.com/KingAlejandro/MotionCorr-standalone/blob/t3code/calibrate-motioncorr-gates/agents/designs/issue_60_gate_calibration.md)

## Outcome

**No blocking numerical acceptance limit is established.** #60 states an inconclusive result is allowed; this is one. The precise boundary of the claim:

- the withdrawal of **blocking** status holds at all three declared harm boundaries (2, 5, 10 Å²);
- at the loosest of them, 10 Å², the envelope diagnostic *does* separate and the frozen decision rule rates it **warning** — θ ≈ 5.72 Å², hold-out 0/228 false alarms, 15/134 false negatives. Reported in §10.4.1 rather than suppressed.

## What is established

1. **The harmless-variation floor is exactly zero.** 176 harmless cells over twelve movies — `--j 1/2/4/8`, three thread placements, five repeats — are bit-identical; largest value on any of the 18 candidate diagnostics is `1.478e-15`. Gate 2's "parallel reductions can alter results" rationale is not supported for thread count or placement on this build, and exact equality is a free, already-met CPU regression bar.
2. **`0.001` ≈ 0.017 Å² of envelope loss — 0.05 % of amplitude at 3 Å.** Three independent faults agree. Roughly 300× stricter than any harm boundary defensible here.
3. **It cannot be repaired by changing the number.** Its negligible and unacceptable populations overlap ~80×; at 0.001 it fires on 58 % of cells costing essentially no signal.
4. **A 1 ppm input change already doubles it**, at an envelope cost of 3.8e-4 Å², and the response then saturates near 1e-2 — where the recorded CUDA range of 0.0029–0.0100 sits. Consistent with harmless arithmetic difference; **not proof** of it.
5. **The largest gate failures in the matrix are scientifically free.** An accounted 2.83 px translation reads 1.399 (1399×) with trajectory error exactly zero and no resolvable envelope change; a 10 % uniform gain error reads 0.629.

## Why the proposals were withdrawn

| Originally proposed | Status |
|:---|:---|
| `std_delta_b_a2 ≤ 2 Å²` blocking | **withdrawn** — the prespecified Layer-2 dose arm, missing from the first analysis, is the arm it fails on. At double dose the true envelope loss is +19.2 to +25.3 Å² and the estimate reads −1.05 to +0.0004 Å²; the instrument rejects its own Gaussian fit in all 90 dose cells |
| `std_shift_px ≤ 0.05 px` blocking | **withdrawn** — its positive class was the *accounted* translation, which the frozen `FAULT_CLASS` calls benign; the limit was being trained to reject the benign case |
| `std_scale_dev` | **withdrawn** — blind to the frame-dependent error its own clause names (1.7e-4 at a 50 % frame ramp) |
| exact equality, same-platform CPU regression | **retained** — needs no calibration |

**Superseded from the first version of this description:** "Δ*B* ≤ 2 Å² and `std_shift_px` ≤ 0.05 px as blocking"; "270/270 detection, 0/90 false alarms" (leaked split, and overstated within it — two checks gave 253/270); "Four results" (now five); "1129 cells / Layer 2 630" (now 1279 / 780); "29 load-bearing numbers" (now 69).

## Review history

Four findings ([r4119255250](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255250), [53](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255253), [56](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255256), [61](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255261)) — all confirmed, all fixed, each guarded by a contract control. Then two independent reviews of the corrected artifact found 8 and 18 further defects; all were reproduced before acting. The most serious was my own: I had suppressed the one harm boundary where the result is positive. See [comment 1](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#issuecomment-5865415698) and [comment 2](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#issuecomment-5865472130).

## Known limits, stated not buried

- **The hold-out is no longer blind.** §8 and §9 were published before §10 was written; re-partitioning cannot restore blindness. The twelve reserved movies are untouched.
- **Detection has never been tested on an unseen micrograph.** Hold-out movies carry zero unacceptable-tier cells.
- **301 cells** are tiered from an envelope fit the instrument rejected, because Layers 1 and 3 have no noiseless object.
- **Layer 1 can never enter the joint hold-out** by construction.
- Four faults are unreachable through the CLI and rest on models, not the pipeline. Full list in §11.

## Checks

```sh
python3 tools/calibration/test_calibration.py        # 11 instrument controls
python3 tools/calibration/test_contracts.py          # 7 data/analysis contract controls
python3 tools/calibration/verify_report_numbers.py   # 69 report numbers, exits non-zero on drift
python3 tools/calibration/reproduce_review_findings.py --prerev <tree at 059d8dd3>
```

CPU-only on `cpu64`, `taskset -c 32-63` (= NUMA node 1); payload heap node-local; colleagues' unpinned `ctffind` untouched. **No GPU run in either round.** Same binary `d88a6c02…` and input hashes throughout.

## Recommended next step

Run `tools/calibration/decompose_pair.py` on the native CUDA outputs already on disk — no GPU, seconds per movie. Check `std_envelope_used` before applying the read-out rule; a rejected fit reading near zero is exactly what a large dose-type fault produces.

Refs #60, #58, #59, #61, #66

🤖 Generated with [Claude Code](https://claude.com/claude-code)