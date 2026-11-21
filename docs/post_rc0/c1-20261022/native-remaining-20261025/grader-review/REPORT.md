# C1 dataset-grade i6 G: archive vs. comparator (read-only investigation)

Result: **tool mismatch, not a publication defect.** `merged/_workers/` is the producer's documented provenance archive; `compare_output_trees.validate_tree`
`rglob`s `*.star`/`*.mrc` over the whole root, so the archived worker joint STAR fails "STAR inventory differs" before any product is compared.
The historical i6 G dataset-grade FAIL stays as recorded (`DATASET.json`, `compare/*.json` untouched).

## Evidence
- Producer: `tools/multi_gpu/merge_workers.py` stages each worker's fixed-name aggregates (`AGGREGATE_NAMES`, copy mode) to `merged/_workers/w<k>/<rel>`, records them in
  `aggregate.json.per_worker_aggregates_preserved`, and writes `_workers/merge.log`. Docstring: per-worker aggregate reports "remain retained as provenance".
  `tests/test_dataset_endpoint.py` asserts `merged/_workers/wK/launcher.console.log` exists.
- Retained real G one/two-worker runs (`docs/post_rc0/issue240/native/multigpu/G/w1,w2/aggregate.json`) list exactly `command.json`, `corrected_micrographs.star`,
  `launcher.console.log` per worker. No archived MRC occurs (and the i6 comparator reached the STAR check, so its MRC inventory was already exactly 24).
- Existing R12 `c1_item12.digest_tree` skips `_workers` by design; `c1_tutorial24.dataset/_compare` (v1 and v2) never accounted for the archive. The comparator is right for
  two standalone trees and wrong for a dataset `merged/` tree. Same failure will hit dataset L.

## Tool: `c1_ds_archive_regrade.py DS_ARM_DIR --out-dir NEW_DIR` (separate, read-only, 0/1/2 = PASS/FAIL-DIFFERENT/INVALID)
1. Retained `DATASET.json` must be FAIL with exactly one problem (the products comparison); dataset_status/workers status/aggregate.json re-read (PASS, ready, 1 worker rc 0, 24 movies).
2. Archive expectation is derived from the retained `workers/w<k>/` trees: every non-product worker file, each a `merge_workers.is_aggregate` name; only
   `corrected_micrographs.star` may be a STAR, no MRC. `merged/_workers/**` must equal that set + `_workers/merge.log` exactly (no symlinks, no extras, none missing);
   each archived file is byte-equal to its worker original; the archived STAR also equals the launcher exit digest (required); `per_worker_aggregates_preserved` must match.
3. Only then the unmodified `compare_trees(compare_auxiliary=False)` and unmodified `c1_tutorial24.classify` run, with `_workers` hidden from `rglob` for that one candidate root
   inside the `with` block (base tree is never filtered). Everything else (extra/missing STAR/MRC, wrong path, mode/dims/header/ext/payload, normalized STAR, symlinks, 24/24/25 counts) is the comparator's own logic.
4. REPORT: full merged inventory (all entries), the 49 canonical products, archive allow-list with worker/exit/archived hashes, per-MRC header/ext/payload hashes, hashes of
   regrader, c1_tutorial24, comparator, merge_workers, manifest, input STAR, status/aggregate files, historical DATASET.json hash.

## Controls (`test_c1_ds_archive_regrade.py`, synthetic 24 x 2x2 float32 MRC, macOS py3.15 + numpy 2.5.4, 4 tests OK, `test-run.log`)
- Base: unmodified comparator CLI on the same merged tree exits 1 with `extra=['_workers/w0/corrected_micrographs.star']`; regrade PASSes (49 products, inventory keeps the archive).
- INVALID (reason checked per case): extra archived STAR / MRC / `.txt`, archived product duplicate, STAR content mismatch, command.json mismatch, missing archived STAR, missing merge.log,
  archive for worker w1, archive symlink, worker original changed after exit, aggregate.json list mismatch, no exit digest, other retained dataset problem; outside the archive: extra STAR,
  extra MRC, wrong canonical path, missing MRC, mode 1, wrong dimensions, product symlink, `_workers` STAR in the base tree.
- FAIL/DIFFERENT with exactly one product: MRC pixel, MRC header byte, movie STAR, joint STAR. `rglob` patch is scoped and restored.

## One-shot data-only grade
CPU only, no GPU, no build, nothing launched on the output. Venue-bound `taskset -c 8-9` (1-2 cores), python with numpy (cpu64 `~/.mc-venv` style; 4GPUs has none), env from `c1_env.sh`
(`C1_SCR, C1_TUTORIAL, C1_FROZEN_RC0, QF_*`), regrader next to `c1_tutorial24.py` (or `C1_TOOLS`). Reads ~48 MRC (24 merged + 24 standalone, ~55 MB each) once via memmap, plus ~200 small files;
writes only `NEW_DIR/REGRADE.json`. Run: `python c1_ds_archive_regrade.py $T24/<arm>-ds-G --out-dir <new dir>`; pass the arm path exactly as c1_tutorial24 spelled it (not `realpath`).
Scratch artefacts: this directory (`c1_ds_archive_regrade.py`, `test_c1_ds_archive_regrade.py`, `.patch` adding both under `tools-v2/`, `venv/` for local numpy).

## Remaining uncertainty
- The real `merged/_workers` listing was not observed (no remote authority). Expected 3 files per worker + merge.log from retained evidence; a different real set yields INVALID with the exact difference, not a PASS.
- GPU witness, lease and cleanup are not re-evaluated; they are taken from the retained `DATASET.json` having no problem other than the comparison.
- Hiding `_workers` is done by a scoped runtime `rglob` filter, to keep the comparator unmodified. A reviewer may prefer an explicit comparator option instead; that changes a shared tool.
- Non-product merged files (logfile.pdf, `.log`, EPS) are inventoried, not content-checked, as in `--products-only`.
- Whether a regraded PASS counts as the D12 row result is the parent's/reviewer's decision; this tool does not change any gate, tolerance, or the historical FAIL.
- Controls ran on macOS/py3.15, not on the venue Python; untested there.

## v1.1 (load_module correction)
v1 failed on the venue's Python 3.12 before any comparison: `load_module` executed `compare_output_trees.py` without `sys.modules[name]`, and `@dataclass` over string annotations
looks up `sys.modules[cls.__module__]` (Python < 3.14; the local 3.15 defers annotations and could not show it). v1.1 registers the module before `exec_module`, and on a failed import
removes the entry (or restores a previous one). Archive and product criteria, report fields and exit codes are unchanged; only `VERSION` and a docstring line differ.
`c1_ds_archive_regrade.v1.py` is the byte-identical v1 (receipt of the failed attempt). Delta: `v1-to-v1.1.diff`.
Controls: base reproduced the failure first (unchanged v1 on Python 3.12.11 + numpy 2.5.4: AttributeError at `dataclasses._is_type` on the real comparator). Now 5 tests OK on both 3.12.11 (`test-run-py312.log`)
and 3.15.1 (`test-run-py315.log`), including a new portable control (`from __future__ import annotations` dataclass imported by `load_module`; failed import leaves no entry / restores a previous one; the retained v1
loader is shown to raise AttributeError on < 3.14). Not tested: the venue's exact Python/numpy; the real data.
