#!/usr/bin/env python3
"""A damaged movie must fail that movie, not the whole run.

The frame read happens inside an OpenMP region, and an exception leaving an
OpenMP structured block is undefined behaviour: the runtime calls
std::terminate. A movie with truncated frame data therefore used to abort the
process with SIGABRT, losing every other movie in the batch and the joint
outputs, and never reaching the failed_movies list that exists for exactly this.

Asserted here: the run exits non-zero but is NOT killed by a signal, names the
damaged movie, and still writes the healthy movie's corrected image.
"""
import argparse
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def write_star(path: Path, movies):
    path.write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n"
        "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
        "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
        "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
        "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n"
        "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        + "\n".join(f"{m} 1" for m in movies) + "\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    source = repo / "test-data" / "synthetic" / "synthetic_movie.tiff"
    if not source.is_file():
        raise FileNotFoundError(f"fixture missing: {source}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good.tiff")
        # Keep the IFD chain intact and cut the strip data, so the failure lands
        # in the frame read inside the OpenMP region rather than the header read.
        raw = source.read_bytes()
        (movies / "bad.tiff").write_bytes(raw[:len(raw) - 200_000])
        write_star(tmp / "m.star", ["Movies/bad.tiff", "Movies/good.tiff"])

        out = tmp / "out"
        out.mkdir()
        res = subprocess.run(
            [str(args.binary.resolve()), "--i", "m.star", "--o", str(out) + "/",
             "--use_own", "--j", "4", "--skip_defect", "--angpix", "1.0",
             "--voltage", "300", "--patch_x", "1", "--patch_y", "1", "--bfactor", "150"],
            cwd=str(tmp), capture_output=True, text=True)

        assert res.returncode != 0, "a damaged movie must fail the job"
        assert res.returncode > 0, (
            f"killed by signal {-res.returncode} -- an exception escaped the OpenMP "
            f"region instead of being captured and rethrown on the serial path")
        combined = res.stdout + res.stderr
        assert "bad.tiff" in combined, f"the damaged movie was not named:\n{combined[-1500:]}"

        produced = sorted(p.name for p in out.glob("**/*.mrc"))
        assert "good.mrc" in produced, (
            f"the healthy movie was not processed; the damaged one took the batch "
            f"down with it. Produced: {produced}")
        assert "bad.mrc" not in produced, f"the damaged movie produced output: {produced}"

    print(f"  damaged movie: exit {res.returncode}, named in output, healthy movie retained")
    print("damaged movie handling: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
