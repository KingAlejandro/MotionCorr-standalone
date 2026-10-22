# Parent response to independent Opus round 2

Reviewed head `f4fc51723ac3f32dc956dcf9e755aaa71b220d0b`. Report and independent-check files copied verbatim from `/tmp/motioncorr-star265-review-r2-20261022/`; hashes in `SHA256SUMS.txt`. No material findings; prerequisite-only DRAFT publication ready.

- R2-L1: corrected the F02 scientific-branch range to all 13 coefficients, 3.5e-12 to 4.8e-10 absolute, using the reviewer's checked values. No CSV/result changed.
- R2-L2: shared-source §9 re-entry wording now distinguishes the three-configuration/touched-route/native-GPU requirements from the additional format rows in the CPU-only list. No requirement removed.
- R2-L3 / R1-A4: narrowed the source cleanliness statement to the actual recorded `src` and `CMakeLists.txt` check. The frozen `run.sh` remains untouched; a whole-tree check on future reuse remains open.

These are routine documentation corrections after independent review, not a third independent round. Frozen criteria, fixtures, harness, receipts and production are unchanged; no run was repeated. #265 remains FILED ONLY. K2 remains NOT MET because F09 is rejected by the real reader. Maintainer parity decision, real pre-write 10641 coefficients, Linux reader behaviour, RELION interoperability, subnormal/non-finite write policy and global_shift precision remain unresolved.
