# Run recipes and archive provenance

These commands record the run settings with machine-specific paths replaced by variables. Use the documented source variants, pinned inputs and capture products from the experiment archive. The source overlays and raw captures are archive prerequisites. This documentation PR publishes the reduced evidence and the [execution artifact hashes](data/execution_sha256.json).

## SCARF synthetic movies

Use the frozen fixture hashes in [the SCARF evidence](data/scarf_compatibility.json), and run from the staged fixture directory. The native and live-hybrid 40-frame producers used this command on eight allocated CPU threads.

```sh
"$binary" --i input.star --o "$output" --use_own --j 8 \
  --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 \
  --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 \
  --skip_logfile --ingest float
```

- The native CUDA arm appends `--gpu 0 --ingest_witness "$ingest_witness"` on the Slurm-assigned A100. The initial trace uses `MC_BOUNDARY_DIR` for the saved windows, spectra and maps and `MC_EXPERIMENT_CCF_DC_ARM=none`.
- The live-hybrid arm uses the same CUDA arguments and adds `MC_DIAG_CCF_FFTW_SCOPE=global` or `MC_DIAG_CCF_FFTW_SCOPE=both`. It records `MC_DIAG_MODEL_OUT`. The native control leaves the hybrid scope unset. The live producer and comparator are `run_movies.py` and `compare.py`.
- The SCARF B2 variant appends `--experimental_local_b2`. The compound variant additionally appends `--experimental_local_full_width_weight`. Both run on CPU and use `MC_TRACE_OBSERVATIONS` and `MC_DIAG_MODEL_OUT` in the scratch build. The `run_fit.sbatch` driver invokes `analyze_fit.py` using the saved observations and the archived C++ fit replayer.

The follow-up replay builds the `mc_boundary_replay` target in Release mode with CUDA enabled, architecture 80 and `BUILD_TESTING=OFF`. The common inputs are the retained native trace results. The frame-35 output provides a byte-identity control for the all-frame driver.

```sh
python3 cross_inverse.py --retained "$native_results" \
  --binary "$replay_binary" --output "$frame35_results"
python3 all_frames.py --retained "$native_results" \
  --frame35 "$frame35_results" --binary "$replay_binary" --output "$all_frames_results"
```

## Real movies on 4GPUs

The ordered inputs and movie, STAR and gain hashes are in [the real-movie evidence](data/real_movies.json). Use the recorded movie-specific dose and frame count. For the EMPIAR-10216 crossover these were dose 1.0 and 59 frames.

```sh
"$binary" --i movies.star --o "$output" --use_own --j 8 \
  --dose_weighting --dose_per_frame "$dose" --bfactor 150 \
  --expected_frames "$frames" --seed 1 --patch_x 5 --patch_y 5 \
  --ingest float --save_noDW --skip_logfile
```

The tutorial runs append `--gainref Movies/gain.mrc`. The CUDA arms append `--gpu 0 --ingest_witness "$ingest_witness"` on the one GPU made visible to the process. The hybrid uses `MC_DIAG_CCF_FFTW_SCOPE=both`. The archived `build.sh` and `run.sh` were each launched under `taskset -c 80-87`. The runners record eight OpenMP threads, single-threaded OpenBLAS, free scratch, CPU admission, device occupancy and a GPU-context witness.

- **Common field.** Build the live-hybrid variant plus `fixed-field-overlay.patch`. Build the frozen RC0 CPU reference separately. `run.py` runs the released CPU, diagnostic CPU, native CUDA and hybrid first. It writes an `MC_FIELD1` record from the ordinary diagnostic CPU's runtime JSON with the per-frame global shifts and local polynomial coefficients. The two fixed-field arms read the same file via `MC_DIAG_FIXED_FIELD` and save preprocessing samples via `MC_BOUNDARY_DIR`. `compare.py` reduces their outputs and `patch_replay.py` refits saved observations offline.
- **Identical patch pixels.** Add the scratch local replay overlay to the preceding diagnostic source. The runners set `MC_PATCH_CAPTURE`, `MC_PATCH_TRACE`, `MC_DIAG_MODEL_OUT` and `MC_TRACE_OBSERVATIONS`. Run the CPU and hybrid on their own inputs first, then cross the crop directories via `MC_PATCH_INPUT`. `analyze.py` checks the recaptured patch hashes, runtime fields, image products and iteration traces. Finally, `python3 replay_ccf.py` replays the two selected frames from each trace using the venue's float FFTW library.

## Noisy known-motion replay

The macOS capture uses `0b0ab0d0` with the extended local CCF capture build. Run from the retained five-frame fixture directory.

```sh
"$binary" --i noisy.star --o "$output" --use_own --j 2 \
  --patch_x 3 --patch_y 3 --group_frames 1 --bin_factor 1 --seed 1 \
  --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 5 \
  --skip_logfile --max_iter 5 --experimental_local_b2 \
  --experimental_local_full_width_weight
```

The capture-off and capture-on arms both set `MC_EXPERIMENT_CCF_DC_ARM=none` and record `MC_DIAG_MODEL_OUT`. The capture-on arm adds `MC_DIAG_LOCAL_CCF_DIR`. The offline driver `replay_candidates.py` takes the captured maps, recorded runtime JSON, original `noisy_field.npy` and the C++ replayer for the same B2 fitter. The captured fit and exact-shift control are in [the known-motion evidence](data/known_motion.json).
