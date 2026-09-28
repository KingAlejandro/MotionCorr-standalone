# Architectural Design Specification: Reject malformed text defect rectangles

- Issue: #98
- Status: Implemented; CPU acceptance evidence recorded; awaiting maintainer review
- Architect: independent read-only code/spec and license/convention reviewers, consulted on the implementation head
- Base: `4c952b3f54479653512c4d208e09c9a8c02f3726`

## Scope and contracts

Replace the unchecked `while (!f_defect.eof())` loop in `MotioncorrRunner::fillDefectMask`
(the `ext == "txt"` branch) with an extraction-checked parser. A malformed token sets
`failbit` without `eofbit`, so the original loop neither advances nor terminates and feeds
uninitialized `int x, y, w, h` to the mask loops.

Each of the four fields is read as a whitespace-delimited token and converted explicitly.
Streaming directly into integers cannot attribute a failure: an out-of-range value sets
`failbit` only after `operator>>` has consumed its digits, so a recovery read names the
following field. Diagnostics report a 1-based record number, the line the record started
on, the offending field name and its token, and distinguish a truncated final record from
a malformed one.

Rectangle bounds are clipped to the image with overflow-safe arithmetic before any
iteration, so an off-image rectangle costs O(1) rather than iterating its nominal area.

Only the txt branch of `fillDefectMask` and its new test change. The defect-map branch,
the SerialEM detector at `src/motioncorr_runner.cpp:182` and `src/micrograph_model.cpp:344`,
the external-MotionCor2 `-DefectFile` passthrough, hot-pixel detection, dose weighting and
all RNG, noise-model and statistical behaviour are untouched. No runner preflight
refactor is included.

## Input contract

The supported format is the UCSF MotionCor2 one: whitespace-separated integer quadruples
`x y w h`, conventionally one rectangle per line.

- Rejected, each with a diagnostic naming the cause: comment lines, header rows, any
  non-integer field, a field that does not fit in a 64-bit integer, a record truncated by
  end of file, and a leading UTF-8 byte order mark.
- Accepted: blank lines and surrounding whitespace are ignored; an empty or whitespace-only
  file is valid and masks nothing; a rectangle with width or height <= 0 is a no-op; a
  rectangle overlapping the image is clipped to the intersection, and one entirely outside
  masks nothing.

The rejecting cases are self-documenting through their error text. The accepting cases emit
nothing, so they are stated in the `--defect_file` help string as well as here.

## Numerical and resource constraints

The mask produced for any well-formed file is unchanged. Clipping yields the same
intersection the original per-pixel `continue` guards produced, without the signed overflow
the original `y + h` could incur. No new allocation in the mask loop; the parser holds one
`std::string` token at a time. Hot-pixel statistics, replacement PRNG and dose weighting are
not reachable from this change, so no numerical gate is affected.

Behaviour on malformed input necessarily changes: the original code's result was undefined,
so no identity claim against it is meaningful for those inputs. Identity is claimed only for
well-formed files, and is evidenced by the positive-control suite.

## Acceptance and evidence

`tests/test_defect_parser.cpp` calls `MotioncorrRunner::fillDefectMask` directly and is
registered as ctest target `DefectParser` with a 120 s timeout, so a regression to the
pre-fix hang fails the suite rather than stalling it. It covers valid single and multiple
records, missing trailing newline, blank-line padding, empty and whitespace-only files,
malformed token first and last, truncated records, non-integer and out-of-range fields,
comment/header/BOM rejection, diagnostic record and line numbering, zero and negative
sizes, clipping on all four edges, and huge and beyond-INT32 rectangles under a wall-clock
bound.

Acceptance requires a positive control on the implementation head and a negative control
built from the base commit in a separately configured tree, since a copied build directory
retains its original absolute source path and would rebuild the old sources. Both arms run
CPU-only on cpu64 under `flock /tmp/motioncorr-issue96-cpu-validation.lock`, on cores within
32-63, with build and runtime parallelism <= 16, recording inherited cpuset, topology,
CPU and memory NUMA policy and observed placement. No GPU work is performed; issue #26 owns
the GPU slot.

## License

Existing RELION GPL-2.0-or-later notices are preserved. No dependency or third-party code
is added. The parser is original work and is not derived from MotionCor2 or MotionCor3
sources; only the format name is referenced.

## Changed-file whitelist

- `CMakeLists.txt`
- `src/motioncorr_runner.cpp`
- `tests/test_defect_parser.cpp`
- `.gitignore`
- `agents/designs/issue_98_text_defect_parser_reject_malformed.md`

## Known limitations

A path can open and still fail to be read; a directory whose name ends `.txt` is the
reachable case, since `std::ifstream` opens a directory successfully on both Linux and
macOS. `peek()` returns `EOF` for that as well as for a genuine end of file, so treating
`peek() == EOF` as normal completion would mask nothing and let the movie publish as if
defect correction had succeeded.

The parser therefore treats end of input as clean only when the stream actually reached
end of file without an error, and otherwise reports a named read failure. How much the
platform exposes was measured rather than assumed, with a directory opened and a single
`peek()`:

| platform | `eofbit` | `failbit` | `badbit` | distinguishable |
|---|---|---|---|---|
| Linux, g++ 13.3, libstdc++ | false | true | **true** | yes |
| macOS, Apple clang, libc++ | true | false | false | **no** |

The check is therefore effective on the deployment target and inert on libc++, where the
condition is genuinely unobservable at this layer. The regression test probes the running
platform and asserts rejection only where the distinction exists, reporting explicitly
when it does not, so it cannot pass silently on a platform that cannot see the fault.
An earlier revision of this document claimed libstdc++ reports a failed read as end of
file; that was wrong, and the table above supersedes it.

A read error arising mid-record is reported as a read failure rather than as a truncated
record, for the same reason.

The strict parser runs on the `--use_own` path only. The external-binary path at
`src/motioncorr_runner.cpp:725-730` passes `-DefectFile` through to MotionCor2 unvalidated,
so the same file can be accepted there and rejected here. `fn_defect` is job-global
configuration but is validated per movie, and the per-movie handler at
`src/motioncorr_runner.cpp:629` continues to the next movie, so one malformed path yields a
full read per movie and one error per movie before the job fails. Validating once in
`initialise()` beside the SerialEM check would address all three; that is a runner preflight
change and is deliberately excluded from this issue's scope.

No CLI-level `--defect_file` identity run exists, because the repository contains no defect
fixture and no movie fixture wired to one. Mask identity for well-formed input is asserted
at unit level only.
