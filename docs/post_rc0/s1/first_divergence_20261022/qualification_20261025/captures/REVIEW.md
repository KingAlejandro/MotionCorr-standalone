# Independent Review: W4 CPU Capture v3 Logging-Neutrality Amendment

## Verdict

**NO BLOCKER** (PASS for the bounded v3 logging-neutrality amendment and remaining-7 selector campaign, subject to the exact conditions below).

---

## Scope & Reviewed Artifacts

This review covers only the v2-to-v3 delta and selector `[1, 1]` data-reuse contract, reusing the prior independent review of the unchanged cleanup, resource-lease, and source-pinning controls in `capture_cpu_v2.py`.

| Artifact | Path | SHA-256 |
|---|---|---|
| Amendment note | `/tmp/motioncorr-20261025-w4-capture-v3/AMENDMENT.md` | `d59f459831fd59e5451e76e66dd982ab3cf51d01353adb4fcb29ab0ea4392a2c` |
| Driver v3 | `/tmp/motioncorr-20261025-w4-capture-v3/capture_cpu_v3.py` | `c69d5fdaa98d0b509ad2a13d8fd82020af171b7a4f288b035ddb9f468484dcb6` |
| Protocol v3 | `/tmp/motioncorr-20261025-w4-capture-v3/protocol.json` | `cd931a88cb194dc24a7ed2cdcaa6827f89f71c70526dbe2e8ce1ebb9e45d4e3d` |
| Log neutrality tests | `/tmp/motioncorr-20261025-w4-capture-v3/test_log_neutrality.py` | `2ac4ad90cc1341573901073badfcf629ad8c76bb7a2db1d47c97f2162a0ef236` |
| Baseline `affine.log` | `/tmp/motioncorr-20261025-w4-capture-v3/retained-affine.log` | `793124b035353e0c5e45d68ac6bfbf2b97516c5fff7f936c00a6cb1b84955dd4` |
| Attempt-1 `affine.log` | `/tmp/motioncorr-20261025-w4-capture-v3/attempt1-affine.log` | `9ba5e333890a96c2f8710e4a95862faa720cded2127c3b0b4a560ae1314c3a4d` |
| Driver v2 (reference) | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c3dca0d/docs/post_rc0/s1/first_divergence_20261022/affine_patch_oracle/cpu_lattice_capture_20261023/capture_cpu_v2.py` | `884e7424fbb49d1c887301129a20f29ae89467839defcd919810bfa1f17bf1b2` |
| Protocol v2 (reference) | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c3dca0d/docs/post_rc0/s1/first_divergence_20261022/affine_patch_oracle/cpu_lattice_capture_20261023/protocol.json` | `c2e7712bb4c16bf4a4e80ce69694177e0961e0a8a608b5e8d62ae217693db15f` |
| Attempt-1 `RESULT.json` | `/tmp/motioncorr-20261025-parent/w4-cpu-capture-collected/RESULT.json` | `87a7d15eccd068ea500f1d492bc628f140c6acbb13ccfd137372e2a0cbf9871e` |
| Durable attempt-1 archive | `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261025/W4-CPU-capture-attempt1.tar` | `e6a4e92b78b5e509a33767445ed5a2416236d6f6ac075aa8567880a83d3ccf6a` |

---

## Point-by-Point Verification

1. **No numerical gate relaxation or hidden source/input/binary/product/resource change (`capture_cpu_v2.py` vs `capture_cpu_v3.py`)**
   - `diff -u` between `capture_cpu_v2.py` and `capture_cpu_v3.py` confirms that the only code changes are:
     - The module docstring updating the campaign description to v3;
     - Addition of `normalized_log(path, output)`;
     - Replacing `checks['affine.log'] = (base / 'out/affine.log').read_bytes() == (run / 'out/affine.log').read_bytes()` with `checks['affine.log:version3_output_path_and_wall_only'] = normalized_log(base / 'out/affine.log', base / 'out') == normalized_log(run / 'out/affine.log', run / 'out')`.
   - All 20 `pins` entries in `protocol.json`, `old_scratch`, baseline `affine.log` hash (`793124b0...`), overlay tar verification (`check_overlay_archive`), `state/global.txt` and `state/model.txt` byte equality, `.star` output-path-normalized byte equality, `.mrc`/`.mrcs` header+payload byte equality and timestamp label normalization, `captures()` schema (`c1.json` global `[0,0]`, `c2.json` patch selector, non-empty `.bin` arrays), CPU `[13]` affinity, single-thread environment, `/tmp/motioncorr-w4-cpu13.lock` non-blocking flock, 64 MiB `scratch_cap_bytes` (`67108864`), 1 GiB `minimum_free_bytes`, and 120 s per-child timeout with process-group `SIGTERM`/`SIGKILL` cleanup are byte-for-byte identical.

2. **Schema-validated log normalization is fail-closed with no overbroad masking**
   - `normalized_log(path, output)` requires `n_written == 1` and `n_wall == 1` (rejecting missing or duplicate lines).
   - For the output-path line, `line.rstrip('\n') != written + str(output / 'affine.mrc')` validates that each arm's log names **its own** exact `<output>/affine.mrc` path (preventing cross-arm path spoofing, arbitrary path substitution, or trailing characters).
   - For the wall-time line, `re.compile(r'Full movie wall time: ([0-9]+(?:\.[0-9]+)?) s\n?\Z').fullmatch(line)` plus `math.isfinite(float(m[1]))` accepts only a finite nonnegative decimal number of seconds and rejects negative values, `nan`/`inf`, scientific notation, trailing garbage, or float overflow.
   - All other lines (including movie dimensions, frame grouping, every global and patch iteration count and RMSD value, and polynomial fit RMSD X/Y) are appended unmodified with `keepends=True` and compared exact.
   - All 6 unit tests in `test_log_neutrality.py` plus independent adversarial checks (duplicate/missing written-path line, cross-arm output path, negative wall time, 400-digit float overflow, extra path suffix) passed locally.

3. **Imported selector `[1, 1]` provenance and immutability of original v2 FAIL**
   - Attempt 1 (`RESULT.json` SHA-256 `87a7d15e...`) ran under pinned `driver_sha256` `884e7424...` (`capture_cpu_v2.py`) and `protocol_sha256` `c2e7712b...` (`protocol.json` v2) on `4-gpu-vm` (`uid=1004`, `affinity=[13]`), exited `0` on selector `[1, 1]`, passed all capture inventory and state/MRC/STAR neutrality checks (`state/global.txt`, `state/model.txt`, `affine.mrc:header_payload`, `affine.mrc:labels`, `affine.star`, `corrected_micrographs.star` all `true`), and failed solely on `affine.log: false` due to the two expected lines (`<output>/affine.mrc` path and `0.014 s` vs `0.015 s`).
   - All 93 recorded files in `launches[0]['files']` (including `c1.json`, `c2.json`, all 80 `.bin` capture arrays, `state/global.txt`, `state/model.txt`, and `out/affine.log`) were verified by SHA-256 and byte length in both `/tmp/motioncorr-20261025-parent/w4-cpu-capture-collected/campaign/patch-1-1` and `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261025/W4-CPU-capture-attempt1.tar`.
   - `protocol.json` v3 explicitly records `"original_protocol_sha256": "c2e7712bb4c16bf4a4e80ce69694177e0961e0a8a608b5e8d62ae217693db15f"` and `"imported_selector": [1, 1]`, preserving the original v2 `FAIL` record without relabeling or overwriting it.

4. **Remaining 7 selectors do not repeat `[1, 1]` and respect the 8-launch total budget**
   - `protocol.json` v3 sets `"selectors": [[1, 2], [1, 3], [2, 2], [2, 3], [3, 1], [3, 2], [3, 3]]` (7 distinct selectors; `[1, 1]` removed, center `[2, 1]` already covered by baseline) and `"maximum_native_launches": 7`.
   - Combined with the single prior native launch for `[1, 1]`, total native launches across both namespaces cannot exceed `1 + 7 = 8`, with no per-selector retry and hard refusal if `campaign` or `RESULT.json` already exists in the new scratch root.

---

## Exact Conditions for Execution & Qualification

1. **Original v2 namespace immutability**: `/mnt/clathrin/alex-motioncorr-w4-cpu13-20261025-d3e1b33e-1082-478e-815a-032ea5f3a83e` (and its collected archive) must remain untouched with `status: "FAIL"` under schema `w4-affine-cpu-lattice-capture/1`.
2. **Read-only v3 grade for selector `[1, 1]`**: Any v3 qualification of selector `[1, 1]` must be recorded as a separate, read-only versioned evaluation artifact referencing attempt-1 `RESULT.json` (`87a7d15eccd068ea500f1d492bc628f140c6acbb13ccfd137372e2a0cbf9871e`) without mutating the attempt-1 files.
3. **Single remaining-7 execution**: Execute `capture_cpu_v3.py` (`c69d5fdaa98d0b509ad2a13d8fd82020af171b7a4f288b035ddb9f468484dcb6`) with `protocol.json` (`cd931a88cb194dc24a7ed2cdcaa6827f89f71c70526dbe2e8ce1ebb9e45d4e3d`) in one fresh canonical `/mnt/clathrin/<new-namespace>` directory on `4-gpu-vm` (`uid=1004`, CPU `13`, `maximum_native_launches=7`, no retries).
4. **Scope boundary**: `CUDA` capture remains `HELD_UNRUN` and `truth_fit_science` remains `UNRUN_THIS_STAGE`; C1, `main`, numerical gates/defaults, adoption, C2, and M6 remain unchanged.
