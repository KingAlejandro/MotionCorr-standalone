# R2B author repair v2.2 — 23 October 2026

Prepared for a fresh independent exact-head review. CPU13 remains **HELD**. Full remote
regrade **UNRUN**. This is a new author iteration, not a revision of any failed record,
production guard approval or a merge recommendation.

Worktree: `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-d9b98408`.
Branch: `verify/264-regrade-v22-sol-20261023`, selected from exact assigned base
`5dc412c346edb8fd774795dfb49b727391e8efd9` within the supplied parent-1f0 worktree.
The author tree `t3-96f54dde` and protected Documents checkout were not changed.

- `614e8184`: AMENDMENT-2 freeze, before implementation/controls.
- `785e6e4a`: additive grader/packer/prospective driver/plan.
- **Tested source** `dd38b6ad5a67d6aace726d38503b206125752d4e`: adds the focused suite.
- Later evidence/README/response/checksum commit(s) are summary only. The four new
  Python files and plan remain byte-identical to the tested source. No native source,
  tests/, tools/, build, gates, defaults, contracts, old plans or evidence were edited.

R2B is retained verbatim at `review-r2b/REVIEW-R2B.md`; referenced reviewer control
source/results are hash-bound in `review-r2b/RETAINED-REFERENCES.json`. R1 is unchanged.
Issue #264 was refreshed live before edits (open, zero comments, last update
2026-10-21T07:46:04Z; same body as supplied snapshot); the full fetched Notion plan,
AGENTS and post-freeze §9 were read. This iteration follows the separate regrader brief,
not production adoption of the original FILE-ONLY issue.

## Repairs and discriminating controls

**F1. Private Git index, not optional-lock semantics alone.** The original input index
is only opened read-only and copied (<=1 MiB) to a temporary sibling of the output.
Every fixed `/usr/bin/git` child gets that explicit private GIT_INDEX_FILE and optional
locks off. Fixed command options disable fsmonitor, caches, split index, hooks, auto
maintenance, external diff/textconv; caller Git environment/global/system config is
not inherited. HEAD/diff/status/runner/helper and live binary/receipt/EXPECT comparisons
remain. Original index hash and device/inode/size/mtime/ctime are recorded around every
Git call, plus overall; atime is excluded because reads may update it.

Fresh five-tree controls passed with Apple Git 2.54.0 and Homebrew Git 2.56.0, both
clean and stale-index cases. Four cases × 15 actual Git children had the private-index
environment. Full fixture inventories (all original file hashes/stats) stayed equal.
A simulated metadata refresh of the selected private index leaves originals unchanged,
exit 0. Its separate coherent redirection-bypass mutant refreshes the isolated original
index and is refused, exit 1. An original-index mtime injection separately triggers the
index guard, exit 1. These injections affect only newly created case fixtures.

This discriminates the new procedure. It does **not** explain R2B's unexpected index
change: both old failed positives remain FAIL, cause unresolved. No old fixture was
rerun and no Linux no-write PASS is claimed.

**F2. Bounded, stable streaming.** `hash_stream` limits each request to remaining cap +
one byte, rejects cumulative growth, and checks final open-file and pathname stable
identity plus exact original length. A fresh 4-byte/cap4 input grown to 8 is refused
at 5 bytes read, exit 1. Removing only the cumulative check still gives exit 1 via
identity, a **diagnostic-only** detection. Removing both checks accepts size5, exit 0.
Same-size-write and pathname-replacement cases reject exact/accept identity-check
mutant (1→0); an independent restored exact input passes. These are tiny instrumented
local controls, not large binary or Linux observations. No same-stat adversarial race
proof is claimed.

**F3. No ancestor exemption.** Only self is skipped. The prospective driver calls all
prechecks in-process; ancestors carry only sibling package/output paths, never S as
a complete pathname. Thus neither an ancestry allowlist nor substring command
allowlist is required. Path boundaries recognize descendants/`--input=S/file` while
permitting the sibling output prefix. Fake-proc controls detect active parent and
unrelated writers, cwd/fd references, permit self and the exact prospective
SSH/bootstrap/driver command shape, and permit the sibling namespace. Restoring the
parent exemption hides the parent writer, a refusal-verdict-changing mutant. No real
/proc inspection, SSH or process execution was used; inaccessible Linux process data
is retained as a limitation, not proof of universal writer exclusion.

**F4. Measured narrow package and executable prospective driver.** The local packer
reads nine exact committed blobs; no bundle/full clone. At tested dd38b6ad the archive
is **122,880 bytes**, content **103,273 bytes**, under the 1 MiB content/archive caps.
The receipt binds commit, paths, Git blob IDs, sha256/size, package and manifest hashes.
Pure package verification passes and fresh driver/manifest/source tampering rejects.
Package sha256: `18f53e52c7c46d13a7f0222a466d2dd67b1928a4b75980453a6b1e8ed9f5baa2`.

`REMOTE-PLAN-v2.2.md` now matches `remote_run_v2_2.py`: one new namespace outside S,
nonblocking lifetime lease, exact CPU13/one-thread verification, Python/version and
executable/script/package pins, fresh CPU13 occupancy sample, live/files prechecks,
grade, live/files postchecks and identity comparisons, atomic receipt, external 180s
deadline, no retry. Private paths are ignored by comparison; original-index changes
reject in pure controls. Fixed output set, 1 MiB per-file limit and <=2 MiB initial
namespace keep the operation below the 20 MiB cap. All actual Linux runtime steps are
**UNRUN**; package/compare controls do not qualify runtime lease, affinity or SSH.
Parent must build a new package from the final reviewed commit; the dd38 package is
a measured author control, not authorization to execute it.

## One retained local campaign

Exact command (one invocation, no retry; exit **0**):

```sh
env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/alex.konstantinov/.local/bin/python3 -I -B docs/post_rc0/issue264/native/n3-cpu1-regrade-v2/test_regrade_v2_2.py --namespace /private/tmp/motioncorr-guard264-v22-author-5d60fd8e-3da5-4d96-84bf-60ab511fdb90 --source-commit dd38b6ad5a67d6aace726d38503b206125752d4e
```

**45/45 control records as intended**, not 45 native tests. No unexpected experimental
failure; intended refusals and mutant outcomes are retained. Each independent case
gets fresh inputs; mutants start from the same frozen source, and the original source
hash is checked unchanged at completion. No failed case was repaired or rerun. The
private-index bypass and index-injection fixtures intentionally mutate their own
original index, documented with before/after inventories. No retained author or
reviewer input was mutated.

Numerical AST is exact for coefficients/global_rows/rows_equal/mrc_check/grade/snapshot/
consumed. The real retained tar is read in place: STAR **PASS**, FULL **UNRUN**, exit 2,
117 consumed identities, exact old-row parity, N4 PASS. A generated full MRC directory
passes exit 0; synthetic header-only/symlink inputs reject; snapshot injection rejects
exact (1) and accepts reread mutant (0). These synthetic products are not native outputs.

Primary records under `evidence-v2.2/author01/`: CONTROLS, runtime/launch/occupancy,
exact live reports and full original-fixture inventories, retained-tar result, selected
regression reports, measured package receipt and `ARTIFACTS.json` hashes for all 3,315
files in the original local namespace. Large generated products and input corpora are
not copied into Git. Native binaries were not executed; their recorded hashes remain
in the retained-tar report, while live-binary controls use tiny synthetic bytes.

Runtime: macOS 26.7.1 arm64, Python 3.13.7, five numeric-thread variables 1, nonblocking
local lifetime flock. No macOS CPU affinity claim, no timing claim, no GPU UUID or
route witness (no native/GPU/build/SSH operation). Initial load 7.04/7.10/6.07, free
8,502,157,312 bytes. UUID invocation `9398ff97-f0e3-4d10-b79b-749112e43ac5`. PID/UTC/
exit receipt retained; child reaped. Namespace ~106.74 MB logical, under 512 MiB cap;
selected durable evidence ~2.15 MB. Unrelated processes and old archives were preserved.

Final scope audit: the first assertion mistakenly counted committed additions as old
files and failed. `FINAL-AUDIT.json` retains that audit failure and the corrected
base-file intersection: only the permitted README addendum modifies an old file.
The 45-case campaign was not rerun and no tested source changed.

Full hashes:

```text
grader      036aa9a2f3c9b0cc49055f63b2c9bd32770a5e4f7832a18452b5480ba6820849
driver      07263bb9bc57fd9e6ba9ad900818c18153a6f8022a793fe99f408446ae670b32
packer      7df36524cfb3117c0a6da01f2284703c3a7ca6f02a92ec0fc357037e39c75f70
suite       205027aba2b0c2cacc3acb33a2f8473253e114cd7bb3a4db34df09e1890a5da7
amendment   74d46b46dfb1a74705f58510696c92802a8a321dc5a59baef2b45b0060681a88
retainedtar 3cc13020d35aaf7113fe16878e8eb63c11652863fd73c0da3974fc7fa09f2760
predictions 6ff11cb5145f3c9f3f0c6380de26b27913eb9da7ccb6652a783c777b205c859e
EXPECT      e12a2199011d9a1485b699e7e449dd6b02a63f8772a37da3f955ef68514a4359
manifest    6bdc14cc25a6361d8ab86f1c0e7edbb05be2099a9c7ed78a337ee8dda5992ed6
receipts    e178e99fa232a785c4758fa25acfae4c43d6266c2609d02570942310fdaabf33
oldresults  1e027cef5950721b3d8299182f279abb314bde9e8d2353df1f7be252b6f18052
```

## Historical limits and handoff

All 25 old files in the assigned subtree and all 15 v2.1 checksum entries matched
before the permitted README addendum. All old artifacts remain exact. R2B's numerical,
old-row-parity/N4/MRC/ASCII/symlink/snapshot conclusions stand. Its frame12/reread/index
controls closed those review gaps; that is retained review evidence, not a claim of a
fresh full matrix here. v2.1 65/65 author controls and contaminated 33-mutant campaign
stay unchanged (`all_consistent: false`): 19 declared detections comprise 12 exit-changing
and 7 diagnostic-only, with 5 equivalent, 4 redundant, 3 originally untested and the
2 wrong declarations. The additional contradiction detection is diagnostic-only.

Original native subset **FAIL**, 24 CPU rows **PASS**, pairs **3 PASS / 5 FAIL**, N4
**PASS**, 16 CUDA **UNRUN**, aggregate **INCOMPLETE** stay. Full remote grade, genuine
native MRCs, Linux Git/index behavior, real process/SSH ancestry, CPU13 allocation,
affinity, lease and before/after runtime checks are **UNRUN**. Motion-truth **2 PASS /
10 FAIL / 4 UNIDENTIFIABLE**, #65 corrected workflow **UNRUN** and certification
**INCONCLUSIVE** remain. Printed precision only; not full-forward-double truth. No
production guard safety, accuracy, performance, CI or merge/adoption claim.

Outstanding: fresh independent review of the final exact head; parent scheduling and
explicit CPU13 release/authorization; the one future read-only operation; carried
non-finite-model and maintainer parity sign-off findings. Recommended next action is
that review, including adversarial package/launch and original-index isolation checks.
No pushes, PRs, GitHub/Notion writes, nested agents or remote jobs were performed.
