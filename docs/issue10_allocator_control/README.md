# Issue 10: allocator setting vs source-level huge pages (24 movies)

Question from the #180 review: does `GLIBC_TUNABLES=glibc.malloc.hugetlb=1` give the
huge-page gain without `madvise` code in `multidim_array.h`?

## Setup

cpu64, glibc 2.39, THP `enabled=madvise`, `defrag=madvise`. Release builds. All 24 tutorial
movies in one process, 5x5 patches, `--dose_weighting --save_noDW --even_odd_split`,
`--j 4` under `taskset -c 8-11`, under `/tmp/motioncorr-cpu64-bench.lock`. Two rounds,
order reversed in round 2. Script: `ab24c.sh`. Raw output: `raw.txt`.

Arms:

| arm | binary | environment |
|---|---|---|
| main | `116eb04` | none |
| main+tunable | `116eb04` | `GLIBC_TUNABLES=glibc.malloc.hugetlb=1` |
| #180 | `03976d94`-based branch (madvise + plan cache) | none |
| plan cache+tunable | plan cache and DW copy elision only, no madvise code | `GLIBC_TUNABLES=glibc.malloc.hugetlb=1` |

## Result

| arm | wall r1, r2 | sys | minor faults | max RSS |
|---|---|---|---|---|
| main | 506.2 s, 452.3 s | 148, 134 s | 51.6M | 4.60 GB |
| main+tunable | 371.3 s, 370.5 s | 30, 40 s | 1.9–2.0M | 4.61 GB |
| #180 | 362.5 s, 359.6 s | 26, 26 s | 2.0–2.2M | 4.39–4.41 GB |
| plan cache+tunable | 357.7 s, 356.7 s | 24, 24 s | 1.6–1.7M | 4.41 GB |

- The tunable on unmodified main recovers about 89% of the main-to-#180 gain (82 s of
  91 s, against the faster main round).
- The remaining gap is the plan cache and copy elision (about 13 s, 3.6%, and 0.2 GB RSS),
  not the `madvise` code. Plan cache+tunable is 4–5 s faster than #180 with its own `madvise`.
- Identity: SHA-256 of all 96 MRC payloads and the STAR files of every run match main
  round 1 (`digests.tar.gz`).
- Main round 1 started at load1 9.1 and is 54 s slower than main round 2. Use round 2
  (452 s) for the baseline. Jiffies on CPUs 8–11 equal the process's own user+sys time in
  every run, so nothing foreign ran on the pinned CPUs.

## Limitations

One host, two rounds per arm. The tunable needs glibc 2.35 or later and applies to every
malloc in the process. On THP `always` hosts neither setting is expected to change anything.
