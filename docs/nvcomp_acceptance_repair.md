# Existing nvCOMP route: checksum acceptance repair

This narrow extraction from PR138 changes the existing checksum mechanism only.
The U16, one-row-per-strip eligibility, TIFF admission, conversion, ingest
selection and decoder trust policy remain unchanged. Issue134 remains open.

## Changes

- Each checksum block checks the decoder status and exact decoded length before
  reading its output. Rejected chunks leave their checksum slot untouched.
- The host rejects the entire batch on status/length before consulting any
  checksum, preserving the original decoder diagnosis even when an earlier
  chunk has a bad checksum.
- Adler weights and lane sums are reduced modulo65521 before overflow. Healthy
  checksums remain the RFC1950 Adler-32 value; the independent512MiB control
  distinguishes the old overflowing reduction.
- The production kernel is shared with the focused host/native tests. This
  retains the donor short-final-strip test API without admitting that format in
  MotionCorr's existing ingest route.
- The acceptance caller retains child stdout/stderr and a failed verdict even
  when startup never creates a movie log.

## Acceptance

Required CPU inventory:39 names, preserving main's36 and adding
Adler32Arithmetic, Adler32KernelHost and NvcompAcceptanceDiagnostics.
The two device tests CudaAdler32 and CudaNvcompAcceptanceFailures require an
actual CUDA+nvCOMP build. Compilation and host controls do not certify them.

Local focused checks:6/6 pass, collection39/39. Diagnostic retention passes
normal/optimized and rejects the original PR138 caller in both modes. Full
Linux/native matrices, current-source review and CI remain pending until
recorded below. macOS's inherited SyntheticRegression failure remains separate.

Native controls must run the actual kernel on healthy/large/status/short cases,
reject separately compiled guard/arithmetic mutants, and exercise the actual
pinned runner's descriptor-readback ordering. Healthy compressed input with
injected result descriptors does not prove malformed-Deflate decoder safety.
No throughput, scientific accuracy or wider-format support claim is made.

Provenance: original donor PR138 head875857f1, acceptance composition50a59b51;
this extraction starts from accepted main e61c9739 and does not import the donor
branch's broader route or obsolete runner history. Original authorship and
failed acceptance records are retained.
