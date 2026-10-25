#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""One-shot NumPy-only W4 all-patch fit consumer; execute on admitted CPU64 only.

All numeric observations are derived from pinned capture bytes. This program does
not launch MotionCorr and makes no scientific PASS claim.
"""
import hashlib
import json
import math
import os
import platform
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
MANIFEST = ROOT / "input-manifest.json"
OUTPUT = ROOT / "cpu-observations.json"
EXPECTED_SELECTORS = {(y, x) for y in range(1, 4) for x in range(1, 4)}
CENTRES = {(1, 1): (20, 15), (1, 2): (62, 15), (1, 3): (104, 15),
           (2, 1): (20, 47), (2, 2): (62, 47), (2, 3): (104, 47),
           (3, 1): (20, 79), (3, 2): (62, 79), (3, 3): (104, 79)}
NX, NY, NF = 128, 96, 5
ROI = (12, 84, 12, 116)  # y0:y1, x0:x1
STRUCTURAL_TEST_MODE = "--structural-test" in sys.argv[1:]
PINNED_PROVENANCE = {
    "inputs/provenance/file-index.json": "31255dab8eef81ee05f68271ac665429db9a48498b240fbe85ebe228ea3c65c3",
    "inputs/provenance/w4-control21-collection.json": "1c00e50547ffa97b0f6a6b3b8b126cfc35929edd2b7d976f8c3d9ba680476e79",
    "inputs/provenance/RESULT-v2-original-FAIL.json": "87a7d15eccd068ea500f1d492bc628f140c6acbb13ccfd137372e2a0cbf9871e",
    "inputs/provenance/RESULT-v3-remaining7.json": "897e54dbdeb09fe44fb2fcf5ec1675ad1abf9220cf5340b963b58f0fdb13fdb0",
    "inputs/provenance/PROTOCOL-v3-remaining7.json": "cd931a88cb194dc24a7ed2cdcaa6827f89f71c70526dbe2e8ce1ebb9e45d4e3d",
    "inputs/provenance/SELECTOR11-v3-REGRADE.json": "2804699f28210e4d3b68a89c3cb64aa1da0d41481c32c748c1a6f567dc8ba690",
    "inputs/affine_patch_oracle.py": "fc3f11b6b5d89d4643eb4925cdbcb480e57dea36913656ac9d1569360ed44d31",
    "inputs/w4_allpatch_decomposition_v2.py": "8ac6a8f9a0ccf9ede6b2507a4a5ccc657263fcd3553e2c7cb53ee57b522c8df6",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate JSON key " + key)
        result[key] = value
    return result


def fail(msg):
    raise SystemExit("FAIL_CLOSED: " + msg)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checked_bytes(rel, pins):
    p = ROOT / rel
    if not p.is_file():
        fail("missing pinned file " + str(rel))
    raw = p.read_bytes()
    pin = pins.get(str(rel))
    if pin is None or len(raw) != pin["bytes"] or sha256(raw) != pin["sha256"]:
        fail("input pin mismatch " + str(rel))
    return raw


def source_after_iterations(source_files, source_kind):
    prefix = "runs/cpu-affine-on/capture/" if source_kind == "original-index" else "capture/"
    return sorted({
        int(match.group(1)) for path in source_files
        if path.startswith(prefix)
        and (match := re.search(r"(?:^|/)c2-i(\d+)-after\.bin$", path))
    })


def verify_source_pins(manifest, pins):
    raw_by_path = {rel: checked_bytes(rel, pins) for rel in PINNED_PROVENANCE}
    for rel, expected_sha in PINNED_PROVENANCE.items():
        if sha256(raw_by_path[rel]) != expected_sha:
            fail("authoritative provenance pin mismatch " + rel)
    identity = manifest.get("identity", {})
    expected_identity = {
        "original_index_sha256": PINNED_PROVENANCE["inputs/provenance/file-index.json"],
        "selector_1_1_v2_result_sha256": PINNED_PROVENANCE["inputs/provenance/RESULT-v2-original-FAIL.json"],
        "selector_1_1_v3_regrade_sha256": PINNED_PROVENANCE["inputs/provenance/SELECTOR11-v3-REGRADE.json"],
        "v3_result_sha256": PINNED_PROVENANCE["inputs/provenance/RESULT-v3-remaining7.json"],
        "v3_protocol_sha256": PINNED_PROVENANCE["inputs/provenance/PROTOCOL-v3-remaining7.json"],
    }
    for name, expected in expected_identity.items():
        if identity.get(name) != expected:
            fail("input manifest lineage identity mismatch " + name)

    def load_json(rel):
        return json.loads(raw_by_path[rel], object_pairs_hook=unique_object)

    original_index = load_json("inputs/provenance/file-index.json").get("files")
    receipt = load_json("inputs/provenance/w4-control21-collection.json")
    if not isinstance(original_index, dict):
        fail("original file index lacks files map")
    if receipt.get("files") != 94 or receipt.get("all_hashes_verified") is not True or receipt.get("native_jobs") != 0:
        fail("original selector 2,1 collection receipt identity mismatch")
    receipt_inputs = receipt.get("inputs")
    if not isinstance(receipt_inputs, dict) or len(receipt_inputs) != 94:
        fail("original collection receipt must bind exactly 94 files")
    for rel, record in receipt_inputs.items():
        if original_index.get(rel) != record:
            fail("original collection receipt disagrees with source index at " + rel)

    result_v2 = load_json("inputs/provenance/RESULT-v2-original-FAIL.json")
    result_v3 = load_json("inputs/provenance/RESULT-v3-remaining7.json")
    protocol_v3 = load_json("inputs/provenance/PROTOCOL-v3-remaining7.json")
    regrade = load_json("inputs/provenance/SELECTOR11-v3-REGRADE.json")
    if result_v2.get("status") != "FAIL" or len(result_v2.get("launches", [])) != 1:
        fail("historical selector 1,1 FAIL record identity mismatch")
    if result_v2["launches"][0].get("selector") != [1, 1]:
        fail("historical v2 result does not identify selector 1,1")
    old_neutrality = result_v2["launches"][0].get("neutrality", {})
    if old_neutrality.get("affine.log") is not False or any(
            value is not True for name, value in old_neutrality.items() if name != "affine.log"):
        fail("historical v2 FAIL is not isolated to the retained affine.log mismatch")
    expected_v3 = {(1, 2), (1, 3), (2, 2), (2, 3), (3, 1), (3, 2), (3, 3)}
    v3_launches = result_v3.get("launches", [])
    v3_pairs = {tuple(x.get("selector", [])) for x in v3_launches}
    if result_v3.get("status") != "PASS" or len(v3_launches) != 7 or v3_pairs != expected_v3:
        fail("pinned v3 result is not the seven remaining selector collection")
    if result_v3.get("protocol_sha256") != PINNED_PROVENANCE["inputs/provenance/PROTOCOL-v3-remaining7.json"]:
        fail("v3 result protocol ancestry mismatch")
    protocol_pairs = {tuple(x) for x in protocol_v3.get("selectors", [])}
    if protocol_pairs != expected_v3:
        fail("pinned v3 protocol selector set mismatch")
    if regrade.get("schema") != "w4-existing-selector-version3-regrade/1" or regrade.get("selector") != [1, 1]:
        fail("pinned selector 1,1 regrade identity mismatch")
    if regrade.get("verdict") != "PASS_VERSION3_REUSE_ONLY" or regrade.get("historical_v2_campaign_status") != "FAIL_UNCHANGED":
        fail("selector 1,1 regrade does not preserve historical FAIL")
    if regrade.get("new_native_launches") != 0 or not regrade.get("checks") or any(
            value is not True for value in regrade["checks"].values()):
        fail("selector 1,1 regrade is not a complete zero-launch reuse review")
    if regrade.get("original_result_sha256") != PINNED_PROVENANCE["inputs/provenance/RESULT-v2-original-FAIL.json"]:
        fail("selector 1,1 regrade does not name the pinned v2 FAIL result")
    if regrade.get("protocol_sha256") != PINNED_PROVENANCE["inputs/provenance/PROTOCOL-v3-remaining7.json"]:
        fail("selector 1,1 regrade protocol ancestry mismatch")

    launch_by_selector = {
        tuple(result_v2["launches"][0]["selector"]): result_v2["launches"][0],
        **{tuple(x["selector"]): x for x in v3_launches},
    }
    for key, selector_record in manifest.get("selectors", {}).items():
        y, x = map(int, key.split(","))
        selector = (y, x)
        source_kind = None
        source_files = None
        for entry in selector_record.get("entries", []):
            source = entry.get("source_pin", {})
            candidate = source.get("record")
            if candidate == "original-index" and selector == (2, 1):
                source_kind, source_files = candidate, original_index
                break
            if candidate == "v2-result" and selector == (1, 1):
                source_kind = candidate
                source_files = launch_by_selector[selector].get("files", {})
                break
            if candidate == "v3-result" and selector in expected_v3:
                source_kind = candidate
                source_files = launch_by_selector[selector].get("files", {})
                break
        if source_files is None:
            fail("selector iteration inventory has no authoritative source " + key)
        authoritative_iterations = source_after_iterations(source_files, source_kind)
        if selector_record.get("available_iterations") != authoritative_iterations:
            fail("captured iteration inventory disagrees with authoritative source " + key)
        for entry in selector_record.get("entries", []):
            source = entry.get("source_pin", {})
            source_record = source.get("record")
            source_path = source.get("path")
            if source_record == "original-index" and selector == (2, 1):
                record = original_index.get(source_path)
            elif source_record == "v2-result" and selector == (1, 1):
                record = launch_by_selector[selector].get("files", {}).get(source_path)
            elif source_record == "v3-result" and selector in expected_v3:
                record = launch_by_selector[selector].get("files", {}).get(source_path)
            else:
                fail("selector source-pin ancestry mismatch " + key)
            if not record or record.get("bytes") != entry.get("bytes") or record.get("sha256") != entry.get("sha256"):
                fail("capture byte pin disagrees with authoritative source record " + entry["path"])

    # Runtime state/output pins are independently represented in the original #275
    # index and the exact frozen v3 result identities; require both to agree.
    final_identities = result_v3.get("final_identities", {})
    runtime_bindings = {
        "state/model.txt": "runs/cpu-affine-on/state/model.txt",
        "state/global.txt": "runs/cpu-affine-on/state/global.txt",
        "out/affine.star": "runs/cpu-affine-on/out/affine.star",
        "out/affine.log": "runs/cpu-affine-on/out/affine.log",
    }
    for local_rel, source_rel in runtime_bindings.items():
        local = "inputs/runtime/" + local_rel
        pin = pins[local]
        indexed = original_index.get(source_rel)
        result_pinned = final_identities.get(source_rel)
        if not indexed or indexed.get("bytes") != pin["bytes"] or indexed.get("sha256") != pin["sha256"]:
            fail("runtime input disagrees with original file index " + source_rel)
        if result_pinned != pin["sha256"]:
            fail("runtime input disagrees with pinned v3 result identity " + source_rel)


def parse_numeric_rows(path, count, fields):
    rows = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("geometry"):
            continue
        bits = s.split()
        if len(bits) != fields:
            continue
        try:
            rows.append([float(v) for v in bits])
        except ValueError:
            continue
    a = np.asarray(rows, dtype=np.float64)
    if a.shape != (count, fields) or not np.isfinite(a).all():
        fail(f"malformed runtime table {path}: shape={a.shape}")
    return a


def parse_star_local(path):
    lines = path.read_text().splitlines()
    in_block = False
    labels = {}
    records = []
    for line in lines:
        s = line.strip()
        if s.startswith("data_"):
            in_block = (s == "data_local_shift")
            labels = {}
            continue
        if not in_block:
            continue
        m = re.match(r"(_\S+)\s+#(\d+)", s)
        if m:
            labels[m.group(1)] = int(m.group(2)) - 1
            continue
        if not s or s.startswith("loop_") or s.startswith("#") or s.startswith("_"):
            continue
        bits = s.split()
        required = ("_rlnMicrographFrameNumber", "_rlnCoordinateX", "_rlnCoordinateY",
                    "_rlnMicrographShiftX", "_rlnMicrographShiftY")
        if not all(k in labels for k in required):
            continue
        if len(bits) < max(labels.values()) + 1:
            fail("short STAR data_local_shift row")
        try:
            row = {k: float(bits[labels[k]]) for k in required}
        except ValueError:
            fail("malformed STAR local shift value")
        if not all(math.isfinite(v) for v in row.values()):
            fail("nonfinite STAR local shift value")
        fval, xval, yval = (row["_rlnMicrographFrameNumber"], row["_rlnCoordinateX"], row["_rlnCoordinateY"])
        if not all(v.is_integer() for v in (fval, xval, yval)):
            fail("STAR frame/coordinates must be integer logged centres")
        frame, coord = int(fval), (int(xval), int(yval))
        if coord not in set(CENTRES.values()):
            fail(f"unknown STAR patch centre {coord}")
        if frame not in range(1, NF + 1):
            fail(f"unknown STAR frame {frame} for centre {coord}")
        records.append(row)
    if not records:
        fail("missing STAR data_local_shift observations")
    return records


def basis(x, y, z):
    x2, y2, xy, z2, z3 = x*x, y*y, x*y, z*z, z*z*z
    return np.stack((z, z2, z3, x*z, x*z2, x*z3, x2*z, x2*z2, x2*z3,
                     y*z, y*z2, y*z3, y2*z, y2*z2, y2*z3,
                     xy*z, xy*z2, xy*z3), axis=-1)


def main():
    unexpected = [arg for arg in sys.argv[1:] if arg != "--structural-test"]
    if unexpected:
        fail("unexpected arguments: " + " ".join(unexpected))
    if STRUCTURAL_TEST_MODE and os.environ.get("MOTIONCORR_W4_STRUCTURAL_TEST_MODE") != "1":
        fail("--structural-test requires the dedicated structural-control environment")
    if not STRUCTURAL_TEST_MODE and len(sys.argv) != 1:
        fail("invalid execution mode")
    if OUTPUT.exists():
        fail("refusing to overwrite existing output " + str(OUTPUT))
    manifest = json.loads(MANIFEST.read_text(), object_pairs_hook=unique_object)
    if manifest.get("schema") != "w4-allpatch-cpu-observations-inputs/1":
        fail("unknown input manifest schema")
    pins = {x["path"]: x for x in manifest.get("files", [])}
    if len(pins) != len(manifest.get("files", [])):
        fail("duplicate manifest path")
    for rel in sorted(pins):
        checked_bytes(rel, pins)
    if not STRUCTURAL_TEST_MODE:
        verify_source_pins(manifest, pins)
    selectors = manifest.get("selectors", {})
    parsed = []
    for key, selector_record in selectors.items():
        entries = selector_record.get("entries")
        available_iterations = selector_record.get("available_iterations")
        selected_iteration = selector_record.get("selected_iteration")
        if not isinstance(available_iterations, list) or not available_iterations or selected_iteration != max(available_iterations):
            fail("missing or inconsistent iteration inventory for " + key)
        m = re.fullmatch(r"([1-3]),([1-3])", key)
        if not m:
            fail("malformed selector key " + key)
        y, x = map(int, m.groups())
        parsed.append((y, x))
        if len(entries) != 2:
            fail(f"selector {key}: expected metadata and one final after file")
        meta = json.loads(checked_bytes(entries[0]["path"], pins), object_pairs_hook=unique_object)
        if meta.get("tag") != "cpu" or meta.get("patch_yx") != [y, x] or meta.get("patch_nxy") != [42, 32]:
            fail(f"selector metadata mismatch {key}")
        if meta.get("frames") != NF or meta.get("scale_xy") != [1, 1]:
            fail(f"selector frame/scale mismatch {key}")
        aft = entries[1]
        match = re.fullmatch(r"c2-i(\d+)-after\.bin", Path(aft["path"]).name)
        if not match or int(match.group(1)) != selected_iteration:
            fail(f"selector {key}: selected snapshot is not the final captured iteration")
        raw = checked_bytes(aft["path"], pins)
        if len(raw) != NF * 2 * 8:
            fail(f"selector {key}: malformed after bytes length")
        arr = np.frombuffer(raw, dtype="<f8").reshape(NF, 2).astype(np.float64)
        if not np.isfinite(arr).all():
            fail(f"selector {key}: nonfinite shift")
        if not np.array_equal(arr[0], np.zeros(2, dtype=np.float64)):
            fail(f"selector {key}: frame-zero gauge is not exactly zero")
        parsed[-1] = (y, x, arr)
    selector_pairs = [(a, b) for a, b, *_ in parsed]
    if len(parsed) != 9 or len(set(selector_pairs)) != 9 or set(selector_pairs) != EXPECTED_SELECTORS:
        fail("selector set must contain exactly nine unique patches")

    run_log = checked_bytes("inputs/runtime/out/affine.log", pins).decode("utf-8")
    if "Frame grouping: n_frames = 5, requested group size = 1" not in run_log or "interpolate_shifts = 0" not in run_log:
        fail("runtime log does not establish five unit groups and interpolate_shifts off")
    if "Patches: X = 3 Y = 3" not in run_log:
        fail("runtime log does not establish the 3x3 patch lattice")

    # Use only the highest recorded iteration per selector; metadata/checker is immutable.
    rows = []
    for y, x, after in sorted(parsed):
        X, Y = CENTRES[(y, x)]
        obs = after + 0.5 * after[1]
        for g in range(NF):
            rows.append((X, Y, g + 0.5, obs[g, 0], obs[g, 1]))
    obs = np.asarray(rows, dtype=np.float64)
    if obs.shape != (45, 5) or not np.isfinite(obs).all():
        fail("derived observation table invalid")

    star_rows = parse_star_local(INPUTS / "runtime/out/affine.star")
    retained = {}
    for r in star_rows:
        fval, xval, yval = (r["_rlnMicrographFrameNumber"], r["_rlnCoordinateX"], r["_rlnCoordinateY"])
        if not all(float(v).is_integer() for v in (fval, xval, yval)):
            fail("STAR frame/coordinates must be integer logged centres")
        frame = int(fval)
        # STAR frame numbering is 1-based; local coordinates are the logged centres.
        coord = (int(xval), int(yval))
        k = (coord, frame)
        if k in retained:
            fail(f"duplicate STAR selector/frame {k}")
        retained[k] = (r["_rlnMicrographShiftX"], r["_rlnMicrographShiftY"])
    expected_star_keys = {(centre, frame) for centre in CENTRES.values() for frame in range(1, NF + 1)}
    if len(star_rows) != 45 or len(retained) != 45 or set(retained) != expected_star_keys:
        missing = sorted(expected_star_keys - set(retained))
        extra = sorted(set(retained) - expected_star_keys)
        fail(f"STAR coverage must be exactly 45 centre/frame rows; missing={missing}, extra={extra}")
    if STRUCTURAL_TEST_MODE:
        raise SystemExit("STRUCTURAL_PREFLIGHT_REACHED")
    max_star_delta = 0.0
    for X, Y, z, sx, sy in obs:
        k = ((int(X), int(Y)), int(round(z + 0.5)))
        if k not in retained:
            fail(f"missing STAR selector/frame {k}")
        max_star_delta = max(max_star_delta, abs(sx-retained[k][0]), abs(sy-retained[k][1]))
    if max_star_delta > 5e-6:
        fail(f"45 observation vs retained STAR discrepancy {max_star_delta:.12g} px/component exceeds 5e-6")

    A = basis(obs[:, 0] / NX - 0.5, obs[:, 1] / NY - 0.5, obs[:, 2])
    cx, residual_x, rank_x, singular_x = np.linalg.lstsq(A, obs[:, 3], rcond=None)
    cy, residual_y, rank_y, singular_y = np.linalg.lstsq(A, obs[:, 4], rcond=None)
    if rank_x != 18 or rank_y != 18:
        fail(f"fit rank is not 18: {rank_x}, {rank_y}")

    model = parse_numeric_rows(INPUTS / "runtime/state/model.txt", 18, 3)
    if not np.array_equal(model[:, 0], np.arange(18, dtype=np.float64)):
        fail("runtime coefficient indices are not 0..17")
    runtime_cx, runtime_cy = model[:, 1], model[:, 2]
    global_rows = parse_numeric_rows(INPUTS / "runtime/state/global.txt", NF, 3)
    if not np.array_equal(global_rows[:, 0], np.arange(1, NF + 1, dtype=np.float64)):
        fail("runtime global frame indices are not 1..5")
    gx, gy = global_rows[:, 1], global_rows[:, 2]

    y0, y1, x0, x1 = ROI
    yy, xx = np.mgrid[y0:y1, x0:x1]
    ux, uy = xx / NX - 0.5, yy / NY - 0.5
    max_vector_error = 0.0
    for g in range(NF):
        B = basis(ux, uy, np.full_like(ux, float(g)))
        dx = B @ (cx - runtime_cx)
        dy = B @ (cy - runtime_cy)
        # Include the retained runtime global term in both reconstructed fields.
        dx = (gx[g] + B @ cx) - (gx[g] + B @ runtime_cx)
        dy = (gy[g] + B @ cy) - (gy[g] + B @ runtime_cy)
        max_vector_error = max(max_vector_error, float(np.hypot(dx, dy).max()))
    report = {
        "schema": "w4-allpatch-cpu-observations/1",
        "science_verdict": "UNRUN_NO_SCIENCE_PASS",
        "selectors": 9, "observations": 45, "frames": NF,
        "observation_vs_retained_star_max_abs_px_component": max_star_delta,
        "observation_star_limit_px_component": 5e-6,
        "runtime_global_shifts_px": np.column_stack((gx, gy)).tolist(),
        "coefficient_delta_fit_minus_runtime_x": (cx-runtime_cx).tolist(),
        "coefficient_delta_fit_minus_runtime_y": (cy-runtime_cy).tolist(),
        "fit_design_condition_2norm": float(np.linalg.cond(A)),
        "fit_rank_x": int(rank_x), "fit_rank_y": int(rank_y),
        "fit_residual_sum_squares_x": float(residual_x[0]) if len(residual_x) else 0.0,
        "fit_residual_sum_squares_y": float(residual_y[0]) if len(residual_y) else 0.0,
        "fixed_roi_runtime_field_max_vector_error_px": max_vector_error,
        "fixed_roi_arithmetic_control_limit_px": 1e-10,
        "runtime_and_star_field_error_limits_angstrom": {
            "runtime": {"rms": 0.20, "p95": 0.40, "max": 0.80},
            "star": {"rms": 0.20, "p95": 0.40, "max": 0.80},
        },
        "runtime_and_star_field_error_limits_status": "UNCHANGED_NOT_EVALUATED_HERE",
        "input_manifest_sha256": sha256(MANIFEST.read_bytes()),
    }
    if max_vector_error > 1e-10:
        fail(f"fixed ROI reconstructed-field arithmetic control exceeded: {max_vector_error:.12g} px")
    target = OUTPUT
    if target.exists():
        fail("refusing to overwrite existing output " + str(target))
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
