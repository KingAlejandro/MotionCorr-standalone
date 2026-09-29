# PR117 final scheduler fixes on current main

Final source: `75a6296` (the review consistency fix on `881daa17763c4f4a1099fd7ad13adc2e2e0165a7`), based on the existing
`3a1a9ef` merge of PR117 `4392871` and main `a75a3f8`.

## Preserved work

The checkout already contained four dirty scheduler/test files from
29 September 00:29-00:38 local time. Their original author/session was not
established; none of those edits was reset or discarded. The inherited diff
was saved before changes; SHA256
`4c364347a746f08a0ba4bce7f6b65d7d5c0a7d7efcdba3911508b6dccdb33097`.
Those edits addressed the four Codex findings on `4392871`: content-bound
comparison reuse, aggregate STAR identity, complete native GPU witness, and
launcher termination handling.

Two further defects reproduced before fixing (logs retained here):

- An extra aggregate `--i` selected changed optics while the tool verified the
  original STAR; the old merge returned PASS. Aggregate-owned `--i`/`--o`
  arguments are now refused before staging.
- Blocking SIGINT/SIGTERM around Popen left those signals blocked in the child
  across exec. A cooperative TERM handler was never reached. The Python
  handler now defers an interrupt until ownership bookkeeping completes,
  without blocking the child OS signal mask. Tests separately prove
  cooperative TERM, TERM-ignoring descendants, and interruption immediately
  after child creation.

Five old mutation anchors had become stale. The initial failed run is retained
as `local-mutations-first.*`; all five were re-anchored to their corresponding
guards. Eleven new mutation controls target the current review fixes. Root review then
found that a witness could be relabelled as CPU by removing its intended-device
list. `75a6296` refuses both missing and null device lists when a witness is
present, with one additional mutant and two altered-status controls.

## Verification

- Local macOS scheduling: 52/52 Python cases PASS. The actual binary check was
  not selected locally; CPU affinity and Linux RSS require the Linux run.
- Local new mutation controls: 11/11 detected.
- Linux `881daa1`: fresh Release CPU build, 53/53 scheduler cases, 80/80
  mutations, collection 19/19, CTest 19/19, real serial/three-worker 6/6 exact.
- Linux final source `75a6296`: 53/53 cases, **81/81 mutations with zero skips**,
  collection 19/19, **CTest 19/19**, real serial/three-worker 6/6 exact, six
  distinct image payloads and identical normalized aggregate STAR. The delta
  changes Python only; `git diff 881daa1..75a6296 -- src CMakeLists.txt` is empty,
  so the same hashed CPU binary was used.
- Both Linux runs held `/tmp/motioncorr-issue96-cpu-validation.lock`, CPUs32-47
  (16 logical CPUs), NUMA memory node1, build16 and sequential CTest. The two
  existing ctffind PIDs1156942/1635429 were unchanged; no owned jobs or lock
  remained after completion. Exact commands, binary hash and provenance are in
  `cpu64/validation.log`, `cpu64/review_delta.log` and `cpu64_review_delta.sh`.
- Retained-native regrade at final tooling: **24/24 primary pairs**, all 24
  MRCs present in both retained arms, full normalized headers, per-movie STARs,
  content-bound reuse PASS and same-size/same-mtime pixel mutation refused.
  Merge PASS over 96 files with the actual stored two-UUID witness. The MRC
  inventory is exactly 24; this run does not cover PS/even/odd products.
  CPUs110-111/membind1, numerical library threads1, separate regrade lock.
  Native compute source remains `a48c7f5`; no CUDA binary or GPU query was
  executed. Aggregate STAR was not regenerated in this retained-native step;
  current aggregate behavior is exercised by the real CPU arm above.
  Original native trees were left intact; the single-pixel mutation affected
  only a new staged copy and was restored in a finally block. Positive reports
  and the expected 23/24 FAIL are retained in separate directories.

No native GPU computation or throughput experiment is performed by this
change. Historical native results retain their original source and resource
provenance. Final independent source review and pushed-head CI remain separate
requirements. No merge is authorized by this report.

## Remaining acceptance

The local branch is not pushed and current-head GitHub CI is therefore unrun.
Root reviewed the focused source delta and its consistency finding is fixed.
Final review confirmation is required before a merge recommendation. The C++
CLI hunk retains its earlier native compilation/24-movie evidence, but a fresh
CUDA build at this composed main has not been run in this task. No scaling or
throughput claim is made. More than two devices, PS/even/odd output modes, EER,
gain rotation/flip and heterogeneous-movie load balance remain unrun here.

## Raw artifacts

Raw logs and JSON comparison reports are preserved in `raw-evidence.tar.gz`.
`SHA256SUMS` identifies each original archive member and the compact archive.
The two before-fix failures and replay scripts are also readable beside it.
