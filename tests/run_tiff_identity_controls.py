#!/usr/bin/env python3
"""#215: real nvCOMP eligibility, then append/rename at three pass boundaries.

Requires both the shim's mutation witness and the production identity-decline
log, plus a compact route witness and host-reference MRC payloads. On unfixed
source these rows fail even if a later checksum/read refusal happens to recover.
All input bodies remain valid; no corrupt-Deflate decoder safety is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from run_nvcomp_acceptance_controls import mrc_payloads
from run_nvcomp_reconstruction_controls import write_deflate_tiff
from test_gain_cache import synthetic_frames, write_star

DECLINE = "nvCOMP ingestion declined (TIFF file identity changed or unavailable); using the host reader."


def identity(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--workdir", type=Path)
    args = ap.parse_args()
    root = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-tiff-identity-"))
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise RuntimeError("workdir must be empty")
    frames = [[int(v) for v in f] for f in synthetic_frames()]
    other = [[v + 1 for v in f] for f in frames]
    rows = []

    def run(label, ingest, content, mode=None, point=None):
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
        assert initial_hash != replacement_hash or content == other
        out = lane / "output"
        out.mkdir()
        witness = lane / "route.txt"
        env = dict(os.environ, OMP_NUM_THREADS="1", MOTIONCORR_NVCOMP_CHUNK_FRAMES="2")
        for key in ("MC_TIFF_CHANGE_MODE", "MC_TIFF_CHANGE_POINT", "MC_TIFF_REPLACEMENT"):
            env.pop(key, None)
        if mode:
            env.update(MC_TIFF_CHANGE_MODE=mode, MC_TIFF_CHANGE_POINT=point,
                       MC_TIFF_REPLACEMENT=str(replacement))
        cmd = [str(args.binary.resolve()), "--i", "movies.star", "--o", str(out) + "/",
               "--use_own", "--gpu", "0", "--j", "1", "--max_io_threads", "1",
               "--patch_x", "2", "--patch_y", "2", "--max_iter", "1",
               "--bfactor", "150", "--seed", "1", "--angpix", "1.0", "--voltage", "300",
               "--ingest", ingest, "--ingest_witness", str(witness)]
        r = subprocess.run(cmd, cwd=inp, env=env, text=True, capture_output=True, timeout=180)
        text = r.stdout + r.stderr
        (lane / "process.log").write_text(text)
        movie_log = out / "Movies/control.log"
        if movie_log.exists():
            text += movie_log.read_text()
        route = witness.read_text().split()[1] if witness.exists() else "none"
        after = identity(movie)
        payloads = mrc_payloads(out)
        ok = r.returncode == 0 and bool(payloads) and (out / "corrected_micrographs.star").is_file()
        if mode:
            marker = f"[tiffidentity] changed mode={mode} point={point}"
            swapped = (after[2] == before[2] + 16 if mode == "grow" else
                       after[1] != before[1] and hashlib.sha256(movie.read_bytes()).hexdigest() == replacement_hash)
            ok = (ok and swapped and text.count(marker) == 1 and DECLINE in text
                  and route == "compact" and payloads == references[mode])
        else:
            swapped = False
            ok = ok and route == ingest and DECLINE not in text and before == after
        rows.append(dict(label=label, command=cmd, returncode=r.returncode, route=route,
                         before=before, after=after, swapped=swapped, passed=bool(ok)))
        return payloads

    references = {}
    references["grow"] = run("host-original", "compact", frames)
    references["replace"] = run("host-replacement", "compact", other)
    healthy = run("healthy", "nvcomp", frames)
    rows[-1]["passed"] &= healthy == references["grow"]
    for point in ("tag-close", "reader-open", "strip-read"):
        for mode in ("grow", "replace"):
            run(f"{point}-{mode}", "auto", frames, mode, point)
    (root / "result.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
