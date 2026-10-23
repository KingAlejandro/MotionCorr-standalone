#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""#215 later-chunk native control; host-only harness tests do not qualify this run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from run_nvcomp_acceptance_controls import mrc_payloads
from run_nvcomp_reconstruction_controls import write_deflate_tiff
from run_tiff_identity_controls import DECLINE, identity
from test_gain_cache import NX, NY, synthetic_frames, write_star

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docs/rc0/qf/tools"))
from compact_compare_output_trees import compare_trees, ValidationError  # noqa: E402

CONVERTED = "[tiffidentity] converted frames=[0,2) frame-pixels=3840 sum-pixels=1920 exact=1"
LATER = "[tiffidentity] later-strip-read index=4 converted=2"


def write_expected(path, frames):
    """Independent fixture oracle: no gain, vertical flip, first two frames/sum."""
    flipped = [[v for y in range(NY - 1, -1, -1) for v in f[y * NX:(y + 1) * NX]]
               for f in frames[:2]]
    values = flipped[0] + flipped[1] + [a + b for a, b in zip(*flipped)]
    path.write_bytes(struct.pack("<" + "f" * len(values), *values))


def mutation_checks(text, before, after, movie_hash, replacement_hash, mode):
    marker = f"[tiffidentity] changed mode={mode} point=later-strip-read"
    return {
        "completed_conversion": text.count(CONVERTED) == 1,
        "later_read": text.count(LATER) == 1,
        "mutation_once": text.count(marker) == 1,
        "ordered": (CONVERTED in text and LATER in text and marker in text and
                    text.index(CONVERTED) < text.index(LATER) < text.index(marker)),
        "identity_changed": (after[2] == before[2] + 16 if mode == "grow" else
                             after[1] != before[1] and movie_hash == replacement_hash),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--mutant-binary", type=Path, required=True)
    ap.add_argument("--workdir", type=Path)
    ap.add_argument("--cpus", help="optional taskset CPU list, at most two CPUs")
    args = ap.parse_args()
    root = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-tiff-later-"))
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise RuntimeError("workdir must be empty")
    frames = [[int(v) for v in f] for f in synthetic_frames()]
    other = [[v + 1 for v in f] for f in frames]
    expected = root / "first-chunk-floats.bin"
    write_expected(expected, frames)
    rows = []
    references = {}
    manifest = dict(schema_version=1, expected_shape_xyz=[NX, NY, 1],
                    joint_star="corrected_micrographs.star", movies=["Movies/control.tiff"])
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def run(label, binary, ingest, content, mode=None, mutant=False):
        lane = root / label
        inp = lane / "input"
        movie = inp / "Movies/control.tiff"
        replacement = inp / "replacement.tiff"
        write_deflate_tiff(movie, content)
        write_deflate_tiff(replacement, other)
        write_star(inp / "movies.star", ["Movies/control.tiff"])
        before = identity(movie)
        initial_hash = hashlib.sha256(movie.read_bytes()).hexdigest()
        replacement_hash = hashlib.sha256(replacement.read_bytes()).hexdigest()
        out = lane / "output"
        out.mkdir()
        witness = lane / "route.txt"
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                   MOTIONCORR_NVCOMP_CHUNK_FRAMES="2", MC_TIFF_CONVERSION_EXPECTED=str(expected))
        for key in ("MC_TIFF_CHANGE_MODE", "MC_TIFF_CHANGE_POINT", "MC_TIFF_REPLACEMENT"):
            env.pop(key, None)
        if mode:
            env.update(MC_TIFF_CHANGE_MODE=mode, MC_TIFF_CHANGE_POINT="later-strip-read",
                       MC_TIFF_REPLACEMENT=str(replacement))
        cmd = (["taskset", "-c", args.cpus] if args.cpus else []) + [
            str(binary.resolve()), "--i", "movies.star", "--o", str(out) + "/",
            "--use_own", "--gpu", "0", "--j", "1", "--max_io_threads", "1",
            "--patch_x", "2", "--patch_y", "2", "--max_iter", "1", "--bfactor", "150",
            "--seed", "1", "--angpix", "1.0", "--voltage", "300", "--ingest", ingest,
            "--ingest_witness", str(witness)]
        r = subprocess.run(cmd, cwd=inp, env=env, text=True, capture_output=True, timeout=180)
        text = r.stdout + r.stderr
        (lane / "process.log").write_text(text)
        movie_log = out / "Movies/control.log"
        diagnostics = movie_log.read_text() if movie_log.exists() else ""
        route_tokens = witness.read_text().split() if witness.exists() else []
        route = route_tokens[1] if len(route_tokens) == 2 else "none"
        after = identity(movie)
        payloads = mrc_payloads(out)
        products = sorted(str(p.relative_to(out)) for p in out.rglob("*")
                          if p.suffix in (".mrc", ".star"))
        checks = {"exit_zero": r.returncode == 0, "mrc_payloads": bool(payloads),
                  "completion_star": (out / "corrected_micrographs.star").is_file(),
                  "movie_log": movie_log.is_file()}
        reference = (root / ("host-replacement" if mode == "replace" else "host-original") /
                     "output") if ingest != "compact" else out
        try:
            product_identity = compare_trees(reference, out, manifest, compare_auxiliary=False)
        except ValidationError as exc:
            product_identity = dict(status="FAIL", error=str(exc))
        (lane / "product-identity.json").write_text(json.dumps(product_identity, indent=2) + "\n")
        fixed_accepted = None
        if mode:
            checks.update(mutation_checks(text, before, after,
                          hashlib.sha256(movie.read_bytes()).hexdigest(), replacement_hash, mode))
            # The SAME fixed acceptance predicate must fail on the mutant. Also
            # require successful native decoding there, so any generic fallback,
            # crash, missing witness or product loss cannot count as discrimination.
            fixed_accepted = (all(checks.values()) and product_identity["status"] == "PASS" and
                        DECLINE in diagnostics and route == "compact" and
                        payloads == references[mode][0] and products == references[mode][1])
            checks["same_fixed_predicate"] = not fixed_accepted if mutant else fixed_accepted
            if mutant:
                try:
                    original_identity = compare_trees(root / "host-original/output", out, manifest,
                                                      compare_auxiliary=False)
                except ValidationError as exc:
                    original_identity = dict(status="FAIL", error=str(exc))
                (lane / "original-identity.json").write_text(json.dumps(original_identity, indent=2) + "\n")
                checks.update(no_identity_decline=DECLINE not in diagnostics, route_nvcomp=route == "nvcomp",
                              complete_original_identity=original_identity["status"] == "PASS",
                              full_original=payloads == references["grow"][0],
                              complete_inventory=products == references["grow"][1])
        else:
            checks.update(route=route == ingest, immutable=before == after,
                          complete_mrc_star_identity=product_identity["status"] == "PASS",
                          no_identity_decline=DECLINE not in diagnostics)
            if ingest == "nvcomp":
                checks.update(completed_conversion=text.count(CONVERTED) == 1,
                              chunk_geometry="chunk=2/6 frames x 3 chunks, slots=2" in diagnostics,
                              full_original=payloads == references["grow"][0],
                              complete_inventory=products == references["grow"][1])
        rows.append(dict(label=label, command=cmd, returncode=r.returncode, route=route,
                         before=before, after=after, initial_sha256=initial_hash,
                         replacement_sha256=replacement_hash, products=products,
                         fixed_acceptance=fixed_accepted,
                         payload_sha256={k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()},
                         checks=checks, passed=all(checks.values())))
        (root / "result.json").write_text(json.dumps(rows, indent=2) + "\n")
        return payloads, products

    references["grow"] = run("host-original", args.binary, "compact", frames)
    references["replace"] = run("host-replacement", args.binary, "compact", other)
    if references["grow"][0] == references["replace"][0]:
        raise RuntimeError("replacement fixture must produce distinct host-reference pixels")
    for mutant, binary in ((False, args.binary), (True, args.mutant_binary)):
        prefix = "mutant" if mutant else "fixed"
        run(prefix + "-healthy", binary, "nvcomp", frames)
        for mode in ("grow", "replace"):
            run(prefix + "-later-" + mode, binary, "auto", frames, mode, mutant)
    print(json.dumps(rows, indent=2))
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
