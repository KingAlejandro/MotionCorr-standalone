# Host qualification attempt04: model-query normalization control

Frozen before new native output. The verified production fit normalizes patch
coordinates by nx/ny; ThirdOrderPolynomialModel::getShiftAt directly consumes
already normalized x/y. Micrograph::getShiftAt likewise normalizes by width/height
before forwarding. A width/height swap at this query boundary therefore tests
fit-to-field coordinate composition without changing the fitted model.

Baseline and the new axis-normalization mutant share the exact observations,
128x96 fit call, coefficients, SVD and fixed rank/condition admission. Only mutant
model-query coordinates become x/96-.5,y/128-.5. Baseline stays x/128-.5,y/96-.5.
The same frozen field oracle and coefficient/field bounds judge both modes.
The static control binds the whole native test source to two exact wiring changes
and rejects old or altered fit dimensions. No oracle values, masks, archived
globals, CMake, production source, extracted fit body or thresholds change.

This supersedes the test-control semantics only. Attempt03 remains FAIL: its
old fit-dimension mutant raised admission before oracle rejection. Its measured
seven baseline passes, four existing passes, sign/frame kills and all receipts
are preserved without relabelling. The new mutant is a distinct test subject.

One fresh Release CPU build will use a new source archive/source/build/output
scratch, CPUs8–9 and parallel2 under both nonblocking locks. Runtime CPU8 with
numeric threads1. No GPU queries/work, full suite/corpus, reconstruction,
scientific/performance qualification, retries, or old build/output mutations.

Pre-output checks: the static wiring control accepts the new source and rejects
both historical fit-dimension wiring and a deliberately swapped fit call. Its
inverse of the two approved blocks recovers the entire historical test hash
f40146aacb2e2664c2c9201addc532d32d5a50b9262f1f2f0ca44094de34f696.
New test hash is362c3a204dec3b2577ffd8d303029956b2100230d8d86f06a0f63bfbe9d1f6fd.
The attempt driver will additionally require native baseline/axis observation
count, rank, condition and coefficient error to match exactly, with all seven
axis cases rejected by the same field oracle. Fresh full CPU targets are built;
no prior artifact is reused or modified. Exact argv and archive identity will be
retained before launch. No normalization result exists when this is frozen.
