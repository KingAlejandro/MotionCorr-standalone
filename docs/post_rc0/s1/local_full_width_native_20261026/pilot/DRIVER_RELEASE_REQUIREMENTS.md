# Driver release requirements (HELD; no driver, no native admission exists)

Written after the independent R3 review (`REPORT.md`, sha256 `36bd2d44...bf341d`). This file is new and outside the immutable v3/v4
files; no code, hash anchor or test was changed to write it. It records a caller contract and a final-release checklist. It is not a
fix and not a PASS claim for any flow it forbids.

## Supported v4 flow (R3 L1: documented caller contract)
1. For each of the 8 cases, run `pre_ON_gate` on the finished OFF run **before** that case's ON producer.
2. After all ON producers have finished, call `decide_pilot` **once**, in a fresh dedicated final decision directory that already
   holds the pre-ON records from step 1 and nothing else.
3. Do **not** call `admit_pair` per case and then `decide_pilot` in the same decision directory. For a global-only case,
   `admit_pair` leaves `pair/<case>/compare_products.json`; `decide_pilot` calls `admit_pair` again, the pinned-comparator wrapper
   refuses to overwrite retained output, and the run stops with `GLOBAL_ONLY` (STOP.json is first-write-wins, so the misleading code is
   what is retained). R3 probe Q6 shows exactly this (`REJECTED:GLOBAL_ONLY ... DECISION_DIR: retained comparator output already
   exists`); the original failure is retained unchanged in the R3 packet (`results/PROBES_R3_run1.json`, `logs/probes-run1.log`). A fresh
   decision directory does not help, because it lacks the pre-ON records (`PRE_ON`).
4. A standalone diagnostic `admit_pair` must use its own unique decision directory, never reused by the final decision.
5. A per-case stop (PLAN.md: stop the affected execution) is taken from `pre_ON_gate` before ON; it is not taken by running
   `admit_pair` early.

## Mandatory final-release checklist (R3 L2, L3, L4; none is fixed now)
- **L2: re-derive, do not trust a handwritten record.** At release, repeat the cheap OFF identity checks against the anchored baseline
  pins: OFF `runtime.json` and `output/<case>.star` byte equality (plus the baseline pin inventory) when the pair is admitted, rather than
  relying on the integrity of `pre_on.json` alone. R3 probe Q2: a self-consistent handwritten record bypasses the OFF_RAW check.
- **L3: OFF manipulation before ON.** Run the pinned `manipulation` (and the DC/coupled coverage checks) on the OFF `stdout.log` inside
  the pre-ON step. v4 checks them only at pair admission, after the ON producer has run (R3 probe Q3).
- **L4: identity against the admission.** Compare the actual binary path and sha256 with the frozen `candidate_binary`, and the source
  identity with the pinned source archive and commit. v4 records these fields but does not compare them (R3 probe Q4).
- The v3 `on_launch_permitted` helper takes caller-typed strings and is forbidden for any future driver. Use the v4 entries only.
- **Re-anchoring.** `pair_decision_v4.py` anchors the HELD v3 admission by hash. A final admission needs a re-issued, re-anchored
  release module with the L2-L4 changes and a delta review. Neither exists yet.

## Why the campaign stays HELD
The final Linux source archive, build, binary, tools, the 33 fixture bytes, the 8x19 retained baseline bytes at the venue, venue identity
and lease/resource admission are all null or absent, and trusted SSH access is unavailable (parent probes: both strict direct probes timed
out with exit 255, gateway not retried). The real admission cannot pass `pre_ON_gate`. Scientific design is unchanged: 8 cases, at most 16
producers, P1 (affine, pedestal, zero, integer, fractional keep PASS on runtime and STAR) and P2 (noisy ON strictly lower rms/p95/max on both),
raw FAIL stays FAIL, flat/repeated UNIDENTIFIABLE. No full100, adoption, merge or default change follows.
