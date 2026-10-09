# Recorded standalone native campaign

These are the retained acceptance sources and invocation details for the
6 October 2026 result. They are not installed or registered with MotionCorr.
The [manifest](campaign_manifest.json) records the actual build command, fixture
command, all 28 probe argument vectors, input/helper hashes, SDK/Python versions
and the final explicit-unit-depth caller. Absolute paths identify the historical
run; use a fresh workspace for reproduction, rather than reusing its outputs.

The helpers are byte-for-byte copies of the executed campaign helpers. The
process observer checks PID births and observed descendants. It cannot prove
ownership of unobserved detached descendants or adversarial processes. No SDK
files are included. A private, independently licensed nvTIFF installation is
required; optional compilation does not resolve production license compatibility.

## Build and generated fixtures

Run from a checkout containing this directory. `NVTIFF_ROOT` must identify the
separately installed 0.8.0.82 SDK with `include/nvtiff.h` and `lib/libnvtiff.so`.
The recorded wheel SHA256 is
`2d4a2ea3b749d78fe446df496235469a4cb71eb64deff907e74f02eaa4a70cdf`.
The historical environment used CUDA12.8, NumPy2.5.3, tifffile2026.9.20 and
imagecodecs2026.8.16; the fixture manifest records the versions actually loaded.

```sh
SOURCE=997b955c883300fc76ec43423ec0c533f7b685cf
OLD=a2888d2df1bb93a8c7f30b96219d12c32069f5cf
WORK=$(mktemp -d)
mkdir "$WORK/source" "$WORK/old-source" "$WORK/harness"
git archive "$SOURCE" | tar -xf - -C "$WORK/source"
git archive "$OLD" | tar -xf - -C "$WORK/old-source"
cp experiments/nvtiff/reproduce/*.py experiments/nvtiff/reproduce/faults.cpp "$WORK/harness/"
export LD_LIBRARY_PATH="$NVTIFF_ROOT/lib:/usr/local/cuda-12.8/lib64:${LD_LIBRARY_PATH:-}"
cmake -S "$WORK/source/experiments/nvtiff" -B "$WORK/build" \
  -DCMAKE_BUILD_TYPE=Release -DNVTIFF_ROOT="$NVTIFF_ROOT" \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.8
cmake --build "$WORK/build" --parallel 4
cmake -S "$WORK/old-source/experiments/nvtiff" -B "$WORK/old-build" \
  -DCMAKE_BUILD_TYPE=Release -DNVTIFF_ROOT="$NVTIFF_ROOT" \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.8
cmake --build "$WORK/old-build" --parallel 4
c++ -std=c++17 -shared -fPIC -I"$NVTIFF_ROOT/include" \
  -I/usr/local/cuda-12.8/include "$WORK/harness/faults.cpp" -ldl \
  -o "$WORK/build/faults.so"
python3 "$WORK/harness/generate_inputs.py" "$WORK/inputs"
```

The historical builds ran under `/tmp/motioncorr-build.lock`, with at most four
build workers and CPU96–103/memory bind1. Its SDK installation was private:
`python3 -m pip download --only-binary=:all: --no-deps nvidia-nvtiff-cu12==0.8.0.82`;
the wheel was checked against the hash above before extraction. No SDK download
or installation is implied by these repository helpers.

## Native invocations and every-sample comparator

Only run on an explicitly assigned, empty device with the matching CPU/NUMA
allocation. The retained caller intentionally pins the original GPU0 UUID and
CPU96–103; changing those constraints requires a separately reviewed campaign.

```sh
export CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
export OMP_NUM_THREADS=4
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader
numactl --membind=1 taskset -c 96-103 \
  flock -n /tmp/motioncorr-gpu0-correctness.lock \
  python3 "$WORK/harness/run_acceptance.py" \
  --binary "$WORK/build/motioncorr_nvtiff_probe" \
  --predecessor "$WORK/old-build/motioncorr_nvtiff_probe" \
  --fault-library "$WORK/build/faults.so" \
  --inputs "$WORK/inputs" --work "$WORK/native"
nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name --format=csv,noheader
```

`run_acceptance.py::call` is the actual command constructor; the manifest also
retains each expanded historical argument vector. Each ordinary case uses
compressed-input cap134217728 and device-output cap67108864 bytes, one image per
batch. Selected ranges use `--first 3 --count 5 --batch-frames 4`. The old binary
must refuse the supported absent-depth fixture; the repaired binary must decode.

`run_acceptance.py::grade` reads the entire dump, validates its four-int64 header
and exact extent, reads every TIFF page with tifffile/imagecodecs, flips the oracle
rows, then requires `numpy.array_equal` for every sample. It powers wrong row
order, within-row swaps preserving row sums, last-frame bit changes, missing
last frame, and U16 byte swaps. Range cases separately reject the wrong first
frame. No tolerance, frame sampling or sum-only comparison is used.

The interposer is compiled from `faults.cpp`. The expanded invocations use
`env LD_PRELOAD=<faults.so> MC_NVTIFF_FAULT=<mode> <probe> ...`; modes are
`healthy`, `decode-refusal`, `decode-execution`, `completion`, and `destroy`.
The caller requires the reached API signature, nonzero failure, no sample
publication or leaked sibling temporary, and no further decode dispatch after
immediate/completion failure. These are injected API statuses on healthy input,
not malformed compressed-stream or genuinely poisoned-context tests.

The attempted `u8-explicit-depth1` fixture actually has no raw ImageDepth tag:
tifffile ignored the reserved extratag. It remains a duplicate absent-depth case.
The separate unit-depth supplement used this exact writer:

```python
arr = np.arange(3 * 32 * 64, dtype=np.uint16).reshape(3, 32, 64)
with tifffile.TiffWriter(movie) as writer:
    for plane in arr:
        writer.write(plane[None, ...], volumetric=True, compression="lzw",
                     predictor=2, rowsperstrip=8, photometric="minisblack",
                     metadata=None)
```

It independently requires every raw tag32997 to be scalar LONG/count1/value1,
then invokes `<candidate> --movie <explicit-unit.tiff> --trusted-input --dump
<samples.bin> --batch-frames 2` and grades all6144 samples with the same `grade`.
The manifest includes the complete actual supplemental caller and its receipt,
including before/after identity and assigned-device release checks.

Content PASS is distinct from release PASS. The original top-level controller
required successful occupancy queries, empty assigned GPU, unchanged source,
inputs/binary/libraries/helpers, and successful process exits before recording
completion. New reproduction runs must retain those records too. Historical raw
logs remain preserved; this manifest makes invocation details accessible without
promoting the probe to a production decoder or making a speed/trust/scratch claim.
