#!/usr/bin/env python3
"""The #262 CCF DC hook has no CUDA implementation (review finding F3): a build with the hook must refuse --gpu unless
MC_EXPERIMENT_CCF_DC_ARM is exactly 'none'. The refusal precedes the CUDA availability and device checks, so it is
testable in CPU-only builds. Registered only for builds with -DMC_EXPERIMENT_CCF_DC=ON.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REFUSAL = "has no CUDA implementation"


def run(binary, tmp, arm, *extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MC_EXPERIMENT_")}
    if arm is not None:
        env["MC_EXPERIMENT_CCF_DC_ARM"] = arm
    cp = subprocess.run([binary, "--i", str(tmp / "no_such_input.star"), "--o", str(tmp / "out"), "--use_own", *extra],
                        capture_output=True, text=True, env=env)
    return cp.returncode, cp.stdout + cp.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    binary = ap.parse_args().binary
    with tempfile.TemporaryDirectory(prefix="motioncorr-dcgpu-") as t:
        tmp = Path(t)
        for arm in ("global", "local", "both", None, "bogus", ""):
            rc, out = run(binary, tmp, arm, "--gpu", "0")
            assert rc != 0 and REFUSAL in out, f"arm {arm!r} with --gpu 0 was not refused: rc={rc} {out[:300]}"
            assert "built without CUDA" not in out and "Invalid GPU device ID" not in out, \
                f"arm {arm!r}: the refusal did not come before the CUDA checks: {out[:300]}"
        # Controls: 'none' with --gpu is not refused for the hook reason; any arm without --gpu is not refused either.
        rc, out = run(binary, tmp, "none", "--gpu", "0")
        assert REFUSAL not in out, f"arm none with --gpu must not be refused by the hook check: {out[:300]}"
        for arm in ("none", "global", "both"):
            rc, out = run(binary, tmp, arm)
            assert rc != 0 and REFUSAL not in out and "no_such_input.star" in out, f"arm {arm!r} without --gpu: {out[:300]}"
    print("PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAIL", e, file=sys.stderr)
        sys.exit(1)
