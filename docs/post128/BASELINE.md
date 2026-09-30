# Post-#128 baseline record

Established before any new experiment, so every later measurement has a fixed
reference rather than being compared to a moving target.

## Merge verification

```
MAIN_SHA=c499b1d3bf1cceec5c3b194f356844d6f493e7f2
PR128_MERGE_SHA=c499b1d3bf1cceec5c3b194f356844d6f493e7f2
PR128_HEAD=d7960a4c99bde5a0c29596de493bb249be6c0fa4
PR128_PRODUCTION_TREE_EQUIVALENT=yes
```

`f41460e` (the source the #128 campaign measured) is an ancestor of main, and
`git diff f41460e c499b1d -- src/ CMakeLists.txt tests/ tools/` is **empty**.
Verified rather than assumed: the two commits after `f41460e` touch exactly
`docs/unified_max_performance/evidence/README.md` and
`docs/unified_max_performance/evidence/scarf-3515779-final.log`.

So the retained #128 numbers describe main's production content. They remain a
measurement of **that venue** and are not carried forward.

## Venue — SCARF `gn3002`, exclusive, job 3515836

| | |
|---|---|
| GPUs | 4x **A100-SXM4-80GB**, UUIDs `7e062742`, `3c9c438e`, `0c25691b`, `5365f504` |
| CPUs | `Cpus_allowed_list: 0-63`, 64 in the cpuset |
| compiler | GCC 11.5.0 (Red Hat 11.5.0-14) |
| CUDA | 12.8.61 |
| nvCOMP | `libnvcomp.so.5.3.0.16` |
| python / numpy | 3.9.25 / 1.22.4 |
| **THP** | **`[always]`** |
| input filesystem | `panfs://130.246.139.193/scarf/work4/scd` on `/work4/scd` |
| `movies.star` | `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041` |
| movies / gain | 24 / `8919cdc7bf0f481c` |

**This is not the #128 campaign's venue.** That was `gnx002`, A100-SXM4-**40GB**,
32 CPUs, THP `madvise`. Three differences that matter for comparability: GPU
memory and SM count, CPU count, and the THP setting -- which is known on this
project to dominate host-side frame allocation. Numbers from the two venues
must not be pooled.

## Builds and required suites

| configuration | binary sha256 (16) | undefined refs | tests | collection gate |
|---|---|---|---|---|
| CPU-only | `25e6a0c52b9a8c41` | 0 | **32/32** | PASS |
| CUDA, no nvCOMP | `0eaa296c19a056c4` | 0 | **38/38** | PASS |
| CUDA + nvCOMP | `00531c10c7a9bf41` | 0 | **39/39** | PASS |

## Baseline product oracle

24 tutorial movies, automatic ingest, the #128 product set
(`--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
--bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8`):

- exit 0
- **24/24 MRC**, **24/24 per-movie STAR**
- joint STAR present, 2 data blocks, **24 micrograph rows**
- 10 EPS/PDF products
- ingest witness: **24 nvcomp**, no movie routed to a fallback
- **zero** fallback or warning lines in any per-movie log
- wall 12.89 s, max RSS 0.578 GiB, 187% CPU

Retained at `post128/baseline-products` on SCARF. This tree is the oracle for
every subsequent experiment on this venue; a later arm is compared against it,
not against the #128 campaign's outputs.

MEASURED. Single observation, deliberately -- this is an identity and
correctness record, not a timing claim.
