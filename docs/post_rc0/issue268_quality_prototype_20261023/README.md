# #268 quality-report prototype — current state

Experimental, default-OFF observation prototype for the maintainer-selected M4
draft "Report quality; preserve publication". Not M4 adoption, not an approved
schema, not on C1 or `main`. Design: `DESIGN.md`. Frozen controls: `PROTOCOL.md`
(amendments A1/A2 recorded before the remote run).

Branch `experiment/268-quality-report-20261023`, base C1 docs head `bbf24607`
(production source = `e77a51a2`). Design/protocol commit `5f2ca4b8`;
tested implementation `c347f59f` (tree `9a11f683`).

## Result (CPU only, 4GPUs, tested source `c347f59f`)

| Row | Verdict | What it shows |
| --- | --- | --- |
| E1 default-off neutrality | PASS | B1 (option OFF) and B2 without flag: products identical to C1 B0; no quality files |
| E2 report-on | PASS | products identical to B0; six sidecars agree with each solver's logged iterations/final RMSD and patch outcomes; summary counts consistent |
| E3 forced `--max_iter 1` (affine) | PASS | global `iteration_limit`, 1 iteration; 4/9 patches converged, 5 dropped, model retained |
| E4 product write failure | PASS | exits equal (1/1); integer `failed`/`product_write_failed`, zero `published`; joint `withheld_movie_failures`; 1×1 → `not_requested` |
| E5 sidecar write failure | PASS | products/exit unchanged; flat sidecar absent; summary records the failure; evidence incomplete |
| E6 summary write failure | PASS | products/exit unchanged; six sidecars; stderr warning; no summary |
| E7 resume | PASS | joint STAR and products equal to B0 resume; `sidecar_missing` ×2, `sidecar_stale`, `resumed_sidecar` ×2, `this_run` (flat) |
| E8 too-few fallback (integer, `--max_iter 1`) | PASS | 0/9 patches converged → `global_only` / `too_few_converged_observations`, observations 0 |
| N1–N5 checker negative controls | PASS | each tampered copy is rejected |

Global states with the default five iterations (P4): zero, affine, flat
`converged`; integer, fractional, noisy `iteration_limit` — matching the #273
CPU prediction. `flat` converges with final incremental RMSD 0 and is reported
`motion_identifiability: not_assessed`, as required. All local models were
retained at default settings on Linux (9/9 patches each).

Platform difference (development only, not evidence): the local macOS/arm64
dev runs gave integer 8/9 and noisy 7/9 converged patches in P4 and 5/9 in P6;
the reports matched their own solver logs there too.

## Identities

- Binaries (GCC 13, `-O3 -DNDEBUG`, CPU): B0 `4ffbba06…eb80c` (C1 base),
  B1 `64069712…77be` (OFF), B2 `3693e2e9…065a` (ON), B3 CUDA+ON compile-only
  `a0708efb…6a1d` (never executed). Full hashes: `evidence-c347f59f-4gpus/receipts/binaries.txt`.
- Fixtures: `generate_motion_diagnostics.py` output, byte-identical to
  `test-data/motion_diagnostics_v2/GENERATION_RECORD.json` (checked by the harness).
- Commands, argv, exits and per-run stdout/stderr: `evidence-c347f59f-4gpus/campaign/P*/run.json`;
  results: `campaign/results.json`; every remote campaign file hash:
  `remote_campaign_files.sha256`. Driver and bundle hashes match the launch receipt.
- Resources: driver PID 3324419, CPU lease `/tmp/motioncorr-q268-cpu14-15.lock`,
  campaign processes `taskset -c 14`, builds `-j2` on 14–15 under the nonblocking
  shared build lock; guard 3315461/3315463 absent and lane locks unheld at admission;
  scratch `/mnt/clathrin/alex-motioncorr-q268-quality-20261023-c347f59f` (533 MiB,
  retained). No GPU process, no `nvidia-smi`.
- Native process count: 14 campaign runs + 2 parse-only flag probes = 16.

## Limitations and unrun rows

- The two flag probes did not test what was intended: both exited 1 on the earlier
  "choose MotionCor2 or own implementation" check. OFF-build absence of the flag is
  witnessed only statically (`receipts/static_flag_witness.txt`: B0/B1 contain neither
  the flag string nor `mcquality::` symbols; B2/B3 do).
- CUDA: hooks are source-wired and compile (B3); every CUDA route (resident/streaming
  global, batched, per-patch device, same-input retry, device-preparation decline) is UNRUN.
- Distortion-guard and fit-RMSD fallback reasons: UNRUN (not produced by these inputs).
- Retained e10216-01, dataset/multi-GPU aggregation, tomography, `--aggregate_only`
  (rejected with the flag), timing: UNRUN / not implemented.
- `operator_error` and `not_run` global states are wired but not exercised.
- Identifiability and peak validity are always `not_assessed`; M5 is untouched.
- `configured_source_revision` is configure-time identity only.
- Convergence states are observations, not accuracy: #273's truth FAIL/UNIDENTIFIABLE
  totals are unchanged and are not re-evaluated here.
