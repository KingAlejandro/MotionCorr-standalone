# cpu1: CPU-only qualification plan (independent of the blocked GPU3 lane)

Purpose: advance the CPU rows of the C1 plan while GPU3 is unavailable (a foreign process holds all four GPUs), without weakening the original objective. GPU rows (T24 L attribution, datasets, CUDA known-motion, R12/R9, A1 #249 GPU route, CUDA census/image) stay **pending**, not skipped or passed.

Rows: T24 CPU G/L (C1 CPU vs the completed frozen-F CPU baselines, products IDENTICAL), K267 CPU (C1 vs same-host frozen-F CPU, exact field metrics; published cross-host values are information only),
K269 CPU census (100 movies, arm `none`, decoded sums vs the retained main-CPU sums, with a same-host F-cpu control on the 10 `dose1` movies to separate a regression from a host effect, and STAR-serialised field metrics),
K272 CPU image evaluation (existing SciPy venv, source/ROI/thresholds unchanged) plus the seed-0 controls. Tested source `e77a51a2`, CPU binary `build-cpu/motioncorr` (no CUDA linkage), tools packet `4facd76d` unchanged.
No GPU is used: no lease, no `nvidia-smi`, no `--gpu`, `CUDA_VISIBLE_DEVICES` exported empty; the chain script is checked for GPU helpers by `cpu1_prereq.py`. Lane: CPUs 8-9, `--j 2`.

Files: `chain-cpu1.sh` (frozen chain with allowed exit sets and stop rule), `cpu1_sums.py` (exact sum/field comparison and the K269 decision), `cpu1_extract_ref.sh` (extracts and sidecar-verifies the retained sums),
`cpu1_prereq.py` (read-only prerequisites), `test_cpu1_sums.py` (host controls). Decision rule for K269: PASS only if C1 equals the retained sums on all 100 movies and the same-host F control; C1 != retained while C1 == same-host F is INCONCLUSIVE (host effect not excluded); C1 != same-host F is FAIL.
