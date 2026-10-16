#!/usr/bin/env python3
"""Issue #194: raw integer MRC movies take the compact native staging.

Small synthetic movies are re-encoded as MRC mode 0 (int8), mode 1 (int16) and
mode 6 (uint16), with negative samples in both signed widths and samples above
32767 in mode 6. Each runs with --ingest compact and --ingest float on the CUDA
path, and the two product trees must be byte-identical (tools/profiling's
identity comparator). The witness file must say which path each run took.

Negative controls, each of which must fail identity or be refused:
  * a flipped payload byte in the compact tree;
  * a float movie holding the unsigned reinterpretation of a signed fixture,
    which is what a zero-extending expansion would have produced;
  * --ingest compact on a float32 MRC, which is not admitted.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "test-data"))
sys.path.insert(0, str(ROOT / "tools" / "profiling"))
import generate_synthetic_fixture as gen  # noqa: E402
from lib import identity  # noqa: E402

STAR = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.000 300.0 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
movie.mrcs 1
"""


def write_mrc(path, stack, mode):
    nz, ny, nx = stack.shape
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, nz, mode)
    struct.pack_into("<3i", header, 28, nx, ny, nz)
    struct.pack_into("<3f", header, 40, float(nx), float(ny), float(nz))
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    struct.pack_into("<3f", header, 76, float(stack.min()), float(stack.max()), float(stack.mean()))
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x44, 0x41, 0, 0))
    with open(path, "wb") as f:
        f.write(header)
        f.write(stack.tobytes())


def run(binary, gpu, work, label, stack, mode, ingest):
    """One movie through motioncorr; returns (rc, output text, out dir, witness lines)."""
    data = work / label / "data"
    out = work / label / "out"
    data.mkdir(parents=True)
    out.mkdir()
    write_mrc(data / "movie.mrcs", stack, mode)
    (data / "movies.star").write_text(STAR)
    witness = work / label / "witness.txt"
    cmd = [str(binary), "--i", "movies.star", "--o", str(out) + "/", "--use_own", "--gpu", str(gpu),
           "--j", "2", "--dose_weighting", "--dose_per_frame", "1.0", "--voltage", "300",
           "--angpix", "1.0", "--patch_x", "3", "--patch_y", "3", "--bfactor", "150", "--seed", "1",
           "--ingest", ingest, "--ingest_witness", str(witness)]
    res = subprocess.run(cmd, cwd=data, capture_output=True, text=True)
    text = res.stdout + res.stderr
    lines = witness.read_text().split("\n") if witness.exists() else []
    return res.returncode, text, out, [l for l in lines if l]


def encodings(stack):
    """int8, int16 and uint16 integer stacks derived from the float fixture."""
    centred = stack - 100.0
    return {
        0: np.clip(np.rint(centred * 2.5), -128, 127).astype("<i1"),
        1: np.clip(np.rint(centred * 300.0), -32768, 32767).astype("<i2"),
        6: np.clip(np.rint(centred * 300.0 + 40000.0), 0, 65535).astype("<u2"),
    }


def check(cond, msg, failures):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--gpu", type=int, default=0)
    args = ap.parse_args()
    failures = []

    with tempfile.TemporaryDirectory(prefix="mc-signed-mrc-") as tmp:
        work = Path(tmp)
        mrcs, _, _ = gen.generate_movie(work / "src" / "float.mrcs", nx=128, ny=128, nframes=8)
        stack = np.fromfile(mrcs, dtype="<f4", offset=1024).reshape(8, 128, 128)
        enc = encodings(stack)

        # A fixture without the cases the checks claim is vacuous: count them.
        check((enc[0] < 0).any() and (enc[1] < 0).any(),
              "int8 (%d) and int16 (%d) fixtures both contain negative samples"
              % ((enc[0] < 0).sum(), (enc[1] < 0).sum()), failures)
        check((enc[6] > 32767).any(),
              "uint16 fixture contains %d samples above 32767" % (enc[6] > 32767).sum(), failures)

        for mode, name in ((0, "int8"), (1, "int16"), (6, "uint16")):
            arrays = enc[mode]
            rc_c, text_c, out_c, wit_c = run(args.binary, args.gpu, work, name + "-compact", arrays, mode, "compact")
            rc_f, text_f, out_f, wit_f = run(args.binary, args.gpu, work, name + "-float", arrays, mode, "float")
            check(rc_c == 0 and rc_f == 0, "mode %d: both arms exit 0" % mode, failures)
            if rc_c or rc_f:
                print(text_c[-2000:], text_f[-2000:])
                continue
            check([l.split()[-1] for l in wit_c] == ["compact"] and [l.split()[-1] for l in wit_f] == ["float"],
                  "mode %d: witness says compact / float" % mode, failures)
            ident = identity.compare_trees(str(out_f), str(out_c))
            check(ident["identical"], "mode %d (%s): compact products identical to float: %s"
                  % (mode, name, ident["problems"] or "no differences"), failures)

            if mode == 0:
                # Flipped payload byte in the compact tree must be reported.
                tampered = work / "tampered"
                shutil.copytree(out_c, tampered)
                target = next(Path(tampered).rglob("*.mrc"))
                raw = bytearray(target.read_bytes())
                raw[-5] ^= 0x01
                target.write_bytes(bytes(raw))
                ident = identity.compare_trees(str(out_f), str(tampered))
                check(not ident["identical"], "control: one flipped payload byte is detected", failures)

            if mode in (0, 1):
                # Zero-extended reinterpretation of the signed samples, as float.
                unsigned = arrays.view("<u%d" % arrays.itemsize).astype("<f4")
                rc_u, text_u, out_u, _ = run(args.binary, args.gpu, work, name + "-unsigned", unsigned, 2, "float")
                if rc_u:
                    print(text_u[-2000:])
                    failures.append("unsigned control did not run")
                    continue
                ident = identity.compare_trees(str(out_u), str(out_c))
                check(not ident["identical"],
                      "control: unsigned expansion of the %s fixture fails identity" % name, failures)

        # Types the compact route does not admit stay refused under a pinned --ingest.
        rc, text, out, wit = run(args.binary, args.gpu, work, "float32-compact", stack.astype("<f4"), 2, "compact")
        check("--ingest compact was requested" in text and not list(Path(out).rglob("*.mrc")),
              "control: --ingest compact refuses a float32 MRC (rc=%d)" % rc, failures)
        rc, text, out, wit = run(args.binary, args.gpu, work, "float32-auto", stack.astype("<f4"), 2, "auto")
        check(rc == 0 and [l.split()[-1] for l in wit] == ["float"],
              "float32 MRC under --ingest auto stays on the float path", failures)

    if failures:
        print("\n%d check(s) failed" % len(failures))
        return 1
    print("\nAll signed MRC staging checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
