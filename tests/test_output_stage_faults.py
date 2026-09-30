#!/usr/bin/env python3
"""The output stage must fail the job, not abort the process.

Control for the Ghostscript overlap introduced with the #127 background-writer
group. generateLogFilePDFAndWriteStarFiles() starts header_thread, then runs
the batch.pdf pass on the main thread, then joins. That pass is not noexcept:
joinMultipleEPSIntoSinglePDF falls back to touch() when Ghostscript fails, and
touch() REPORT_ERRORs if the ofstream will not open. Unwinding through a
still-joinable std::thread is an unconditional std::terminate, so an
output-directory I/O failure became SIGABRT instead of the named, catchable
RelionError that src/apps/run_motioncorr.cpp turns into RELION_EXIT_FAILURE.

The fault is a *directory* named batch.pdf in the output root. Ghostscript
cannot open it as an output file, the touch() fallback cannot either, and the
throw happens on the main thread with header_thread still joinable. No files
are filled and nothing outside the test's own temporary directory is touched.

What distinguishes pass from fail is the SIGN of the return code, not that it
is non-zero: a negative returncode is death by signal (SIGABRT from
std::terminate), a positive one is the job reporting failure. Asserting merely
"non-zero" would pass on the very defect this exists to catch.
"""
from __future__ import annotations
import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ARGS = ["--use_own", "--j", "1", "--skip_defect", "--angpix", "1.0",
        "--voltage", "300", "--patch_x", "1", "--patch_y", "1", "--bfactor", "150"]

STAR = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.0 300 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/a.tiff 1
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    a = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    fixture = repo / "test-data" / "synthetic" / "synthetic_movie.tiff"
    if not fixture.is_file():
        print(f"FAIL: fixture missing: {fixture}")
        return 1

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "Movies").mkdir()
        shutil.copy(fixture, tmp / "Movies" / "a.tiff")
        (tmp / "in.star").write_text(STAR)

        # Control arm first. Without it, an unrelated reason for the fault arm
        # to fail would be indistinguishable from the behaviour under test.
        clean = tmp / "clean"
        rc_clean = subprocess.run(
            [str(a.binary.resolve()), "--i", "in.star", "--o", str(clean) + "/"] + ARGS,
            cwd=tmp, capture_output=True, text=True).returncode
        if rc_clean != 0:
            print(f"FAIL: the control arm did not succeed (exit {rc_clean}); "
                  "the fault arm below would prove nothing")
            return 1
        print("control arm: the same command without the fault exits 0")

        out = tmp / "out"
        out.mkdir()
        # Ghostscript's output path is a directory: it cannot write it, and the
        # touch() fallback cannot either.
        (out / "batch.pdf").mkdir()
        res = subprocess.run(
            [str(a.binary.resolve()), "--i", "in.star", "--o", str(out) + "/"] + ARGS,
            cwd=tmp, capture_output=True, text=True)
        rc = res.returncode
        tail = (res.stdout + res.stderr)[-2000:]

        if rc < 0:
            name = signal.Signals(-rc).name
            print(f"FAIL: the job died on {name} instead of reporting a failure. "
                  "A throw from the batch.pdf pass unwound through a joinable "
                  "std::thread, which is std::terminate.")
            failures += 1
        elif rc == 0:
            print("FAIL: the job reported success although the PDF stage could not "
                  "write its output")
            failures += 1
        else:
            print(f"PASS: the job reported failure (exit {rc}) rather than aborting")

        if "terminate called" in tail:
            print("FAIL: std::terminate was reached even though the exit code looks clean")
            failures += 1

        # The products that were already on disk before the PDF stage must still
        # be there: this is a reporting failure, not a reason to lose a movie.
        mrc = out / "Movies" / "a.mrc"
        if not mrc.is_file() or mrc.stat().st_size == 0:
            print("FAIL: the corrected micrograph written before the PDF stage is "
                  "missing or empty")
            failures += 1
        else:
            print("PASS: the micrograph written before the PDF stage survived")

    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("output stage faults: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
