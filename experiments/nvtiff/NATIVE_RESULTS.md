# nvTIFF0.8 native sample experiment — 6 October 2026

**PASS for the controlled standalone experiment; product integration DEFER.**
Source `997b955c883300fc76ec43423ec0c533f7b685cf`; docs/evidence after that
source do not change executable code. Default-OFF, not installed, and no
MotionCorr ingest route changed. [Pinned case/identity receipt](native_20261006.json).

| Exercised gate | Actual result |
|---|---|
| LZW U8/U16,24/48 frames, strips,predictor1/2 | Every sample exact against independent tifffile/imagecodecs |
| U16 big-endian; U8 tile; U16 tile/predictor2 | Every sample exact |
| First3/count5/batch4 on U8/U16 | Exact selected samples; wrong-first control discriminates |
| Orientation2,MINISWHITE,signed,mixed width,valid3D depth2 | Refusal, no sample dump |
| Trust/input/output caps/range/symlink/existing destination | Named refusal; prior destination unchanged; no leaked temporary |
| Immediate SDK refusal/execution,completion,decoder-destroy injections | Failure, no dump; decode/completion faults stop dispatch |
| Actual old `a2888d2` absent ImageDepth admission | Refuses SDK-supported2D; repaired source decodes exactly |
| Genuine scalarLONG ImageDepth1,three U16 frames | Exact6144samples, raw tags independently verified |
| Physical/runtime/resource/owned release | GPU0 UUID/process/birth/binary/mask witnessed; exit0/query0/release0 |

The main campaign has28cases and143,654,912 compared samples, including a
duplicate absent-depth fixture, ranges and a healthy interposer control. The
genuine explicitunit-depth supplement adds6144samples: **143,661,056 total**.
This is seven controlled layout variants, not29 independent datasets.
Every comparison includes wrong-row-order, row-sum-preserving transposition,
last-frame bit and dropped-frame controls; U16 also checks byte order. Same
actual grader14host controls and extracted release10HOST controls passed both
normal Python and `-O`. These host controls are distinct from native outcomes.

## Failure history and narrow repair

First native source `a2888d2` linked and loaded nvTIFF but refused all ordinary
2D files: the SDK reports geometry depth0 when ImageDepth is absent. The
experiment required geometry depth1. It now reads the scalarLONG raw tag,
defaults absent tags to1, and rejects non-unit raw depth or SDK depth>1.
This does not admit3D volumes. The actual old binary discriminates the defect.

Tifffile ignored an attempted explicitunit extratag; that case is truthfully an
absent-depth duplicate. A separate `volumetric=True`/Z1 writer verified the raw
LONG/value1/count1 tags. Its first external assertion wrongly expected SDK
geometry depth1; nvTIFF also reports0 for this explicitunit case. Correcting
that caller assertion to the already-reviewed `<=1` semantics produced the
exact supplement result. Original failed logs,dumps,source/binary identities
and release records remain retained. No pixel tolerance or source gate changed.
An initial attached `taskset -c96-103` launcher failed before payload execution;
the actual payload used separate `taskset -c 96-103` arguments.

## Provenance and limits

VM A100-80GB, GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, all descendants
CPU96–103, NUMA memory bind1, build4 under the shared build lock. Actual v2
payload PID3265948/birth673635273;32 physical CUDA samples confirm the loaded
binary,PID/birth,UUID,CPU mask and library. Every child exits and owned cleanup
records contain no survivors/errors. Final release09:47:29UTC; supplement also
queries assigned device empty. Other devices may run concurrent correctness;
there is **no timing or application-gain conclusion**.

Private pinned NVIDIA wheel0.8.0.82; CUDA12.8 runtime. Candidate binary SHA256
`0643930d608c1e0670edd6fef687affa2af5df555e147fb940f216c8fa004ed9`;
nvTIFF library SHA256
`d46cfdef19db2530a5cfe06cc093edba7592d51656f1cbf833d51ce60b8a7830`.
All inputs are known generated pixels read independently; source/archive/cache,
binary/library/input/helper hashes are bound before/after. Full external callers
and raw records are retained at coordinator work/nvtiff-native-v2-20261006 and
on the same private VM acceptance root. No SDK material is redistributed.

API fault injections operate on healthy compressed inputs; they are not corrupt
LZW safety tests or genuinely poisoned CUDA contexts. Vendor internal scratch
remains unknown. Explicit compressed/output buffers are capped; process/VRAM
samples are not a whole-process peak or worker-admission proof. Input snapshot
checks are not atomic against concurrent producers. There is no full MotionCorr
gain/FFT/product comparison,licence compatibility decision or automatic trust
policy change. **Issue134 stays HOLD.**

Next: separately resolve decoder trust/licensing and scratch bounds; only then
evaluate matched isolated full-process off/on pairs and complete products before
any explicit opt-in adapter. The declared >=0.15s/movie application threshold
remains untested. Do not derive a speedup from standalone decoder wall fields.
