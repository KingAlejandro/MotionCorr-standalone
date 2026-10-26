# Oracle floor provenance (additive; oracle_floor.py, ORACLE_FLOOR_RESULT.json, PLAN and README are unchanged)

Status: independently reproduced; not an estimator, native or scientific acceptance.

An independent Opus review reproduced the parent's direct physical-field oracle without importing the parent's adapter,
using exact rational temporal projectors, a Householder-QR spatial projector and a Kronecker projection on the dense
72x104 ROI (report `REPORT.md`, `oracle_reproduce.py`, `ORACLE_REPRODUCTION.json`, hashes in its `SHA256SUMS`):

| case / fixed G | reviewer RMS Å | difference from parent |
|---|---:|---:|
| noisy runtime | 0.036792526966214566 | 1.7e-16 |
| noisy STAR | 0.03679260984730614 | 3.2e-16 |
| affine runtime | 4.582282970e-05 | 2.1e-19 |
| affine STAR | 4.496010060e-05 | 2.3e-17 |

Coefficients agree to <=1.9e-14 px. p95 = max at the RMS optimum (0.0594253 Å for noisy). The existence statement stands: a
passing field exists in the fixed-G native-18 family for these two exposed movies.

Reviewer qualifications to keep with any citation: the floor reduces to `pixel_size * |t_hat^T G| / sqrt(5)` for this affine
truth, so it carries no information about the estimator, the patch observations, the CCF weight or the 10 px fit
rejection; it does not carry over to non-polynomial truth or other movies; native noisy (1.645 Å) is ~45x the floor, so
representability is not the cause of that failure. **No floor is subtracted from any result, there is no percentile or
maximum floor claim, and the earlier ~0.465 Å perfect-observation figure is an observation-fit outcome, not this oracle.**

## Pinned original import set of `oracle_floor.py` (preserved, not rerun)
`oracle_floor.py` (sha256 in the table below) imports `score_fields.py` (V1), which pins only five of the
six consumer files and does not check module origins (Opus L6); the result is unaffected because the reproduction imports
neither. Original files:

| file | sha256 |
|---|---|
| oracle_floor.py | 02751125a66b3a1517f8d0d5c4e021a88fe4c66a52237247dc3d88e70211954a |
| score_fields.py (V1) | 81bf519a2360c367e5f593b78b14a609348d54b81e8b66485f6c5dacbf347cd7 |
| ORACLE_FLOOR_RESULT.json | 1d70a3aa34bb19c44edfcd878effce6891398cdbbb58a2a1710a5e8ae2430a4c |
| ORACLE_FLOOR_PLAN.md | 4b38aeb1f060942f8e380ab504835e2fd052d1ac0480776bb3ab3d24104cb16b |
| consumers under /tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6 | check_motion_diagnostics 2be34b82..., check_realistic_motion b0ab099a..., motion_field d72cfad7..., generate_motion_diagnostics 5e781bb2..., generate_realistic_motion a10f694a..., generate_known_motion_fixture f28fbf51... (transitive; pinned by v2/v3) |
| runtime | uv CPython 3.13.7, NumPy 2.4.2 |

No numerical rerun was done for this note. The Opus originals are archived additively outside Git (see V3_INDEX.md).
