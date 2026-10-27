#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit retained C1 route receipts; no native, GPU or remote operation."""
import hashlib
import json
from pathlib import Path
import shlex
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    c1 = here.parent
    readback_bytes = (here / "readback.json").read_bytes()
    readback = json.loads(readback_bytes)
    manifest_path = c1 / "evidence/summary/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    binary_path = c1 / "evidence/summary/build-nvcomp.binaries.sha256"
    expected_binary = binary_path.read_text().split()[0]
    expected_source = "e77a51a220cb0d91f4ac3c7fac211876d0c6833f"
    expected_input = "fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041"
    lane = manifest["lane"]["gpu_uuid"]
    assert manifest["source_sha"] == expected_source
    assert readback["host"] == "4-gpu-vm" and readback["cpus"] == [13]
    archive_path = c1 / "evidence/c1-evidence-iteration3.tgz"
    result = {"schema": "c1-retained-route-audit/1", "source_sha": expected_source,
              "readback_utc": readback["utc"], "verdict": "PASS",
              "scope": "two completed tutorial arms; route evidence only",
              "inputs_sha256": {"readback.json": digest(readback_bytes),
                                "verify_routes.py": digest(Path(__file__).read_bytes()),
                                "readback_remote.py": digest((here / "readback_remote.py").read_bytes()),
                                str(manifest_path.relative_to(c1)): digest(manifest_path.read_bytes()),
                                str(binary_path.relative_to(c1)): digest(binary_path.read_bytes()),
                                str(archive_path.relative_to(c1)): digest(archive_path.read_bytes())},
              "arms": {}}
    with tarfile.open(archive_path) as archive:
        for arm in ("c1-G", "c1-L"):
            live = readback["arms"][arm]
            name = f"t24-i3/{arm}/RUN.json"
            archived_bytes = archive.extractfile(name).read()
            run = json.loads(archived_bytes)
            assert digest(archived_bytes) == live["RUN_sha256"]
            assert run == live["RUN"]
            assert run["label"] == arm and run["rc"] == run["time_exit_status"] == 0
            assert run["binary_sha256"] == live["live_binary_sha256"] == expected_binary
            assert run["cpu_mask"] == "8-9" and run["extra_env"]["OMP_NUM_THREADS"] == "2"
            assert run["env"]["CUDA_VISIBLE_DEVICES"] == lane
            assert run["health_pre"]["rc"] == run["health_post"]["rc"] == 0
            assert run["cleanup"]["remaining"] == []
            assert run["gpu_witness"]["on_lane_gpu_only"] is True
            assert run["gpu_witness"]["uuids_seen_for_pid"] == [lane]
            assert run["gpu_witness"]["pid_hits"] > 0
            args = run["args"]
            assert args[args.index("--ingest") + 1] == "auto"
            assert args[args.index("--ingest_witness") + 1] == live["files"]["witness"]["path"]
            assert ("--patch_x" in args) == (arm == "c1-L")
            if arm == "c1-L":
                assert args[args.index("--patch_x") + 1] == args[args.index("--patch_y") + 1] == "5"
            files = live["files"]
            for value in files.values():
                data = value["text"].encode()
                assert len(data) == value["size"] and digest(data) == value["sha256"]
            assert files["input_star"]["sha256"] == run["input_star_sha256"] == expected_input
            # This pinned native input has a two-column movies loop.
            block = files["input_star"]["text"].split("data_movies\n")
            assert len(block) == 2
            lines = [shlex.split(line) for line in block[1].splitlines()
                     if line.strip() and not line.lstrip().startswith("#")]
            assert lines[:3] == [["loop_"], ["_rlnMicrographMovieName", "#1"], ["_rlnOpticsGroup", "#2"]]
            movies = [row[0] for row in lines[3:] if len(row) == 2 and row[1] == "1"]
            assert len(movies) == len(lines[3:]) == len(set(movies)) == 24
            witnesses = files["witness"]["text"].splitlines()
            assert witnesses == run["ingest_witness"] == [movie + " nvcomp" for movie in movies]
            assert all(movie.endswith(".tiff") for movie in movies)
            result["arms"][arm] = {"verdict": "PASS", "movies": len(movies),
                                   "route": "nvcomp", "run_sha256": digest(archived_bytes),
                                   "binary_sha256": expected_binary, "gpu_uuid": lane,
                                   "witness_sha256": files["witness"]["sha256"],
                                   "input_star_sha256": expected_input,
                                   "native_start_utc": run["start_utc"]}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
