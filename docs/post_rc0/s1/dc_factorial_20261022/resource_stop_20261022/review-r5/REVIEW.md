# Independent R5 review: DC worker v6

**Verdict: changes required. The supplied source/control combination is not ready for the prospective bounded Mac process suite, including from a genuinely admitted provider context.** This review grants no execution authorization.

Reviewed final `1fe458ecc33e9eb2e89f8617d6394854e7a5b6f2`, tested-tool source `f5946de124de13379766331bf4f7d2e6491d0bc2`, exact base `c823cc630451411812406f35dd906b17197c3ed3`. Author branch `experiment/262-worker-v6-sol-20261023`, worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-334e8a36`. Its HEAD and clean status were read back. The six tools are byte-identical between tested source and final evidence commit.

Reviewer branch `dc-worker-v6-r5-review`, worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-ab8909ee`, HEAD `1f0a58bf6e0639d8b62f74da52f250cc664c0b30`, unchanged and clean. No reviewer commit. All writes belong to this new UUID namespace, `inv-f02b09aa-12dd-4b6d-b34f-83d4671763fc`, under a nonblocking lifetime scratch lease acquired before exports or report writes. No author/root checkout writes, checkout changes, nested agents, pushes, PRs, comments or Notion writes.

## Findings

### R5-1 — P2: K22's old root stub makes the base harness abort

Exact final `tools/test_gpu_worker_v6.py:860-866` (under `docs/post_rc0/s1/dc_factorial_20261022/`) defines a fake `Root` with `pid` and `poll()`, then calls the new `terminate_owned`. That worker now calls `root_exited` at `gpu_worker_v6.py:293`, which reads `root.returncode` at `:215`. K22's fake root has no such attribute.

**Scenario:** a genuine provider passes frozen admission and the runner invokes its first `--group base` harness. `controls()` reaches K22 at harness `:569`. The uncaught `AttributeError: 'Root' object has no attribute 'returncode'` leaves `controls()` before it returns to `main()` (`:938`); the result writer at `:946` is never reached. The runner receives no complete `controls-worker-base.json` and stops failed/unrun at runner `:173-188`. This spends the bounded invocation on a deterministic fixture failure before the R3/R4 groups.

**Data reproduction:** `focused-probes-iteration02.py` calls the exact `k22` with process spawning and real signal functions forbidden; K22's group signalling is its existing in-memory lambda. Result: the exact AttributeError and traceback in `focused-probes.json`. A separate in-memory fixture-only counterfactual adds `Root.returncode=0`; the same K22 passes, retaining the own-group exclusion assertion (`late-error-and-k22-counterfactual.json`). No author file was changed and no fix was adopted.

**Bounded correction:** align this fake root with the unreaped/reaped interface used by v6; keep K22 discriminating. Exercise K22 itself as a data-only control before spending the prospective process suite. Merely compiling embedded scripts and passing K28/K30 misses this defect.

### R5-2 — P2: observer errors arriving during cleanup skip the original-group fallback

Exact final `tools/gpu_worker_v6.py:280-285`. `terminate_owned` checks `own.errors` only at entry (`:267`). If the background observer appends an error after that check, while the main-thread refresh succeeds, `:284-285` refuses group signalling and continues. Neither that path nor its subsequent iteration calls `signal_job_group`; the fallback is used only for an error already present at entry or a raised exception (`:269`, `:275`, `:290`). The frozen helper can append an observer error asynchronously at `tools/multi_gpu/process_ownership.py:365-367`.

**Scenario:** the time-wrapped job is still live at timeout/cancellation, the observer fails between cleanup entry and its group check, and the main thread can still refresh/read the recorded root identity. TERM and KILL are both refused; the root and same-group native child can continue running. `run_job` subsequently records cleanup failure and follows the lease-hold path (`:531-558`, `:648-649`). The lease remains conservative; the job-stop obligation is not fulfilled. CONTRACT-v6 requires the original-group fallback on observer-error ownership uncertainty, and this retains the R3-m2/R4-3 liveness failure for the late-error interleaving.

**Discriminating data reproduction:** `late-error-and-k22-counterfactual.py` uses a synthetic live root and changes only whether `Own.errors` becomes populated on the second refresh. Healthy control: two mocked group-signal calls (TERM/KILL), no errors. Late-error case: zero group calls, zero fallback calls, two refused-signal errors. No real PID, Popen, process group or signal was used. This demonstrates branch selection; actual job survival and kernel lease lifetime remain UNRUN.

**Bounded correction:** take the existing checked root-group fallback when observer errors appear during cleanup, preserving the uncertainty error and lease hold. Add a late-error discriminator that fails when this fallback is removed. K14R currently injects errors early enough for the entry branch, so it does not cover this interleaving. Any worker repair needs a new source identity and fresh independent review; do not edit frozen v5/v6 contracts or old evidence.

## Verified scope, responses and provenance

Read the full fetched Notion plan, AGENTS.md, release-plan section 9, exact frozen CONTRACT-v5/v6, full R3/R4 reviews and responses, full RESPONSES-v6, collision trust table, worker, runner, harness, admission/static tests and mutant specifications. Refreshed live #262 and both full comments; latest issue timestamp remains 2026-10-21T12:46:36Z, with two comments. The original R3/R4 report bytes equal their retained git objects. `VERIFICATION.json` records exact hashes and checks.

The transferred partial remains 39,012 bytes with SHA-256 `de3709767a39e0a49130648ce493190cb58e8f24055a3554ac3954c6cff3e72c`; the original author file still matches. Final worker SHA-256 is `df141c02d2432144f2cafb8cba3e703618ae8cbfee8361437f6ddfa628f1508c`. Harness SHA-256 is `0fe17877776351843eb1e2c71ce1cb8c349c047c26e2630595f81af0a037ccc0`; runner is `3ddbb3434666f41390810364c1c6f2587a683045896669e48ea2a070c566fec7`. All six source hashes match the author's SOURCE-HASHES packet and the scratch exports.

Frozen campaign.py, process_ownership.py, CONTRACT-v5/v6, v2-v5 and named v5 controls match exact base. The base-to-final source/control diff is confined to new v6 host tooling and retained evidence/docs under the DC experiment tree; production src and top-level tools do not change. New executable sources carry GPL-2.0-or-later notices and use stdlib plus in-repository helpers. No additional scope or licence finding.

The principal R4 I/O repair is visible: hold state/signal disposition precede receipt I/O; write fallbacks are guarded; failed writes after verified cleanup become typed 79; query/job unresolved state precedes birth lookup; cleanup uncertainty precedes output/witness stage errors; activation FINAL and HUP handling are present. These are static/data observations. No real filesystem-to-live-job failure, process disappearance, time-wrapper, kernel lease or native cleanup claim is qualified here. R5-2 limits the claimed complete observer-error repair.

## Checks and retained outcomes

All commands use `/Users/alex.konstantinov/.local/bin/python3 -B`, OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=VECLIB_MAXIMUM_THREADS=1, and TMPDIR within this UUID namespace. Let N be this namespace and T be `N/exact/docs/post_rc0/s1/dc_factorial_20261022/tools`.

- `python3 -B T/test_v6_static.py --json N/static-units.json`: exit 0, **PASS 14/14**. Synthetic Popen/process tables/signals only.
- `python3 -B T/test_run_v6_admission.py --json N/admission-units.json`: exit 0, **PASS 11/11** synthetic admission cases.
- `python3 -B N/focused-probes-iteration02.py`: exit 0; K28/K30 **PASS**, K22 **FAIL** caught and retained with traceback; late-error branch probe retained. Calling only `r3_controls(...,['K28','K30'])` avoids the process harness and even its signal-handler installation.
- `python3 -B N/late-error-and-k22-counterfactual.py`: exit 0; K22 in-memory fixture counterfactual **PASS**; live-root healthy/late-error comparison discriminates R5-2. Exit 0 means the diagnostic script completed, not that the reviewed source passed.
- All 13 declared mutant replacements are unique and compile in memory (`MUTANT-STATIC-CHECK.json`); none was executed. No full matrix or process-level mutant campaign was repeated. Author final nine synthetic rejections are retained as author evidence in `author-mutant-records.json`, with no process credit.

Reviewer probe iteration 01 (`focused-probes.py`) is retained as **FAIL**, exit 1: an unterminated string literal in the reviewer's driver stopped parsing before any probe ran. `probe-iteration01-FAIL.json` records it; iteration 02 is a separate script, and the original failed script was not repaired in place. This does not alter any author result.

Author static iteration 02 remains **FAIL**, 13 passing tests and one embedded-fixture compile error, no jobs. Its mutant outcomes retain zero discrimination credit. Iterations 03 and 04 remain separately retained; final 14/14, 11 admission and K28/K30 PASS claims are reproduced within their data-only limits. v4 overlapping attempts 34-37 remain **UNTRUSTED**. Original R4 Mac GO was source-only; the actual process suite remained UNRUN.

Host SCMAC-7L9P2F, macOS 26.7.1 arm64, CPython 3.13.7, 14 logical CPUs. Fresh preflights are retained. Before the two baseline data checks, loads were 6.29/6.01/5.48; numeric threads 1, no CPU affinity on macOS. Post-check interpreter SHA-256 `127b5dc839447e76f0ed6a6c3b3097dc7903547d2f1a1fe21d7fc40c20b7bc65` is an observation after checks, not a per-launch measurement. Scratch is below 1 MiB before final report/hash inventory, far below 256 MiB. Inputs are exact source/control files and small synthetic data. No MotionCorr binary or movie was built, read or launched; device UUID, native route witness and native build/runtime options are N/A/UNRUN. No timings are qualified.

## Unresolved blockers and recommended next action

Return R5-1 and R5-2 to the existing author context for narrow new-source repair and discriminating data checks, then obtain a fresh independent delta review. Preserve this review, the failed controls, contracts, prior attempts and original source. Do not spend the full process suite on this exact harness.

The frozen runner requires a genuinely bound exact --resume owner in its ancestor chain. This Codex ancestry cannot satisfy that rule. No old Claude PID/session/UUID was supplied, no admission rule was weakened, and no runner invocation was attempted. A provider-neutral amendment is a separate prospective change requiring its own authorization/review; none is implemented or adopted here. A genuine-admission process suite is still UNRUN and its authorization remains unspent.

After the bounded repairs and fresh review, the parent can decide the provider-binding disposition and any later single bounded Mac process run with a fresh load/lease preflight. This review is not execution authorization. Linux fake-SMI/subreaper/taskset/GNU-time qualification remains UNRUN; the namespace consumer is unimplemented and BLOCKED; GPU work remains PAUSED. No merge or native/science/performance recommendation. Historical truth remains 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE; #65 corrected numerical workflow UNRUN, certification INCONCLUSIVE.

The artifact whitelist is HASHES.txt and excludes itself. Source and checkout state checks, exact input hashes, live context, commands, failed and successful data outputs are retained in this invocation only.
