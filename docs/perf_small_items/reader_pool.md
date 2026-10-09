# nvCOMP reader team (fix 4, port of E's reader pool)

Ported from perf/e-omp-wait-hotpixel 4e9d07d + d0bda26, which was based on dfca087
rather than main. The cherry-pick applied cleanly to 7d64043 plus fixes 1 and 2.

**Change.** `ingestCompressedTiffStrips` read each chunk's strips in an OpenMP
parallel region. libgomp's idle threads spin after a region ends, and under the 8-CPU
cap they competed with the thread submitting GPU work (`docs/nvcomp_ingest_pipeline.md`,
`OMP_WAIT_POLICY=passive` rows). `mc_cuda::ChunkReaderPool` (`cuda_reader_pool.h`)
keeps a team that sleeps on a condition variable between chunks. Frames are taken
from a shared counter, as the `schedule(dynamic, 1)` loop did. Each thread's TIFF
handle is opened once per movie instead of once per chunk.

**Failure behaviour.** A refused `TIFFOpen` now declines the ingest before any chunk
is staged, with a WARNING, and the movie falls back to the host reader. Before, it
refused the chunk being read. In both cases the movie completes on the host path.
A throwing reader job is reported as a failed chunk instead of terminating the
process. The `tiff-open-partial` row of `CudaNvcompReconstructionFailures` covers
the refused open.

**Changes to E's code.**
- `runTeam` no longer clears `job_` after the join. Helpers read it only after a new
  generation, which sets it first. Clearing it made the no-join mutant crash on a
  null job (29/50 runs) instead of failing its check.
- The header is now a CMake configure dependency. Without that, editing the header
  left the generated mutant copies stale.
- A doc reference to a file that is not on main was removed.

**Tests.** `ReaderPool` checks that every thread runs once per job and the call
joins, failure reporting and reuse, a one-thread team, and that an idle 8-thread
team uses < 0.25 CPU-s per wall second. Compiled mutants `ReaderPoolMutant_spin`
(helper spins instead of sleeping) and `ReaderPoolMutant_nowait` (no join) must
fail it: 50/50 runs each fail cleanly, and the real test passes 50/50 (MEASURED).
