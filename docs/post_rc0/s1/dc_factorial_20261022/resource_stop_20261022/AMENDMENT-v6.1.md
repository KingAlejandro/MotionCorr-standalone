# Additive v6.1 amendment, frozen before implementation and tests

Frozen 23 October 2026 for R5-1/R5-2 in [review-r5/REVIEW.md](review-r5/REVIEW.md).
Reviewed v6 at `1fe458ecc33e9eb2e89f8617d6394854e7a5b6f2` and tested tools at
`f5946de124de13379766331bf4f7d2e6491d0bc2` remain byte-exact, including all contracts and evidence.
CONTRACT-v5/v6 continue to apply, with these additive implementation/control corrections only.

- New paths: gpu_worker_v6_1.py, test_gpu_worker_v6_1.py, run_v6_1_controls.py,
  test_v6_1_static.py and v6_1_mutants.json. RUN schema `dc262-run/v6.1`, worker `gpu_worker_v6_1`.
  Reuse frozen test_run_v6_admission.py via its existing --runner argument; no admission broadening.
- R5-1: K22's fake reaped Root exposes `returncode=0`. Run exact K22 data-only; require the
  worker's own group excluded and a verified other group included. Add an own-group-exclusion
  mutant discriminator. Compiling fixtures or running K28/K30 alone is insufficient.
- R5-2: errors arriving after cleanup entry, including inside group verification, take the existing
  identity-checked original-session fallback. Preserve uncertainty errors and lease-hold classification.
  Root birth/parent/PGID/SID/unreaped checks and worker-group exclusion stay unchanged. No guessing
  escaped/foreign descendants. Healthy-versus-late-error synthetic K36 and one single-site mutant
  removing the new fallback discriminate this branch; early-error and refresh-exception controls stay.
- Version references, schema/labels, frozen input hashes and runner control-name matching must identify
  v6_1. Only new-version control names are added to exclusion matching. Owner PID/birth/ancestor and
  exact Claude resume-token requirements remain unchanged; no old identity is used or spoofed.
- Verification here is data-only: mocked Popen/process tables/signals and exact K22. No live worker,
  mock job, process suite, SMI, SSH, Linux, build/native or GPU execution. The process suite remains
  UNRUN/unspent. New failures freeze a separate iteration before repair. Native/process qualification
  is UNRUN, independent R6 is required, and provider-neutral admission is a separate parent decision.
- No production source, campaign.py, process_ownership.py, default, gate, tolerance, policy or dependency
  change. GPU PAUSED; namespace consumer unimplemented/BLOCKED; historical outcomes remain unchanged.
