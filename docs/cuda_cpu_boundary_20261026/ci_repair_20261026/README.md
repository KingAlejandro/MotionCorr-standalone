# PR288 additive CI anchor repair and sealed audit archive

The CUDA compile-only job for `58cd3a563ac0b0af6999369b60a3377d656abad4`
failed during configure, before compiling a mutant. The diagnostic hook reads
actual inverse inputs between per-patch Hermitian projection and cuFFT; the
CMake mutant anchor incorrectly required those statements to be adjacent.

Exact original failure: [run40360025226, job121702633874](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/40360025226/job/121702633874),
CMakeLists.txt:794/852, `mutant ccf_perpatch_no_projection: target line missing
or not unique in cuda_alignpatch.cu`. [Original complete log](ci40360025226-job121702633874-original.log)
and [original status](ci40360025226-original-status.json) are retained. Ubuntu
succeeded at that head; the CUDA failure remains a FAIL record.

## Smallest repair and local validation

Only `CMakeLists.txt` changes outside this new additive documentation directory.
The per-patch match now includes the exact projection line's leading newline
and eight-space indentation, distinguishing the batched twelve-space statement
without depending on inverse adjacency. Replacement still removes exactly the
per-patch projection. `mc_cuda_mutant` and its missing/nonunique fatal guard are
unchanged. No source arithmetic, mutant waiver/disable, acceptance tolerance,
production result, test invariant or expected-failure mode changes.

Local validation executes the actual CMake mutation function and both affected
registration calls with target-building commands mocked. CMake 4.4.4; no CUDA
compiler, build, test execution or GPU is involved. [Reproduction script](validate_anchor.py),
[results](static-validation/result.json), [single-line mutant diff](static-validation/perpatch-mutant.diff).

1. Original stale anchor + current CUDA source: expected configure-helper FAIL.
2. Repaired anchor: PASS; exactly one per-patch projection removed, batched
   projection retained, both actual inverse calls and capture hook untouched.
3. Missing per-patch projection control: expected configure-helper FAIL.
4. Duplicate per-patch projection control: expected configure-helper FAIL.

Both mutants retain `MC_CHECK_HERMITIAN` and `--expect-invariant-failure`.
The existing native wrapper checks the actual C2R consumption input, and the
existing test rejects a mutant that does not violate that invariant. This source/
registration inspection is not new native proof that the mutants are rejected.

Full CUDA configure/build: **UNRUN locally/remotely**. No remote build attempted,
so Sonnet's native DC allocation is undisturbed. Any later 4GPUs build requires
coordination plus fresh GPU2/CPU80–87 overlap, benchmark/build admission. The
repair is pushed for ordinary current-head hosted CI; this child does not watch
or poll it. New native/movie/replay/science processes: **0**.

All tracked scientific report/evidence files at 58cd were compared byte-for-byte
and remain unchanged, as does `src/`: [frozen-file witness](frozen-58cd-scientific-files.json).
[CI repair ledger](REPAIR-LEDGER.json) keeps original failures and scope limits.

## Independent result audit: original sealed 0ba72 only

The parent supplied a completed independent audit **CLEAR for bounded reporting
at 0ba72a7197933f5f0c7149491853c04b0d780013**. It independently reproduced 710
covered scalar values, 39 v2 controls, strict 12 RUN↔12 ADMISSION coverage and 72
selected fetched-file hashes. It does not audit the 58cd DC follow-up, all 882
files, image pixels, native correctness, physical truth, performance or M1.

Compact artifacts are preserved unchanged in [independent-0ba72-audit/](independent-0ba72-audit/REPORT.md):
report, original/additive scripts and results, manifests, fetch bindings and the
original reviewer failure traceback. No audit script or scientific analysis was
rerun here. Parent's original metadata analysis incorrectly inferred payload
identity from whole-MRC hashes; its failure trace and separate v2 amendment
remain. No old failure is silently upgraded.

Durable raw reviewer archive (outside Git):
`/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/CUDA-independent-result-review-r1/`.
Parent COPY_INDEX binds 192 files/426,450,734bytes. `fetched.tar`, fetched arrays
and large raw trees are not added to Git. Compact copies total 24 files/373,430bytes;
[copy binding](independent-audit-copy-binding.json) records hashes and the 15-entry
original reviewer manifest, including entries whose payload remains external.

- REPORT.md SHA256: `02e0db9aafb6d6741dbc2714f216bb39e68e3d56f0d1d98f1a886e85b808f891`
- COPY_INDEX.json SHA256: `540581f62dacd73136daab7d03d04e6fbfdb5e645be9b81a568504742000127a`

This additive archive changes neither the frozen scientific packets nor their
historical pending-review statements. The later independent CLEAR applies only
to the audit's explicitly covered 0ba72 results. M1 remains held. No merge,
default/gate/policy change, new numerical campaign or watcher.
