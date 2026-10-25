# Proposed controller ownership v1 — design only, 23 October 2026

Status: **PROPOSED / NOT ADOPTED**. Start `c7953a467e4225bcacfdd1e8717680eb64b43a0b`;
read the retained R6 NO MATERIAL FINDINGS and PARENT-v6.1-CHECKPOINT. v6.1 tested source remains
`2f32e7be`, final `52ad29a1`. All runner/worker/contracts/evidence stay frozen.
This proposal grants no process-suite execution permission.

## What can be established now

The three successful own-ancestry observations identify the same Codex `app-server`, PID 58401,
UID 502, birth `(1792750711,394411)`, executable under ChatGPT's CodexCLI bundle, cwd the user's
home directory. Different short-lived inspection/tool processes have that same parent. Thus the
host is **reused across separate tool calls**. Whether it concurrently serves other logical threads
is **UNPROVEN** within the permitted own-ancestry scope; no other thread's process was inspected.
Do not claim task exclusivity, or invent a confirmed cross-thread sharing result. Treat the host
as potentially shared for admission. Its PID/birth identifies a host, not the suite's owner.

The current tool env supplies equal public CODEX_SESSION_ID/CODEX_THREAD_ID and a changing
CODEX_TOOL_CALL_ID. T3's read-only route independently supplies this exact delegated thread's public
thread/run/project/provider/worktree metadata. The inspected ancestry has no exact argv token
matching those Codex IDs or the public T3 thread/active-run IDs. No T3-prefixed env key is present.
These observations establish public logical labels and worktree association, **not** a unique
persistent OS controller or a trusted binding from the provider host to this one active author.
The inspection helpers themselves are unique but exit after a read; they cannot own a later suite.

There is also a branch spelling discrepancy: actual Git branch is
`experiment/262-worker-v6-sol-20261023`; T3 metadata reports `262-worker-v6-sol-20261023`.
Never silently strip the prefix. Parent must approve this exact alias pair or obtain corrected
metadata before a later binding can be accepted. Canonical realpath and exact Git HEAD remain required.

## Recommended mode A: app-attested, per-attempt controller

Proposed contract identifier: `dc262-controller-binding/v1`. This requires a trusted T3/parent
launcher facility **not established by the currently inspected public metadata/tools**. Do not
implement an env-only fallback if that facility is unavailable.

The trusted launcher must attest the following immutable tuple after creating a dedicated
controller and before allowing any harness, mock, query or worker launch:

- Authority: exact T3 project/thread/active-run IDs, provider instance, provider thread/session ID,
  fresh attempt ID and monotonic ownership generation. IDs stay opaque; no substring matching.
- Controller: host identity, UID, PID, OS birth, canonical executable path and file identity/hash,
  controller script hash, fixed cwd and observed parent/ancestor PID-birth-executable chain.
  The controller must be the runner's actual ancestor. The shared app-server is only a recorded
  ancestor; its entire process family is never exempted as owned.
- Worktree: canonical realpath, directory device/inode, Git common-dir identity, full branch name,
  exact approved HEAD, and the approved raw T3/Git branch pair. Resolve symlinks and refuse drift.
- Inputs: exact worker/harness/runner/mutant/helper/admission/contract hashes, explicit control set,
  serial order, expected output schemas, bounds, scratch cap and immutable snapshot digest.
  Bind the same hashes again before launch and in every receipt; retain originals on mismatch.

Public IDs and JSON supplied by the agent are claims, not authority. The application/parent must
independently bind its authenticated task/run routing and actual launch receipt to that OS tuple.
Pass a read-only, inode-bound receipt descriptor over an app-owned parent-child channel; verify the
issuer, generation and actual controller identity. Copying a JSON file or argv marker must not grant
ownership. This is a cooperative lifecycle protocol, not containment against a malicious same-UID user.
A particular transport/issuer implementation requires separate selection and review.

Before any launch, the issuer must prove **one live author execution**, not merely one logical
T3 activeRunId. Its census must cover duplicate provider connections/executions and unreconciled
orphan instances for the same task/session, including copies outside the controller's descendants.
If the app cannot account for an orphan, refuse. Immutable inputs do not replace this original
collision protection. The existing Claude mode's exact-token/orphan checks remain untouched.

## Lifetime lease and refusal sequence

1. Independently verify issuer/task/controller/worktree/input tuple and the active ownership generation.
   Invalid, stale, replayed, unreadable or ambiguous evidence refuses before jobs or queries.
2. Take one stable, private, host/UID/campaign-wide **exclusive nonblocking controller lease** shared
   across all local DC control versions, threads and worktrees. A fresh namespace cannot bypass it.
   Check the lock directory/file UID, modes, device/inode and symlink absence; never unlink/replace
   a busy lock. Per-attempt directories remain unique but do not define the exclusion domain.
3. Refuse any duplicate author registration, foreign live control/controller, unreconciled attempt
   or concurrent controller, even if it shares this app-server. Exempt only helpers whose recorded
   PID/birth/ancestry is actually under this exact controller. Disconnected/unclassified state refuses.
4. Recheck issuer generation, identities and immutable hashes immediately before launch. Require both
   1- and 5-minute load averages **<=14**, fresh occupancy/space, numeric threads 1 and the existing
   bounded scratch policy. No waiting/retry/admission loop. Preserve the <=180 s harness bounds and
   serial targeted mutants; controls JSON remains the verdict, not runner `RAN` or exit 0.
5. Controller retains the same open lease through final health, identity-checked cleanup, reap,
   receipts and closeout. Loss of author heartbeat/generation stops new launches and takes existing
   bounded cleanup; ambiguity holds/refuses instead of handing ownership to another task.
6. Unknown cleanup keeps the lease and an unreconciled durable record. SIGKILL/interpreter crash can
   still drop flock; it is not crash-proof. A persistent RUNNING/HELD record fences a new admission
   after such death until parent independently reconciles owned identities. No stale-file deletion,
   guessed signals or automatic takeover based only on an expired PID/heartbeat.

No runtime lease or identity protocol above has been implemented or exercised here. A later
implementation must define and review the authoritative registry and crash/replay transitions.

## Bounded alternatives and parent choices

**B — dedicated provider context:** explicitly migrate the task to a genuinely isolated, single-task
Codex provider process under a trusted launcher, with public session/task binding, independently
verified PID/birth/executable ancestry, exclusive lifetime lease and duplicate/orphan refusal. Prove
that it is actually single-task and fence the prior execution; adding flags/env labels to today's
shared/potentially shared host is insufficient. Availability and lifecycle are UNRUN, and migration
needs parent authorization. This may avoid depending on a multiplexed-host attestation API.

**Hold:** if neither A's issuer/census nor B's dedicated ownership can be proved, keep the suite
UNRUN/unspent. A manually declared quiet window, same UID/cwd, copied thread ID, app-server ancestor
or controller-only lease cannot silently substitute for author uniqueness. An operator-owned mode
would be a separate explicitly selected policy with its own protections and review, not this design.

Parent choices: select A or B (or hold), specify the trusted issuer/census/transport and reconciliation
owner, and resolve the branch alias. Only then freeze an implementation amendment, independently
review it and obtain separate process-suite authorization. Prospective discrimination must cover
shared-host foreign controllers, duplicate/orphan authors, copied IDs, PID reuse/exec/cwd drift,
replayed receipts, changed hashes, lock contention across worktrees, controller death and unknown
cleanup. These are required future controls, all UNRUN today.

R6's source/data-only result stands. Process suite UNRUN/unspent, Linux UNRUN, consumer
unimplemented/BLOCKED, GPU PAUSED. No worker/control/mock process, signals, SSH, native/GPU, external
write or gateway retry was performed. Historical truth 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE and
#65 corrected workflow UNRUN/certification INCONCLUSIVE remain unchanged.
