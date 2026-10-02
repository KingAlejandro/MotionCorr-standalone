# PR138 checksum and decoder-acceptance repair

Starting source: `7b47c18cefbcc3c754c0df660ce3b2ceb134fee0`. This narrow
follow-up addresses reviews `5949134611` and `5949227743`; it does not alter the
admitted TIFF encodings, the nvCOMP malformed-Deflate trust policy in issue #134,
conversion arithmetic, failure classification, or fallback policy.

## Arithmetic proof

For a strip of `n` bytes, RFC 1950 gives
`A = 1 + sum(d_i)` and `B = n + sum((n-i)*d_i)`, both modulo 65521.
Reducing each coefficient `(n-i)` modulo 65521 before multiplication preserves
that residue. `mc_tiff_adler::Lane` starts with `(n-lane) mod 65521`, subtracts
`stride mod 65521` per byte, and reduces its sums every 4096 bytes. Including the previous
remainder, the weighted sum is bounded by
`65520 + 4096*65520*255 = 68,434,395,120 < 2^36`
and the byte sum by `65520 + 4096*255 = 1,110,000`. These bounds do not depend on strip length.
Every completed lane contributes less than 65521; the 256-lane shared reduction
is less than `256*65521 < 2^24`. Finalization first reduces `n`, then adds the
bounded reduction. None of these steps can overflow its integer type.

The predecessor reduced only after its uint64 weighted reduction had wrapped.
At 512 MiB of `ff` bytes it produced `0x645a3c03`, instead of exact Adler
`0x2a2a3c03`. This is a valid large-strip defect, independent of malformed input.

## Acceptance ordering

The actual Adler kernel receives nvCOMP's per-chunk status and actual size.
It returns uniformly for that block unless status is `nvcompSuccess` **and**
actual size equals that chunk's expected size, before decompressed-output pointer
arithmetic or byte reads. Its output slot is unchanged for a rejected chunk.
Stream ordering makes the decoder's descriptor writes precede this check.

On the host, a complete status/length pass runs before any Adler comparison.
Thus a decoder failure in chunk one is reported before a checksum mismatch in
earlier chunk zero, and no conversion, gain application, or sum kernel is launched
for the rejected batch. The number of host synchronizations is unchanged.
The session's existing failure/cleanup and runner's pinned-route refusal remain
responsible for preventing publication after failure.

## Executed local controls

| control | result | scope |
|---|---|---|
| `Adler32Arithmetic` | PASS | production host/device arithmetic, seven ordinary lengths and every byte of a 512 MiB **logical**, allocation-free constant strip |
| predecessor arithmetic model | discriminating FAIL | frozen uint64 reduction model gives `645a3c03`; this is not a native predecessor kernel run |
| `Adler32KernelHost` | PASS | actual kernel body compiled with explicit single-thread CPU CUDA-syntax doubles; full/short checksum and rejected null-output guards |
| remove status / remove size guard mutants | discriminating FAIL | actual kernel body attempts a null-output read (each process exits by SIGSEGV); not a genuine GPU poison test |
| wrong coefficient-step mutant | discriminating FAIL | ordinary nonuniform checksum mismatch |
| `CiFailClosedControls` | 8/8 PASS with bundled Python | includes both CPU tests in the 34-test required inventory; fixture/collection negatives retained |
| nvCOMP declaration guards, Python syntax, diff whitespace | PASS | static checks only |

Retained local commands, source/binary hashes and logs:
`co/pr138-checksum-20261002/result.json`. No CUDA compiler is installed on this
Mac. The first ambient-Python `CiFailClosedControls` attempt failed because it had
no NumPy (five NumPy-dependent cases); the bundled-runtime retry passed all eight,
retained as `ci-controls-bundled.log`. This is not current-head full 34-test
CPU-suite or CI approval.

## Native controls prepared, not executed here

* `CudaAdler32`: **UNRUN**. Includes the actual production kernel, four healthy
  full/short strip checksums, one bounded 512 MiB **real device** constant strip
  (`--case large`, no TIFF allocation), and failed-status/short-size chunks with
  inaccessible null output. Run each missing-gate native mutant in its own process.
* `CudaNvcompAcceptanceFailures`: **UNRUN**. A separate actual runner binary uses
  only a test-linked readback shim, on healthy compressed input. It changes chunk
  one's returned status or length plus chunk zero's returned checksum. A healthy
  pinned nvCOMP run must publish products; both rejection runs must report
  `nvCOMP rejected strip 1`, report no earlier Adler diagnostic, exit unsuccessfully
  and publish no MRC or STAR. Removing/reordering the caller's status pass must fail
  the diagnostic control. Descriptor interposition is not a corrupt decoder run.
* Current-source native parity, existing recovery controls and full configured
  CPU/CUDA suites: **UNRUN** by this repair owner; coordinator must validate the
  composed candidate at its final source head.

No new timing or throughput result is claimed. This repair does not establish safe
execution of corrupt compressed Deflate within nvCOMP, recovery from a genuinely
poisoned GPU, or stronger input authenticity than the existing Adler contract.
