# Native CUDA CTest on the composed candidate — 29 Sep 2026

**30/30 PASS**, 0 failed, 103.57 s total. This is a real device run, not a
compile check.

| | |
|---|---|
| Source | `0ed67fabfc95ab13492a91579e5238ee40075d40`, clean working tree |
| Host | `4-gpu-vm`, AMD EPYC 7452, four A100 80GB PCIe, driver 570.86.10 |
| Device | **GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`** only, via `CUDA_VISIBLE_DEVICES` |
| CPUs | `taskset -c 96-103`, the shared eight-CPU cap from #66 |
| Build | Release, `-DCUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=80`, `-j4` under `/tmp/motioncorr-vm-build.lock` |
| Binary | `motioncorr` `7b71e7ec…`, `motioncorr_faultinject` `a17fe77b…`, `cuda_fault_matrix` `670ee933…` |
| Lock | `/tmp/motioncorr-gpu3-integrate.lock`, `flock -n` |

GPU0, GPU1 and GPU2 were not used: they belong to the shared
reconstruction-cleanup fix validation. The occupancy gate reads
`--query-compute-apps` before taking the lock and **refused a first attempt**
because something briefly held a context on GPU3; the run below is the retry
after that cleared, and `occupancy-before/recheck/after.csv` are all empty for
the devices in question.

Registered: **30** tests — 23 device-free, 7 `cuda`-labelled of which 6 are
`hardware`. `CudaU16FailurePaths` stays unregistered because
`MOTIONCORR_U16_TEST_MOVIE` was not supplied; that is the intended default and
the count reflects it.

Both preprocessing arms ran and both passed:

| Test | Time | What only this arm can see |
|---|---|---|
| `CudaPreprocessingFailurePaths` | 4.86 s | the compact uint16 staging path; additionally requires the "Released native uint16 host staging" and "Materialized native uint16 frames as float" log witnesses |
| `CudaPreprocessingFailurePathsFloatHost` | 3.74 s | the float host movie every non-uint16-TIFF input still takes |

Keeping both was the composition decision: PR115 registered only the second and
PR118 only the first, and the composed source contains both production paths.

## Scope

Correctness only. No timing, throughput or scaling figure appears here and none
was measured; the run shared the box with nothing but was not an isolated
benchmark and its durations are CTest bookkeeping. This does **not** cover the
all-24 serial-versus-2-and-4-worker matrix, which needs four devices and is
queued separately, and it does not cover the pending shared reconstruction
cleanup fix, which is not in this source.

## Files

`source.txt`, `source-status.txt` — revision and clean-tree proof ·
`host.txt` — devices, driver, CPU · `binary-hashes.txt` ·
`registered.txt` — the full collected inventory · `ctest-native.log` — every
case with its time · `occupancy-*.csv` — device occupancy before, at retry and
after · `configure.log`, `build.log.tail`.
