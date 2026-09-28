# Corrections to the #94 evidence

Four corrections raised against the artifacts retained at head `67d11809`. All are appended;
no raw manifest, log or table is rewritten. The original claims are quoted so the change is
checkable rather than silently absorbed.

The verdict is unchanged: **no-go on promotion, `--prefetch` stays opt-in and off by default.**
None of these corrections required a new GPU run, a new timing, or any change to
`src/`; the frozen source is untouched.

---

## Correction 1 — the headline said 0/9; it is **1/9**

**Was claimed** (PR #108 `issuecomment-5865942642`, #94 `issuecomment-5865942956`, #66
`issuecomment-5865947621`, and the earlier evidence headline): *"prefetch faster in 0 of 9
paired blocks"*.

**Correct:** **1 of 9.** Series A pair 1 is off 114.088 s vs on 108.815 s, i.e.
`delta = +5.273 s`, which is prefetch **faster**. The raw table in
`scarf_gpu/README.md` recorded that row correctly, with `+5.273` and "faster in 1/3" for
series A; the aggregate headline was wrong, not the data.

| series | budget | pair 1 | pair 2 | pair 3 | mean | faster in |
|---|---|---|---|---|---|---|
| A | 8 log / 4 phys | **+5.273** | −5.560 | −10.031 | −3.44 s on ~103 s | **1/3** |
| B | 1 logical | −13.685 | −8.384 | −8.383 | −10.15 s on ~171 s | 0/3 |
| C | 16 log / 8 phys | −0.677 | −5.462 | −1.018 | −2.39 s on ~100 s | 0/3 |
| | | | | | | **1/9 overall** |

**What does not change.** All three per-series means remain negative (prefetch slower), the
n=3-per-budget limit and the large within-series scatter (series A off-arm spread 16.6 s,
series C 11.5 s) remain, and the +86% host RSS cost is unaffected. One favourable block out of
nine, inside scatter several times the effect size, does not support promotion. The no-go and
the off-by-default position stand on the memory cost and the absence of a demonstrable gain,
not on the count being zero.

---

## Correction 2 — "72 full normalized headers" overstated what was compared

**Was claimed:** *"72/72 normalized headers identical"*, and in places *"complete normalized
full headers"*.

**What the job actually compared:** bytes `0..224` only. The label area `224..1024` — 800 bytes
of real header content — was set aside wholesale. That is not full-header parity, and the
phrase should not have been used. The in-run comparison did disclose the byte range; the
summary prose did not carry the caveat.

**Now verified properly, from the RETAINED outputs, with no rerun.** `tools/compare_prefetch_arms.py`
gained a complete MRC comparison and a `--pair` mode, and was run over **every retained arm
pair**: 3 series × (1 correctness pair + 3 timing pairs) = **12 pairs, 72 MRC files each, 864
file comparisons**.

What is compared now: file length; main header `0..224`; `nsymbt` and, if nonzero, the extended
header; `nlabl`; the entire label area `224..1024`; and every pixel byte after
`1024 + nsymbt`. In other words the **whole file**, minus one justified whitelist.

**The whitelist, justified from the writer rather than from observation.** `src/rwMRC.h`
sets `nsymbt = 0` and `nlabl = 1` on every MRC it writes, and builds one label as
`"Relion " + PACKAGE_VERSION + "   " + strftime("%d-%b-%y  %R:%S")`. Exactly one field can
legitimately differ between two runs of the same binary on the same input: that 19-character
wall-clock timestamp. The tool locates it by the pattern `strftime` produces, requires it to
appear in a declared-used label record, requires **both** sides to parse as
`%d-%b-%y  %H:%M:%S`, and requires both to sit at the **same offset behind an identical
prefix**. A garbage, relocated or absent label cannot hide inside the whitelist.

**Result, all 12 pairs:**

```
MRC files fully identical (whole file minus whitelist): 72
of which the whitelisted timestamp actually differed:   72
whitelisted bytes in total:                             1368     (72 files x 19 bytes)
pixel bytes compared:                                   2759049984
STAR artifacts identical:                               25
PROBLEMS: none
```

So the corrected, defensible claim is: **the two arms produce byte-identical files except for
19 bytes per file of writer timestamp**, and `nsymbt = 0` throughout, so there is no extended
header anywhere in this dataset.

**Discriminating negative control** (`scarf_gpu/full_header_verification_negative_control.txt`,
also `tools/compare_prefetch_arms.py --self-test`). A comparison that only ever says
"identical" proves nothing, so ten mutations were applied to a synthetic MRC:

| mutation | required | observed |
|---|---|---|
| timestamp → another **valid** timestamp | accepted | accepted |
| one pixel byte flips | caught | caught |
| main header byte flips (`nx`) | caught | caught |
| label prefix byte flips (`Relion` → `Reliom`) | caught | caught |
| unused label record 1 gains content | caught | caught |
| timestamp → same-length garbage | caught | caught |
| timestamp → impossible date `99-Zzz-26` | caught | caught |
| `nsymbt` claims an extended header | caught | caught |
| `nlabl` changes | caught | caught |
| file truncated | caught | caught |

**STAR normalization rules, stated explicitly:** comment lines (`#`) are dropped, and the
output directory path — necessarily different between two arms — is replaced by a placeholder.
Nothing else is normalized; every shift, exposure, optics and filename field is compared
literally.

**Coverage:** 12/12 retained pairs verified; 0 UNVERIFIED. Per-file input hashes are in
`scarf_gpu/input_sha256.txt`; source, binary and toolchain hashes are in each series manifest.

---

## Correction 3 — the cpu16 manifest's topology counters were wrong

**Was recorded** (`scarf_gpu/cpu16_manifest_3511138.txt`, left as-is):
`distinct_physical_cores: 0`, `numa_nodes_spanned:` *(empty)*, while the prose said 8 physical
cores across two NUMA nodes.

**Cause:** the manifest computed those with an `awk` one-liner that split the mask on commas
only. That works for an explicit list like `0,1,2,3,32,33`; it matches nothing for a Linux
**range** list like `0-7,32-39`, which is the form both `Cpus_allowed_list` and `taskset -c`
use. Series A and B used explicit lists and were reported correctly; series C used a range list
and reported zero.

**Corrected, derived from the retained `lscpu -p=CPU,NODE,SOCKET,CORE` witness
(`scarf_gpu/lscpu_gn3000.csv`) and the retained mask strings**, via
`tools/cpu_mask_topology.py`:

| series | job | recorded mask | logical CPUs | distinct physical cores | NUMA nodes spanned | cores with both SMT siblings in mask |
|---|---|---|---|---|---|---|
| A | 3511125 | `0,1,2,3,32,33,34,35` | 8 | 4 | [0] | 4 |
| B | 3511134 | `0` | 1 | 1 | [0] | 0 |
| C | 3511138 | `0-7,32-39` | 16 | **8** | **[0, 1]** | 8 |

The prose was right and the manifest counters were wrong. The raw manifest is preserved
unedited; this table supersedes its two broken fields and nothing else.

**Range-mask control** (`tools/cpu_mask_topology.py --self-test`): the new parser is checked
against range lists, explicit lists and a single CPU, **and** the old comma-only logic is
re-run alongside to confirm it returns 0 for the range mask and the correct 4 for the explicit
list — i.e. the control reproduces the exact failure before asserting the fix. The sbatch
script now calls the tool instead of the `awk` line.

**No locality inference.** A CPU mask says where threads may run. Series C's `numactl` policy
was recorded as unrestricted `membind`, so **no NUMA memory-locality claim is made**, and none
of the timing differences are attributed to NUMA.

---

## Correction 4 — the mechanism was stated as fact; it is a hypothesis

**Was claimed:** *"the decode was never what the wall clock was waiting for, and the producer's
concurrent CPU use plus 2.5 GiB of extra residency costs at least as much as the hidden decode
saves."*

**What is measured** (prefetch-ON arms only; these counters do not exist in the OFF arm):

| series | `consumer_wait_s` | `producer_queue_blocked_s` | `producer_budget_blocked_s` |
|---|---|---|---|
| A | 0.393 | 86.17 | 0 |
| B | 5.39 | 94.56 | 0 |
| C | 0.337 | 81.10 | 0 |

**What that licenses:** in the prefetched arm, the consumer spent 0.3-5.4 s of a 100-180 s run
waiting for decoded input, and the producer was ahead for most of the run. That is a statement
about the ON arm and nothing else.

**What it does NOT establish, and is now labelled hypothesis:**

- That decode was not on the critical path **in the OFF arm**. The OFF arm was never
  instrumented for decode time; no per-stage timers were collected (`TIMING=ON` was not used).
  Inferring the serial arm's structure from the parallel arm's wait counter is an inference.
- That CPU contention or the extra residency **caused** the regression. No experiment varied
  contention or residency independently, so this is an untested explanation for a difference
  that is, in two of three series, inside the noise.

The measured facts that stand on their own are the per-series means, the 1/9 count, and the
RSS delta.

**RSS statistic, units and limitations, stated precisely.** The figure is the **peak over time
of the sum of `VmRSS` across the owned process tree**, in kibibytes from `/proc/<pid>/status`,
sampled every 200 ms, converted to GiB for reporting. It is therefore:

- a **sampled** maximum, i.e. a lower bound on the true peak — a spike between samples is
  missed;
- **resident set size**, not an allocator trace and not virtual size;
- restricted to the measured process and its direct children, not the node;
- **not** device memory. Device high-water was separately sampled from NVML at 100 ms and was
  unchanged at 3497 MiB between arms.

Measured: off 2.97 GiB, on 5.51 GiB, **+2.55 GiB (+86%)**, with a within-arm spread of 5-13 MiB
across nine runs. The reproducibility is the strong part of this result; the causal story is not.

---

## Correction 5 — an over-restriction on my own side, withdrawn

I wrote that composing PR103/PR110 *"would be a merge this task is not authorised to make."*
That was wrong: **integration-branch composition and testing are authorized; only
merge-to-main is forbidden.**

The composition nonetheless remains **UNRUN**, for a different and better reason: with a no-go
verdict on prefetch, launching a composition and new benchmarks to support prose would spend
shared GPU capacity on a feature that is not going to be promoted. It stays UNRUN by choice,
not by permission.
