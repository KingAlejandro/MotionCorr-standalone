# Independent R6 delta review: DC worker v6.1

**NO MATERIAL FINDINGS. Ready, within source/data-only review limits, for consideration of the prospective genuinely admitted bounded Mac mock suite. This is not execution authorization.** R5-1 and R5-2 are resolved in the reviewed v6.1 delta. No remaining concrete P2 finding, scope finding or GPL compatibility finding was identified.

Exact final: `52ad29a1531a1fb1cbe3df2254eac319a05f7f37`.
Tested source: `2f32e7be4d75c4451d46fbef66a87540716f48c6`.
Prior frozen amendment: `6c64883988a0451dc1ff617a72ae2627cac5163f`.
Author branch `experiment/262-worker-v6-sol-20261023`, worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-334e8a36`, final HEAD read back and clean.
Reviewer branch `dc-worker-v61-review`, worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-36c6acfe`, HEAD `1f0a58bf6e0639d8b62f74da52f250cc664c0b30`, unchanged and clean. No reviewer commit or checkout/index mutation. All writes are in this UUID namespace under a nonblocking exclusive lifetime scratch lease acquired before exports or report writes. Cap: 64 MiB.

## Delta assessment

**R5-1:** `test_gpu_worker_v6_1.py:862-866` gives the reaped fake Root `returncode=0` and consistent `poll()`. Exact K22 now completes and retains both the own-group exclusion and other-group positive control. The single-site exclusion-removal mutant fails only `test_k22_exact_fixture_interface_and_own_group_exclusion`, with no test errors. The original v6 AttributeError remains historical FAIL; this does not qualify the original process harness.

**R5-2:** `gpu_worker_v6_1.py:287-291` obtains verification, checks observer errors again, invokes the existing checked original-group fallback and returns an uncertainty error. This covers an error arising during refresh or during either result of `verified_group`. Failed verification without observer errors still refuses signalling (`:292-293`). The enclosing exception path (`:296-299`) still selects the same checked fallback. Cleanup errors/observer uncertainty still make `run_job` select CLEANUP_FAILED, ahead of record/output/witness errors, and `locked_main` selects hold; the outer main backstop holds on unexpected failure after possible work.

The `signal_job_group` AST is identical to frozen v6. It still checks unreaped root, recorded birth, worker parent, original PGID, SID and exclusion of the worker's own group before each signal. It does not guess escaped descendants. My independent probes additionally inject errors during `known_live`, `group_live`, verification, at KILL verification and after the TERM check. They take exactly one checked fallback and retain errors. Changing birth, parent, PGID, SID, own-group identity or root reaped state between TERM and KILL prevents the second group signal; unreadable identity permits only mocked root-handle signals. Mocked main transitions for a cleanup-uncertain outcome and an unexpected exception after a launch select hold. These are branch observations, not kernel identity or lease-lifetime evidence.

The two new mutants fail only their intended K22/K36 checks, without unrelated fixture errors. All 15 replacement sets are unique and compile in memory; the other 13 mutant executions remain UNRUN on v6.1. No full process matrix was run.

## Scope, integrity and context

Read AGENTS.md, the full fetched Notion plan, release test plan section 9, full retained R4 and immediate R5 reviews, R5 late-error/K22 probes and results, v6 contract and author response, v6.1 amendment/response, actual delta, new control definitions, runner and evidence packet. Read the complete supplied #262 issue/comment snapshots. No GitHub/Notion API call was made in this bounded review; those snapshots are context, not refreshed live issue state or source evidence. No source change was made that required a before-change discussion refresh.

`PROVENANCE.json` verifies 36 exported git blobs against the final tree, every author packet whitelist entry, source hashes, the complete published five-file diff against the actual old/new blobs, and seven selected R5 evidence files against the original retained review namespace and final git objects. The R4 original report also matches the retained final object. The five new tools are unchanged from tested source to final. All 24 final-commit additions are evidence/response paths. Every pre-existing tracked file remains unchanged from `1fe458ec`, including v6, contracts, campaign.py, process_ownership.py and historical evidence. No production source/default/gate/tolerance/policy/dependency change. GPL-2.0-or-later notices remain; dependencies are stdlib and frozen repository helpers.

Worker SHA-256: `704e21205d223194d3067ffd7bccc1d02fe6126fe16307816f95d0344c5b1f79`.
Harness: `13c0bdecedf844c510748e740b676d8dd20a64b5004c9fb986d5555aa044dd6f`.
Runner: `e026bdae4c4bd6b7e3083cfea402e872f83208c799b8e91609884837389e35d5`.
Frozen campaign: `8701cf248f247d03eb95c36e99bf9d3a9eaf0ad28660460646afc7128cf84eae`.
Frozen ownership helper: `8de59b8cd741630f8188ef5e98b4877415df90f3bddd8a4a99013e0e7ff908cb`.
Full input/artifact hashes are retained in REPRODUCTION.json, PROVENANCE.json, CONTEXT.json and HASHES.txt.

## Independent checks

`reproduce.py` and `independent-probes.py` were executed through guarded `exec(compile(...))` in the same `/Users/alex.konstantinov/.local/bin/python3 -B -i` interpreter that holds the private lease. CLI unit entry points use runpy with their exact argv and captured SystemExit codes; COMMANDS.json records them. Outer guards forbid actual Popen, os.kill, os.killpg and signal.signal; synthetic tests substitute in-memory mocks. The harness CLI and provider-bound process runner are never invoked.

- `test_v6_1_static.py --json static-units.json`: exit 0, PASS 17/17.
- `test_run_v6_admission.py --runner run_v6_1_controls.py --json admission-units.json`: exit 0, PASS 11/11.
- Direct exact K22, K36 and `r3_controls(...,['K28','K30'])`: PASS, details in focused-controls.json.
- Two new single-site mutants via the static entry point: each exit 1, exactly its intended test failure, zero errors; expected FAIL, discrimination PASS.
- Independent probes: 13 branch/identity cases and two mocked main hold transitions PASS, independent-probes.json. No unexpected probe failure.
- Exact-source/frozen-evidence verification: PASS, PROVENANCE.json. Tested-source-to-final tool diff: exit 0, no differences.

One setup-only archive selection failed because the v6 response was initially addressed at the resource directory instead of its actual review-r4 subdirectory. No source/evidence files were exported by that failed selection; the namespace then held only its lease and preflight. SETUP.json retains the error and corrected path. This was not an experiment or a retried failed control. Old reviewer syntax FAIL, original v6 K22 FAIL, author iteration-02 fixture FAIL and v4 attempts 34-37 UNTRUSTED remain unchanged.

Host SCMAC-7L9P2F, macOS 26.7.1 arm64, CPython 3.13.7, 14 logical CPUs. Interpreter SHA-256 at lease acquisition: `127b5dc839447e76f0ed6a6c3b3097dc7903547d2f1a1fe21d7fc40c20b7bc65`. Numeric threads OMP/OpenBLAS/VECLIB=1, unpinned macOS. Initial load 9.47/9.29/8.38, free 4,430,483,456 bytes; immediate baseline load 6.84/8.43/8.17. PREFLIGHT.json, REPRODUCTION.json, LOCAL-OCCUPANCY.txt and CLOSEOUT.json retain resource observations and scratch accounting. Inputs are exact Python/JSON/text sources and small synthetic data. No MotionCorr binary/movie input, native build/runtime options, device UUID or route witness applies (N/A/UNRUN). No timing claim.

## Remaining blockers and next bounded action

The frozen genuine owner PID/birth/ancestor/exact Claude resume-token rule is unchanged. The synthetic frozen admission fixtures are data, never actual supplied owner credentials. Codex ancestry cannot meet the genuine admission requirement; no old PID/session identity was supplied to a real runner, and admission was not weakened. The parent must decide provider binding or arrange a genuine provider context before considering the unspent single bounded Mac process suite under fresh occupancy/nonblocking leases. A provider-neutral amendment would be separate prospective work; none is implemented or adopted here.

Actual worker/mock/query process execution, kernel signals, wrapper/binary disappearance, independent flock hold and real failure/receipt behavior remain UNRUN. Process-suite authorization remains unspent. Linux/subreaper/taskset/GNU-time, real SMI, builds/native/GPU remain UNRUN; GPU PAUSED. Namespace consumer unimplemented/BLOCKED. No Linux/GPU readiness, native/science/performance, merge or M3 claim. Historical motion truth remains 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE; #65 corrected workflow UNRUN, certification INCONCLUSIVE.

No nested agents, SSH, shared-resource compute, author/root writes, push, PR, external comment or Notion write. Parent owns launch/publication and policy decisions. The own artifact whitelist is HASHES.txt and excludes itself.
