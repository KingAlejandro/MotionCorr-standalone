# The workload landscape is a design input

The product handles a distribution of movies, not one tutorial movie expressed
in several encodings. A format is not a sufficient execution-policy key:
frame count, rendered dimensions, sample representation, compression layout,
gain/defects, physical metadata, available memory and storage behavior interact.

The original #142 experiments isolate FFT scheduling and process startup.
The follow-up `tools/architecture/workload_matrix.py` adds a small heterogeneous
input screen. [RESULTS.md](RESULTS.md) records execution and evidence boundaries.

## Coverage and gaps

| Axis | New small screen | Still needed for general acceptance |
|---|---|---|
| Container/sample type | Classic TIFF U8/U16; MRC U16/F32/F16; XZ-compressed F32 MRC | Real EER; BigTIFF; packed 4-bit application processing; signed integers; more compression families and byte orders |
| TIFF encoding | Raw, Deflate, one-row and 17-row strips with a short final strip | LZW, PackBits, predictors, tiled layouts; native nvCOMP and malformed-input trust policy |
| Frame count | 4, 12, 17, 24, 80, 160; expected counts in STAR | Longer independent acquisitions, selection/fractionation/grouping and variable dose; EER raw-event versus rendered-frame counts |
| Geometry | 256×192 and 384×256 mixed in one job; larger/odd shapes in the separate FFT probe | Detector-sized decode/I/O, super-resolution 8K, whole-worker memory peaks |
| Values | Synthetic low counts, U16 values above 255, signed fractions; encodings must preserve samples exactly | Independent low-dose, high-drift, weak-signal and tomography content; scientific outcomes |
| Metadata | Two optics groups with different pixel size/voltage; per-movie frame count | Per-frame doses, EER gain conventions, changed binning/selection on resume |
| Preprocessing | Spatially varying gain and a 2×2 defect region on compatible dimensions | Gain replacement/rotation/flip, identity transitions, dense defects and memory pressure |
| Worker transitions | Mixed formats/counts/dimensions/optics, reversed movie order, automatic versus forced-float ingest | Pool eviction, genuinely poisoned devices, very long sequences, concurrent workers |
| Storage/operations | Scratch/local files and a sequential compressed-MRC decoder | Network storage, partial arrivals, slow/missing decoders, failure/restart under real acquisition workflows |

Broader focused tests already exist for some cases, including packed 4-bit
decoded samples and injected CUDA failures. Preserve their claims at the actual
layer; a reader test is not a whole-application scientific pass.

## Three distinct kinds of evidence

1. **Equivalent-data encodings** isolate decoding, row order, conversion,
   routing and metadata. The screen compares canonical samples with the
   production reader, then corrected headers/payloads and per-movie metadata
   across encodings. Re-encoding a file or repeating frames does not create a
   new scientific dataset.
2. **Synthetic content with known truth** tests controlled motion, signal,
   defects and failures. Truth is independent of CPU/CUDA agreement. The new
   texture families are encoding/transition controls, not motion-truth tests.
3. **Independent experimental datasets** establish useful scientific outcomes
   across acquisition conditions. They remain necessary before numerical
   acceptance changes or general performance claims.

Avoid a huge Cartesian product. Isolate factors with tiny fixtures, then test
interactions that could invalidate the architecture: long + high-resolution +
small memory; EER grouping + dose/gain; geometry changes + cached plans;
compact ingest + defects + fallback; mixed formats + decoder lifetime.
Report each workload stratum before any weighted aggregate throughput number.

## Design consequences

- A movie specification must distinguish source frames, rendered frames,
  selected frames and alignment groups. EER grouping affects both memory and
  dose interpretation. One unqualified frame count is an inadequate interface
  between reader, estimator and resource planner.
- Choose input routes from real capabilities: sample type, codec, layout,
  transformations and backend build. Keep a reliable general route and record
  the path actually used. The fastest tutorial TIFF route is one case.
- Account separately for host staging, resident device movie, FFT scratch,
  retained caches and overlap. FFT batching does not bound full-movie memory.
  Do not silently change binning/grouping to fit; that can change the science.
- Reusable workers must survive transitions. The screen exposed a compressed
  reader lifecycle error on macOS: a later XZ movie failed although it worked
  in a fresh invocation. Repair the ownership boundary rather than masking it
  by restarting every movie.
- The 11.25 s versus 2.09 s result concerns six tiny movies and invocation
  granularity. Main already supports batches; it is not a fivefold speedup for
  detector-sized motion correction.

No EER, nvCOMP or independent scientific diversity is implied by these new
re-encodings. Choose the next real-data portfolio with facility/pipeline users,
recording their input distribution and required products instead of selecting
only files convenient for the current fast path.
