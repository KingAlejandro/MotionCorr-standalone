# Retained output regrade — 29 September 2026

This is a read-only regrade of the retained PR #118 run trees. No MotionCorr binary was run and
no retained output was rewritten.

## Provenance

- Host: `4-gpu-vm`; CPU-only comparison pinned to logical CPUs `96-103`.
- GPU inventory at the regrade check: all four UUIDs at 1 MiB / 0% utilization; no MotionCorr
  process was present.
- Comparator: `../compare_output_trees.py`, SHA-256
  `64872c869491036ff3457fa4f825fbdb6dc68d9fd00f977ee01ce5ca6b165cd0`.
- Manifest: `../tutorial_24_movie_manifest.json`, SHA-256
  `30bbe4a30a389df06416b0f3d1d002514d6fd3ef2666aeb6e6c1c063c25cec1d`.
- Input STAR: `/home/alex/MotionCorr-standalone/relion30_tutorial/movies.star`, SHA-256
  `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`; this matches the
  manifest-pinned digest.
- Retained candidate source identity: `src/` tree
  `2c4f73bac053d17f7fca225126d0832009b3d1e` as recorded by `RESULTS.md`; candidate binary SHA-256
  `ee631181e1c27a4845c5c54ab83b3aeee6e246dcb3bad50f063bb6e5239341c6`. The base binary SHA-256
  is `614c00904fddc7513b869cfebae8d7cbfe79dd5d9cccd01c6781ae9987799374`.

The candidate source identity above is the retained measurement source, not the current composed
integration source. These reports establish retained-product completeness and equality; they do
not substitute for healthy CUDA validation of the final source.

After this regrade, `--products-only` was narrowed to ignore differing auxiliary-file inventories;
each arm still independently validates the complete manifest-required MRC/STAR inventory. The
retained trees already had matching file inventories, so this does not change any of the 12 report
results. The current comparator SHA-256 is
`2f1effd1ebdf4250096e55c4ee84a7299e12bef6c9d7919741d8d2fae91da160`; its CPU controls also cover
a valid extended header with a changed length, proving the pixel offset and header hash use the
declared `nsymbt` value.

## Regrade command

For each pair, the runner used the comparator and manifest above with the base output tree first,
the candidate tree second, the input STAR, and `--products-only`:

```text
/home/alex/.mc-venv/bin/python compare_output_trees.py BASE/out CANDIDATE/out \
  --manifest manifest.json \
  --input-star /home/alex/MotionCorr-standalone/relion30_tutorial/movies.star \
  --products-only --json-out REPORT.json
```

Each arm was checked independently before equality was considered. Required inventory is 24 movie
MRCs, 24 per-movie STARs and the joint STAR. Every MRC had the manifest's 3710×3838×1 dimensions,
supported float32 mode, valid header and machine stamp, valid extended-header offset, and exactly
the declared payload length with finite pixels. The MRC header, extended-header and pixel hashes,
per-movie STAR association and joint STAR inventory were then compared.

## Results

All 12 product-only reports pass. Every pair has 24 movies, 24 MRCs, 25 STARs and 341,735,520
pixels per arm; each has zero different MRC/STAR products and 24 matching per-movie MRC hash
records.

| Pair | Base → candidate (or repeat) | Product result |
|---|---|---|
| `timed_pair_1` | `s_base_1` → `s_cand_2` | PASS |
| `timed_pair_2` | `s_base_4` → `s_cand_3` | PASS |
| `timed_pair_3` | `s_base_5` → `s_cand_6` | PASS |
| `gain_pair` | `m_base_gain` → `m_cand_gain` | PASS |
| `no_gain_pair` | `m_base_nogain` → `m_cand_nogain` | PASS |
| `selected_frames_pair` | `fs_base` → `fs_cand` | PASS |
| `skip_defect_pair` | `sd_base` → `sd_cand` | PASS |
| `early_full_gain_pair` | `base_gain` → `cand_gain` | PASS |
| `early_no_gain_pair` | `base_nogain` → `cand_nogain` | PASS |
| `time_pair` | `t_base_1` → `t_cand_2` | PASS |
| `same_arm_base_gain_repeat` | `m_base_gain` → `m_base_gain_rep2` | PASS |
| `same_arm_candidate_gain_repeat` | `m_cand_gain` → `m_cand_gain_rep2` | PASS |

Machine-readable product reports are in [`products-only/`](products-only/).

The matching complete non-PDF tree reports are retained in [`full-tree/`](full-tree/). The 10
cross-arm comparisons return `FAIL`, with exactly 24 differing files and all 24 are movie `.log`
files; the two same-arm repeats return `PASS`. No MRC or STAR is listed as different. The log
differences include the candidate's added “Staging this movie as native unsigned 16-bit” line,
measured CUDA timings, and the per-run output-root path. A representative raw diff was inspected;
the full-tree failure is therefore retained and not relabeled as a pass.

## Decision

These retained results are not evidence of truncation or missing products, so a rerun solely to
repair the old comparator's blind spot is unnecessary. The original retained candidate and base
trees are complete and their MRC/STAR products are equal under the stronger check. The separate
required healthy CUDA cases still need to run on the final current-main composition.
