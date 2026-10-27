# Amendment (2026-10-27): `amend1_window/SHA256SUMS` listed itself

The original `SHA256SUMS` in this directory (13 lines, written by a `find . -type f` that included the file being written) is kept unchanged. Re-checked by the Opus driver review r1 (finding F7) and again here: 12 lines verify OK and 1 FAILS, `./SHA256SUMS` (its own line cannot match a file that was being written when it was hashed). This is the same class as the Stage A/B `chain.out` case. The other 12 files (guard, tests, rc and output files of the venue window) are unchanged since the window.

`SHA256SUMS.v2` binds exactly those 12 files, excludes itself and this amendment, and verifies 12 of 12. Every manifest the Stage C driver writes excludes itself (and the driver never hashes a file a live process is still writing); the counts above are asserted by `tools/test_ccf_dc_stagec_seal.py`.
