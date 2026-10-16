# Device EER renderer: standalone feasibility experiment (#193 option 2)

Experiment only. Nothing here is built by the top-level `CMakeLists.txt`, and `src/` is not modified.
The result and the GO / NO-GO decision are in `RESULT.md`.

| file | role |
|---|---|
| `eer_device.cu`, `eer_device.h` | decode kernel: one thread per fraction, scatter into a uint16 frame per group |
| `eer_exp.cpp` | driver: LibTIFF strip index, parallel `pread` into pinned memory, H2D, decode, host comparison, timing |
| `eer_fixture.cpp`, `.h` | BigTIFF writer and 65000/65001/65002 stream encoders for synthetic and mutated movies |
| `CMakeLists.txt`, `build.sh` | separate nvcc/CMake build; compiles `src/renderEER.cpp` from the same tree as the host reference |
| `run_lane.sh`, `lane_precheck.py` | 4GPUs lane wrapper (GPU0 by UUID, CPUs 96-103, locks) and the foreign-use check |
| `run_matrix.sh`, `run_sweeps.sh`, `run_malformed.sh`, `classify_malformed.py` | the measurement and malformed-input campaigns |

Build: `experiments/eer_device/build.sh <build-dir> [cpu-list]` (CUDA 12, LibTIFF, FFTW3, libpng, libjpeg; Release is forced).

```
eer_device_exp compare --eer F --grouping G --upsampling U [--repeats 7] [--read_threads 8] [--stage pinned|ring]
eer_device_exp dev-frames  --eer F --upsampling U      # per-fraction device verdicts (grouping 1)
eer_device_exp host-frames --eer F --upsampling U --first a --last b   # per-fraction EERRenderer verdicts
eer_device_exp fixtures --src <65001 .eer> --out DIR   # mutated and synthetic movies
```

`compare` first checks every pixel of every group against `EERRenderer::renderFrames<unsigned short>` (and the per-group
electron counts), then times the device path and the host render, `--repeats` times after one warm-up run.
