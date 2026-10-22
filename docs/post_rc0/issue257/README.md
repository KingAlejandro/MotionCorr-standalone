# #257: CUDA subpixel peak-fit precision

PR #260 fixes the fit on the stored float CCF samples, independently of #254.
Base: main `3691374061f782bc84531fd1c79d017ddcb5a7c2`. Production implementation:
`531e9db40c10799627e7a06efd9462f16e868a1f`; native test revision:
`6c23ba1d10364507db39c51745af5a7a2dbf0c06`. Commits after that through
`d888ab11` add evidence only.

The native results below describe that retained revision. The
[2026-10-22 review response](arithmetic-control/README.md) adds independent
exact-rational expectations and host controls on top of `d888ab11`; its expanded
CUDA test has **not** been compiled or run natively.

The five selected samples and the parabola vertex are evaluated in double.
The existing float threshold `1e-15f` is promoted for the strict `abs(denom) > EPS`
comparison, with the integer position as fallback. Correcting the denominator can
intentionally change an old rounded-zero guard decision. Integer winner/tie
selection is unchanged. The existing float scales are multiplied into the double
vertex, then rounded once when stored in the existing float candidate arrays.
This is accurate same-sample evaluation, not a promise of CPU bit matching or
recovery of contrast already lost in the float map. No interface, dependency,
convergence, gate or tolerance changed.

## Native result

Release builds on 4GPUs (`4-gpu-vm`), GCC 13.3.0, CUDA 12.8.61, sm_80,
optional nvCOMP 5.3.0.16, A100 80 GB PCIe. GPU0 UUID
`GPU-eddb42fe-4f9a-adde-76d3-b924e14add54` selected by UUID under its advisory
flock, with the shared benchmark lock. Builds/initial suites used CPUs 96–103;
the clean CPU rerun and supplementary controls used 40–47, eight CPUs per
process. Other correctness work shared the host; no performance claim is made.

| Check | Result |
|---|---|
| Full CPU CTest, with Git metadata | **74/74**, exit 0, no skips |
| Full CUDA CTest | **110/110**, exit 0, no skips |
| Full CUDA+nvCOMP CTest | **113/113**, exit 0, no skips |
| Actual production kernel, 15 constructed/captured map cases | PASS, exit 0 |
| Float-denominator mutant, normal invocation | **FAIL**, exit 1, captured pedestal witness detected |
| Same mutant with `--expect-mismatch` | PASS, exit 0, requires the named witness |
| Known-motion launcher, CPU and CUDA | OVERALL PASS, exit 0 on both |
| Legacy Tier A exact fixture | **FAIL**; frozen-F CPU and this branch's CPU outputs are exact matches on the same fixture |

The known-motion gate cases are global high-SNR, local high-SNR and nonsquare
local. The noisy case retains its visible characterization accuracy failure;
execution/backend/invariance checks still pass under the existing launcher policy.
This is bounded known-motion evidence, not downstream scientific qualification.

The first CPU suite ran from a source archive and passed 73/74: the Git-backed
fixture control expected Git metadata. A shallow fetch supplied the exact commit
metadata without changing code; the full clean CPU rerun passes 74/74. Both runs
are retained. No test was skipped or weakened. Required Python tests used the
pre-existing `/home/alex/.mc-venv`; no packages were installed.

The Tier A failure is retained rather than relaxed: reference-relative image
RMSE `2.318762e-4`, maximum shift error `0.003030` px, and eight STAR field
differences. Repeating the same recipe with the retained frozen-F CPU binary
and this branch's CPU binary gives pixel-identical images, equal normalized
headers and zero STAR field differences under the exact comparator (exit 0).
CPU production source is unchanged by this PR. The legacy fixture mismatch is
therefore present in the frozen-F control too; this PR does not requalify or
repair that gate.

## Discriminating same-map control

`tests/cuda_peak_fit.cu` launches `findPeakAndInterpolateKernel` directly. It
checks a double host reference after the selected float scale and final output
cast, within one float relative epsilon (zero must match exactly). Flat,
one-ULP plateau/unique peak, integer tie, below/at/above guard, subnormal,
unbracketed search-edge/wrapped neighbours, positive curvature, large finite
and non-finite cases retain the stated arithmetic/fallback policy.

For the captured x samples `m=36366.4296875`, `vp=36365.69140625`,
`vn=36366.359375`, scale 4:

| | Candidate, image pixels |
|---|---:|
| Double same-sample reference before output cast | -1.6521739130434783 |
| Fixed native float output | -1.6521738767623901 |
| Float-denominator mutant native output | -1.6442307233810425 |

The old float denominator is -0.8125; the promoted denominator is
-0.80859375. The one-ULP plateau independently exercises the intended guard
change: fixed x=2 px versus mutant x=0. The mutation is compiled from the
production CUDA translation unit by the existing CMake mutant helper; there
is no separate test-only fit kernel. The existing native patch-batch and retry
suites also run with the shared corrected production kernel.

Flags are retained verbatim. Release uses `-O3 -DNDEBUG`; no fast-math, FTZ or
reassociation option was added. CUDA's normal contraction settings remain.
Non-finite tests characterize the existing algebra/fallback, with matching
NaN/Inf classes; they introduce no new peak-validity policy.

## Evidence and limits

`raw.tar.gz`: SHA-256
`c61a338faf9204eb1a19e83bd7322ad3b27ae28a4a2793a6501555be572f8e50`.
All 76 indexed files were extracted and hash/size verified; see
`raw-index.json` and `archive-verification.json`. The archive includes commands,
build flags, source and binary hashes, host/occupancy records, all build/CTest
logs and JUnit, fixed/mutant exits and logs, known-motion reports and the
retained Tier A controls. The recorded source diff for CMake/src/tests/tools/
test-data is empty at `6c23ba1d`.

The full #254/peak-fit/DC/null attribution is separate evidence PR #261, under
`docs/post_rc0/s1/peakfit_attribution/`. It does not change this production diff.
S1 closure, S1.4 CTF/FSC/B-factor outcomes, production timing/memory overhead,
other GPU/toolchain coverage and a new full QF are **UNRUN**. Existing QF rows
retain their original SHA. Intentional CUDA result changes need maintainer
sign-off before merge; no merge or release recommendation is made here.
