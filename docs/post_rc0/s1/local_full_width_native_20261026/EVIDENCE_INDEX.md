# Evidence index: local full-width weight implementation

| Object | Value |
|---|---|
| Base | `42af54069e9b33a3f6b7b63c4046457c50daa93c` |
| Reviewed source | `634e4b486240f4c811c3052d573c6d6ebcc5b298` (tree `9db91248...`) |
| Archive-built commit (attempt 3) | `5bcfa9878157ae7286d8de01e4baa5df9c073f25` |
| Head at sealing | `ed897ebbf823d157de78531940889a37e5b03923` (C++, tests and CMake equal to `5bcfa987`; `src/` and `tests/` equal to `634e4b48`) |
| Real runtime (attempts 2, 3) | `/Users/alex.konstantinov/.local/bin/python3` 3.13.7, NumPy 2.4.2, `numpy/__init__.py` sha256 `2e8da3e4385e79c4885b3f7324a8b957e6f01732b239e99e266a12c62a008b8d` |
| Attempt-3 binaries (sha256) | motioncorr `64f00132debdd374d00d03b619388ef8c60b6bf03428f4a43ea3cf6a06a4a5ab`, local_full_width_weight `801825d9a0f215ebad84759f8952323ae38c8e063a070da848016d4a1afe8035`, ccf_dc_hook `b6d54782daba59cd3b639e861ab3f3fe62e25bcff4fabed5be04eca8a09edc24` |

| Directory | Status |
|---|---|
| `evidence/source_review/` | Independent source review of `634e4b48`: no BLOCK, no MATERIAL; four LOW, addressed in `5bcfa987`/docs. Source-only, conditional clearance. |
| `evidence/attempt1_NONQUALIFYING/` | Stub-NumPy attempt. Nonqualifying. Mutant kills UNVERIFIED (logs hold no test verdicts). |
| `evidence/attempt2_real_numpy/` | Real NumPy, live worktree at the unchanged `634e4b48` tree, no as-built manifest. Default 6/6. DC: 3 pass + 1 Not Run (target unbuilt), then `LocalFullWidthWeight` passed on rerun. |
| `evidence/attempt3_clean_archive/` | `git archive` of `5bcfa987`, 11641 files matching Git blobs before and after the build; DC targets only; caller `MC_EXPERIMENT_CCF_DC_ARM` unset; 4/4 selected DC tests pass; bare-binary control without the arm aborts (134). `SHA256SUMS` verifies these files. |

Raw build trees and the extracted archive are not kept in Git or the durable copy; the archive is reproducible from the
commit. Durable originals (additive copy with verified `COPY_INDEX.tsv`):
`~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-implementation-r1/`. The original review report is also
in sibling `Native-local-full-width-source-review-r1/`.

Limitations: host results only (macOS arm64, AppleClang, Release, `-j2`). The default-build 6/6 is attempt 2's. UNRUN:
full-movie and global-trajectory byte neutrality, the rest of CTest, CUDA execution, any movie, native pilot, field gates,
runtime-vs-STAR, N5/9/13/20, harm controls, scientific accuracy; the combination with `--experimental_local_b2` is
untested. Ubuntu CI and CUDA compile-only success at `ed897ebb` are separate GitHub facts, not native evidence. The
pending parent oracle and pilot packet are outside this index and may be added additively.

Repo copy integrity: `EVIDENCE_SHA256SUMS` lists every file under `evidence/` (`cd evidence && shasum -a 256 -c ../EVIDENCE_SHA256SUMS`).

Original compiler/ctest log text, including a few trailing-whitespace lines, is preserved unmodified (`git diff --check` flags them).

## Pilot packet integration
`pilot/` (snapshot, additive): `PACKET_SHA256SUMS` lists every file; the original `SHA256SUMS_v3` and `SHA256SUMS_v4` verify inside it. Durable originals:
`~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-final-packet-r1/`. Source `634e4b48` and CMake `5bcfa987` are unchanged.
