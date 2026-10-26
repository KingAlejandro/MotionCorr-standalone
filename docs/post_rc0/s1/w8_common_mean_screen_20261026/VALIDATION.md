# Package validation

The parent independently verified all 490 original manifest entries and nine changed-status field calculations; the largest metric difference is 1.34e-15 Å. No original scientific file was changed.

`git diff --cached --check` returns 2 solely on original CSV CRLF records and the original environment log trailing space (three files). These are retained verbatim to preserve the original hashes. Full output is archived at /Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Common-mean-screen-r1/parent-diff-check.txt (SHA256 3e66c974b3f3afc6ddc2fe3fac95a24be62163e98c6b345221bfb5645b460f72). This is a recorded packaging limitation, not a numerical-test failure.

Original worker stage 1/2 each exited 0. The parent first audit assertion failure and corrected inventory assertion are retained under parent-review. No native, image-pixel or CUDA check was run for this arm.
