# docs reference classification at e77a51a2 (identical scoped tree at bbf24607)

Summary: {"ACTIVE_BUILD_INPUT": 1, "ACTIVE_EVIDENCE_FIXTURE": 1, "ACTIVE_EXEC_READ": 7, "ACTIVE_FILE_READ": 4, "ACTIVE_FILE_READ_USER_SOURCE_TREE": 9, "COMMENT_OR_LINK": 60, "FALSE_POSITIVE": 3, "GENERATED_PATH": 1, "STRING_LITERAL": 4}

| file:line | class | referenced path(s) [main/e77/bbf] | scenario |
|---|---|---|---|
| CMakeLists.txt:440 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| CMakeLists.txt:762 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| CMakeLists.txt:772 | COMMENT_OR_LINK | `docs/perf_vram_tier1/report.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| CMakeLists.txt:1179 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| CMakeLists.txt:1224 | ACTIVE_BUILD_INPUT | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | add_test(CudaU16FailurePaths) argv[4]; only if -DMOTIONCORR_U16_TEST_MOVIE set (CUDA, hardware label, opt-in); script receives comparator path |
| src/acc/cuda/cuda_alignpatch.cu:739 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_alignpatch.h:80 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_movie_session.cu:1634 | COMMENT_OR_LINK | `docs/nvcomp_ingest_pipeline.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_movie_session.cu:1836 | COMMENT_OR_LINK | `docs/nvcomp_ingest_pipeline.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_movie_session.cu:2136 | COMMENT_OR_LINK | `docs/fft_dw_device_overheads.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_movie_session.cu:2426 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_movie_session.h:280 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_movie_session.h:292 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_reader_pool.h:22 | COMMENT_OR_LINK | `docs/nvcomp_ingest_pipeline.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/acc/cuda/cuda_realspace_dw.cu:429 | COMMENT_OR_LINK | `docs/host_device_overheads.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/apps/run_motioncorr.cpp:29 | COMMENT_OR_LINK | `docs/issue10_allocator_control/` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/apps/run_motioncorr.cpp:48 | COMMENT_OR_LINK | `docs/host_buffer_reuse.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/error.h:173 | FALSE_POSITIVE | - | URL docs.amd.com inside an error-message string; not a repository path |
| src/float16.h:53 | FALSE_POSITIVE | - | URL `gcc.gnu.org/onlinedocs/`; not a repository path |
| src/motioncorr_runner.cpp:127 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/motioncorr_runner.cpp:143 | STRING_LITERAL | `docs/stage_profile.md` [Y/Y/Y] | CLI --profile help text names docs/stage_profile.md; no read |
| src/motioncorr_runner.cpp:2065 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/motioncorr_runner.cpp:3447 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/motioncorr_runner.cpp:3574 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/multidim_array.h:2712 | COMMENT_OR_LINK | `docs/output_timing_20260930/mutants.txt` [N/N/N] | comment/docstring/markdown link; not executed |
| src/stage_profile.cpp:2 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| src/stage_profile.h:2 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/cuda_fault_matrix.cpp:23 | COMMENT_OR_LINK | `docs/issue69/gpu_plan.md` [N/N/N] | comment/docstring/markdown link; not executed |
| tests/cuda_fault_matrix.cpp:379 | COMMENT_OR_LINK | `docs/issue69/gpu_plan.md` [N/N/N] | comment/docstring/markdown link; not executed |
| tests/cuda_nvcomp_acceptance_shim.cpp:7 | COMMENT_OR_LINK | `docs/nvcomp_ingest_pipeline.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/cuda_patch_batch.cpp:1 | COMMENT_OR_LINK | `docs/batched_patch_alignment.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/cuda_patch_batch.cpp:9 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/cuda_patch_fft_batch_probe.cpp:3 | COMMENT_OR_LINK | `docs/perf_vram_tier1/report.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/cuda_vram_alias.cpp:1 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/run_dw_alias_controls.py:2 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/run_enumeration_boundary_control.py:27 | ACTIVE_EXEC_READ | `docs/issue69/evidence/ownership-20260929/compare-native.py` [Y/Y/Y] | default --comparator, executed via subprocess (:112); NOT registered in CMake/CI (manual hardware control) |
| tests/run_nvcomp_acceptance_controls.py:8 | COMMENT_OR_LINK | `docs/nvcomp_ingest_pipeline.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/run_nvcomp_reconstruction_controls.py:167 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/run_preprocessing_failure_controls.py:69 | ACTIVE_EXEC_READ | `docs/issue69/evidence/ownership-20260929/compare-native.py` [Y/Y/Y] | only with --float-host (importlib exec of compare-native.py); --float-host is not registered in CMake |
| tests/run_preprocessing_failure_controls.py:70 | ACTIVE_EXEC_READ | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | default branch: importlib exec of compare_output_trees.py; ctest CudaPreprocessingFailurePaths (CUDA build, hardware label) |
| tests/run_preprocessing_failure_controls.py:173 | COMMENT_OR_LINK | `docs/vram_live_ranges.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/run_resident_retry_controls.py:15 | COMMENT_OR_LINK | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/run_stale_cuda_error_controls.py:25 | COMMENT_OR_LINK | `docs/issue85_laneC/compare_output_trees.validate_mrc` [N/N/N] | comment/docstring/markdown link; not executed |
| tests/run_stale_cuda_error_controls.py:54 | ACTIVE_EXEC_READ | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | importlib exec at import time; ctest CudaStaleErrorAfterOom (CUDA build, hardware label) |
| tests/run_tiff_identity_later_chunk_controls.py:19 | ACTIVE_EXEC_READ | `docs/rc0/qf/tools` [Y/Y/Y] | sys.path insert + import compact_compare_output_trees; ctest CudaNvcompTiffIdentityLaterChunk (CUDA build, hardware label) |
| tests/test_compare_output_trees.py:16 | ACTIVE_EXEC_READ | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | importlib exec of comparator under test; ctest (CPU build, run by CI `ctest`) OutputTreeComparator |
| tests/test_host_buffer_reuse.py:2 | COMMENT_OR_LINK | `docs/host_buffer_reuse.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/test_multi_gpu_scheduling.py:12 | COMMENT_OR_LINK | `docs/multi_gpu/negative_controls.py` [N/N/N] | comment/docstring/markdown link; not executed |
| tests/test_multi_gpu_scheduling.py:16 | COMMENT_OR_LINK | `docs/multi_gpu/gpu_evidence/a0_device_list_witness.log` [N/N/N] | comment/docstring/markdown link; not executed |
| tests/test_multi_gpu_scheduling.py:22 | COMMENT_OR_LINK | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/test_native_movie_staging.cpp:222 | STRING_LITERAL | `docs/issue95_staging` [N/N/N] | printf failure message names docs/issue95_staging; no read |
| tests/test_runner_numerics.cpp:223 | COMMENT_OR_LINK | `docs/output_timing_20260930/mutants.txt` [N/N/N] | comment/docstring/markdown link; not executed |
| tests/test_stage_profile.py:2 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tests/test_sticky_cuda_process_lifecycle.py:245 | ACTIVE_EVIDENCE_FIXTURE | `docs/issue213/evidence` [N/Y/Y] | reads docs/issue213/evidence/control-{cuda,nvcomp}-final/{single,multi}.txt as retained console records; ctest (CPU build, run by CI `ctest`) StickyCudaProcessLifecycle (UNIX) |
| tools/check_known_motion.py:56 | COMMENT_OR_LINK | `docs/known_motion_validation.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/compare_motioncorr.py:283 | COMMENT_OR_LINK | `docs/gate_contract.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/compare_motioncorr.py:601 | COMMENT_OR_LINK | `docs/gate_contract.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/gate_representations.py:4 | COMMENT_OR_LINK | `docs/gate_contract.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/gate_representations.py:18 | ACTIVE_FILE_READ | `docs/cuda_24_movies_gate2_rerun.json` [Y/Y/Y] | reads docs/cuda_24_movies_gate2_rerun.json and docs/spa_24_movies_manifest.json; table regenerator, not registered in CMake/CI |
| tools/gate_representations.py:19 | ACTIVE_FILE_READ | `docs/spa_24_movies_manifest.json` [Y/Y/Y] | reads docs/cuda_24_movies_gate2_rerun.json and docs/spa_24_movies_manifest.json; table regenerator, not registered in CMake/CI |
| tools/multi_gpu/merge_workers.py:359 | STRING_LITERAL | `docs/multi_gpu/AGGREGATE_STAGING.md` [Y/Y/Y] | error-message text names docs/multi_gpu/AGGREGATE_STAGING.md; no read |
| tools/multi_gpu/run_multi_gpu.py:702 | COMMENT_OR_LINK | `docs/multi_gpu/scaling/README.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/nsys_analysis/README.md:3 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/nsys_analysis/selftest.py:150 | ACTIVE_FILE_READ | `docs/profiling_20261001/data24/arms24.json` [Y/Y/Y] | reads docs/profiling_20261001/data24/arms24.json (fails the check if absent); selftest not registered in CMake/CI |
| tools/nsys_analysis/selftest.py:207 | ACTIVE_FILE_READ | `docs/profiling_20261001/data24/arms24.json` [Y/Y/Y] | reads docs/profiling_20261001/data24/arms24.json (fails the check if absent); selftest not registered in CMake/CI |
| tools/profiling/lib/__init__.py:1 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/profiling/lib/identity.py:1 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/profiling/lib/metrics.py:1 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/profiling/lib/provenance.py:1 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/profiling/lib/report.py:22 | STRING_LITERAL | `docs/stage_profile.md` [Y/Y/Y] | report label constant names docs/stage_profile.md; no read |
| tools/profiling/lib/stats.py:1 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/profiling/mcprof.py:2 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/profiling/tests/fixtures/nsys_2024_6_schema.sql:216 | FALSE_POSITIVE | - | SQL column comment "See docs for format"; not a repository path |
| tools/profiling/tests/test_discards.py:1 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/run_cuda_reconstruction_validation.py:77 | GENERATED_PATH | `docs/cuda_reconstruction_validation_summary.json` [N/N/N] | default value of --out-json (output written under docs/, never read) |
| tools/single_gpu/refresh_profile.sh:23 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y]; `docs/issue85_laneC/tutorial_24_movie_manifest.json` [Y/Y/Y] | reads $D/baseline-src/docs/issue85_laneC/... (a baseline source copy under the caller-chosen $D); not registered |
| tools/single_gpu/run_dose_options.py:6 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | loads docs/issue85_laneC/{compare_output_trees.py,tutorial_24_movie_manifest.json} from required --source tree (a checkout supplied by the caller); not registered |
| tools/single_gpu/run_dose_options.py:7 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/tutorial_24_movie_manifest.json` [Y/Y/Y] | loads docs/issue85_laneC/{compare_output_trees.py,tutorial_24_movie_manifest.json} from required --source tree (a checkout supplied by the caller); not registered |
| tools/single_gpu/run_dose_pairs.py:50 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/tutorial_24_movie_manifest.json` [Y/Y/Y] | docs/issue85_laneC/... under --source (:50 only when --manifest absent); not registered |
| tools/single_gpu/run_dose_pairs.py:135 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | docs/issue85_laneC/... under --source (:50 only when --manifest absent); not registered |
| tools/single_gpu/run_option_matrix.py:6 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | loads docs/issue85_laneC/{compare_output_trees.py,tutorial_24_movie_manifest.json} from required --source tree (a checkout supplied by the caller); not registered |
| tools/single_gpu/run_option_matrix.py:7 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/tutorial_24_movie_manifest.json` [Y/Y/Y] | loads docs/issue85_laneC/{compare_output_trees.py,tutorial_24_movie_manifest.json} from required --source tree (a checkout supplied by the caller); not registered |
| tools/single_gpu/run_pairs.py:25 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/tutorial_24_movie_manifest.json` [Y/Y/Y] | docs/issue85_laneC/... under --source; not registered |
| tools/single_gpu/run_pairs.py:97 | ACTIVE_FILE_READ_USER_SOURCE_TREE | `docs/issue85_laneC/compare_output_trees.py` [Y/Y/Y] | docs/issue85_laneC/... under --source; not registered |
| tools/stage_profile.py:2 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/test_ci_fail_closed.py:249 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/test_ci_fail_closed.py:255 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/test_combined_eval.py:16 | ACTIVE_EXEC_READ | `docs/post_rc0/s1/synth_combined/eval_v2.py` [N/Y/Y] | subprocess runs docs/post_rc0/s1/synth_combined/eval_v2.py; CI step `python3 tools/test_combined_eval.py -v` (ci.yml:105); not in ctest |
| tools/validate_test_collection.py:61 | COMMENT_OR_LINK | `docs/stage_profile.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
| tools/validate_test_collection.py:71 | COMMENT_OR_LINK | `docs/profiling.md` [Y/Y/Y] | comment/docstring/markdown link; not executed |
