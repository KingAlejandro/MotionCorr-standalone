# Release v5 and minimal producer driver: criteria (frozen before any v5 code or test exists)

Status: preparation only. Native movie execution is NOT launched by this work. Scope is the frozen pilot: 8 cases, at most 16
producers (OFF then ON), P1/P2 and the .20/.40/.80 A limits exactly as in PLAN.md. No change to CCF source, tests, CMake, B2, the
global isotropic arm or the weight arithmetic; v1-v4 files, sealed packets and durable copies stay immutable. Source identity for the
build is `git archive` of `d1c498b8` (src = 634e4b48, CMake = 5bcfa987).

## 1. Recovery and pins (done before code; read-only on the old owned evidence)
On cpu64, over direct strict SSH, all 33 fixtures at /tmp/motioncorr-damping-a1c78adc1d0f/v2/v2fixtures and all 8x19 = 152 baseline
files (durable /home/ubuntu/motioncorr-evidence/... copy and the /tmp task copy) were hashed and compared with the pins of
ADMISSION_DRAFT_v3.json. Nothing is regenerated; a missing or different file is a STOP.

## 2. CPU build and selected checks (cpu64, CPUs 32-47, owned namespace /tmp/motioncorr-lfw-v5-20261026)
Stage the exact archive, hash it, build Release, CUDA OFF, MC_EXPERIMENT_CCF_DC=ON, -j2, OMP/BLAS caps <= 2, all overlapping leases plus the
canonical bench lock held by the existing lane.py for configure, build and checks, foreign-compute (busy cores on 32-47) and scratch checks
before each step, no signals to others. Selected ctest (arm unset): LocalFullWidthWeight, IsotropicWeight, GlobalHalfGain, CoupledPeak,
PatchRetryState, ExperimentalFlagsCli, LocalCcfCaptureCli, CcfDcHook. Receipts: occupancy before/after each step, configure/build/ctest
logs, build_receipt.json (archive, binary, test-binary and shared-library hashes, compiler, cmake args). No timing claim. A failed step is kept.

## 3. Release module `pair_decision_v5.py` (a re-anchored copy of v4 with a reviewable diff; v4 is not edited)
- Anchors: constants for the sha256 of ADMISSION_V5 and COMMANDS_V5 and of score_fields_v3.py. The v5 module, driver and tests are bound out of
  band by the parent release index, so the admission does not pin them (no circular hash).
- No public function takes binary path/hash, roots, expected, admission or commands arguments: they come only from the anchored admission.
- **L4 identity:** the admission carries candidate_binary {path, sha256}, source_archive {path, sha256, commit, tree}, build_receipt {path, sha256},
  compiler, libraries, venue, allocation and clearance fields, all non-null for a final admission. The gate and the pair/decision entries
  (and the driver at start and before each launch) require: the actual file at binary path hashes to candidate_binary.sha256; the source archive
  file hashes to its pin; candidate_source_commit equals source_archive.commit; the build receipt hashes to its pin and its recorded archive
  sha256, commit and binary sha256 equal the admission's. Any null, missing or different value is a STOP (code IDENTITY or HELD).
- **L3:** `pre_ON_gate` runs the pinned `manipulation` on the OFF stdout.log with the same coverage rules as the pair (global eligible > 0, 3x3 local
  eligible > 0, global-only local eligible 0 and coupled patch peaks 0, arm both) before any ON launch; the OFF stdout hash and the manipulation result
  are bound in the pre-ON record.
- **L2:** `admit_pair` re-derives, from the anchored baseline pins and the files on disk, the baseline inventory/byte identity and OFF runtime/STAR byte
  equality, and repeats the comparator-JSON check; it no longer relies on the pre-ON record alone. A self-consistent handwritten record must fail.
- **L1:** pair-stage comparator output goes to `pair/<case>/run_<k>/` with a fresh k, so `admit_pair` for each case followed by `decide_pilot` in the same
  decision directory works; a pre-ON record is still written once per case (a rerun in the same directory is refused, never overwritten).
- Everything else of v4 (witness prescan, pinned comparator subprocess, AST-extracted pinned `star_blocks`/`manipulation`, P1/P2 rules, case checks) is kept.
- The typed-string `on_launch_permitted` of v3 is not used.

## 4. Minimal driver `driver_v5.py` (launches only the frozen commands; the real path is not exercised by tests)
- Reads only the anchored admission/commands; real launch additionally requires `<campaign>/PARENT_RELEASE.json` naming the sha256 of the v5 module, the driver
  and a delta-review report, each equal to the files in use. Without it the driver refuses (dry-run validation only).
- Before every launch step: a fresh guard (all overlapping leases named by MOTIONCORR_HELD_LEASES equal the computed set, allowed CPUs equal 32-47, foreign
  busy cores <= 1.5 over 2 s, free memory, combined scratch <= 25 GiB incl. prior namespaces) whose receipt is retained; failure is a STOP.
- Per case in admission order: stage a fresh exclusive run directory (`mkdir` without exist_ok) holding only `<case>.star` and `<case>.mrcs` at their pins
  (truth/target files never staged); launch OFF once; write the v3 receipt (case, arm, exit, binary sha, run_dir, argv, cwd, declared environment, observed
  controlled environment, complete output inventory, runtime.json and stdout.log hashes); `pre_ON_gate`; only then stage and launch ON once; no retry.
- The child runs with exactly the declared environment plus PATH, argv exactly the resolved row, combined stdout+stderr to stdout.log, affinity set to the
  allowed CPUs, a wall limit; a non-zero exit, timeout, failed admission, failed gate or guard failure stops all further launches and is kept. At most 16
  launches, recorded in an append-only ledger. After all 8 pairs: `decide_pilot` once. A scientific FAIL is recorded and removes no row.

## 5. Tests (fixed before running; fake child only, no MotionCorr movie, no real MRC pixels)
Real comparator subprocess and the pinned helper functions run on synthetic trees as in v4; a test admission copy with real fake binary/archive/build-receipt
files and filled pins replaces the anchors (documented test double).
- v5 mandatory changes: L4 (binary hash differs from candidate; binary path differs; actual binary file changed after the pin; source archive changed; commit
  mismatch; build receipt hash, receipt archive/binary/commit mismatch; null identity field; a hand-built binary argument is impossible), L3 (OFF zero global DC,
  missing DC line, 3x3 OFF local eligible 0, global-only OFF with local work all stop the gate before ON), L2 (self-consistent handwritten pre-ON record with a changed OFF
  runtime or STAR is rejected by `admit_pair`; baseline byte change after the gate), L1 (gate all cases, `admit_pair` per case, then `decide_pilot` once in the same
  directory succeeds and keeps every comparator output; a repeated gate in the same directory is refused), anchors (altered v5 admission/commands refused).
- v4 behaviors still hold for the v5 module: one positive 3x3 and one global-only pair, witness variant rejection, a global trajectory 1-ulp change, the real HELD-style
  admission refusal (null field), comparator-detected product change.
- Driver with a fake child (a small script obeying the frozen argv): a full 8-case run ending in `decide_pilot` with crafted scoring only where truth fixtures are absent;
  refusal without PARENT_RELEASE or with a wrong hash; guard failure before the first launch and before an ON launch; run directory already exists; truth file found in
  the staged directory; fake child exit 1, timeout, missing runtime.json, extra output file, wrong witness count, OFF differing from baseline (STOP before ON, no ON
  directory created); ledger counts and 16-launch ceiling; no retry after a failure; dry-run creates no run directories.
- Guard-removal controls for the new v5 guards (IDENTITY checks, L2 re-derivation, L3, driver release/guard/exclusive-dir/truth/ledger), shadowed guards declared, not claimed.
- Real-path checks on cpu64 that launch no movie: `driver_v5 --dry-run` under lane.py validating the real pins, fixtures, baselines, tools, binary and guard receipts.
Every run, including failed attempts, is kept; no criterion is relaxed after results.

## 6. Not claimed
No native movie ran; no scientific, neutrality, harm, N5/9/13/20 or GPU result; no timing claim. Synthetic tests prove consumer/driver logic, not that the real binary obeys
it. The release remains conditional on one independent delta review commissioned by the parent before the first native producer. No merge, default change, full100 or adoption.
