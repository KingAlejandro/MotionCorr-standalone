# Issue 77 source review and correction

Baseline `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26`; final code `4934db76583fbfa62e5da6bda0c1bfd18ea79207`.

The initial independent source reviews of characterization candidate `5b9e5a4` missed a blocking regression: alignment CUDA/cuFFT/cache failures returned false while global callers ignore that convergence boolean. Root found this before publication. The earlier source approval is withdrawn; successful-path equality did not prove error behavior.

The narrow final correction logs and throws RelionError on real allocation, plan, transform, transfer, event and launch errors. Ordinary completed alignment still returns its convergence boolean. Independent read-only re-review verified REPORT_ERROR throws, cache construction cleans temporary resources, and scoped guards run during unwinding. No remaining blocker was found in this narrow correction. Cleanup is best effort under a damaged CUDA context, not a universal resource-release guarantee.

The full candidate retains the resident global/local/reconstruction pipeline, original dose divisions/powf/expf/sqrtf, interpolation, peak reduction and ascending frame accumulation. Reused scratch/FFT tiles remain ordered on the default stream. Required host-shift downloads and completion boundaries remain. Cache keys cover geometry/device/frame count/B; metadata replacement remains transactional. No new dependency/vendor code/compiler flag/license/default or unrelated I/O implementation is introduced.

Final runtime evidence in RESULTS.md establishes complete same-backend real-data identity, repeatability, native resident-stage witnesses and two actual alignment allocation/plan fault controls. It does not establish all failure paths, scientific equivalence or a stable full-run speedup. The original requirement for a demonstrated full-application gain beyond variability remains unsatisfied: this stays a draft characterization/optimization PR, not an unconditional merge certificate.

Scoped license/provenance delta passes; this does not certify all pre-existing dependencies. No review agent ran tests; dedicated validation was separate.
