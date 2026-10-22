# #257 / PR #260: independent arithmetic review response

Base: `d888ab111b1965aeda484a928e76f421112737e0`. The clean T3 branch
`peak-fit-arithmetic-control` was fast-forwarded from `c8844894` to that exact
fetched PR head. Issue #257, its discussion and the latest PR review were read
live before edits; [live-review.json](live-review.json) retains a second live
snapshot with the same head. This is a local test-only follow-up for parent
review/publication. Production source, math, thresholds, selection/tie order,
interfaces, failure/publication policy and FILE-ONLY #258/#262–266 are unchanged.
No dependency was added; new C++ files use GPL-2.0-or-later.

## Independent expectations

`tests/peak_fit_reference.h` supplies 13 selected finite, exactly representable
integer-grid fixtures to both `tests/peak_fit_arithmetic.cpp` and the actual
production-kernel launcher in `tests/cuda_peak_fit.cu`. If stored samples are
`m, vp, vn` in common power-of-two units, integer drops `L=m-vn`, `R=m-vp`
give the interpolating polynomial
`p(t)=m+(L-R)t/2-(L+R)t²/2`, with vertex `(L-R)/(2(L+R))`.
Bounded signed 64-bit rational arithmetic checks the vertex against separately
declared analytic values and applies the selected position and exact stored
float scale. Sample conversion is checked for exact representability. Guard
magnitudes are exact integer-grid values scaled by a power of two; the strict
comparison uses the exact promoted legacy `1e-15f` threshold.

A double division merely proposes the final float expectation. Integer
cross-products certify its exact rational value lies within that float's
nearest-rounding interval, using adjacent floats and ties to even. Bounds reject
unsupported values before the certificate's integer products; this is a small
fixture oracle, not a general rational/float library. Long double is unnecessary.
Equality assertions apply only to these selected, certified finite outputs:
they establish correct final rounding on these cases, not exact vertices or
correct rounding for every possible input/compiler setting. Both rounding
midpoint directions have host controls.

Analytic cases include `16+t-2t²` (vertex 1/4), `16+t-3t²` (1/6), and
`32+11t-18t²` (11/36), with reversed y slopes. The 1/6 case rejects storing
the vertex in float before multiplying by 5/4. The 11/36 case distinguishes the
stored float scale `11184811/2097152` from real `16/3`; the two outputs differ
by one ULP. Further fixtures cover the captured pedestal, rounded-zero plateau,
unique one-ULP peak, nonzero correction below half an output ULP, exact
below/equal/above threshold curvatures, and unbracketed/positive curvature fits.
At/below the threshold the selected integer is retained; fixing the old rounded
zero intentionally changes the plateau's fallback into a ±1/2-grid correction.
No clamp or new peak-validity rule is introduced.

Quantization has a separate analytic control: `1-2^-28*(t-1/4)²` has vertex
1/4 and curvature magnitude above the guard, but all three samples round to
float(1). The stored flat map therefore takes the specified zero fallback.
Here map information loss is 1/4 grid pixel and arithmetic error on the stored
samples is zero; this does not claim a unique mathematical vertex for a flat
parabola. Increased fit precision cannot recover that missing information.

The CUDA test retains all 15 previous cases and their tolerances/non-finite
classification checks, adding the 13 exact fixtures (28 total). Its production
float-denominator mutant must now fail both independent pedestal and
rounded-zero witnesses as well as the retained captured witness. The new host
negative controls mutate a host arithmetic replay, not production code. CMake
registers all four host tests; collection requirements cover them and both CUDA
peak-fit tests, with the independent fail-closed collection inventory updated.

## Local evidence and commands

[host-checks.json](host-checks.json) records full commands, outputs, exits, UTC,
occupancy, source hashes, original archive hash and thread environment. Host:
arm64 macOS, Apple Clang 21.0.0; Release `-O3 -DNDEBUG`, no added fast-math or
FTZ flag. Only the focused target was built. Build/CTest and numerical library
thread limits were 2; unrelated processes were left alone. Results:

- `cmake -S . -B build/peak-fit-control -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF
  -DBUILD_TESTING=ON -DPython3_EXECUTABLE=<recorded Python>`: PASS.
- `cmake --build build/peak-fit-control --target peak_fit_arithmetic --parallel 2`:
  PASS; `ctest --test-dir build/peak-fit-control -R '^PeakFitArithmetic' -j 2
  --output-on-failure`: **4/4 PASS**.
- Direct executable: normal exit 0, 13/13 fixtures. Normal invocations of
  `float-denominator`, `early-store`, `wrong-scale`: **exit 1**, respectively
  2/2/1 mismatched cases; CTest's expectation mode requires named witnesses and
  exits 0. Exceptions exit 2 and cannot satisfy expectation mode.
- `python3 tools/test_ci_fail_closed.py
  TestCiFailClosedControls.test_3_zero_or_missing_collected_tests_fails`: PASS,
  including removal of each newly required registration with additive filler.
- Filtered CTest JSON plus `tools/validate_test_collection.py --min-count 4
  --required-tests <four host names>`: PASS. The attempted full collection
  validation is retained as **FAIL**, exit 1: unrelated C++ targets were not
  built, so CTest omits their command programs. There are 78 registrations;
  this is not a full CPU-suite execution or a full runnable-collection pass.
- Standalone host build with `-Wall -Wextra -Werror -fsanitize=undefined
  -fno-sanitize-recover=undefined`: PASS, no diagnostic. `git diff --check`: PASS.

CUDA compile and native execution of the expanded tests are **UNRUN** (`nvcc`
unavailable). No remote/GPU jobs, push, merge, GitHub comment or Notion write.
The original `raw.tar.gz` remains unchanged at SHA-256
`c61a338faf9204eb1a19e83bd7322ad3b27ae28a4a2793a6501555be572f8e50`;
its previous native passes do not qualify these new assertions.

The latest review's scientific limits remain: the full #261 census changed
#254-only → fit from 17→19/60 screen positives and median maximum global
discrepancy from 0.038605→0.039105 px in the other 58 configurations. This is
not an S1 solution. High-SNR motion gates pass in the retained evidence; noisy
characterization remains FAIL. No new downstream, performance or scientific
qualification, nor merge recommendation, follows from these host controls.
