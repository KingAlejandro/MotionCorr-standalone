# Tests and compiled controls

All results MEASURED on 4GPUs GPU0 (`GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`),
Release build of each fix commit, `ctest` under the gpu0 correctness lock.

| fix | test | compiled negative controls | result |
|---|---|---|---|
| 1 hot-pixel merge | DefectNeighbours (merge vs full scan, 200 random masks, refusal cases); DefectParser (cached index list through hit, failure, recovery, geometry change, rewrite) | DefectMergeMutant_{append_only, no_order_check, swap_xy} must fail DefectNeighbours; removing the runner x/y swap fails DefectParser with 3 checks | ctest 75/75; all mutants detected |
| 2 geometry retention | CudaGeometryRetention; CudaFaultMatrix (535 trials incl. warm second movie); CudaDeviceGainPool; CudaDoseSessionPlan | CudaGeometryRetentionMutant_{no_take, return_failed, keep_taken_alias} | ctest 79/79; all mutants detected; `run_gain_cache_host.py` controls pass |
