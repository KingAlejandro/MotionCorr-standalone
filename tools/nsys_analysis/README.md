# nsys / ncu analysis scripts

Post-processing for Nsight Systems and Nsight Compute captures of MotionCorr. Most
scripts take their input and output paths as arguments and work against any profile.

Two are not generic, and the difference matters:

* `arms24_json.py` hardcodes the arm list, the capture filenames and the two
  unprofiled wall observations of the 2026-10-01 campaign. It takes only a root
  directory. Re-point it by editing `ARMS`.
* `patch_nvtx.py` matches literal source anchors. It carries one variant per known
  `motioncorr_runner.cpp` generation and refuses with a non-zero exit, naming what it
  tried, when none matches. It does not guess.

The remaining scripts are parameterised and campaign-independent.

Python 3, standard library only (`sqlite3`, `csv`, `json`). No numpy — `4GPUs` has none.

## Self-test

```sh
python3 tools/nsys_analysis/selftest.py
```

Runs every script's CLI against throwaway inputs: each one parses and imports what it
uses, `arms24_json.py` reaches its input handling and creates its output directory,
`patch_nvtx.py` patches each known `motioncorr_runner.cpp` generation and refuses an
unsupported, unbalanced, misordered or already-patched one with a non-zero exit
(including under `python -O`),
and `mkarms24.py` emits both charts without reinstating the cross-run idle label. No
capture, GPU or network needed. It fails on the first version of this directory.

Not registered with CTest: this is a documentation/tooling lane that touches no build
files. Whoever next edits `CMakeLists.txt` should register it.

## Capture

Permissions first. On a host with `kernel.perf_event_paranoid > 2`, nsys prints
`CPU IP/backtrace sampling not supported, disabling` and `--cudabacktrace` silently
dies with it; GPU counters give `ERR_NVGPUCTRPERM`. Run **the profiler** under `sudo`
rather than lowering the sysctl box-wide on a shared machine:

```sh
sudo -n env CUDA_VISIBLE_DEVICES=GPU-<uuid> OMP_NUM_THREADS=8 PATH=$PATH \
  nsys profile --output=p1 --force-overwrite=true --stats=false \
  --trace=cuda,nvtx --sample=process-tree --backtrace=fp --sampling-period=250000 \
  ./motioncorr --i movies.star --o out/ ... --gpu 0
sudo -n chown -R "$USER" .           # outputs come back root-owned
nsys export --type sqlite --force-overwrite true --output p1.sqlite p1.nsys-rep
```

Pick the trace set for the quantity you want. Instrumentation changes host-side
numbers substantially while leaving device-side counts invariant:

| want | use |
|---|---|
| kernel time, byte counts, grid/block | any profile — these are invariant |
| host stage walls | `--trace=nvtx,osrt` (no CUDA; CUPTI inflates CUDA-heavy stages) |
| GPU busy/idle, per-stage GPU attribution | `--trace=cuda,nvtx` |
| flame graph | `--trace=cuda,nvtx --sample=process-tree --backtrace=fp` |
| H2D rate | the lightest CUDA trace you have |

Build with `-g -fno-omit-frame-pointer` (host) and `-lineinfo` (device) so stacks
unwind and kernels attribute to source. Measured cost of those flags: none.

**Cross-check anything host-side against an unsampled profile.** In the campaign,
`cuModuleLoadData` read 732 ms under CPU sampling and 27-58 ms everywhere else.
`compare.py` exists to make that check cheap.

## NVTX stage annotation

`patch_nvtx.py` turns the existing `RCTIC`/`RCTOC` markers in
`src/motioncorr_runner.cpp` into NVTX ranges via one `#elif defined(MC_NVTX)` branch,
so the whole pipeline is annotated without scattering edits. NVTX3 is header-only and
is a no-op when no tool is attached. Run it against a **copy** of the tree and build
with `-DMC_NVTX`:

```sh
cp -a src-base src-nvtx
python3 patch_nvtx.py src-nvtx/src/motioncorr_runner.cpp
cmake -S src-nvtx -B build-nvtx -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
  -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -g -fno-omit-frame-pointer -DMC_NVTX" \
  -DCMAKE_CUDA_FLAGS_RELEASE="-O3 -DNDEBUG -lineinfo -Xcompiler=-fno-omit-frame-pointer"
```

The script checks its anchors with explicit `raise SystemExit`, not `assert`, so the
refusal survives `python -O` / `PYTHONOPTIMIZE`; an earlier version used bare asserts
and under `-O` would print a success line while inserting nothing. It reports which
signature variant it matched, so the profile records which source generation was
instrumented.

Known variants: 29 stage labels and a blocking `Iref.write` at `1d7e13f`; 38 labels
and an async `submitImageWrite` on current main. On current main the scope at that
position is therefore named **`submit output`**, because it measures the handoff to
the writer thread, not the write. The writer drain lies inside the process wall but
inside no NVTX range — it cannot be read off the stage table.

`nvtxRangePush`/`Pop` is a stack. Before writing, the script rejects missing,
misordered and mismatched literal stage markers using explicit checks. This is a
textual nesting check, not proof of every runtime branch or exception path. Verify
runtime ranges before trusting a new capture. The per-movie range uses an RAII
guard for early returns; existing RCTIC/RCTOC stages remain explicit push/pop pairs.

## Analysis

```sh
python3 analyze.py   p1.sqlite    # session, GPU busy/idle + gaps, kernels, transfers,
                                  # API census, syncs, NVTX stages, VRAM, threads, OSRT
python3 stages.py    p8.sqlite    # per-stage wall with GPU kernel/memcpy clipped in
python3 gaps2.py     p8.sqlite    # GPU-idle split at stage boundaries and charged per stage
python3 syncs.py     p8.sqlite    # streams/contexts, host-blocked vs GPU-working, sizes
python3 compare.py  'nsys/*.sqlite'   # cross-profile invariants — run this first
python3 xfer.py     'nsys/*.sqlite'   # H2D bytes (fixed) vs rate (not)
python3 ncu_sum.py   ncu_all.csv  # per-kernel SM%/MEM%/occupancy
python3 folded.py    p9.sqlite out.folded [main]   # folded stacks; 'main' = target process only
python3 flamesum.py  out.folded   # self and inclusive leaders
```

`gaps2.py` splits every idle interval at stage boundaries. An earlier version charged
each gap to the stage at its *start*, which put the whole ~800 ms tail on whichever
stage happened to contain the last GPU op — if you adapt this, keep the splitting.

`ncu_sum.py` filters metrics by **unit**: `Memory Throughput` is reported both as `%`
and as `Gbyte/s`, and summing across them produces values like `168242228298%`.
`Duration` comes back in `ns`. ncu serialises kernels and flushes caches, so its
durations run ~1.1-1.8x the nsys wall figure — take counters from ncu, timing from nsys.

For `ncu --kernel-name`, only one `regex:` prefix is allowed per string and matching is
against the mangled name unless `--kernel-name-base demangled` is given. A filter that
matches nothing prints `==WARNING== No kernels were profiled` and **exits 0**.

## Charts

```sh
python3 timeline_json.py p8.sqlite timeline.json && python3 mktimeline.py out.svg timeline.json
python3 vram_json.py     p3.sqlite vram.json     && python3 mkvram.py     out.svg vram.json
python3 folded.py p9.sqlite f.folded main        && python3 mkflame.py    f.folded out.svg "title"
```

For a multi-arm comparison (e.g. 24 movies across ingest paths), `arms24_json.py` folds
several sqlite exports into one payload that `mkarms24.py`, `mktl24.py` and `mkvram24.py`
all read; `cmp24.py` prints the same comparison as a table. `mkflame.py` takes an optional
5th argument capping rendered stack depth, for traces with a few very deep stacks.

`vram_json.py` needs a capture taken with `--cuda-memory-usage=true`. Colours are the
validated default data-viz palette (blue `#2a78d6` kernel, orange `#eb6834` transfer,
neutral idle). Chart rendering is deterministic: the same folded/JSON input gives a byte-identical SVG.
`mkflame.py` originally jittered colours with `hash()`, which Python salts per process
(`PYTHONHASHSEED`), so successive runs differed; it uses `zlib.crc32` now. If you add a
renderer, avoid `hash()` on strings for anything that reaches the output.

Rasterise with headless Chrome — `qlmanage` pads SVGs to a square:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --screenshot=out.png --window-size=1480,617 --force-device-scale-factor=1.5 \
  --default-background-color=FFFFFFFF "file://$PWD/out.svg"
```

## bwtest.cu

Measures H2D for a given payload and chunking, pageable vs pinned, on the device
selected by `CUDA_VISIBLE_DEVICES`, using the same synchronous `cudaMemcpy` the
application uses. Edit `CHUNK`/`N` to match the workload rather than quoting a spec
sheet at it.

```sh
nvcc -O3 -arch=sm_80 -o bwtest bwtest.cu && CUDA_VISIBLE_DEVICES=GPU-<uuid> ./bwtest
```

## Shared-host discipline

Take `flock /tmp/motioncorr-bench.lock` around anything that touches a GPU or loads the
CPU — profiling perturbs whoever is measuring next, and that is invisible to them
afterwards. After acquiring, gate on quiescence (no `cc1plus`/`nvcc`/`cicc`/`ptxas` by
exact name, zero foreign compute apps on the **target GPU by UUID**, load1 < 2.0) and
log how long you waited. Never background a sampler with `&` inside the locked region:
it inherits the lock fd and can hold the mutex after the driver dies.
