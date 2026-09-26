#!/usr/bin/env python3
"""Run the two-movie Issue 36 common-global-trajectory counterfactual.

This is a diagnostic runner, not a production parity mode. It verifies the
specific tutorial inputs and complete CPU trace before launching CUDA.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess


MOVIES = {
    "00021": ("movies.star", "Movies/20170629_00021_frameImage.tiff",
              "df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0"),
    "00046": ("validation/movie_00046.star", "Movies/20170629_00046_frameImage.tiff",
              "61094383ce6750976275b13227033dcdb154c8214ef3db402aa6440a505ad377"),
}
GAIN_SHA = "8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1"
CPU_TRACE_EXECUTABLE_SHA = "a77777bc84bb033ce279dffc3e036c62100c5f0f43881cccc244753b1a59a6f7"
SOURCE_STAR_00046_SHA = "29be387682e00c48da13d69e517709a8ff0b4583cca31fa037ee9366ffe32a31"
SOURCE_STAR_00021_SHA = "fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041"
CPU_TRAJECTORY_SHA = {
    "00021": (
        "5b67ab73439a635c773f0a578fce2a6a54f5701c3ae2363a23bc8e7f33d4a2a3",
        "617c7e94e1bf370881bf35cb38676788492b1784833e41ab6763d25361a27a22",
        "16a91361c51711c19345d1f26a62d5c1d0615ce9cfeac77030b142618c2597de",
        "7c06b937f8e03b12be0c53605f40f6e297c3d31ededd3fb7e883b6be76d2c5d9",
        "9701fc40eb191036df184d29486a2e7ce6007836c44711572740c499c77d13de",
        "21f9c54e0cd42304f93ec0def1f996b86b8252be62adc2845bff9e1b802a115d",
    ),
    "00046": (
        "5c05e165ed5f2c8ee12e1114c47fc033db003a30840ba30f2a3bd05f0d9b8b17",
        "69b28b90aed7eb8506b206115d7ca91c371d9f8ef7fb7f070136d9f5d987f28e",
        "f3d431f71405d0355e76ac80aa62a9f303e65a989261f05f49ce93390888994c",
        "6ab901f93cb15b94c3f3b83175d4e079a4786ae39f022a169678c8ab83fdc7e2",
        "65076d1bd3d9ef0c14882c60ea4ad941a98e2e831a4f2434a950459ec15abc7f",
        "519a5830bf8e103bc855a1c49e0e6b9b7a85f247cf79931fa0dbacc0f3bfb49c",
    ),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_trace_array(trace, key):
    sidecar = json.loads((trace / f"{key}.json").read_text())
    expected = {"key": key, "dtype": "f8", "shape": [24], "bytes": 192, "endian": "native"}
    if sidecar != expected:
        raise ValueError(f"Wrong CPU trajectory sidecar: {key}: {sidecar}")
    source = trace / f"{key}.bin"
    if source.is_symlink() or source.stat().st_size != 192:
        raise ValueError(f"Wrong CPU trajectory chunk: {source}")
    values = struct.unpack("=24d", source.read_bytes())
    if values[0] != 0 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Invalid CPU trajectory values: {key}")
    return values, sha256(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie", choices=MOVIES, required=True)
    parser.add_argument("--mode", choices=("trajectory", "legacy-trajectory"), required=True)
    parser.add_argument("--gpu", type=int, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cpu-trace", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    checkout = args.checkout.resolve(strict=True)
    dataset = args.dataset.resolve(strict=True)
    cpu_trace = args.cpu_trace.resolve(strict=True)
    output_root = args.output_root.absolute()
    if output_root.exists():
        raise ValueError(f"Fresh output root required: {output_root}")
    star_name, movie_name, expected_movie_hash = MOVIES[args.movie]
    movie_file = dataset / movie_name
    gain_file = dataset / "Movies/gain.mrc"
    star = dataset / star_name if args.movie == "00021" else checkout / star_name
    if sha256(movie_file) != expected_movie_hash or sha256(gain_file) != GAIN_SHA:
        raise ValueError("Tutorial movie or gain content hash changed")
    expected_star_hash = SOURCE_STAR_00021_SHA if args.movie == "00021" else SOURCE_STAR_00046_SHA
    if sha256(star) != expected_star_hash:
        raise ValueError("Tutorial STAR selection or ordering changed")
    start = f"backend=cpu\nmovie={movie_name}\nformat=motioncorr-full-trace-v1\n"
    if (cpu_trace / "trace_start").read_text() != start or \
            (cpu_trace / "trace_complete").read_text() != "complete\n":
        raise ValueError("Wrong or incomplete CPU trace")

    geometry = {}
    for key, shape in (("g_i01_input_f000", [3838, 1856]),
                       ("g_i01_fref", [972, 487]),
                       ("g_i02_fref", [972, 487])):
        metadata = json.loads((cpu_trace / f"{key}.json").read_text())
        if metadata != {"key": key, "dtype": "c8", "shape": shape,
                        "bytes": shape[0] * shape[1] * 8, "endian": "native"}:
            raise ValueError(f"Wrong CPU trace geometry: {key}")
        geometry[key] = shape

    arrays, array_hashes = {}, {}
    for iteration in (1, 2):
        for axis in ("x", "y"):
            key = f"g_i{iteration:02d}_delta{axis}"
            arrays[key], array_hashes[key] = read_trace_array(cpu_trace, key)
    for axis in ("x", "y"):
        key = f"g_i02_total{axis}"
        arrays[key], array_hashes[key] = read_trace_array(cpu_trace, key)
        if any(a + b != total for a, b, total in zip(
                arrays[f"g_i01_delta{axis}"], arrays[f"g_i02_delta{axis}"], arrays[key])):
            raise ValueError(f"CPU trajectory total mismatch: {axis}")
    expected_array_keys = [f"g_i{iteration:02d}_delta{axis}"
                           for iteration in (1, 2) for axis in ("x", "y")]
    expected_array_keys += ["g_i02_totalx", "g_i02_totaly"]
    if tuple(array_hashes[key] for key in expected_array_keys) != CPU_TRAJECTORY_SHA[args.movie]:
        raise ValueError("CPU trajectory differs from the verified baseline trace")
    rmsds = []
    for iteration in (1, 2):
        x = arrays[f"g_i{iteration:02d}_deltax"]
        y = arrays[f"g_i{iteration:02d}_deltay"]
        rmsds.append(math.sqrt(sum(a * a + b * b for a, b in zip(x, y)) / 24))
    if not (rmsds[0] >= 0.5 and rmsds[1] < 0.5):
        raise ValueError(f"Unexpected CPU global iteration count: {rmsds}")

    binary = checkout / "build-issue36-cuda/motioncorr"
    source_hashes = {name: sha256(checkout / name) for name in (
        "src/motioncorr_runner.cpp", "src/motioncorr_alignment_weight.h",
        "src/acc/cuda/cuda_alignpatch.cu")}
    command = [str(binary), "--i", str(star), "--o", str(output_root / "output"),
               "--use_own", "--j", "1", "--do_at_most", "1", "--seed", "1",
               "--dose_weighting", "--dose_per_frame", "1.277", "--patch_x", "5",
               "--patch_y", "5", "--bfactor", "150", "--gainref", "Movies/gain.mrc",
               "--gpu", str(args.gpu)]
    manifest = {
        "format": "motioncorr-issue36-phase5-v1", "mode": args.mode, "movie": movie_name,
        "movie_sha256": expected_movie_hash, "gain_sha256": GAIN_SHA,
        "star_sha256": sha256(star), "cpu_trace_start_sha256": sha256(cpu_trace / "trace_start"),
        "cpu_trace_executable_sha256": CPU_TRACE_EXECUTABLE_SHA,
        "cpu_trace_array_sha256": array_hashes, "cpu_global_rmsd_px": rmsds,
        "geometry": geometry, "source_sha256": source_hashes,
        "global_frame_count": 24, "global_pnx": 3710, "global_pny": 3838,
        "ccf_nx": 972, "ccf_ny": 972, "prescaling": 1,
        "alignment_options": {"threads": 1, "seed": 1, "patch_x": 5, "patch_y": 5,
                              "bfactor": 150, "dose_per_frame": 1.277,
                              "dose_weighting": True, "max_iter": 5},
        "expected_global_iterations": 2,
        "candidate_executable_sha256": sha256(binary), "command": command,
        "cpu_trace_directory": str(cpu_trace),
    }
    output_root.mkdir(parents=True)
    (output_root / "output").mkdir()
    (output_root / "trace").mkdir()
    (output_root / "preflight.json").write_text(json.dumps(manifest, indent=2) + "\n")
    env = dict(os.environ)
    env.pop("MOTIONCORR_ISSUE36_LEGACY_GPU_WEIGHT", None)
    env["MOTIONCORR_FULL_TRACE_DIR"] = str(output_root / "trace")
    env["MOTIONCORR_FULL_TRACE_MAX_GIB"] = "128"
    env["MOTIONCORR_ISSUE36_CPU_GLOBAL_TRACE_DIR"] = str(cpu_trace)
    if args.mode == "legacy-trajectory":
        env["MOTIONCORR_ISSUE36_LEGACY_GPU_WEIGHT"] = "1"
    with (output_root / "run.log").open("w") as log:
        subprocess.run(command, cwd=dataset, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True)
    if not (output_root / "trace/trace_complete").is_file():
        raise RuntimeError("Counterfactual run did not complete the full trace")
    corrected = output_root / "output/Movies" / Path(movie_name).with_suffix(".mrc").name
    if not corrected.is_file():
        raise RuntimeError("Counterfactual corrected image missing")
    with corrected.open("rb") as image:
        image.seek(1024)
        payload_hash = hashlib.sha256(image.read()).hexdigest()
    movie_log = (output_root / "output" / Path(movie_name).with_suffix(".log"))
    if not movie_log.is_file():
        raise RuntimeError("Counterfactual movie log missing")
    global_log = movie_log.read_text().split("Global alignment:\n", 1)[1].split("\nLocal alignments:", 1)[0]
    actual_iterations = sum(line.lstrip().startswith("Iteration ") for line in global_log.splitlines())
    if actual_iterations != 2:
        raise RuntimeError(f"Counterfactual global iteration count changed: {actual_iterations}")
    (output_root / "result.json").write_text(json.dumps({
        "format": "motioncorr-issue36-phase5-result-v1", "mode": args.mode,
        "movie": movie_name, "candidate_executable_sha256": sha256(binary),
        "corrected_pixel_payload_sha256": payload_hash, "trace_complete": True,
        "actual_global_iterations": actual_iterations,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
