# PR #252: complete conditional retry admission

Source base: `1fd0aea62e70901af625987a250799af5edda4af`.
Review: <https://github.com/KingAlejandro/MotionCorr-standalone/pull/252#discussion_r4315391298>.
This follow-up addresses D2 only. The [retained native campaign](README.md) keeps
its original source identities and does not qualify this changed implementation.

## Allocation lifetime and decision

After a completed resident patch attempt, the resident movie, patch-preparation
buffers/R2C plan, patch window and original single/batched alignment workspace
remain allocated. `cudaMemGetInfo` already excludes all those live allocations
from the available bytes. Admission must therefore count only the **additional**
peak, without counting those existing buffers a second time.

`downloadPatchSpectra` allocates a full-spectrum stack S and frees it before
returning. Its preparation reuses the successfully prepared patch's buffers and
R2C plan. The subsequent `alignPatch` dispatches `cudaAlignPatch`, allocating S
again and constructing a fresh `PatchAlignmentWorkspace`. That workspace owns a
reference, weights, complex and real CCF stacks, four shift arrays, and a batched
C2R plan/work area. The original session workspace cannot supply these bytes and
remains live until the later release before reconstruction.

For G groups and a CCF half-plane W = ccf_h * (ccf_w/2+1), the extra peak is:

```
S = G * patch_h * (patch_w/2+1) * sizeof(cufftComplex)
required = S + W * (sizeof(cufftComplex) + sizeof(float))
             + G * W * sizeof(cufftComplex)
             + G * ccf_h * ccf_w * sizeof(float)
             + 4 * G * sizeof(float) + actual_C2R_work
```

S occurs once in the peak, since its download and upload lifetimes do not overlap.
Admission receives the same scaled B and CCF downsampling as the actual retry,
derives the same CCF geometry, and queries its out-of-place batch-G C2R plan with
automatic device-work allocation disabled. The probe is destroyed before sampling
free memory. Checked products/sums reject invalid or overflowing sizes before
planning or comparing against available memory; cuFFT int distances are checked.

For the review's e10216 geometry (G=59, 818-square patch, 216-square CCF), S is
158,299,360 bytes and the fresh non-cuFFT alignment buffers are 22,407,056 bytes.
The minimum is 180,706,416 bytes plus actual cuFFT work. Thus 175,000,000 free
bytes must decline, even though S fits.

Resource ownership and lifetimes do not change. The check stays inside the
non-converged resident retry branch. Decline still preserves both globally aligned
representations, checks fatal CUDA state, discards the session and uses the
existing streaming retry. Kernels, shift reset, tolerances, batching policy,
publication and dependencies are unchanged. This is admission, not an atomic
reservation: allocator granularity, internal plan overhead and concurrent memory
users can still cause later allocation failures handled by existing contracts.

## Controls and local verification

`PatchRetryAdmission` is host-only and tests the production checked byte helper:
the literal e10216 census, nonzero cuFFT work, full and rectangular windows,
S-fits/complete-peak-does-not headroom, exact `size_t` maximum, sum and batch
overflow, invalid dimensions/groups and int-distance overflow.

`CudaLocalAdmission` retains initial local-stage boundaries and now independently
queries real cuFFT plan sizes for three retry configurations. Wrapped free-memory
values include S-1, S, S+1, the incomplete-admission interval, and complete
required-1/required/required+1. Expected bytes are independently summed rather
than parsed from production diagnostics. Invalid/overflowing requirements must
decline even with `SIZE_MAX` free bytes. This test requires native CUDA; it is
**UNRUN** here.

Local environment: macOS arm64, AppleClang 21, C++17; occupancy checked before
compilation, build parallelism at most two, test processes use thread caps of two.
CUDA toolkit/compiler/device are unavailable; no remote or GPU jobs are launched.
The CPU build uses FFTW 3.3.11, OpenMP and the existing libraries. Configure selects
the existing original CPU dose-weighting loop and reports the existing missing
`pbzip2` fixture waiver. The first configure selected a Python without NumPy;
reconfiguration explicitly selects the installed Python 3.13.7 with NumPy 2.4.2.

Commands run on 2026-10-22 (all successful commands exited zero):

```sh
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF \
  -DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3
cmake --build build --target motioncorr patch_retry_admission patch_retry_state --parallel 2
ctest --test-dir build -R '^(PatchRetryAdmission|PatchRetryState)$' --output-on-failure --parallel 1
python3 tools/test_ci_fail_closed.py TestCiFailClosedControls.test_3_zero_or_missing_collected_tests_fails
ctest --test-dir build -R '^(PatchRetryAdmission|PatchRetryState)$' --show-only=json-v1 > build/d2-collection.json
python3 tools/validate_test_collection.py --json build/d2-collection.json --min-count 2 \
  --required-tests PatchRetryAdmission PatchRetryState --dump-json build/d2-collection-validation.json
c++ -std=c++17 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined \
  -fno-omit-frame-pointer -I. tests/test_patch_retry_admission.cpp -o build/patch_retry_admission-sanitized
build/patch_retry_admission-sanitized
git diff --check
```

Results: CPU targets compile; focused CTest **2/2 PASS**; collection fail-closed
control **1/1 PASS** (including removing `PatchRetryAdmission` at unchanged test
count); actual focused CMake collection **PASS**, two required tests; strict
warning/ASan/UBSan arithmetic executable **PASS** with no sanitizer diagnostics.
Logs are in the ignored local `build/d2-{build,ctest,collection-controls,sanitizers}.log`.
The full CPU suite is **UNRUN**, not represented by the focused collection check.

Four isolated copies of the helper were compiled serially with
`c++ -std=c++17 -Wall -Wextra -Werror -pedantic -Ibuild/d2-mutants/NAME -I. tests/test_patch_retry_admission.cpp -o build/d2-mutants/NAME/patch_retry_admission`.
Each copy changes exactly one expression; production files are untouched:

| Mutation | Observed rejection (each executable exits 1) |
|---|---|
| Replace final total by S alone | e10216 retry allocation census differs |
| Initialize total to zero instead of cuFFT work | cuFFT workspace missing or counted twice |
| Add the spectrum stack twice | e10216 retry allocation census differs |
| Replace checked total addition by unchecked addition | invalid or overflowing requirement accepted |

All four negative controls are rejected as intended; local receipts are in
`build/d2-negative-controls.log`. They test host arithmetic, not CUDA allocation
or the runner's native fallback/publication behavior. The native boundary test
has been updated but neither compiled nor executed on this host.

Native re-entry, numerical product parity, constrained VRAM campaigns, performance
and scientific validation remain **UNRUN** for this follow-up. Ready for parent
source review; no merge readiness or current-head CI claim is made. D3/#251 is
independent: its test is absent at this D2 source base; the existing CUDA required
test lists are unchanged here. When combining branches, retain both
`CudaLocalAdmission` and `CudaEarlyStreamingOom` in CMake and both CUDA lists,
as well as the new device-free `PatchRetryAdmission` control.
