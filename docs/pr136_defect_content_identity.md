# PR136 defect premask content identity repair

## Scope and ownership

This repair starts from PR136 `e2ca6032836fbcea982e7991605647b23d91d252`.
It changes only external defect-mask cache identity and its focused CPU controls.
Gain filename/generation, mask geometry, runner ownership, and the per-movie hot
pixel copy remain part of the existing contract. CUDA pool admission, retention,
cleanup, numerical arithmetic, and tolerances are unchanged.

TXT lookup reads the file bytes on every movie. A reusable premask requires the
same filename **and exact bytes**, as well as the existing gain/geometry keys.
The checked MotionCor2 parser consumes those same bytes from a stream snapshot;
it never reopens the filename after checking identity. Equal size and timestamps
are insufficient. Snapshot read or parse failure invalidates the old mask and
clears/releases its content key before propagating the failure. The common
stream parser preserves the previous extraction checks and diagnostics.

Image defect maps retain the original per-movie reader and are deliberately not
advertised reusable. Their readers reopen filenames and some supported formats
have separate header/data files. This conservative fallback avoids introducing
an unproved snapshot architecture or metadata-only key for those readers.

## Cost and limitations

The runner now retains one full TXT file's bytes (plus string capacity overhead)
while its text premask is valid. Every lookup reads another full snapshot; on a
miss the stream parser also owns a temporary copy after the previous key has
been released. These are host allocations, not GPU VRAM or measured process RSS.
There is no arbitrary new file-size cap: very large TXT files incur proportional
read/memory cost and allocation failure propagates with the cache invalidated.
Concurrent in-place writing is not promised to produce an atomic filesystem
snapshot; the exact bytes observed by a lookup are the bytes it parses and keys.
Image-map caching is deferred. No performance result is claimed for this repair.
Legacy PR136 cache/benchmark evidence remains historical, not evidence for this
new source.

## Executed controls

Local AppleClang 21 / CUDA=OFF, with the bundled Python 3.12 + NumPy used for
configuration:

- `cmake --build build-content-identity --target defect_parser -j 4`
- `ctest --test-dir build-content-identity -R '^DefectParser$' --output-on-failure`
- Direct `defect_parser`: **87 assertions passed, 0 failed**.
- The exact predecessor production source/header, built with these new tests:
  exit 1, six assertion failures. The targeted failures include changed valid
  coordinates at identical byte length/mtime, malformed replacement at that
  same identity, cache invalidation after failure, and same-size/same-mtime image
  replacement. Both valid rectangles contain four pixels, so count alone cannot
  make this test pass.
- Existing parser syntax/range/EOF controls, gain generation, geometry, hot-pixel
  isolation, dense-defect behaviour, and independent-runner controls remain in
  the same suite. Unchanged TXT repeat and restoration are positive controls.

The original direct filename parser's libc++ directory-read diagnostic remains
platform-dependent; the new snapshot reader uses `fread`/`ferror`, and its
read-error/cache-invalidity control passes locally. A source comparison confirms
that the extracted common parser body retains the predecessor's tokens apart
from whitespace/indentation.

CUDA compilation and native movie output/failure validation of this repaired
source are **UNRUN** here. CPU controls do not substitute for those gates. No
SCARF/VM job or benchmark was started or altered.
