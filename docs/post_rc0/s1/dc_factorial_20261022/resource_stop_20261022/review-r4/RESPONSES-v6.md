# R4 response: v6 implementation transferred to Codex, 23 October 2026

Implementation branch: `experiment/262-worker-v6-sol-20261023`.
Worktree: `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-334e8a36`.
Exact base: `c823cc630451411812406f35dd906b17197c3ed3` (normal new-branch checkout).
Final tested source: `f5946de124de13379766331bf4f7d2e6491d0bc2`.
This is proposed host-tooling repair, awaiting independent review and process controls. GPU readiness
is **BLOCKED**. The provider-bound real-worker suite is **UNRUN**, not refused or attempted.

Read the fetched Notion plan, AGENTS.md, post-freeze plan §9, CONTRACT-v5/v6, R1–R4 and preceding
responses, caller/admission and collision provenance. Refreshed #262 issue and both complete comments
before changing source; fresh copies are retained with the controls. No Claude calls or child agents.

## Transfer and commits

Copied only the supplied partial worker into the new v6 source path. Transfer provenance:
[TRANSFER.json](../gpu_worker_v6_controls/TRANSFER.json). Verified 39,012 bytes and SHA-256
`de3709767a39e0a49130648ce493190cb58e8f24055a3554ac3954c6cff3e72c` before copying.
The unfinished source was not treated as qualified. The original Opus worktree, its partial v6 and
its old `.lease` were not edited or used to launch anything.

- `dfce97f99607216e6300d1bb9ac6d18fde5189d5`: worker, versioned harness/runner, mutants and data checks.
- `15daad228ccc65fc5444eadd26082c5200307a5e`: explicit wrapper topology and embedded-fixture compilation checks.
- `1c0e4e864925347da20ed9a6a48add927c4d6e88`: fix one escaped newline after the retained static FAIL.
- `f5946de124de13379766331bf4f7d2e6491d0bc2`: worker docstring only; remove stale v5 receipt guarantees.

Final worker SHA-256: `df141c02d2432144f2cafb8cba3e703618ae8cbfee8361437f6ddfa628f1508c`.
The [transfer-to-final patch](../gpu_worker_v6_controls/transfer-to-final.patch) preserves the complete
byte-level source delta. All six final tool hashes and frozen-file hashes are in
[SOURCE-HASHES.json](../gpu_worker_v6_controls/SOURCE-HASHES.json).
The subsequent evidence/report commit is separate and changes no tool source.

## R4 findings addressed in proposed source

- **R4-1:** ignore TERM/INT/HUP and establish the holding state before receipt I/O; atomic writes
  use temporary file, fsync and rename. Receipt/RUN write exceptions stay in memory and have a
  guarded stderr fallback. Storage failure promises no files. After verified cleanup a record
  failure produces `RECORD_WRITE_FAILED`, exit 79; cleanup uncertainty still holds the lease.
  FINAL failure and activation-path storage failure also produce typed 79. The post-lease
  unexpected-exception backstop permits release only with zero launches/identities/unreaped queries.
  A successful launch is marked unverified before birth lookup; an interrupted cleanup cannot be
  mistaken for clean release. Query PIDs enter the unreaped set before their birth lookup.
- **R4-2:** K25a, K25c and K14R separately exercise initial refresh failure, third main-thread
  refresh failure (the first two succeed) and `own.errors`. Each has a distinct single-site mutant
  and requires root gone, recorded signalling and held lease. The old combined root-removal mutant
  is replaced by these three. The other four v5 targeted mutant specifications are unchanged.
- **R4-3:** no root polling/reaping before cleanup signals. The ownership helper does not reap roots
  in refresh/watch; `restore()` runs later. Fallback group signalling requires unreaped Popen root,
  recorded birth, worker parent, original PGID, matching SID and exclusion of the worker group,
  rechecked before TERM and KILL. Failed identity checks allow only the unreaped root handle;
  escaped descendants remain unresolved. K25W requires a real platform time wrapper, its binary
  child in the original group, no surviving same-group children, two surviving escaped children,
  and a held lease. Linux K25W/K5P additionally require `linux-child-subreaper` in RUN.json.
- **R4-4:** uncertain cleanup precedes record-write and outputs/witness stage errors. K32 and K32W
  combine uncertainty with each stage failure; K33 covers output hashing alone. The worker-level
  cleanup verification flag is an additional hold backstop, not a replacement for that ordering.
- **R4-5/6:** zero-job activation failure attempts FINAL; running SIGHUP cancels and held SIGHUP is
  ignored. SIGKILL, interpreter crash and power loss remain unavoidable lease-loss limits.

The worker/harness/runner are stdlib Python with GPL-2.0-or-later notices. No new dependency or
production algorithm/interface/default/gate/tolerance/policy adoption. CONTRACT-v5/v6, campaign.py,
process_ownership.py, v2–v5, previous reviews, receipts and historical verdicts remain byte-exact.
No src, root checkout, shared cache, old scratch or scientific result was changed.

## Evidence and retained failure

[Control packet](../gpu_worker_v6_controls/README.md), with exact commands, exits, source/input hashes,
resource preflights and four separate UUID namespaces:

- Final `f5946de1`: **PASS**, 14/14 data-only tests; **PASS**, 11/11 synthetic admission cases;
  **PASS**, K28/K30 data-only checks. Each command exits 0.
- Nine R4 mutants: **FAIL as expected**, each exit 1 on its corresponding synthetic check;
  all replacement targets are unique and compile. `unguarded_hold_receipt` fails via the injected
  ENOSPC escaping instead of reaching the mocked pause. These are synthetic discriminators, not
  the contract's process-level mutant campaign. The other four v5 mutant executions are UNRUN.
- Iteration 02 at `15daad22`: **FAIL**, 13 tests passed and embedded FAULT_ENTRY compilation failed
  on an unescaped newline. No job or worker process ran. Its raw outputs and source revision remain
  intact. Its mutant runs share that fixture error and are not used as discrimination evidence.
  Iteration 03 fixes the fixture separately; iteration 04 binds the final docstring source hash.

Host SCMAC-7L9P2F, macOS arm64, CPython 3.13.7, 14 logical CPUs. OMP/OpenBLAS/VECLIB numeric threads
were 1. Fresh occupancy/ancestry snapshot and nonblocking lifetime scratch lease for every iteration.
Final 1-/5-minute loads 3.72/5.69; no CPU pinning on macOS. Each scratch namespace was under 0.5 MiB;
all retained namespaces plus copied evidence remain well within 256 MiB. The post-run interpreter
hash is recorded separately; it was not captured per launch. No MotionCorr binary or movie input
was built/read/launched; device UUID and native route witness are N/A/UNRUN.

## Outstanding blockers and next bounded action

The actual ancestry was Python → Codex app-server → T3 → launchd, with no bound Claude owner.
PID 23920 was not an ancestor. No old UUID/PID/birth was supplied to the runner and its admission
was not weakened. Real-worker base/R3/R4 groups and targeted process mutants are **UNRUN**, leaving
root/group disappearance, independent flock hold, signal handling and the real time-wrapper behavior
unqualified. Data-only tests mock Popen, process tables and signals; none establishes those claims.

Parent: obtain fresh independent review of this exact source and controls. Decide separately whether
to authorize a minimal provider-neutral owner binding or arrange a genuinely admitted existing
provider context; no such amendment is adopted here. Only then consider the unspent single bounded
Mac suite, serial targeted mutants, fresh load ≤14 and the frozen nonblocking lease rules. The
runner reads controls JSON for verdicts, splits real-worker tests into base/R3/R4 groups ≤180 s each,
and stops on unexpected failure or missing results; `RAN`/runner exit 0 is not acceptance.

No Linux/SSH/build/native/real-SMI/GPU work was performed. GNU time, Linux K5P/subreaper execution and
all native qualification remain **UNRUN**; GPU work stays PAUSED. The namespace consumer remains
unimplemented and **BLOCKED**. Binary rehashing and campaign admission-lock scope remain out of
scope. Parent owns any publication, linking, external status, Notion update or later merge. No push,
PR, external comment, Notion write, main merge or tag was made. Motion-truth totals remain
2 PASS / 10 FAIL / 4 UNIDENTIFIABLE; #65 corrected workflow UNRUN, certification INCONCLUSIVE.
