# Parent N1 readback verification

Read-only raw receipts and configured CTest inventories captured at 2026-10-22T21:11:24Z from the original clean source `0a1f64ab3e192c3ebad57b35149d872b21331730`. `check_guard_n1.py` is the original verifier, retained verbatim; its paths point to the parent scratch `/tmp/motioncorr-orchestrator-20261022`. Do not run it here assuming relative paths. The summary adds the separately checked health receipts after the script ran.

CPU77, CUDA111, CUDA+nvCOMP114 test cases all ran and passed, with listed sets equal to actual JUnit sets, no duplicates/skips/failures/errors, and three required guard tests. The collected inventory is from existing configured builds, not a historical frozen expected-union file. Health receipts separately show the expected GPU1 UUID, no compute process, volatile uncorrected ECC0 and no pending/failed remap. They do not establish aggregate ECC or kernel-Xid status.

N1 build/test evidence only. N2/N3/N4 qualification remains incomplete. Round3 review did not inspect these native receipts. No science, timing, parity approval or full native campaign acceptance follows.
