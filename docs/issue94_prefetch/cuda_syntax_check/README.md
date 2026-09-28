# `_CUDA_ENABLED` syntax check — what this is, and what it is NOT

## It is not a CUDA build

No CUDA toolkit was used. No `.cu` file was compiled. Nothing was linked, nothing was
executed, and no GPU was touched. `cpu64` has no CUDA toolkit installed, and building on the
shared `4GPUs` box would take `/tmp/motioncorr-bench.lock` and perturb #26, who owns this
round's slot. So this gap was closed as far as it can be closed without a slot, and no
further.

## What it does establish

That the `#ifdef _CUDA_ENABLED` branches of the two translation units this PR changes still
**parse and name-resolve** after the edits. That is the realistic failure mode for a change
like this one: the `Iframes` reference-alias, the relocated read path and the new
`inline_reservation` all sit next to CUDA-only code that a CPU-only build never looks at, so a
CPU-only green run would not notice a broken `_CUDA_ENABLED` branch at all.

`cuda_runtime.h`, `cufft.h` and `curand.h` here are minimal hand-written stubs covering only
the symbols the project's headers reference. The project's own `src/acc/cuda/*.h` are the real
ones and are parsed normally.

## Commands and results

macOS 25.6.0, AppleClang, 2026-09-28, source `412f2f98` (unchanged in `189ed1fc`; the diff between them touches tests and docs only):

```
c++ -std=c++17 -fsyntax-only -w -D_CUDA_ENABLED -I<stubs> -I. \
    -I/opt/homebrew/include -I/opt/homebrew/opt/libomp/include \
    -Xpreprocessor -fopenmp -DHAVE_TIFF -DHAVE_PNG -DHAVE_JPEG src/motioncorr_runner.cpp
  -> exit 0

c++ ... src/movie_prefetch.cpp
  -> exit 0
```

## The control, because a silent no-op looks identical to a pass

A syntax check that never reached the CUDA branches would also exit 0. So the check was rerun
against a deliberately broken copy, with one identifier inside an `#ifdef _CUDA_ENABLED`
region replaced by an undeclared one:

```
if (!movie_session->downloadRealFrames(Iframes))
  ->
if (!movie_session->downloadRealFrames(Iframes_NOT_A_SYMBOL))
```

That produced **1 error**, so the harness does compile CUDA-only code and the clean result
above is not vacuous.

## Still unverified, and listed as such

Real `nvcc` compilation, device code generation, linking against cuFFT, and every runtime
behaviour on an actual GPU. `scripts/prefetch_gpu_screen.sh` builds with
`-DCUDA=ON -DCMAKE_BUILD_TYPE=Release` inside the benchmark lock as its first step, so the real
toolkit build happens when a slot is transferred — not before.
