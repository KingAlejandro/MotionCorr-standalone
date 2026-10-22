# Host fit-boundary oracle, 2026-10-22

Implementation is on `test/fit-boundary-oracle-20261022`, based on PR273
`805d9de27898b4a10e6212e65098d5995a40fdb1`. Oracle code commit is
`135ee09e0925deb933bfd0f4ce7e24d6ddbd080a`; subsequent changes are evidence
and task-local documentation/orchestration only. This is an **unexecuted native
oracle**, with a retained resource-blocked launch. No production defect has
been demonstrated, and no merge or scientific/performance promotion is proposed.

Production files under `src/` are byte-unchanged from the base. FILE-ONLY
258/262–266/268, estimator/objective, math, DC, iterations/convergence,
defaults, gates and dependencies are unchanged. Parent owns publication;
there was no push, merge, GitHub comment or Notion write. Live PR273/272/269
bodies, comments and reviews plus issue268/comments were read before code
and retained in `live/`. All requested PR heads matched the supplied heads.

## Expectations and implementation

[EXPECTATIONS.md](EXPECTATIONS.md) and [frozen.json](frozen.json) predate the
native launch. `freeze.py` derives the independent rational 3x5 temporal
projection and verifies archived masks/global inputs; NumPy only measures
design rank/conditioning. Actual generator axis, frame and sign conventions
give X[3,9]=(-.384,+.192), Y[3,9]=(-.192,+.240), other coefficients zero
under exact global correction. All coefficients and fields are in original
pixels; .885 Angstrom/px, fixed ROI x=[12,116), y=[12,84), f=0..4.
The fixed absolute coefficient gate is **1e-7 px**, fixed maximum vector
field error versus analytic fitted expectation **2e-5 px**. No threshold
was changed after observing native output; no native output exists.

Three exact-global cases cover all9, affine-CUDA missing (row2,col1), and
noisy-CUDA missing (row1,col3). Four archived-global cases use retained
affine/noisy CPU/CUDA global STAR values with their actual masks. The full
designs have rank18 and independent conditions 4069.25/4768.47/5399.94.
Native rank/conditioning checks are **UNRUN**. Archived-global expected
field RMS is affine .242162266/.332923134 px and noisy
.575151890/.409572049 px (CPU/CUDA). Those are counterfactual analytic
composition values, not native results, estimator floors or scientific passes.

`runner_numerics fit_boundary` constructs analytic point-residual inputs,
calls real `MotioncorrRunner::interpolateShifts`, applies the default
group-center recentering recipe, invokes the source-extracted production
design matrix and actual `solve`/SVD, then evaluates real
`ThirdOrderPolynomialModel::getShiftAt` throughout the fixed ROI before any
serialization. It prints maximum coefficient error, field-oracle maximum
vector error, composed truth RMS/max, rank, conditioning and observation count.
No independent 18-column fit implementation is used as the native subject.

There is no public production fit seam. CMake generates a test-only adapter
from the byte-unchanged inline matA/solve block, retains the upstream GPL
notice, rejects ambiguous/missing boundaries and tracks source changes.
Local comparison proves the extracted body is verbatim (hash in `result.json`).
Only runner_numerics links it. The enclosing `processMovie` acceptance,
coefficient rejection and publication paths are outside this seam. No runner
or CUDA source was edited; the separate CCF worker has no production-source
hunk conflict. A change to the fit-block boundaries requires reconciling the
CMake extraction, which fails closed. New scripts are GPL-2.0-or-later and
add no dependency.

Three mutants alter test residual sign, width/height normalization or the
.5 fit-frame origin while retaining the same oracle and bounds. Each mode
requires all seven cases to be rejected; admission/runtime exceptions cannot
count as successful kills. Direct mutant runs are intended to exit1, and
registered expectation modes exit0 only for ordinary oracle rejection.
**All native mutant rejection outcomes remain UNRUN.** Existing recenter and
model controls are scheduled in the driver but were not executed.

## Actual checks and resource stop

Singlethread local checks on the busy Mac:

- Release CMake configure: **PASS**, exit0. It warns that pbzip2 is absent
  and that USE_NVCOMP is unused in a CPU configuration; no decoder was run.
- Both runner_numerics and the generated adapter: **PASS** clang syntax-only,
  exit0, sequential `nice -n 19`, no object or binary built or executed.
- CI `test_3_zero_or_missing_collected_tests_fails`: **PASS**, exit0. The
  required CPU lists and independent integrated list include all four new
  registrations, with each new name tested in the drop-one loop.
- CTest discovers **84** actual generated declarations. Static declaration
  validation: **PASS**, exit0. Drop each new registration and add a filler:
  **4/4 PASS**, each validator exits1 for its missing required name.
- Full runnable collection on the unbuilt tree: **FAIL**, exit1, retained.
  CTest omits command fields for absent helper executables. No required
  registration is missing. This is not relabelled as a runnable-suite pass.
  `check_registration.py` validates generated declarations separately and
  requires exact name agreement with CTest's JSON. No placeholder binary is
  created. The updated future driver also checks actual runnable commands
  for only the four new registrations after a successful focused build.

The sole detached remote attempt used fresh
`/mnt/clathrin/alex-motioncorr-fit-boundary-20261022-135ee09e` on
**4-gpu-vm**, reached with `ssh -J ccp4-gateway 4GPUs`. PID **3032254**,
source archive SHA256
`405e8faa11602bb7de92d49cd5bc6e58772d46909fad87f2290bca80272b3a59`.
All 7470 archived source files were hashed in its source receipt. Launch
affinity was CPUs8–9; numeric threads1, bytecode off. Intended compile
parallelism2/runtime affinity CPU8/runtime thread1 never began.

The fresh `/tmp/motioncorr-fit-boundary-cpu8-9.lock` was acquired. The one
nonblocking acquisition of `/tmp/motioncorr-build.lock` failed at
**2026-10-22T16:28:19.278467Z**, before configure/compilation. `lslocks`
identified owner **PID3030366 python3**, and the contemporaneous process
receipt identifies the other lane's
`alex-motioncorr-residual-ccf-20261022-805d9de2/build.py`, whose CMake child
was building on CPUs10–11. It was left alone. There was **no retry, sleep,
lock polling, CPU10–13 work or GPU execution** by this lane.

Driver exit is **75**; release receipt at **16:28:19.282925Z** records all
owned locks released, and subsequent process inspection found PID3032254
absent. Source archive and unpacked source remain in the fresh remote scratch.
Read-only discovery recorded GCC13.3.0, CMake3.28.3, Python3.12.3/NumPy2.5.3,
497GiB free scratch, no GPU compute applications, all four A100 UUIDs and
zero volatile uncorrected ECC. GPU3's UUID still matched the assigned prior
identity, but no GPU was acquired or used. These are admission observations,
not GPU qualification.

Remote Release configure/build, binary identity, native host oracle,
mutants, recenter/model controls and runnable native collection are all
**UNRUN**. No binary/field/coefficient error is reported as measured.
Full suite/corpus/reconstruction, native CUDA, scientific qualification and
controlled performance are also **UNRUN**. The existing truth failures keep
their original d751ff28 provenance and are not repaired or reclassified here.

## Receipts and handoff

`evidence.tar.gz` stores compact lossless launch, local and remote receipts;
`evidence-index.json` binds every member's size/SHA256 and the archive hash.
`result.json` is the compact status/source/input index. Original retained
native STAR members are rechecked against PR273's immutable archive index;
fixture manifest SHA256 is
`9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc`.
The earlier archive/research inputs were read only. No binaries or source
archive are committed in this evidence directory.

Root checkout remains `c8844894c7c6366abf297699b5312e4b775eb5b0`, with only
the pre-existing untracked `pr117-fix-measure-20260929/`; a read-only receipt
is retained. The isolated implementation branch is committed and ready for
parent review. Native verification needs a separately authorized future
attempt after resource coordination; this lane does not retry the busy lock.


## Native attempt02 — 2026-10-22, separate qualification result

The sections above describe the original historical attempt and retain their
original bytes/statuses. The parent-observed build-lock state change at
16:35:54 UTC authorized one new attempt, documented in
[native_attempt02/README.md](native_attempt02/README.md) and
[native_attempt02/result.json](native_attempt02/result.json).

**Attempt02 FAIL / blocked, exit1; native host oracle remains UNRUN.** Source
archive is `5c8f6b4f9242510545f852c15065bd93e762a2a1`, SHA256
`48fee9dbbc6536f4ab2aa27fcc87fdfd2778f31e63623a37d0715ff431feb5d1`.
All 7,475 regular source files match the unpacked tree before/after build;
the compiled oracle source and unchanged production body match 135ee09e.
No source/test/CMake/helper logic or frozen expectation was changed.

On 4-gpu-vm, fresh scratch
`/mnt/clathrin/alex-motioncorr-fit-boundary-native-attempt02-20261022-5c8f6b4f`,
PID 3036046 acquired the CPU 8–9 and shared build locks nonblocking. Release
CPU configuration/build of runner_numerics and motioncorr **PASS**, exit0,
with parallel 2 on CPUs8–9. Executable hashes and compile/link identities
are retained. Runtime driver affinity was CPU 8, numeric threads 1, no GPU use.

CTest collects 84 registrations, including all four new commands. The unchanged
`check_registration.py:30` then fails before native test execution: CMake 3.28.3
bracket-quotes names (`[=[RunnerFitBoundary]=]`), which its shlex parser keeps
literally while CTest reports `RunnerFitBoundary`. Full raw declarations,
collection JSON, stderr and name diff are retained. No repair or retry followed.

New targeted runnable validation, required/four-drop-one controls, seven-case
oracle, all three mutants, focused recenter/model controls and CI drop-one check
are **UNRUN**. Full runnable collection is **UNRUN** with unrelated helpers
unbuilt. No coefficient/field/rank/condition/mutant measurement exists.
Enclosing acceptance/rejection/publication paths, GPU, full suite/corpus,
reconstruction, science and performance remain outside this qualification.

Release at 16:41:50.515566 UTC records all owned locks released; reconciliation
at 16:42:41 UTC finds PID absent, no task processes and both locks FREE.
Original clean worktree, root checkout, historical result/archive and frozen
inputs were preserved. Compact indexed receipts are in native_attempt02;
parent owns subsequent review/publication and any separately authorized repair.


## Native attempt03 — registration repair and retained mutant failure

[Attempt03 report](native_attempt03/README.md) and
[separate result](native_attempt03/result.json) retain the single authorized run.
Only declaration support/new host regressions and a reuse-only evidence driver
changed. Fixed registration regressions **PASS 11/11**; historical checker fails
three of those tests. Frozen math, CMake, oracle/native tests, adapter, inputs,
coefficient 1e-7/field 2e-5 px bounds and all historical receipts remain unchanged.

After full matching source/build/test/generated-adapter/binary verification,
attempt03 reused attempt02's successful `5c8f6b4f` compiled subjects (oracle
`135ee09e`); **no fresh compilation** is claimed. New support commit is
`0bcb09b248c6bca1eb5db70bad37dbf429fa1cbd`. Fresh outputs are isolated under
`/mnt/clathrin/alex-motioncorr-fit-boundary-native-attempt03-20261022-0bcb09b2`.

**PASS:** 84 declarations with all required names and four drop-one controls; eight actual
focused runnable commands and four runnable drop-one controls; native baseline
oracle 7/7; sign/frame-origin seven ordinary rejections each; existing focused
recenter/model controls 4/4. Baseline maximum coefficient error is 9.2716633e-14 px
and maximum field-oracle error is 1.2974429e-14 px, under unchanged bounds.

**FAIL / incomplete qualification:** axis-normalization mutant throws
`exact-all9: rank/condition admission failed`, rather than ordinary oracle
rejection. Focused CTest is 7/8, exit 8; driver PID 3039133 exits 1. Native rank and
condition for the failed mutant were not printed. No retuning, repair or native
retry followed. Direct oracle/mutant commands and CI drop-one check are **UNRUN**
after this stop; full runnable collection, full suite, GPU/corpus/reconstruction,
science and performance remain **UNRUN**. Enclosing production acceptance and
publication are outside this seam; archived-global fields remain characterizations.

One launcher wrapper SyntaxError occurred before any process started and is
retained separately; correcting its receipt newline syntax started the sole
native attempt. Actual driver launch 16:54:33.941967 UTC; lock release
16:54:44.049653 UTC; reconciliation 16:55:50.115145 UTC confirms PID absent,
no owned processes, both locks FREE and reused build/source unchanged. Execution
used CPU 8/numeric threads 1, no GPU. New compact indexed evidence includes full
untruncated native rows; old result.json/frozen.json/archives and old checkouts
are preserved. No push, main merge, comment, Notion or production change.
