# Checked single-particle joint STAR publication

Base: `57e98666a6225a8fdb6dafbdbc356478c21cea3a`.

Issue #142 reproduced a successful process exit when the single-particle joint
STAR destination was a directory. `ObservationModel::save` ignored the temporary
stream state and rename result, and renamed while the stream was still open.

The bounded fix retains the general/optics/micrographs table order and existing
serialization. It checks temporary open, write state, flush, explicit close and
rename before returning to the runner's publication-success message. Failure
throws a named `RelionError`, retains any previous destination and attempts to
remove the unpublished temporary file. Cleanup does not replace the original
error. This does not add `fsync` or establish crash durability, concurrent-writer
arbitration or a transaction across all movie products.

## Executed CPU evidence

AppleClang 21, Release/CUDA=OFF, macOS arm64, four build processes:

- `JointStarPublication` passes against the actual production method and runner.
  Healthy general/optics/micrographs bytes equal the original stream serialization.
  Temporary-path-directory, destination-directory, bounded deferred-flush and
  in-write faults throw their expected named stages. The write controls run in
  separate subprocesses with soft `RLIMIT_FSIZE=128` and a finite hard limit
  (8192 bytes under the observed unlimited inherited limit), ignoring SIGXFSZ.
- The actual runner succeeds, refuses a destination-directory joint STAR during
  resume with a positive failure exit and no joint publication-success claim,
  then repairs publication byte for byte. Completed movie MRC/STAR bytes and
  modification times remain unchanged throughout.
- The Python driver also passes under `-O`; acceptance does not depend on Python
  assertions.
- Main's exact old `obs_model.cpp` was compiled with the candidate flags and
  substituted into a copied candidate archive. The same current helper retains
  healthy exactness but fails all four named false-success controls. The actual
  predecessor runner fails the named directory-publication oracle.
- All 33 required CPU tests are collected, including a missing-name negative
  control for this registration. The full suite is **31 PASS / 1 FAIL / 1 SKIP**:
  SyntheticRegression retains the macOS historical-baseline mismatch
  (max pixel 23.6498565674, RMSE 0.3119288, max shift 0.004670, RMSD 0.003305323).
  The predecessor publication object reproduces exactly that mismatch.
  NativeMovieStaging skips its Linux `/proc` check on macOS. No gate changed.

Raw commands, build/test outputs, predecessor source/object/archive and result
JSON are retained outside the repository at
`co/work/joint-star-publication-evidence-20261002/`.

## Scope and remaining checks

This fixes `ObservationModel::save`, used for the SPA joint
`corrected_micrographs.star`. `ObservationModel::saveNew` remains an unchecked
sibling. Tomography's `TomogramSet::write` uses `MetaDataTable::write(filename)`;
that sibling writer checks open but still leaves close/rename unchecked. Neither
is certified by this fix. Dedicated injected close-only failure, Linux CI and
current-head Codex review remain outstanding; real bounded write/flush/rename
failures above executed. No CUDA arithmetic, ingest, output scheduling or GPU
execution changed or was tested for this IO claim.
