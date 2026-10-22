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

## Actual attempt04 result: PASS for the bounded host claim

The new compiled source is `15516b6436ed7d97f395358155e94e9e89cc4a1f`.
It contains the pre-output frozen mutant semantics and only the two approved
native test wiring blocks. Historical oracle 135ee09e / compiled source 5c8f6b4f
remain the provenance of the earlier baseline implementation and attempt02/03
binaries; this new test translation unit is not relabelled with those hashes.
The production query call at motioncorr_runner.cpp:4342–4348 explicitly divides
x/y by nx/ny; Micrograph::getShiftAt also does so when normalise=true.

Archive SHA256:
`ab7283a09dc6421033cff8be0e9bf7847cdb4e5d5c437ecc5e6b7d352759ccec`.
All 7,494 archived regular files match the unpacked tree before/after execution.
Fresh Release CPU configure and both targets build **PASS**, parallel 2 on
CPUs 8–9. No artifact reuse or old-tree write occurred. Generated adapter SHA256
remains `d44dbbb1b9ebfc4af20788993466f945201b2c37864de819cbe818163366680f`;
its production body remains verbatim, SHA256
`2d04cc4348bf657e2fa0140e401276605736462c7b5c337abc26d840379d6e54`.
New executable identities:

- runner_numerics: `cf6b0dca84104cab4e29f0a63c2db1aa2583f7757efaae0d4cdb0789bd2cd243`
- motioncorr: `9071bd9e02523ab3b4a67d3a518cc4a9c8bf2fcd7f672be6aa42b50226be280c`

Source/test, object, dependency, compile/link, CMake cache, executable, frozen
expectation and command/exit bindings are retained in the indexed evidence.

- Static wiring control **PASS** on the new source; historical and intentionally
  altered fit geometry both rejected. Repeated remotely before configure.
- Generated declaration/required collection **PASS**: 84 registrations with every
  required name and four missing-name controls. Actual targeted runnable
  collection **PASS**: eight real commands plus four drop-one controls.
- Focused CTest **PASS 8/8**, no skipped tests: the seven-case oracle, three mutant
  expectation modes, and four existing recenter/model controls.
- Direct oracle **PASS 7/7**, exit 0. Maximum coefficient error 9.27166329822704e-14
  px; maximum vector error against field oracle 1.2974429256897861e-14 px.
- Sign, new query-normalization and frame-origin mutants **PASS**: each has seven
  ordinary ORACLE REJECT rows both registered and direct. Each direct run exits 1
  with empty stderr; no crash or rank/condition exception is counted as a kill.
- New axis control native fit-invariance check **PASS 7/7**: observation count,
  rank, condition and maximum coefficient error exactly match the baseline
  printed values. Ranks are 18 and conditions 4069.2536437806307 /
  4768.4697310391157 / 5399.9378860720481. Coefficient errors remain under 1e-7 px,
  but field error is 0.7637291732021134–0.763729173202127 px, above 2e-5 px.
- Focused existing CI collection unittest **PASS**, exit 0 (one unittest with
  its zero/count/required-name internal controls).

`native-metrics.json` contains 56 parsed rows (28 registered and 28 direct);
registered/direct values agree exactly. Full untruncated stdout is retained
because CTest's JUnit system-out truncates long outputs. No thresholds changed.
Archived-global composed truth RMS remains .242162266/.332923134/.575151890/
.409572049 px for affineCPU/CUDA/noisyCPU/CUDA. These inputs characterize
counterfactual composition; no new CUDA estimator measurement or science pass.

Full runnable collection is **UNRUN**: 33 unrelated helper registrations still
lack command fields in this focused build. No placeholder binary was created,
no required declaration was waived and no full suite ran. Production enclosing
acceptance/coefficient rejection/publication paths are outside the seam. GPU,
corpus, reconstruction, scientific and performance qualification remain **UNRUN**.
There is no timing comparison, production change, push, merge or publication.

Fresh admission 17:05:52 UTC recorded both locks FREE, no pinned user work on
CPUs 8–9, 439,930,208 kB MemAvailable and 531,617,423,360 scratch bytes free.
Sole detached PID 3040697 launched 17:06:38.636777 UTC, exited 0 and released owned
locks 17:08:51.470624 UTC. Read-only reconciliation 17:09:11.060058 UTC found
PID absent, no owned processes and both locks FREE. Runtime/numeric work used
CPU 8/thread 1; build workers inherited CPUs 8–9 with parallel 2. No GPU query or work.

Historical remote attempt02's 7,693 and attempt03's 7,544 indexed source/build/
receipt files match their pre-existing hashes, including original source archives
and binaries. Local historical archives/results/frozen expectations and protected
checkouts are unchanged. Attempt03 remains FAIL for the old fit-dimension mutant,
with its seven baseline passes/four controls/sign/frame kills preserved exactly.
This PASS belongs only to attempt04's new query-boundary control and new binaries.
Parent will perform the separate complete-package review.
