# Host qualification attempt03

Narrow registration-support repair after attempt02's retained declaration FAIL.
The checker now handles generated bracket/quoted/bare names, rejects malformed,
missing and duplicate declarations, and uses matching CTest canonical names.
Commands remain generated declarations; full declaration validation does not
claim full runnable collection. All existing required checks remain active.

Host regressions read the retained CMake3.28.3 syntax directly from attempt02's
immutable evidence archive. The old checker fails3/11 tests (bracket forms and
accepted duplicates); fixed checker passes11/11, including missing required names,
quoted/bare forms and malformed syntax. No native math, oracle, adapter, CMake,
original native tests, frozen inputs or numerical tolerances change.

Attempt03 reuses attempt02's Release binaries only after matching every retained
source file, build artifact hash, dependency manifest, tool hash and source archive
hash. Compiled identity remains5c8f6b4f / oracle135ee09e; no fresh compilation is
claimed. New support source is archived separately at the support commit.

Both locks use nonblocking acquisition; CPU ownership is held through execution.
The common build lock is released after identity verification because no build is
needed. Runtime uses CPU8 and numeric threads1. A fresh CTest view byte-copies
original generated declarations/cache, retaining their actual executable/script
commands. Its logs and all temporary outputs go to new task scratch; old source,
build and output trees are read only. Four new and four existing focused commands
must be runnable; every new registration also gets an actual-command drop-one
check. Full unbuilt collection remains outside the claimed runnable subset.

No retry on admission or native failure, placeholder binaries, GPU queries/work,
full suite, corpus, reconstruction, scientific or performance qualification.

## Actual result: incomplete qualification, attempt FAIL

Support commit `0bcb09b248c6bca1eb5db70bad37dbf429fa1cbd`; archive SHA256
`677bc91a21ebba2c31fc20ff5a2ff13e00477de5c4bc71c68cc1fe98ae37adf5`.
The 7,484-file support tree is distinct from compiled source `5c8f6b4f` /
oracle `135ee09e`. Attempt02's 7,475 source files, all retained build/artifact
hashes (including adapter, objects and binaries), dependency manifests and tool
hashes matched before reuse. Source/build identity matched again after execution.
No build ran. Reused executable SHA256 values are:

- runner_numerics: `07f3fd30ec9654fc7104a1b7e9176fedc5e85b799dbf385154626a667dc2582c`
- motioncorr: `94c292d8d9ee6edfaa56c20674ee1186ade41f8b6b9ba99e68cad9569121728f`

Fresh admission at 16:53:28 UTC found both locks free, no pinned CPU 8–9 user
threads, sufficient RAM and 531,910,684,672 scratch bytes free. One initial launcher
wrapper failed to parse before any statement executed (receipt newline quoting).
Its failed transport and exact source are retained. The corrected wrapper changes
only receipt serialization, checks that no launch artifacts exist, and starts the
one actual driver PID 3039133 at 16:54:33.941967 UTC. Its frozen driver argv, source
and environment are unchanged; no native job was retried.

All checks below ran on CPU 8 with numeric threads 1, in fresh scratch
`/mnt/clathrin/alex-motioncorr-fit-boundary-native-attempt03-20261022-0bcb09b2`:

- Declaration/required collection **PASS**: 84 names and four missing-name controls.
- Actual targeted runnable collection **PASS**:eight commands, plus **4/4 PASS**
  drop-one controls requiring ordinary missing-required-name rejection. Full
  unbuilt collection is not claimed runnable; 33 unrelated helpers remain unbuilt.
- Native baseline oracle **PASS 7/7** through registered RunnerFitBoundary.
  Every case has rank 18; conditions are 4069.2536/4768.4697/5399.9379.
  Maximum coefficient error is 9.27166329822704e-14 px; maximum field-oracle
  vector error is 1.2974429256897861e-14 px. Frozen bounds remain 1e-7/2e-5 px.
- Registered sign and frame-origin mutants **PASS**, each with seven ordinary
  `ORACLE REJECT` rows and expectation-mode exit 0. These are actual ordinary
  oracle rejections, not admission/runtime failures.
- Registered axis-normalization mutant **FAIL**: first case `exact-all9` raises
  `rank/condition admission failed`, exits 1, and emits no ordinary oracle-rejection
  row. Its native rank/condition values were not printed; they are unknown.
  This exception does not qualify as a mutant kill. No input, mask, mutant,
  admission policy, oracle, adapter, native math or bound was adjusted afterward.
- Four existing controls (RunnerInterpolateRecenter, RunnerInterpolateShifts,
  MicrographModelBounds, RunnerModelParser) **PASS 4/4**.

Focused CTest is **FAIL 7/8**, exit 8; driver exits 1 and stops. Separate direct
oracle, direct exit 1 mutant runs and CI drop-one unittest are **UNRUN** after
that failure. No extra native run was performed to fill those gaps.

The full untruncated numeric rows are in `native-fit-rows.txt` and LastTest.log
inside the evidence archive; JUnit's system-out is truncated by CTest at 1024 bytes.
`native-metrics.json` retains all 21 parsed baseline/sign/frame rows. Archived-global
composed truth RMS values remain .242162266/.332923134/.575151890/.409572049 px;
these are counterfactual composition characterizations, not scientific passes or
new CUDA measurements. Production enclosing acceptance/rejection/publication,
full suite, GPU, corpus, reconstruction, science and performance remain UNRUN.

Owned locks were released at 16:54:44.049653 UTC. Reconciliation at 16:55:50.115145
UTC finds PID absent, no task processes, both locks FREE, and new/old source and
reused build unchanged. No foreign processes, caches or services were changed.
Historical attempt01's lock stop and attempt02's registration FAIL remain intact.
Parent owns subsequent independent review and any publication or new authorization.
