# PR117 numeric GPU ID range control — 29 September 2026

Review finding: [r4134289924](https://github.com/KingAlejandro/MotionCorr-standalone/pull/117#discussion_r4134289924).
Tested source: `b70f352b523daffa47ef8e95501dcfdd77fa1861`, based on PR117
`074b169b486d37c8679202c2f0159355eb14befb` (including main `6393547e`).
The publication commit adds only this evidence directory. The bounded source review
of `b70f352b` found no further blocking issue.

The own-backend parser now bounds each decimal multiply/add by `INT_MAX` before
assigning the device ID or querying CUDA. The existing single-device and digit
rules remain; representable IDs and external MotionCor2 arguments retain their
previous handling. Motion correction and numerical code are unchanged.

## Executed acceptance

| Check | Result |
| --- | --- |
| Fresh CPU build; required test inventory | PASS; 21 required tests, none missing |
| Full CPU CTest | 21/21 PASS |
| Scheduler regression suite including actual binary | 54/54 PASS |
| Scheduler mutation controls | 83/83 detected, zero skipped |
| Six distinct movies, serial versus three CPU workers | 6/6 exact comparisons; six distinct payloads; aggregate STAR identical |
| Old CPU binary against expanded range regression | Expected FAIL: oversized `2147483648` reached the missing-CUDA refusal instead of the required range refusal |
| Old CUDA binary, `--gpu 4294967296` | Defect reproduced: one enumeration call, logical GPU0 selected, then missing-input refusal |
| Fresh CUDA 12.8 / sm80 build | PASS |
| Fixed CUDA CLI matrix | 10/10 PASS: four oversized IDs refuse before enumeration; zero/leading-zero and `INT_MAX` boundaries follow normal handling; two external-backend cases retain their handling |
| Existing actual-binary CLI case against CUDA build | PASS |

The CUDA CLI controls use the actual CUDA-linked executable with only
`cudaGetDeviceCount` interposed to return one device and record every call.
A deliberately nonexistent input STAR stops execution before movie processing.
**These are parser/pre-initialization controls, not fresh GPU motion computation,
all-24 correctness, or performance measurements.** In particular, the old binary's
“Using CUDA” message witnesses the wrong parsed ID, not executed GPU kernels.

The old CPU binary was built from `169b1b2582ae28b2b643227c534e19db32602892`;
the retained old CUDA binary was built from
`a48c7f501bc116394830bcbeda10d9c2b4a3f9f9`. Both vulnerable validation/conversion
blocks are byte-identical to PR117 `074b169b` (block SHA-256
`c563b2d57f54291c26a9a7fc8220428da3b854065b6e8d7aef08648b18cd40ca`).
They are separately identified in `provenance.json`, rather than relabelled as
current PR binaries. The earlier failures and retained native evidence remain in
the preceding evidence directories.

## Resources and reproduction

CPU run: cpu64, CPUs 32–47, `membind=1`, validation lock,
build at most 16 threads, sequential CTest, worker total at most 12 threads.
Driver PID3811233 ran 14:02:31–14:04:33 UTC. Existing ctffind processes
1156942 and1635429 remained unchanged.

```sh
flock -n /tmp/motioncorr-issue96-cpu-validation.lock \
  taskset -c 32-47 numactl --membind=1 bash \
  /home/ubuntu/mc-pr117-gpu-range-20260929/src/docs/multi_gpu/port_validation/cpu64_port_validation.sh \
  /home/ubuntu/mc-pr117-gpu-range-20260929
```

CUDA CLI run: VM CPUs104–111, `membind=1`; reserved GPU1 UUID
`GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` with its correctness lock,
shared build lock and build-j4. Driver PID1875094 ran 14:02:31–14:03:30 UTC.
`run_cuda_cli.sh` records the exact build and invocations; `check_cuda_cli.py`
asserts old/fixed behavior. No GPU computation or timing campaign was launched.
At 14:08:34 both drivers were absent, all three owned locks were available and the
VM compute list was empty; release receipts are retained.

## Artifacts

- `cpu64-reports.tar.gz`: commands, full validation/CTest logs, old-source failure,
  mutation results, inventory, input and output STAR/JSON reports.
- `cpu64-files.json`: hashes and sizes of all retained CPU artifacts, including
  image/PDF/EPS payloads omitted from the compact reports archive.
- `cuda-cli-raw.tar.gz`: build/configuration logs, old and fixed CLI logs, exact
  arguments, enumeration records and binary/shim hashes.
- `provenance.json`: source and binary hashes, resource limits and archive hashes.

The complete 16,461,130-byte CPU archive is retained locally at the path in
`provenance.json`, SHA-256
`d9eb6be8638e13f97a1ec993569054775beea6f022b4d9451b208da0bae8d9f0`;
the full remote run remains under `/home/ubuntu/mc-pr117-gpu-range-20260929`.
No scheduler scaling claim, PDF equivalence claim, scientific gate change, or
additional feature is made by this parser fix. Exact publication-head CI and the
requested Codex delta review are separate from these executed local checks.
