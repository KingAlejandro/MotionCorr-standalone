# Second-venue confirmation: static multi-GPU on 4GPUs (4-gpu-vm)

Source `098b4bd` (branch `experiment/post128-multigpu`). Nothing merged.
Companion to `MULTIGPU_PHASE1.md`, which measured the same source on SCARF gn3002.

## Result

The 2-GPU result reproduces almost exactly. The 4-GPU result does not — it is
substantially **better** here — and the difference points at the filesystem.

| GPUs | 4GPUs median | vs 1 | eff. | spread | SCARF median | vs 1 | eff. | spread |
|-----:|-------------:|-----:|-----:|-------:|-------------:|-----:|-----:|-------:|
| 1 | 13.08 s | ×1.00 | 100 % | 0.78 s | 12.03 s | ×1.00 | 100 % | 0.18 s |
| 2 | 7.54 s | ×1.73 | 86.7 % | 1.14 s | 6.97 s | ×1.73 | 86.3 % | 0.24 s |
| 4 | 5.25 s | ×2.49 | 62.3 % | 0.13 s | 6.04 s | ×1.99 | 49.8 % | 1.78 s |

5 interleaved repeats per arm, rotating order, 24 movies, budget of 32 whole
cores in every arm (32 / 16 / 8 per worker at 1 / 2 / 4 GPUs).

## What the two venues agree on

- **2-GPU scaling: ×1.73 on both**, 86.3 % against 86.7 %. Independent hardware,
  interconnect, filesystem and THP setting. This is the solid number.
- **The serial part is a property of the software, not the host.** Amdahl fitted
  to (T1, T2) gives 1.91 s on SCARF and 2.00 s here — a 5 % difference across
  completely different machines.
- **The host CPU is not binding anywhere.** Peak was 5.04 busy cores of 32 here
  (4.37 / 7.10 on SCARF).
- **`--j 32` wastes CPU on both.** 41.9 CPU-seconds at 1 GPU against 25.6 at
  4 GPUs for identical work, consistent with OpenMP spin-wait.
- **Products are byte-identical at 1, 2 and 4 workers on both hosts.**

## Where they disagree, and why it matters

The 4-GPU Amdahl shortfall is **+0.48 s here against +1.60 s on SCARF**, and the
run-to-run spread inverts: 0.13 s here, 1.78 s on SCARF — the tightest arm in
this campaign against the loosest in that one.

Phase 1 named two candidates for the SCARF shortfall and measured neither: PanFS
contention between concurrent TIFF readers, and per-process CUDA startup. This
campaign discriminates them **partially**. Per-process startup is the same
software on both hosts and the fitted serial part is the same to 5 %, so startup
cannot explain a shortfall that is 3.3× larger on one host. Input here is on a
local disk; on SCARF it is on PanFS. That is the expected signature of
read contention, and the inverted spread supports it.

**This is not conclusive.** The two hosts differ in filesystem *and* interconnect
(PCIe here, SXM4/NVLink on SCARF) *and* THP (`madvise` here, `always` there), so
the comparison is confounded. The clean discriminator is the queued SCARF job
that runs PanFS against node-local `/tmp` on one node with everything else
fixed. Treat "PanFS contention" as supported and not established.

Phase 1 said 4 GPUs was not worth taking. That conclusion was venue-specific and
is withdrawn: on local storage the 4th GPU returns ×2.49, and 4-GPU sharding is
worth taking where input is not on a contended shared filesystem.

## Venue

`4-gpu-vm`, 4× **A100 80GB PCIe**, AMD EPYC 7452, 124 vCPUs, no SMT, 2 NUMA
nodes, THP `madvise`, input on local disk. Run under
`flock /tmp/motioncorr-bench.lock` with the 8-CPU host cap lifted for this
campaign by the maintainer. Settle gate passed with zero wait; **zero foreign
GPU compute apps throughout all 15 runs**; load 0.00 at start.

No GPU-local CPU pinning is possible here and none was attempted: `nvidia-smi
topo -m` reports every GPU as PHB with CPU affinity 0-123 and NUMA affinity 0-1.
On SCARF each worker held its own GPU's NUMA node. That is one of the reasons
absolute times are not carried between the two.

## Controls

- **Product oracle**: a 1-process 24-movie run on this host. Each corrected MRC
  hashed as `header[0:224] + bytes[1024:]`, skipping only the 800-byte label
  block that carries a `strftime` timestamp; per-movie STAR hashed with the tree
  root normalised. numpy is absent on this host, so the Phase 1 comparator could
  not be used.
- **Digest is stable**: re-digesting the oracle reproduces it exactly.
- **Digest is sensitive**: flipping one payload byte in one movie changes exactly
  one line. (The in-job control only mutated the digest file, which proves `cmp`
  works rather than that the hash sees a pixel; the byte-flip was run afterwards
  and is the one that counts.)
- **Pinning witnessed**, not asserted: masks read back from `/proc/<pid>/status`,
  `MATCH` on every worker, budget 32/32 covered and disjoint in every arm.
- **Devices witnessed** by UUID: `all_pids_witnessed_on_intended_distinct_devices`
  true in every arm.

## Evidence

- `evidence/g4_scaling_4gpuvm.log` — full run log
- `evidence/g4_campaign_points.txt` — the 15 campaign points
