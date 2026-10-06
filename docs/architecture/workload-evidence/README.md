# Heterogeneous input screen, 2 October 2026

This is separate from the original FFT/granularity campaign in `../evidence`.
Production source is fix commit `47b20d37239a6e8efdce941c85a62c8c6e1bfda0`
over baseline `57e98666a6225a8fdb6dafbdbc356478c21cea3a` (PR #146).
The two experiment scripts remain in PR #144. Local and remote source hashes
were compared successfully against [gpu/source.sha256](gpu/source.sha256).

- Native [venue](gpu/venue.txt), [accounting](gpu/accounting.txt),
  [configure](gpu/configure.log), [build](gpu/build.log),
  [CTest](gpu/ctest.log), [binaries](gpu/binary.sha256).
- Native [case manifest](gpu/matrix/cases.json),
  [results/commands](gpu/matrix/results.json),
  [provenance](gpu/matrix/provenance.json), [audit](gpu/audit.json),
  [probe log](gpu/matrix.log), and per-profile ingest witnesses in `gpu/matrix`.
- CPU [case manifest](cpu/cases.json), [results/commands](cpu/results.json),
  [provenance](cpu/provenance.json), [audit](cpu/audit.json), and ingest witnesses.
- Local [regression before the fix](compressed-sequence-before.log) and
  [full suite after the fix](compressed-fix-ctest.log). The existing macOS
  SyntheticRegression failure remains; NativeMovieStaging is Linux-only.
- A standalone [pipe lifetime reproducer](pipe-lifecycle.cpp), with
  [fclose](pipe-fclose.log) and [pclose](pipe-pclose.log) outputs on macOS.
- [Cross-platform input comparison](workload-cross-platform-inputs.json):
  all canonical samples and uncompressed payloads match; generated mean-header
  rounding differs for four families. Both exact file manifests are preserved.
- [Submitted script](run-workload-scarf.sh); it requires a Slurm allocation.
  `verify_workload.py` was run afterward against retained full outputs.

Full native inputs, corrected images, per-movie logs and metadata remain under
`/work4/scd/scarf1415/motioncorr/issue142-architecture-20261002/workload-evidence/matrix`.
Only compact evidence is committed. The audit needs those full outputs; the
compact evidence alone is not enough to recompute all equivalence checks.

To reproduce, build the fix commit with testing enabled, then run these scripts
from the experiment branch against that binary and its `runner_numerics` helper:

```sh
python3 tools/architecture/workload_matrix.py --binary /fix-build/motioncorr \
  --helper /fix-build/runner_numerics --output /new/scratch/matrix --gpu
python3 tools/architecture/verify_workload.py /new/scratch/matrix
```

Omit `--gpu` for the CPU screen. This intentionally fixed 49-case matrix uses
NumPy, Python's LZMA support and the `xz` executable. It does not assert CPU/GPU
output equivalence, scientific acceptance or performance. MRC/STAR output
equivalence is required within each backend across encoding/route/order arms.
