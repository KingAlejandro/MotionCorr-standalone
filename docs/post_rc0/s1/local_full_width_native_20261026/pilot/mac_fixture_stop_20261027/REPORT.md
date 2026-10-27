# Mac fixture identity STOP, 2026-10-27

Requested Mac arm64 pilot at starting HEAD `381d7d0bf4a33610370022040a5d084ccc29e88e`. No native movie was launched. The explicit fixture identity stop rule applies: 32/33 pinned files match in size and SHA-256, but `MANIFEST.json` does not. Its sole textual difference against the pinned audit-bundle manifest is `numpy` = `2.4.2` instead of `2.5.3`. This is a failed identity check even though all 32 data files match; no manifest or fixture was altered to make it pass.

- Pinned manifest SHA-256: `9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc`.
- Generated manifest SHA-256: `f48c2f16398c356533865d3377a11659bb35bdc845dc7eb0aa670425c4929b39`.
- `git archive 5bcfa987` tree `d1a67904bdd515bebc548f881e8889ac4a682bb2`; archive SHA-256 `edb6ad1bf729a67dfdd634ea66f87e2fa5a33dc587e3367a51beb54ef7253942`. This is the documented CMake successor to reviewed source `634e4b48`, on macOS arm64; no Linux byte identity is asserted.
- Generator SHA-256 `5e781bb290b3f12b38f6dc7ec18bb955d56331219dc0216321e010ecbcdaf4cc`, matches admission pin. Python `/Users/alex.konstantinov/.local/bin/python3`, NumPy 2.4.2. Command: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 /Users/alex.konstantinov/.local/bin/python3 /tmp/mc-mac-pilot-20261027/source/test-data/generate_motion_diagnostics.py --outdir /tmp/mc-mac-pilot-20261027/fixtures-r2` (exit 0).
- Initial fixture preparation failed before generation because its output directory was already present (`FileExistsError`); the successful fresh-directory attempt is retained separately. Logs and generated files remain under `/tmp/mc-mac-pilot-20261027/`.
- Configure was interrupted after the fixture mismatch; build, binary hash, CTests, venue amendment, OFF/ON producers, checker/scorer, predictions, regressions and reach witness are UNRUN. No result is inferred from Linux. No SSH was attempted.

Next: obtain an approved NumPy 2.5.3 environment and regenerate into a fresh directory; recheck all 33 frozen hashes before any producer. This is a proposal, not an override of the STOP.
