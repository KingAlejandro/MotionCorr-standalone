NO MATERIAL FINDINGS — bounded CPU capture GO

Exact reviewed candidate: fb5b0b05db8729170ebedb180baef9955812ca42
Author branch: diag/affine-patch-oracle-20261022
Author worktree: /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c3dca0d
Reviewer worktree: /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-86e208e7 at 1f0a58bf6e0639d8b62f74da52f250cc664c0b30
Reviewer UUID: 970ae955-5464-4e8c-836d-db336987aaca
No reviewer source edits or commits. Both worktrees remained clean. No root-checkout operation.

Decision

No material static/data-only defect blocks the parent's ONE fresh iteration-2 CPU-only campaign: at most eight serial selectors, CPU13, retained #275 binary, unchanged argv, no retry, stop on first failure/mismatch. This is prelaunch review, not native acceptance or a merge recommendation. Parent must reserve CPU13, acquire the nonblocking CPU lease, refresh occupancy/free space, and verify the actual remote source/binary/input/archive pins at launch. The prior resource snapshot is not a reservation. GPU remains paused.

Scope and controls

Read the full fetched Notion plan, AGENTS.md and exact-revision POST_FREEZE_TEST_PLAN.md section 9; protocol freeze7d203929, cleanup amendment0a4ef2ce, frozen iteration2b9bfcb5c, both drivers/suites/results and retained iteration-1 failure. Read relevant #238/#198 discussions and refreshed the live #238 latest checkpoint, #198 resource-policy comment6244279982 and #278 published context. Exact fb5b0b05 is local/unpublished (GitHub commit lookup422); no current-head CI is claimed.

All changes since22675db7 are confined to the assigned cpu_lattice_capture_20261023 subtree. V1 driver, suite and retained results are byte-identical to f73eb930. V2's driver delta only replaces the nonexistent diagnostic.patch archive-member check with four bounded regular patched-source members.

capture_cpu_v2.py lines38–60: count/set checks reject missing/extra/duplicate names; type/positive size<=1MiB and content hashes are checked without extracting files. Protocol src/src/... -> archive src/... is correctly implemented by n[4:]. The resulting mapping equals #275 overlay-binding.json and the retained archive-member inventory. Whole source/overlay archive and live four-source pins remain in identities(). The Git-retained diagnostic.patch SHA was independently verified; no empty tar or missing patch member is credited.

lines130–179: host/UID/CPU13 checks, canonical fresh campaign/result admission, nonblocking lease, same-user MotionCorr overlap refusal, minimum free space, before/after identity checks, fixed selectors and launch ceiling remain intact. The parent must use a fresh namespace and launch the driver itself under CPU13; child affinity inherits and is checked. Numeric environment is one thread, CUDA_VISIBLE_DEVICES empty, diagnostic/CCF/CUDA inherited variables cleared as frozen. No GPU argument/query is present.

lines181–217: Popen creates the private session/group before exec. Initial /proc birth/affinity/PGID/SID reads precede any poll/wait, so an ordinary fast exit leaves an unreaped child rather than making its PID immediately reusable. Timeout/exception cleanup targets only that owned group and has bounded waits; a failure stops the loop. Native timing/race/cleanup paths were not exercised here. ROOT_REAPED proves only direct-root reap, not arbitrary escaped or TERM-resistant descendants. The retained program's PDF calls use synchronous system(); this bounded review found no concrete detached-descendant scenario requiring a framework expansion. Receipt-I/O failure, forced reviewer/driver termination, and hostile process behavior are not qualified.

lines89–126,218–237: exact global/model state and affine.log; all STAR/MRC/MRCS inventories; STAR bytes with only output-prefix replacement; exact MRC header/payload with only the frozen label timestamp regex normalized; c1 global/c2 selected local tag/call/frame metadata and nonempty arrays. No tolerance change. Capture completeness beyond the frozen metadata/nonempty-array contract is for downstream admission; no fit is run here. Scratch cap is checked between/after jobs, not an OS quota; the frozen proposal estimates about2MiB/job, well within64MiB for eight tiny jobs. No native peak-storage proof is claimed.

Independent execution (Mac static/data only)

Occupancy checked before data work. macOS26.7.1 arm64,14 logical CPUs; OPENBLAS_NUM_THREADS, OMP_NUM_THREADS, MKL_NUM_THREADS, NUMEXPR_NUM_THREADS, VECLIB_MAXIMUM_THREADS all1. No affinity API is available on this Mac; no remote CPU13 use is claimed. Nonblocking review lease held through review writes; own UUID scratch only, cap64MiB.

Exact Git objects were copied to exact/. Commands (full argv/exit receipts in review-controls.json):
/Users/alex.konstantinov/.local/bin/python3 -B exact/check_driver_v2_data.py /tmp/mc-residual-review.h52lh3/raw/runs/cpu-affine-on v2-controls
PASS:18/18 expected, exit0 (six archive and12 neutrality/selector cases).
/Users/alex.konstantinov/.local/bin/python3 -B exact/check_driver_data.py /tmp/mc-residual-review.h52lh3/raw/runs/cpu-affine-on v1-controls
PASS:12/12 expected, exit0.

Read-only local retained fixture MANIFEST, affine.mrcs/.star/target/field and baseline global/model/STAR/MRC files match the frozen protocol pins; affine.log matches793124b035353e0c5e45d68ac6bfbf2b97516c5fff7f936c00a6cb1b84955dd4. Full individual hashes are in review-controls.json. Git source/overlay binding hashes, patch hash, inventory mapping and scope/immutability controls all passed (binding-controls.json). Remote binary/live sources/archives were not accessed or rehashed by this reviewer.

Review identities

V2 driver SHA256:884e7424fbb49d1c887301129a20f29ae89467839defcd919810bfa1f17bf1b2
V2 suite SHA256:b4428d6a014051ae7d3326f87ab1d9473c9606daaba81f355049a4cff7f90b6e
Protocol SHA256:c2e7712bb4c16bf4a4e80ce69694177e0961e0a8a608b5e8d62ae217693db15f
Pinned CPU binary SHA256:778ca7d5fd4ff70bb7162598940ae6a60a12afa0f6cb129a13eca7d46dfb5df1
Pinned source archive SHA256:1df4099244aca2b09a59df39c732f94640dfcf1fae9c3ca18b390dd669b9d8dc
Pinned overlay archive SHA256:655e7fe72adeafb0d5273fe54bc478d818255c30607e3c1875048f03c6ee386c
Git-verified overlay patch SHA256:061c5c5be6b427cb6643605ac1473e21beeb9e45fea1bd022500eec651a787e4
Fixture MANIFEST SHA256:9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc
Affine input MRCS SHA256:1cf918d5da48d4c746020983017222829db9c949e362d07169a823bdc118260a

Retained outcomes and limits

Iteration1 remains FAIL_ADMISSION, zero native launches, no campaign/result directory created by that driver; retained trace/log/readback/archive inventory support the nonexistent-patch-member cause. A later raw-tar collection failed SSH banner255; its empty tar is uncredited and full old namespace remains remote per retained record. Reviewer did not independently inspect that remote namespace.

No SSH/native/build/process mock/SMI/GPU/signal operations, nested agents, push, PR publication/linking, GitHub comment, Notion write or cache claim. No new dependency or license change; drivers retain GPL-2.0-or-later headers. No GPU UUID or native ingest witness was collected because no native work was run. Native capture/runtime cleanup, fit, GPU, timing and science are UNRUN. Historical motion truth stays2 PASS/10 FAIL/4 UNIDENTIFIABLE. No accuracy fix or policy/default/gate adoption.

Next bounded action: parent may run the frozen iteration2 CPU capture once after fresh resource admission, retain every exit/hash/neutrality result and stop on first mismatch. Downstream fit/oracle admission and any additional/native iteration require their own bounded decision. No minimal source fix is requested by this review.
