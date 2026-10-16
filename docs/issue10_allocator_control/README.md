# Issue 10: huge pages by allocator setting (24 movies)

Question from the #180 review: does `GLIBC_TUNABLES=glibc.malloc.hugetlb=1` give the
huge-page gain without `madvise` code in `multidim_array.h`, and what is left for the
FFTW plan cache (#187)?

## Setup

cpu64: AMD EPYC 7763, Linux 6.8.0-86, glibc 2.39, gcc 13.3.0, THP `enabled=madvise`,
`defrag=madvise`. Release builds (`-O3 -DNDEBUG`), built from `git archive` trees of
main `116eb04a` and #187 head `3fb58c2a` (`ab24d.sh`; binary hashes in `provenance.txt`).
All 24 tutorial movies in one process (hashes in `inputs.sha256`), 5x5 patches,
`--dose_weighting --save_noDW --even_odd_split`, `--j 4` under `taskset -c 8-11`, under
`/tmp/motioncorr-cpu64-bench.lock`. Rounds alternate arm order. Output check: SHA-256 of
the data of every MRC and of every STAR (`digest24.py`) against main; all runs below match.

## 1. Allocator setting on unmodified main (`ab24e.sh`, `raw-main-tunable.txt`)

| arm | wall, rounds 1-4 | mean | sys | minor faults | max RSS |
|---|---|---|---|---|---|
| main | 499.6, 503.4, 514.9, 514.1 s | 508.0 s | 146-167 s | 51M | 4.39 GiB |
| main + `hugetlb=1` | 386.2, 392.0, 393.3, 397.1 s | 392.2 s | 43-53 s | 2.1-2.8M | 4.39 GiB |

The tunable cuts wall time by 23% (116 s) with identical output.

## 2. #187 on top of the tunable (`ab24d.sh`, `raw-exact-revisions.txt`)

| arm | wall, rounds 1-4 | mean | max RSS |
|---|---|---|---|
| main + `hugetlb=1` | 374.3, 382.9, 383.4, 373.2 s | 378.4 s | 4.39 GiB |
| #187 + `hugetlb=1` | 366.4, 372.5, 364.8, 366.6 s | 367.6 s | 4.21 GiB |

#187 is faster in all four pairs: 10.9 s (2.9%) on average, 0.19 GiB less RSS. The
`FloatPlanCache` test passes on the head and fails on a mutant whose cache key drops the
FFTW alignment classes (both run in `ab24d.sh`).

## 3. First run (`raw-retained-first-run.txt`, `ab24c-first-run.sh`)

Two rounds, same setup, run before the revisions above were recorded. Its binaries are
`motioncorr` built in `mc-cpuprof-116eb04` (main), the #180 head, and a plan-cache build
without `madvise`; their exact source revisions were not recorded, so use it as supporting
evidence only. Main took 506 s and 452 s, main + tunable 371 s and 371 s, #180 363 s and
360 s, plan cache + tunable 358 s and 357 s. The 3-5 s between #180 and plan cache +
tunable is not resolved from run-to-run variation, so this run shows no benefit from the
source `madvise` beyond the tunable.

## Limitations

- One host, four rounds per arm in sections 1-2, two in section 3. Main varies from 452 s to
  515 s across these runs, so compare within a section, not across them.
- Host load1 was 7-18 during sections 1-2 (other users). The pinned CPUs 8-11 show no
  foreign work: their jiffies exceed the process's own user+sys time by at most 1.2%
  (section 1, plain round 3; below 0.3% in every other run). Memory bandwidth and cache contention from other
  users are not measured.
- The tunable needs glibc 2.35 or later and applies to every malloc in the process. THP
  `always` (SCARF) and `never` hosts were not measured; no gain is expected on `always`.
