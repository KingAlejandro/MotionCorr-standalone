# CPU stabilization handoff

Branch `fix/stabilize-cpu-contract`, worktree `work/stabilize-cpu-20260926`, base `3e3a19679337d3de61327c02eef1a2947cf13517`, candidate `2c27c7bcb8a697bcc78e17c224bc88f338f1b9ff`. Clean worktree; `git diff --check 3e3a196` passes.

## Commits (oldest first)

- `db8bc03`: port existing Gaussian cache reset from `8a75a5c`; ordinary clean seeded stream arithmetic unchanged.
- `9933359`: preserve pending and original movie pre-exposure vectors through filtering; original vector used for tomography aggregation.
- `bd53acd`: reject nonpositive grouping/thread options; record false-return failures and fail before joint success outputs while retaining successful per-movie products.
- `c03af7f`: resume requires readable complete requested MRC products plus complete global-shift metadata and parseable declared local model. Generate requested even/odd files when dose weighting is enabled without saving noDW.
- `86cf34f`: sum full-size unweighted frames before late binning; bin odd/even sums as well.
- `b400892`: scale only a cloned native early-binned polynomial model on serialization; keep runtime coefficients unchanged.
- `f543fe7`: reject duplicate/nonfinite local motion coefficients; strengthen unit and tomography regressions.
- `2c27c7b`: reject malformed floating/integer STAR tokens instead of using failed/partial numeric extraction. Parent approved this narrow scope extension after the new regression found `nan` was silently parsed as zero by libstdc++.

These commits are an ordered stack. Some regression harness corrections land in later commits; review/build the final stack, or fold test-only corrections into their owning commits before splitting PRs. PR57 was not applied.

## Runtime evidence

Host `cpu64` / `small-refmac-machine`; CPU only; all builds and tests wrapped in `taskset -c 48-55`, build `-j8`, tests serial. Initial host load 2.07 and existing jobs preserved. GCC 13.3.0, CMake 4.4.3, `CMAKE_BUILD_TYPE=Release`, `CUDA=OFF`, `BUILD_TESTING=ON`.

Remote base/candidate source and binaries: `/home/ubuntu/mc-stabilize-20260926-cpu/{base,candidate,build-base,build-candidate}`. Sources were transferred from exact Git archives; six changed production-file hashes were verified against both local revisions (see `provenance.json`).

Candidate binary SHA256: `c68596ae62c029c06278854a19ccfb850e60fdc46a5f2cf20448ef84cc5696d2`.
Base binary SHA256: `45aa89c7e37c25cf3867c858b874e78250d70269d5f2f802ec781eba93cd4f31`.

Build commands (same for base with `candidate` replaced by `base`):

```sh
taskset -c 48-55 /home/ubuntu/.mc-venv/bin/cmake -S /home/ubuntu/mc-stabilize-20260926-cpu/candidate -B /home/ubuntu/mc-stabilize-20260926-cpu/build-candidate -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON
taskset -c 48-55 /home/ubuntu/.mc-venv/bin/cmake --build /home/ubuntu/mc-stabilize-20260926-cpu/build-candidate -j8
taskset -c 48-55 /home/ubuntu/.mc-venv/bin/ctest --test-dir /home/ubuntu/mc-stabilize-20260926-cpu/build-candidate --output-on-failure
```

**10/10 CTests passed in 5.20 seconds** (final `candidate-ctest.log`): historical SyntheticRegression at 1 and 4 threads, Gaussian determinism, non-prefix resumed exposure, mixed movie failures, invalid options, missing/truncated requested products, tomography interrupted/resumed equality, late-bin exact sums, exported units/repeated save/runtime immutability, and malformed local models.

Base-failing checks used the same helper tests linked to the unmodified base production sources:

- Gaussian: 26824 of 36864 probe pixel bytes differ after a preceding odd-draw movie.
- SPA exposure: resumed movie c gets 8.5 instead of 14.5.
- Mixed failures: base command returns success despite a two-frame failed movie.
- Group zero: base crashes instead of an option-validation error.
- Resume: missing final MRC is skipped because EVN exists.
- Late bin: maximum pixel error 18.944916 versus binning the completed full-size sum; candidate exact for dose/noDW/odd/even products.
- Exported units: base fails the known polynomial roundtrip; candidate passes at nonzero spatial position and first-frame offset, without modifying live coefficients or double scaling repeated saves.
- Tomography: resumed b dose-weighted output differs; candidate matches every requested image and per-movie STAR, and aggregate pre-exposures remain 0/5/11 (CLI offset not counted twice).
- Model parser: base accepts duplicate coefficient indices and `nan`; truncated tables and negative indices were already rejected. Final candidate also rejects trailing numeric junk and invalid textual indices.

All logs and provenance are copied into this directory. No GPU jobs, no remote background job left running, and CPU build slot released.

## Integration notes and limits

- Integrating PR57 must include `even_odd_split` in its real-space inverse-FFT requirement.
- Resume completeness checks inspect headers/file lengths and metadata; they do not reread every image pixel or detect arbitrary bit corruption/configuration changes.
- Valid STAR numeric parsing is unchanged; malformed scalar double/integer tokens now fail globally. Vector/bool parsing was not redesigned.
- Tomography full interrupted/resumed runs are covered. Existing partial-tomography `--do_at_most` aggregation semantics are deliberately unchanged.
- The new exported-model fixture verifies serialization units mathematically; it does not establish whole-dataset local-motion scientific accuracy.
- Full tutorial collection, GPU runtime, EER decoder fixtures, mode-12 resume, external MotionCor2, performance benchmarking, and CPU/RELION image RMSE acceptance are not claimed by this CPU package.
- Source-manifest documentation was not edited under the assigned ownership; root can reconcile it when publishing.
