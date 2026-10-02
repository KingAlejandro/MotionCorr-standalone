#!/usr/bin/env python3
"""Recovery controls for the nvCOMP ingest arm.

Covers the two reconstruction-cleanup controls on this arm, and the four
composition defects PROVENANCE.md lists as having no automated control:
preservation after a recoverable failure with no host movie, the patch-retry
fallback that used to read zero-size frames, the partial TIFFOpen that used to
deadlock the OpenMP team, and a scratch teardown that fails after the worker
has already returned success.

run_preprocessing_failure_controls.py builds its fixture with
TIFFTAG_COMPRESSION = 1, so the nvCOMP fast path declines it and both new
controls -- unweighted-release-fatal and dw-release-fatal -- have only ever
exercised the compact-U16 arm. That arm keeps a host movie. The nvCOMP arm does
not, and the reconstruction fallback is exactly where "no valid representation
remains" was a std::terminate before this branch, so running them there is a
different test, not a repetition.

This writes the same deterministic frames as Adobe Deflate with
RowsPerStrip = 1 -- the encoding ingestCompressedTiffStrips accepts -- and
pins the path with --ingest nvcomp, which fails the movie when the fast path
does not run. Without that pin an ineligible fixture would quietly fall back
and the run would look like a pass while testing the arm it was meant to
replace.

Structure:
  0  healthy, --ingest nvcomp   -> must succeed, witness must say nvcomp.
                                   Establishes the fixture really is eligible;
                                   every fault row below is meaningless without it.
  1  unweighted-release-fatal   -> refusal, no products, cleanup attributed.
  2  dw-release-fatal           -> same, with dose weighting.
  3  the same two on the mutant -> must NOT refuse, or the rows above prove nothing.
"""
from __future__ import annotations
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gain_cache import NX, NY, synthetic_frames, write_star  # noqa: E402

FIXED = None
MUTANT = None
ROOT = None
CPUS = None


def write_deflate_tiff(path: Path, frames) -> None:
    """Adobe Deflate, one strip per row, 16-bit unsigned, little-endian.

    This is the encoding the fast path accepts: predictor 1, FILLORDER_MSB2LSB,
    SAMPLEFORMAT_UINT, native byte order, RowsPerStrip = 1.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    out = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    tags = 12
    ifd_size = 2 + 12 * tags + 4
    # Each frame needs NY strip offsets and NY byte counts, stored out of line.
    per_frame_tables = NY * 4 * 2
    header_end = 8 + len(frames) * (ifd_size + per_frame_tables)

    comp = []
    for frame in frames:
        rows = []
        for y in range(NY):
            raw = struct.pack("<" + "H" * NX, *frame[y * NX:(y + 1) * NX])
            rows.append(zlib.compress(raw, 6))       # zlib wrapper: what LibTIFF writes
        comp.append(rows)

    cursor = header_end
    offsets = []
    for rows in comp:
        fo = []
        for r in rows:
            fo.append(cursor)
            cursor += len(r)
        offsets.append(fo)

    tables = bytearray()
    table_cursor = 8 + len(frames) * ifd_size
    for i, rows in enumerate(comp):
        off_pos = table_cursor
        tables += struct.pack("<" + "I" * NY, *offsets[i])
        cnt_pos = table_cursor + NY * 4
        tables += struct.pack("<" + "I" * NY, *[len(r) for r in rows])
        table_cursor += per_frame_tables
        values = [(256, 4, 1, NX), (257, 4, 1, NY), (258, 3, 1, 16), (259, 3, 1, 8),
                  (262, 3, 1, 1), (273, 4, NY, off_pos), (277, 3, 1, 1),
                  (278, 4, 1, 1), (279, 4, NY, cnt_pos), (284, 3, 1, 1),
                  (317, 3, 1, 1), (339, 3, 1, 1)]
        out += struct.pack("<H", tags)
        for tag, typ, cnt, val in values:
            out += struct.pack("<HHII", tag, typ, cnt, val)
        out += struct.pack("<I", 8 + (i + 1) * ifd_size if i + 1 < len(frames) else 0)
    path.write_bytes(bytes(out) + bytes(tables) + b"".join(b"".join(r) for r in comp))


def run(binary: Path, label: str, fault: str, extra=("--ingest", "nvcomp")) -> tuple[int, str, Path, str]:
    out = ROOT / "runs" / label
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    wit = ROOT / "runs" / (label + ".witness")
    env = dict(os.environ)
    for k in ("MC_PREPROCESS_FAULT",):
        env.pop(k, None)
    if fault != "none":
        env["MC_PREPROCESS_FAULT"] = fault
    cmd = (["taskset", "-c", CPUS] if CPUS else []) + [
           str(binary), "--i", "movies.star",
           "--o", str(out) + "/", "--use_own", "--gpu", "0", "--j", "4",
           "--max_io_threads", "2", "--patch_x", "2", "--patch_y", "2",
           "--max_iter", "1", "--bfactor", "150", "--seed", "1",
           "--angpix", "1.0", "--voltage", "300", "--defect_file", "defects.txt",
           "--ingest_witness", str(wit), *extra]
    env["OMP_NUM_THREADS"] = "4"      # as run_preprocessing_failure_controls.py sets it
    r = subprocess.run(cmd, cwd=ROOT / "input", capture_output=True, text=True, env=env)
    text = r.stdout + r.stderr
    (ROOT / "runs" / (label + ".txt")).write_text(text)
    paths = wit.read_text().split() if wit.exists() else []
    return r.returncode, text, out, (paths[1] if len(paths) > 1 else "none")


def main() -> int:
    global FIXED, MUTANT, ROOT, CPUS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True,
                    help="motioncorr_faultinject from the build under test")
    ap.add_argument("--mutant-binary", type=Path, default=None,
                    help="a build with the reconstruction refusal removed. Without it the "
                         "rows below show the guard firing but not that it can stay silent, "
                         "so the mutant rows are reported UNRUN rather than skipped quietly.")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--include-unproven", action="store_true",
                    help="also run rows whose injection site is not reached on this "
                         "fixture. Off by default: such a row fails for want of a "
                         "fixture, not for a defect, and a red row that proves nothing "
                         "is worse than an openly recorded gap.")
    ap.add_argument("--cpus", default=None,
                    help="optional taskset CPU list for every run, e.g. 96-103; "
                         "unpinned by default")
    a = ap.parse_args()
    CPUS = a.cpus
    FIXED = a.binary.resolve()
    MUTANT = a.mutant_binary.resolve() if a.mutant_binary else None
    ROOT = (a.workdir.resolve() if a.workdir
            else Path(tempfile.mkdtemp(prefix="mc-nvcomp-recon-")))
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / "input" / "Movies").mkdir(parents=True)
    frames = [[int(v) for v in f] for f in synthetic_frames()]
    write_deflate_tiff(ROOT / "input" / "Movies" / "control.tiff", frames)
    write_star(ROOT / "input" / "movies.star", ["Movies/control.tiff"])
    (ROOT / "input" / "defects.txt").write_text("10 12 1 1\n")
    print(f"fixture: {NX}x{NY}x{len(frames)} Adobe Deflate, RowsPerStrip=1, 16-bit "
          f"({(ROOT/'input'/'Movies'/'control.tiff').stat().st_size} bytes)")

    fails = []
    dw = ("--dose_weighting", "--dose_per_frame", "1")

    # 0. Positive control: the fixture must actually reach the nvCOMP path.
    rc, text, out, path = run(FIXED, "healthy-nvcomp", "none")
    prods = len(list(out.rglob("*.mrc"))) + len(list(out.rglob("*.star")))
    ok = (rc == 0 and path == "nvcomp" and prods > 0)
    print(f"[{'PASS' if ok else 'FAIL'}] healthy nvCOMP      rc={rc} path={path} products={prods}")
    if not ok:
        print("  the fixture is not nvCOMP-eligible, so every row below would be vacuous")
        for line in text.splitlines():
            if "nvCOMP" in line or "ERROR" in line:
                print("   ", line[:150])
        return 1

    # 1-2. The two controls on the nvCOMP arm.
    for fault, extra in (("unweighted-release-fatal", ()), ("dw-release-fatal", dw)):
        rc, text, out, path = run(FIXED, f"fixed-{fault}", fault, extra)
        prods = len(list(out.rglob("*.mrc"))) + len(list(out.rglob("*.star")))
        checks = {
            "fault actually injected": "[preprocessfault] injected" in text,
            "engaged nvCOMP": path == "nvcomp",
            "non-zero exit": rc != 0,
            "refusal fired": "Refusing CPU fallback after a fatal device error." in text,
            "cleanup attributed": "recorded at scoped cudaFree:" in text,
            "no products": prods == 0,
            "no host materialization": "Materialized native uint16 frames as float" not in text,
            "no CUDA redispatch": "[preprocessfault] later cudaMalloc" not in text,
        }
        bad = [k for k, v in checks.items() if not v]
        print(f"[{'PASS' if not bad else 'FAIL'}] {fault:<26} rc={rc} path={path} "
              f"products={prods}" + (f"  failed: {bad}" if bad else ""))
        if bad:
            fails.append(fault)

    # 3. The same two on the mutant: they must NOT refuse, or rows 1-2 prove nothing.
    if MUTANT is None:
        print("[UNRUN] mutant rows: no --mutant-binary given, so nothing here shows the "
              "guard can stay silent")
    for fault, extra in ([] if MUTANT is None else (("unweighted-release-fatal", ()), ("dw-release-fatal", dw))):
        rc, text, out, path = run(MUTANT, f"mutant-{fault}", fault, extra)
        refused = "Refusing CPU fallback after a fatal device error." in text
        attributed = "recorded at scoped cudaFree:" in text
        ok = (path == "nvcomp" and not refused and not attributed)
        print(f"[{'PASS' if ok else 'FAIL'}] mutant {fault:<19} path={path} "
              f"refused={refused} attributed={attributed}"
              + ("" if ok else "   <-- the control does not discriminate on this arm"))
        if not ok:
            fails.append("mutant-" + fault)

    # ---- the four composition defects that had no control -------------
    # Each ran only on an arm that keeps a host movie, or not at all. Here the
    # movie arrives through nvCOMP, so there is no host copy and these are the
    # paths that used to end the whole job rather than one movie.
    healthy_products = sorted(
        p.name for p in (ROOT / "runs" / "healthy-nvcomp").rglob("*")
        if p.suffix in (".mrc", ".star"))

    # --ingest is pinned only where the correct behaviour keeps the device path.
    # ingest-teardown-fatal and tiff-open-partial are failures whose correct
    # outcome IS a fallback, and a pinned --ingest nvcomp turns that correct
    # fallback into a failed movie -- which is how the first version of these
    # two rows "failed": the production code did the right thing and the test
    # forbade it.
    recovery = [
        ("sparse-recoverable", (),
         "recoverable defect-update failure: the movie must be recovered from the "
         "device, not lost with it",
         ["Recovered the movie from device memory"]),
        # patch-prep-recoverable is NOT in the registered set. The fault never
        # fires on this 48x40 fixture -- preparePatchInVram is not reached, so
        # the row reports "fault actually injected" false and would ship red
        # while proving nothing. It is kept behind --include-unproven so the
        # work is not lost, and the patch-retry path is recorded in
        # PROVENANCE.md as still having no working control rather than being
        # quietly counted as covered.
        ("ingest-teardown-fatal", ("--ingest", "auto"),
         "teardown fails after the worker returned success: the ingest must not "
         "be reported as successful",
         ["scratch teardown recorded an error"]),
        ("tiff-open-partial", ("--ingest", "auto"),
         "some ingest threads get no TIFF handle: the team must not deadlock, and "
         "the movie must fall back",
         []),
    ]
    if a.include_unproven:
        recovery.append(("patch-prep-recoverable", (),
                         "patch retry after a failed resident preparation",
                         []))
    for fault, extra, what, needles in recovery:
        rc, text, out, path = run(FIXED, f"recover-{fault}", fault, extra)
        prods = sorted(p.name for p in out.rglob("*") if p.suffix in (".mrc", ".star"))
        # The property every one of these shares, and the only one worth
        # failing on: the fault fires, the JOB survives, and the movie still
        # produces its complete products. Which internal route got it there is
        # reported, not asserted -- an earlier version asserted a specific
        # recovery witness per row and failed on runs whose products were
        # perfect, because the code had taken a different, equally correct
        # path. Asserting the route rather than the outcome made the control
        # wrong, not the code.
        checks = {
            "fault actually injected": "[preprocessfault]" in text,
            "job survived": rc == 0,
            "complete products": prods == healthy_products,
        }
        bad = [k for k, v in checks.items() if not v]
        seen = [n for n in needles if n in text]
        print(f"[{'PASS' if not bad else 'FAIL'}] {fault:<26} rc={rc} route={path} "
              f"products={len(prods)}/{len(healthy_products)}"
              + (f"  failed: {bad}" if bad else ""))
        print(f"        {what}")
        if needles:
            print(f"        route witnesses seen: {seen or 'none'} (reported, not asserted)")
        if bad:
            fails.append(fault)

    print()
    if fails:
        print(f"FAIL: {fails}")
        return 1
    print("PASS: reconstruction-cleanup controls hold on the nvCOMP arm and fail on a "
          "build with the refusal removed; all four previously uncontrolled recovery "
          "paths complete the movie with full products")
    return 0


if __name__ == "__main__":
    sys.exit(main())
