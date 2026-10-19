# #215: TIFF identity across nvCOMP ingest passes

Code/test head: `76fa8112b829d4e3e9d95f7f869513da5e64b39d`, based on main
`c8844894`. Production changes first appeared at `bf2e2d4a`; `76fa8112` only
corrects the test shim for GCC's fortified `__pread_chk` call. Later evidence
and release-document commits do not change executable source.

The tag-scan TIFF descriptor pins device, inode, size and nanosecond mtime.
Each fresh reader handle is checked against that identity, as is the pathname
before opening readers and before every chunk submission. The latter also
checks each descriptor after staging. A mismatch or failed identity lookup
returns the existing nvCOMP refusal, with:

```
nvCOMP ingestion declined (TIFF file identity changed or unavailable); using the host reader.
```

`auto` then uses its existing compact host reader; the explicit `nvcomp` pin
continues to refuse when that route is unavailable. No decoder, arithmetic
gate, tolerance, product format or dependency changes. No inherited RELION
numerical behaviour changes, so no output-parity sign-off is requested.

## Controls and re-entry

Native venue: `ssh -J ccp4-gateway 4GPUs`; scratch
`/mnt/clathrin/alex-motioncorr-215`. GCC 13.3, CUDA 12.8.61, nvCOMP
5.3.0.16, A100 80 GB PCIe UUID
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` (physical GPU3).
Every GPU invocation holds `/tmp/motioncorr-gpu3-correctness.lock` and checks
occupancy; it selects the UUID through `CUDA_VISIBLE_DEVICES`. Builds and
runs use `taskset -c 64-71` (eight CPUs), Release, and builds use `-j8`.
There is no timing/performance claim. Other users' jobs remained untouched.

Reproduction drivers: [build.sh](build.sh), [validate.sh](validate.sh),
[native_tutorial.py](native_tutorial.py). Stage a clean Git checkout at the
code/test head using a Git bundle (this run), `git archive`, or rsync; do not
use macOS tar. Git metadata is needed by the existing fail-closed fixture
checks. Copy the drivers to the scratch root, then run
`nohup bash /mnt/clathrin/alex-motioncorr-215/validate.sh` on a quiet build host.
The driver retains command exit statuses and stops on unexpected failures.
This run used continuations to reuse checked builds and run CPU CTest first
while every GPU lane was occupied; the retained logs distinguish those stages.

`CudaNvcompTiffIdentity` runs nine rows: two compact host references, one
healthy pinned nvCOMP input, and append/atomic-rename mutations at tag-scan
close, first reader open, and first strip read. The replacement is a separately
encoded valid TIFF with different pixel values. Every mutation row requires
both the shim witness and an observed size/inode/content change, the production
identity-decline log, the compact route witness, completion STAR and identical
MRC payloads to the corresponding host reference. The healthy row requires
nvCOMP routing and identical host-reference payloads.

For the negative control, only `cuda_movie_session.cu` is restored from
`c8844894`; the identical shim, test and CMake registration stay in place.
Both binaries are rebuilt with checked exit status. All six mutations must
occur on this unfixed binary, and all six mutation rows must fail the acceptance
predicate. The original fixed source is then restored and rebuilt.

The initial control attempt at `bf2e2d4a` passed the four tag-close/reader-open
mutation rows but rejected the two strip-read rows because no swap occurred.
`nm` showed that GCC fortification called `__pread_chk`, bypassing `--wrap=pread`.
`76fa8112` wraps both symbols. This initial failed attempt is retained separately;
it is not counted as a pass.

Initial 4GPUs CPU suite: **73/74**, CTest exit 8. `ProfilingKit` had two
30-second actual-CLI subprocess timeouts; the other 73 tests passed. Its settle
routine waits for compilers anywhere on the host, and this venue had concurrent
agents building; the parent attributes exactly these two import-subset `TimeoutExpired` errors
to the independent test-harness defect [#246](https://github.com/KingAlejandro/MotionCorr-standalone/issues/246).
The other CLI controls already disable the global settle wait; these two do not,
so a 300-second compiler wait runs inside their 30-second timeout. The failure is retained. No test limit was changed. A clean CPU
Release rebuild/full CTest is run separately on `cpu64`, CPUs 24–31, using
[cpu64.sh](cpu64.sh), after checking occupancy and writable scratch capacity.

Final results at the code/test head (no skipped tests):

- Full CPU CTest on `cpu64`: **74/74 PASS** on the full retry
  ([log](evidence/cpu64/ctest-retry.log), [driver/exit](evidence/cpu64/retry.log)).
  The initial cpu64 run was also 73/74 with the same two #246 timeouts
  ([log](evidence/cpu64/ctest.log)); its driver recorded active `cc1plus`
  processes before CTest. The already-started retry completed without a test,
  timeout or tolerance change. The retry did not stop a compiler or reserve the host.
- Full CUDA CTest on 4GPUs: **108/108 PASS** ([log](evidence/ctest-cuda.log)).
- Full CUDA+nvCOMP CTest on 4GPUs: **111/112**, with **only `ProfilingKit`
  failing from the two exact #246 import-subset `TimeoutExpired` errors**
  ([log](evidence/ctest-nvcomp.log), [compiler observations](evidence/occupancy-at-nvcomp-profiling.txt),
  [timestamped occupancy](evidence/occupancy.log)). This is not reported as a
  green full suite. Every other test passed, including `CudaNvcompTiffIdentity`.
- The dedicated fixed control passed **9/9** rows. The reverse-applied control
  exited **1** as required: its three healthy/reference rows passed; all six
  observed mutation rows failed the identity/fallback predicate
  ([fixed](evidence/control-fixed/result.json), [unfixed](evidence/control-unfixed/result.json),
  [actual log witnesses](evidence/identity-witnesses.log)). Five unfixed mutation
  rows stayed on nvCOMP; the early rename hit the existing zlib-wrapper refusal.
- Real tutorial movies `20170629_00026` and `20170629_00031`, plus gain, match
  the hashes in `docs/workload_corpus/corpus.md`
  ([input identities](evidence/tutorial/inputs.json)). Six two-movie runs cover
  G and L, each with unfixed auto, fixed auto and fixed compact. Both auto arms
  take `nvcomp` for both movies in both configurations; compact stays compact.
  All four complete MRC-header/payload and STAR product comparisons pass,
  normalizing only declared output paths and MRC label timestamps
  ([commands, binary hashes and route log lines](evidence/tutorial/result.json),
  [G unfixed](evidence/tutorial/G-unfixed-identity.json),
  [G compact](evidence/tutorial/G-compact-identity.json),
  [L unfixed](evidence/tutorial/L-unfixed-identity.json),
  [L compact](evidence/tutorial/L-compact-identity.json)).

[Raw evidence archive](evidence/raw-evidence.tar.gz) retains 242 evidence files:
JUnit XML, process/movie logs, route witnesses, generated input/output STARs,
initial failed controls and compiler observations. Selected records remain
plain text beside it. The archive was round-trip checked against every file it contains. [retained-files.json](evidence/retained-files.json)
records remote evidence hashes, including the build/configuration logs retained
on the host; [binaries.sha256](evidence/binaries.sha256) pins the binaries.
The scratch source was clean at collection. GPU locks were released after each
run/batch. No merge or release tag was made.

## Limits

This is an identity check, not a file lock or a Deflate-body validator. A writer
after the final check, or same-size edits with restored timestamps, remains
outside the trusted immutable-input precondition. All fixture TIFFs are valid. In the unfixed early-rename row, stale offsets
triggered the existing zlib-wrapper refusal before the first submission; the
other five mutation rows incorrectly kept the nvCOMP route. No arbitrary
corrupt-Deflate safety claim follows from these controls. No performance, multi-GPU scaling, full QF campaign,
independent collection or Tier D scientific acceptance was run here. Rows not
rerun retain their earlier frozen-source provenance in the acceptance report.
