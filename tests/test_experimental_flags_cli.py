#!/usr/bin/env python3
"""CLI contract of the experimental global half-gain research flags.

--experimental_global_half_gain and --experimental_align_tolerance are CPU-only. With
--gpu they must be refused with a clear error, in CPU-only and CUDA builds alike (the
refusal precedes the device query). Without --gpu they must be accepted, so the error a
missing input produces is not the refusal.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REFUSAL = "CPU-only research options and are refused with --gpu"


def run(binary, tmp, *extra):
    cp = subprocess.run([binary, "--i", str(tmp / "no_such_input.star"), "--o", str(tmp / "out"), *extra],
                        capture_output=True, text=True)
    return cp.returncode, cp.stdout + cp.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    binary = ap.parse_args().binary
    with tempfile.TemporaryDirectory(prefix="motioncorr-expflags-") as t:
        tmp = Path(t)
        for flags in (["--experimental_global_half_gain"],
                      ["--experimental_align_tolerance", "1e-9"],
                      ["--experimental_global_half_gain", "--experimental_align_tolerance", "1e-9"]):
            rc, out = run(binary, tmp, "--use_own", "--gpu", "0", *flags)
            assert rc != 0 and REFUSAL in out, f"{flags} with --gpu 0 was not refused: rc={rc} {out[:300]}"
            assert "built without CUDA" not in out and "Invalid GPU device ID" not in out, \
                f"{flags}: refusal did not come first: {out[:300]}"
            rc, out = run(binary, tmp, "--use_own", *flags)
            assert rc != 0 and REFUSAL not in out and "no_such_input.star" in out, \
                f"{flags} without --gpu was wrongly refused or failed for another reason: {out[:300]}"
        # Control: --gpu alone is not refused for the experimental reason.
        rc, out = run(binary, tmp, "--use_own", "--gpu", "0")
        assert REFUSAL not in out, out[:300]
        for bad in ("0", "-1", "abc", "nan", "inf"):
            rc, out = run(binary, tmp, "--use_own", "--experimental_align_tolerance", bad)
            # A non-numeric string is rejected by textToFloat itself; the rest by the positivity check.
            assert rc != 0 and ("must be a positive number of pixels" in out or "Error in textToFloat" in out), \
                f"tolerance {bad!r}: {out[:300]}"
            if bad != "abc":
                assert "must be a positive number of pixels" in out, f"tolerance {bad!r}: {out[:300]}"
        rc, out = run(binary, tmp, "--use_motioncor2", "--motioncor2_exe", "/bin/false", "--experimental_global_half_gain")
        assert rc != 0 and "valid only with --use_own" in out, out[:300]
    print("PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAIL", e, file=sys.stderr)
        sys.exit(1)
