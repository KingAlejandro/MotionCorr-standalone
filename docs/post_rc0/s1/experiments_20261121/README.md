# MotionCorr experiments, 21 November 2026

This checkpoint records two lines of investigation under [issue #238](https://github.com/KingAlejandro/MotionCorr-standalone/issues/238).

- [CPU and CUDA compatibility](compatibility.md). Substituting FFTW and the CPU peak reader for both correlation inverses met the existing image limit on two selected synthetic movies. Results were mixed on three real movies. Reconstructing with an identical CPU field passed all six real-movie image comparisons. Feeding identical patch pixels to both local aligners still left a residual on EMPIAR-10216.
- [Accuracy against known motion](known_motion.md). B2 passed on one tested low-contrast seed. On the retained noisy fixture, even truth-assisted peak selection from the final correlation maps could not recover the field. Exact shifts at the same patch sites passed. The one-site pedestal case still lacks spatial support for the B2 fit.

Numerical gates and release decisions remain as recorded in the earlier issue and PRs. These runs are diagnostics on selected development inputs. Performance, independent scientific accuracy and release qualification remain open.

The [run recipes](run_recipes.md) record the producer commands, diagnostic switches and replay prerequisites.

The linked JSON files retain the measured values, input and binary hashes, exit codes and GPU-context witnesses where available. [Source SHA-256 index](data/source_sha256.json) identifies the local evidence used to assemble these records. GPU UUIDs, process IDs, timing and host paths were omitted from the public receipts. Raw arrays and binaries remain in the experiment archives.
