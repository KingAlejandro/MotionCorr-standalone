# cpu1 regrade v2, amendment 1 (frozen before code, 23 October 2026)

Responds to review R1 of `364a1a73` (NO-GO for the remote regrade). `CONTRACT.md`, `regrade_v2.py`, its 33
controls, `remote_precheck.py`, `REMOTE-PLAN.md` and every earlier artefact stay unchanged. They are the record
for grader `8bf7b10f`. The amendment adds new files: one script, `regrade_v2_1.py` (subcommands `grade`,
`precheck-files`, `precheck-live`), plus a control suite, a remote plan and the live EXPECT file. The scope is
otherwise as in `CONTRACT.md`. The original subset FAIL, 16 CUDA rows UNRUN and the INCOMPLETE aggregate are
unchanged.

**A1 (R1 F2): the MRC product contract.** The cpu1 options do not use `--float16`. `rwMRC.h` writes `"MAP "` at byte 208,
`nsymbt = 0`, and mode 2 for float, with nx, ny, nz at bytes 0–11. The fixture is 768×512 at `--bin_factor 1`. Every
pair-member MRC must therefore meet all of the following:
- nx = 768, ny = 512, nz = 1, mode = 2, nsymbt = 0;
- map word `"MAP "`;
- exactly 1024 + 0 + 768·512·4 = 1,573,888 bytes.

So all 16 sizes are equal by this contract, not by assumption. Reads are bounded at 16 MiB per file. Payload equality
compares the 1,572,864 data bytes exactly. Other header bytes, including label timestamps, are not compared.
A pair's descriptors must also be equal; under the exact prescription this is implied, and it is kept as a guard.
`precheck-files` applies the same validation.

**A2 (R1 F3): the snapshot and self-binding.**
- **One snapshot.** Every consumed input is read once into an immutable in-memory snapshot: 24 rows ×
  RUN/STAR/stdout/stderr, 3 build receipts, the receipts file, `RESULTS.json`, and the 16 MRCs if present.
- **Report.** The report records each file's size and sha256, plus the grader, amendment, manifest, precheck and input-file identities.
- **Re-read check.** After grading, every file is re-read; any change, appearance or disappearance fails the run.
- **Directory mode** also requires two inputs:
  - `--manifest` (sha256 `6bdc14cc…92ed6`), whose 101 hashes must match;
  - a `precheck-files` report, whose MRC sizes and hashes must match the snapshot. A change after the precheck fails.
- **Contradiction gate.** A recomputed image relation that differs from the original `RESULTS.json` boolean for the same pair fails as "contradicts original evidence".
- **Output refusals.** `--out` must not exist, must not lie inside the scratch, and its parent must be canonical. Input
  paths must be canonical (equal to their realpath).
- **Publication.** The report is written to a temporary file in `--out` and published with `os.replace`. Nothing is written in the scratch.

**A3 (R1 F4): symlinks.** In directory mode every component below the root is opened with `O_NOFOLLOW`. A symlink
leaf or a symlinked directory component is invalid input (exit 1). It is never treated as missing.

**A4 (R1 F5): grammar and RUN binding.**
- **ASCII only.** Every line of the global block must be ASCII.
- **Frames.** The frame token must equal the canonical decimal of the expected frame, `"1"`…`"12"` (no `01`).
- **Values.** Values match `^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$` under `re.ASCII` and are compared as finite `Decimal` plus sign (as v2).
- **Errors.** Invalid input gives a report without a traceback. A traceback is kept only for unexpected exceptions.
- **RUN binding.** Each RUN.json must satisfy, against the recorded root `R = /mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1`:
  - `label == arm-case`, `arm == arm`, `case == case`, `gpu == false`;
  - `cwd == R/n3-cpu1/<arm>/<case>/cwd`;
  - `argv == ['taskset','-c','14-15', R/build-<arm>/motioncorr, '--i','km_local_nonsquare.star', '--o', R/n3-cpu1/<arm>/<case>/out/, '--use_own','--j','1','--patch_x','4','--patch_y','4','--bin_factor','1','--seed','1','--save_noDW','--skip_defect']`.
  - These are exactly the fields `tools/n3.py` and `runlib.run` write; no field is invented.

**A5 (R1 F1): the live precheck (`precheck-live`).**
- **Environment.** Read-only, explicit arguments, `GIT_OPTIONAL_LOCKS=0`.
- **Trees.** For the five trees it compares against the committed `EXPECT_LIVE.json`:
  - HEAD;
  - `git diff` sha256;
  - exact `git status --porcelain` lines;
  - runner and helper sha256.
- **Index guard.** Each `.git/index` size and mtime must be unchanged across the git calls; a change fails the precheck.
- **Binaries.** It hashes the three live `build-ov-*-cpu/motioncorr` files. They must equal the receipts and the EXPECT values, and be distinct.
- **Processes.** It scans `--proc-root` for any process other than itself and its ancestors whose cmdline, cwd or open fd refers to the scratch, and refuses if one exists. It sends no signals. A missing proc root fails closed.
- **Output.** A new file outside the scratch.

**A6 (R1 F6): controls.**
- New coverage: y-only change, y signed zero, distinct binaries (only that check fires), and spec consistency. The receipt pin refuses a consistently edited receipts file. RUN-binding, grammar, MRC-structure, symlink, snapshot, precheck and live controls are added too.
- Built inputs are separate from the runs.
- Every control record carries the grader sha256, the amendment sha256 and the consumed-input identities.
- A mutant pass reports, for each mutant, killed, equivalent or redundant with a reason, never just "all killed".
- New namespaces only.

Unchanged from `CONTRACT.md`: every row rule and its tolerances, the 24 CPU rows PASS / 16 CUDA UNRUN
requirement, N4 exact kills, exact global-row equality with sign and no tolerance, and the exit codes (0 FULL PASS,
2 STAR layer PASS with FULL UNRUN, 1 FAIL or invalid).
