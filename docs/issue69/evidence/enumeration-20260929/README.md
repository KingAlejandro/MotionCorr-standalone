# Returned enumeration-error controls

Production/C++ test change: `7572e3a631e23e8e422bd42f088cbc5fc17b3865`.
The native build, CTest, matrix, mutants and all24 ran with checkout
`930d74154dd671061c78ddac04ce35419e75f762`; the additional commit only captures
actual control-process identity. The final production driver ran at
`0e159ffff4817fca57d6484d72f123a9236cac77`, adding structural product grading and
support for the composed initialization diagnostic. `graded-production-delta.txt`
is empty: its C++/CUDA/CMake sources match those of the native build.

## Results

- `ctest.log`: 22/22 pass.
- `matrix.log`, `restored-matrix.log`: 301 resource trials plus six enumeration
  controls, zero failures. These are separate counts.
- Each one-line recording mutant gives two enumeration failures (fatal and
  recoverable provenance). Its production fatal arm completes instead of refusing;
  both mutants exit0 and create an image/joint STAR, excluding unrelated crashes.
- `production-graded/results.json`: query ordinals2/5 identify session initialization
  and patch fallback preparation. Fatal returns with a clean runtime error slot fail
  closed, with no subsequent allocation or image/joint STAR. Four recoverable/
  zero-device arms match healthy **14,238,980 pixels**, complete normalized MRC
  headers/extended headers and both STAR files exactly.
- `parity24.json`: 24 MRC, 25 STAR, **341,735,520 pixels** and complete normalized
  headers exact against the retained main `a75a3f87` reference.

The first `production/` run used the older driver, which checked completion/inventory;
`retained-production-parity.json` independently grades its outputs. The fresh
`production-graded/` run integrates those comparisons in the driver. Both are retained.
The discovery probes at other query ordinals are recorded but are not claimed as
additional repaired boundaries. Logs/PDFs and scientific equivalence are outside this
product gate. Only validated writer timestamps and output roots are normalized.

## Execution and provenance

One VM A10080GB, CUDA12.8/sm80, physical UUID
`GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`; descendants CPUs112-119,
OMP4, runner j4/io2. Builds used j4 under the exclusive VM build lock; native work
held the GPU2 correctness lock. Other tasks could use other GPUs, so no timing claim
is made. GPU2 was empty before acquisition and released afterward.

`validate.sh` is the executed build/mutant/native driver. Afterward the test-driver-only
commits were fetched and this command ran under the same GPU2 lock and environment:

```sh
taskset -c 112-119 /home/alex/mc-env/bin/python3 \
  src/tests/run_enumeration_boundary_control.py build/motioncorr_faultinject \
  /home/alex/MotionCorr-standalone/relion30_tutorial/Movies/20170629_00021_frameImage.tiff \
  production-graded --initialize-mutant binaries/initialize-mutant \
  --patch-mutant binaries/patch-mutant
```

`production-graded/hashes.json` pins binary, input, mutants, driver and structural
comparator. Each run's `payload.json` captures actual PID, executable, process start
identity, CPU/memory masks and status. `provenance.txt`, `all24-input-hashes.txt`,
`binary-hashes.txt`, source/delta/status files and release inventories preserve the
remaining identity. Default memory policy/masks do not prove NUMA locality.

Raw MRC/STAR outputs and binaries remain at
`4GPUs:/home/alex/mc-pr115-enumeration-20260929`; do not remove them while reviewing.
Published files omit those large payloads. Result directories are create-only. Negative
controls changed only the private source clone and restored it; patches/build logs and
the expected failing matrix logs remain available.

No hardware was poisoned or reset. Older-toolkit/other-GPU behavior, genuine context
poisoning and pre-release driver refusal remain unrun. This follow-up does not repair
all legacy streaming helpers or approve the separate U16 preprocessing transitions.
