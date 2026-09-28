# Raw run logs

Unedited stdout/stderr of every build and test run behind
`docs/issue95_staging_evidence/REPORT.md`. Filenames carry the lock epoch,
because the two epochs are not interchangeable and must not be merged.

| file | lock | source tree | what it is |
| --- | --- | --- | --- |
| `01-oldlock-build.log` | `/tmp/motioncorr-issue96-cpu.lock` | pre-review | first configure/build/test of the component |
| `02-oldlock-ctest.log` | same | pre-review | whole-project build + `ctest` |
| `03-oldlock-mutants.log` | same | pre-review | first intentional-bug control, 3 mutants |
| `04-validationlock-mutants.log` | `/tmp/motioncorr-issue96-cpu-validation.lock` | post-review | 4 mutants targeting the confirmed review findings |
| `05-validationlock-final.log` | same | post-review | build, component test, `ctest`, hashes at the first post-review head |
| `07-validationlock-rereview-build.log` | same | post-re-review | build and test after the second review's fixes |
| `06-validationlock-rereview-mutants.log` | same | **final head** | baseline, 5 mutants targeting the second review's findings, restore, `ctest`, hashes |

The old-lock runs are retained as **non-timing** evidence for a source tree that
no longer exists on this branch. They are not restamped with the validation
lock, and no result from them is carried forward as current.

`04` and `05` are likewise superseded: they predate the second review's fixes.
The only results quoted for the **final head** come from
`06-validationlock-rereview-mutants.log`, which contains the baseline, the
mutants, the restore, the `ctest` run and the source hashes in one locked
session.

`01-oldlock-build.log` begins with a failed configure caused by macOS
AppleDouble `._*` files in the transfer tarball. It is kept verbatim rather than
trimmed; the successful configure follows in the same file.
