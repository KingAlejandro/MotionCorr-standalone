# Iteration 3 stop: read-only diagnosis (22 Oct 2026)

**Result: admission failure, not a native product failure.** `i3-run-only260-L` (the 26th of the 61 frozen stages; exit 1 at 21:25:57Z) never launched `motioncorr`.

| Fact | Evidence |
|---|---|
| The tool stopped before launch | `t24-i3/only260-L/RUN.json`: `rc` None, no `child_rc`, `error` = "foreign compute process on the lane GPU; stopped before launch"; no `wall_s`, no `time_exit_status`, no health or cleanup records, no GPU witness; the arm directory holds only `cwd/` (the `movies.star` copy and `Movies` link) and an empty `logs/`; no `out/` |
| The occupant was foreign | `foreign` field: `GPU-b2cb2c39…` (GPU3), PID **3276184**, 414 MiB. The process is `/home/dvi41342/Software/llama.cpp/build/bin/llama-server` (user `dvi41342`, started about 21:25:39Z, model resident on all four GPUs; 49.7 GiB on GPU3 by 21:31Z, 0 % utilisation) |
| Our previous stage was clean | `i3-run-only254-L` exit 0 (21:25:47-21:25:54Z); its post-run health under the lease: no apps, 4 MiB used. The foreign context appeared in the 3 s before `only260-L` |
| Lease handling was correct | the lease was taken non-blocking, the foreign check ran under it, and the lease was released on the early return; no holder remains (`fuser` empty) |
| Chain terminal receipt | `logs/chain-i3.stop`: "stage i3-run-only260-L exited 1 (allowed: 0)"; `chain-i3.done`/`finished` absent; the chain exited (PID 3273979 gone); nothing of C1 is running on GPU3 |
| Binary/tool identity | `only260` binary `2bc46a2c…73f9`, tools `tools-v2.3-run` (packet `4facd76d`), source `e77a51a2`, frozen chain and manifest hashes unchanged |

The foreign-occupant stop worked as designed; the cause is a resource conflict with another user's process, which was not touched or signalled.

## Completed before the stop (all valid, retained)

Stages exited as follows: `F-fresh` run and `lane-hash` (G, L) 0 (IDENTICAL, 49/49); `c1`, `N`, `only254` runs (G, L) 0; G: `only260`, `only270` runs 0, every comparison valid (`cmp-F-*` 1 = DIFFERENT, `F-only270` 0 = IDENTICAL, `N-c1` 0 = IDENTICAL), `i3-attribute-G` 0; L: `F-c1`, `F-N`, `F-only254` comparisons exit 1 (valid DIFFERENT).

**G attribution (COMPLETE, no blockers):** lane control IDENTICAL; 49 products change F to C1 (24 MRC, 25 STAR). **N equals C1 exactly** (0 differing products), so D2/D3 and the independent fixes change no G product. #270 alone changes nothing in G. The 25 STAR files are reproduced by #260 alone (`SINGLE_FIX_REPRODUCES:only260`). The 24 MRC images are reproduced only by #254+#260 together (`COMBINED_NUMERICS_COMPOSITION_ONLY`): #254 alone changes the 24 MRC, #260 alone changes all 49, neither alone gives C1's bytes, so per-fix attribution of the MRC change is unresolved (interaction or composition). This is a bounded engineering statement about config G, not scientific acceptance.

**L attribution is incomplete, not labelled complete:** `only260-L` and `only270-L` never ran, no `N-vs-c1-L` or single-vs-C1 L comparison exists and `i3-attribute-L` did not run. Partial L facts only: F vs C1 and F vs N each differ in 49 products, F vs only254 in 48. Everything after `i3-run-only260-L` (L comparisons, datasets, K267, R12/12ds, R9, A1, census, T24 CPU, image) is **UNRUN**.

## Proposal (not executed; needs a new frozen iteration)

1. **Precondition:** GPU3 free of foreign compute processes (the same user's server currently holds a context on every GPU). That is a coordination point with the owner or the parent; nothing was signalled or reset. A pre-launch occupancy gate is already part of each stage.
2. **Iteration 4, L-only first:** because `t24-i3/only260-L` now exists (the tool refuses to overwrite an arm directory), resume in a new T24 directory with new stage names, re-running the six L arms (F-fresh, c1, N, only254, only260, only270; about a minute of GPU time) with the unchanged tools, the same lane-hash gate, the same allowed sets and the same N-vs-C1 and attribution stops. G results in `t24-i3` stay as retained. Then the frozen remainder (datasets, K267, R12/12ds, R9, A1, census, T24 CPU arms, image) in the original order, unchanged.
3. **Discriminating control:** the L iteration passes only if the lane control is IDENTICAL, `N_vs_c1-L` is IDENTICAL, and attribution completes; a foreign occupant again stops the chain before launch.
4. No gate relaxation, no tool or source change, no skipping; iteration-3 chain, manifest, receipts and outputs stay as they are.

Parent readbacks used or preserved verbatim under `evidence/parent-readbacks/` (sticky native verification, freeze verification, full-CTest verification, status probe).
