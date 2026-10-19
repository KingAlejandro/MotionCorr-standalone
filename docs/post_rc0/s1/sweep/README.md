# S1.1/S1.2: frozen RC0 breadth and longevity sweep

First complete pass over all ten #186 families, measured on 2026-10-19. Frozen source F is `6d68e2d6ec45c37b75fd0f4aaff8272f192b7029`. No product source, default or gate was changed. Tracking: [#238](https://github.com/KingAlejandro/MotionCorr-standalone/issues/238).

## Current result

The first pass comprises **16 distinct movies, 32 CPU/CUDA pairs** (5×5 and 3×3). The additional locally staged movies are being processed separately; the first-pass counts below are complete, not an estimate of the full EMPIAR populations.

For the incidence summary, **large S1 disagreement** means relative RMSE ≥0.1. This is a descriptive screen for the large disagreement discussed in SUPPORT §0, not an acceptance gate. The unchanged `compare_motioncorr.py --gate backend` outcome, all metrics and the continuous relative RMSE are retained separately in [per_movie.csv](per_movie.csv) and [evidence/analysis](evidence/analysis). Backend failures can occur below this screen, including absolute-error failures on large-dynamic-range inputs.

| family | distinct movies | large S1 5×5 | large S1 3×3 | relative RMSE 5×5 | relative RMSE 3×3 | backend FAIL 5×5 / 3×3 |
|---|---:|---:|---:|---|---|---|
| e10028 | 2 | 0/2 | 0/2 | 0.0128603–0.0140085 | 0.014208–0.0142256 | 2 / 2 |
| e10164 | 1 | 0/1 | 0/1 | 0.00125191 | 0.00153384 | 0 / 1 |
| e10216 | 1 | 1/1 | 1/1 | 0.434362 | 0.196182 | 1 / 1 |
| e10361 | 2 | 0/2 | 0/2 | 0.00680919–0.00909065 | 0.00765729–0.0101048 | 2 / 2 |
| e10441 | 1 | 0/1 | 0/1 | 0.00712118 | 0.00742159 | 0 / 0 |
| e10474f3 | 2 | 1/2 | 0/2 | 0.0201855–0.599858 | 0.0433468–0.0433551 | 1 / 2 |
| e10474f4 | 2 | 0/2 | 0/2 | 0.0209341–0.0229488 | 0.0217086–0.0264645 | 0 / 0 |
| e10641 | 2 | 1/2 | 0/2 | 0.0415992–0.807827 | 0.0223716–0.0343092 | 2 / 2 |
| e12963 | 1 | 1/1 | 0/1 | 0.499014 | 0.0781668 | 1 / 1 |
| tutorial | 2 | 0/2 | 0/2 | 0.00649463–0.00835825 | 0.00664285–0.00900204 | 0 / 0 |

The 5×5 large-disagreement cases all have non-converging patches and different accepted sets. The second 10641 movie is a new example: CPU keeps 8 patches, CUDA 9, with CUDA-only patch (5,2), and relative RMSE **0.807827**. The first 10641 movie keeps zero patches on both backends and has relative RMSE 0.0415992.

Non-convergence is **not necessary**: the 10216 3×3 run keeps all 9 patches on each backend (531 local-shift rows each) and still has relative RMSE **0.196182**. Matching accepted sets do not guarantee agreement. These observations associate patch rejection with the large 5×5 cases; they do not establish a universal classifier or a new causal mechanism.

## Longevity

Coarse probes use `6b6adf44`, `c499b1d3` and `2ff18e93`, all older than `116eb04a`, on the S1-positive first 10216 and Falcon 3 movies, 5×5. Each older CPU product is compared against F before that older CUDA result is interpreted. The complete records are under `evidence/analysis/*-cpu.json` and `*-cpu-exact.json`; the sweep is invalid for any probe whose CPU control fails.

**6/6 older CPU controls are identical**, including the exact comparator. All six CPU/CUDA probes reproduce relative RMSE 0.434362 (10216) and 0.599858 (Falcon 3). S1 is present at all three sampled older revisions, extending the observed range back to `2ff18e93` (2026-09-27) through F. No absent endpoint, introduction commit or continuous per-commit proof is established.

Identity requires exact MRC core header bytes 0–223, payload bytes, extended header and per-movie STAR bytes, plus the unchanged comparator `--gate exact --require-complete-coverage`. Unmasked MRC labels contain timestamps and differ; the comparator checks their normalized form. Logs, plots, PDFs and the joint-output inventory are outside this CPU control. This is same-backend identity, not scientific equivalence.

## Provenance and reproduction

- Both frozen binaries are the QF builds on 4GPUs, rehashed against `docs/rc0/qf/run_6d68e2d6/`: CPU `43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42`; CUDA+nvCOMP `2e00e0e8fb75aafaf23f15a3c2a142c7d35b6e30477d594244ecba495a5bb6b3`.
- Every arm uses `taskset -c 96-103`, `--j 8`, and the GPU0 correctness lock per invocation, with bench-lock probes. CUDA is selected by UUID `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, with process-descendant UUID sampling. Every completed CUDA arm in this snapshot witnessed that UUID only.
- CPU arms use the CPU-only QF binary on the same 4GPUs host. A separate F CPU Release build on cpu64 exited 0, but no cpu64 movie arm is part of this evidence. A gateway transfer of the second 10164 movie failed after 57 MiB; the partial scratch file was renamed `.failed-transfer` and was not used. This venue choice avoids bulk product transfers and uses the expressly permitted QF binary reuse.
- Input/gain SHA-256 and original corpus matches are in [evidence/manifest.json](evidence/manifest.json). All 52 currently staged, byte-distinct movies were inventoried. The original #186 examples are ordered first. This is a directory census of the staged corpus, not a search of the whole host or a claim that EMPIAR has no more movies.
- Exact argv, binary hashes, input hashes, CPU mask, environment, exit statuses, occupancy and GPU witnesses are retained in `evidence/runs/*/run.json`. The STAR paths are relative `Movies/...`; products were checked under `out/Movies/...`, including dotted-name normalization and `.mrc` to `.mrcs` links.
- Options follow `families.json`: `--use_own --dose_weighting --bfactor 150 --seed 1 --j 8`, family gain/dose/EER parameters, and the explicit patch grid. Corpus voltage/dose placeholders remain placeholders; this is a backend comparison, not a scientific recipe validation. F and later old builds also use expected frame counts and ingest witnesses. `2ff18e93` omits the then-unsupported expected-frame/ingest flags; its decoded STAR row counts are still checked.
- Older sources were copied with `git archive` containing CMakeLists, src and upstream notices. All six configurations use `-DCMAKE_BUILD_TYPE=Release`; configure/build commands, statuses, flags, cache and binary hashes are in [evidence/builds](evidence/builds). No nvCOMP is needed for the older int16-MRC/EER float-route probes.
- Raw per-movie STARs, logs, GNU time logs and witnesses are compressed. Their time fields are retained only because the backend comparator requires the process log; **no timing claim is made**. No MRC or executable is committed. Full products remain in `/mnt/clathrin/alex-motioncorr-s1/sweep`.

Run on 4GPUs, with tools copied into that scratch tree:

```sh
W=/mnt/clathrin/alex-motioncorr-s1/sweep
SRC=/mnt/clathrin/alex-motioncorr-rc0/W-QF/src
PY=/home/alex/.mc-venv/bin/python3
taskset -c 96-103 "$PY" "$W/tools/sweep.py" inventory --root "$W" --source "$SRC"
taskset -c 96-103 "$PY" "$W/tools/campaign.py" --root "$W"
bash "$W/tools/build_older.sh"
taskset -c 96-103 "$PY" "$W/tools/longevity.py" --root "$W"
taskset -c 96-103 "$PY" "$W/tools/campaign.py" --root "$W" --extras
"$PY" "$W/tools/collect.py" --root "$W"
```

The runner refuses to overwrite a run directory. Use a fresh scratch directory for a new run; the campaign can resume already completed arms. Generate CSV/family counts locally with `python3 tools/summarize.py evidence` from this directory.

## Limits and remaining work

This PR is opened after the first complete ten-family pass, as requested. The 36 additional staged movies are not yet part of the first-pass table. Wider sampling toward ≥10 movies in every family, additional downloads, the second 10164/10216 original corpus movies, an earlier absent-S1 endpoint or exact introduction bisection, older-build 3×3 arms, S1.3 CCF logging, and S1.4 downstream CTF/FSC/B-factor are not established here. No support/default/gate change or merge is proposed.
