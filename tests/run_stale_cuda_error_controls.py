#!/usr/bin/env python3
"""Issue #226 D1: a handled allocation failure must not degrade the next movie.

A cudaMalloc that fails inside cudaAlignPatch* is checked by HANDLE_ERROR, which
throws without reading the runtime's last-error slot. Before the fix the slot kept
cudaErrorMemoryAllocation, and the next movie's first post-launch
HANDLE_ERROR(cudaGetLastError()) read it as its own failure: under --ingest auto the
movie lost its route, under a pinned --ingest nvcomp it was refused.

The fault is MC_ALIGN_ALLOC_FAULT=genuine in tests/cuda_fault_inject_shim.cpp: the
first alignment cudaMalloc of the process is replaced by a real cudaMalloc of an
impossible size, so the runtime itself sets its last-error slot. A shim that only
returned a code would leave the slot clean and could not reproduce the defect.

Three identical movies a, b, c per row; the fault fires in movie a.
  0  healthy references       b alone on each fixture, for the product comparison.
  1  nvCOMP, --ingest nvcomp   a fails cleanly; b and c take nvcomp, products identical.
  2  nvCOMP, --ingest auto     same, and b must not fall back to another route.
  3  compact, --ingest auto    uncompressed 16-bit TIFF: b and c take compact without
                               the CPU-preprocessing fallback, products identical.
Rows 1 and 2 are skipped on a build without nvCOMP only if --no-nvcomp is given.
"""
from __future__ import annotations
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gain_cache import synthetic_frames, write_star  # noqa: E402
from run_nvcomp_reconstruction_controls import write_deflate_tiff  # noqa: E402
from run_preprocessing_failure_controls import write_tiff  # noqa: E402

MOVIES = ("a", "b", "c")


def mrc_payload(path: Path) -> bytes:
    """Pixels only: the MRC label area carries a wall-clock timestamp."""
    data = path.read_bytes()
    nsymbt = struct.unpack_from("<i", data, 92)[0]
    return data[1024 + nsymbt:]


def products(out: Path, movie: str) -> dict[str, bytes]:
    found = {}
    for p in sorted((out / "Movies").glob(movie + "*")):
        if p.suffix == ".mrc":
            found[p.name[len(movie):]] = mrc_payload(p)
        elif p.suffix == ".star":
            found[p.name[len(movie):]] = p.read_bytes()
    return found


def run(binary: Path, root: Path, label: str, star: str, ingest: str, fault: bool,
        cpus: str | None):
    out = root / "runs" / label
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    wit = root / "runs" / (label + ".witness")
    wit.unlink(missing_ok=True)
    env = dict(os.environ)
    env.pop("MC_ALIGN_ALLOC_FAULT", None)
    if fault:
        env["MC_ALIGN_ALLOC_FAULT"] = "genuine"
    env["OMP_NUM_THREADS"] = "4"
    cmd = (["taskset", "-c", cpus] if cpus else []) + [
        str(binary), "--i", star, "--o", str(out) + "/", "--use_own", "--gpu", "0",
        "--j", "4", "--max_io_threads", "2", "--bfactor", "150", "--seed", "1",
        "--angpix", "1.0", "--voltage", "300", "--ingest", ingest,
        "--ingest_witness", str(wit)]
    r = subprocess.run(cmd, cwd=root / "input", capture_output=True, text=True, env=env)
    text = r.stdout + r.stderr
    (root / "runs" / (label + ".txt")).write_text(text)
    routes = {}
    if wit.exists():
        for line in wit.read_text().splitlines():
            movie, route = line.split()
            routes[Path(movie).stem] = route
    return r.returncode, text, out, routes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True,
                    help="motioncorr_faultinject from the build under test")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--cpus", default=None, help="optional taskset CPU list")
    ap.add_argument("--no-nvcomp", action="store_true",
                    help="build without nvCOMP: run only the compact row")
    a = ap.parse_args()
    binary = a.binary.resolve()
    root = a.workdir.resolve() if a.workdir else Path(tempfile.mkdtemp(prefix="mc-stale-cuda-"))
    if root.exists():
        shutil.rmtree(root)
    frames = [[int(v) for v in f] for f in synthetic_frames()]
    inp = root / "input"
    write_tiff(inp / "Movies" / "a.tif", frames)                       # uncompressed
    write_deflate_tiff(inp / "Movies" / "a.tiff", frames)              # nvCOMP-eligible
    for m in MOVIES[1:]:
        shutil.copy(inp / "Movies" / "a.tif", inp / "Movies" / f"{m}.tif")
        shutil.copy(inp / "Movies" / "a.tiff", inp / "Movies" / f"{m}.tiff")
    fixtures = {"compact": ".tif"} if a.no_nvcomp else {"nvcomp": ".tiff", "compact": ".tif"}
    for kind, ext in fixtures.items():
        write_star(inp / f"{kind}.star", [f"Movies/{m}{ext}" for m in MOVIES])
        write_star(inp / f"{kind}-b.star", [f"Movies/b{ext}"])

    fails = []
    refs = {}
    for kind in fixtures:
        rc, text, out, routes = run(binary, root, f"ref-{kind}", f"{kind}-b.star",
                                    kind, False, a.cpus)
        refs[kind] = products(out, "b")
        ok = rc == 0 and routes.get("b") == kind and refs[kind]
        print(f"[{'PASS' if ok else 'FAIL'}] reference {kind:<8} rc={rc} route={routes.get('b')} "
              f"products={len(refs[kind])}")
        if not ok:
            print("  the fixture does not take its route when healthy; every row below "
                  "would be vacuous")
            return 1

    rows = [("nvcomp", "nvcomp"), ("nvcomp", "auto"), ("compact", "auto")]
    for kind, ingest in rows:
        if kind not in fixtures:
            print(f"[UNRUN] {kind} --ingest {ingest}: no nvCOMP in this build")
            continue
        label = f"{kind}-{ingest}"
        rc, text, out, routes = run(binary, root, label, f"{kind}.star", ingest, True, a.cpus)
        logs = {m: (out / "Movies" / f"{m}.log") for m in MOVIES}
        later_logs = "".join(logs[m].read_text() for m in MOVIES[1:] if logs[m].exists())
        failed_line = [l for l in text.splitlines() if "Motion correction failed for" in l]
        checks = {
            "genuine fault set the runtime slot":
                "returned=cudaErrorMemoryAllocation pending-after=cudaErrorMemoryAllocation"
                in text,
            "job fails for movie a only":
                rc != 0 and len(failed_line) == 1
                and "failed for 1 movie(s): Movies/a" in failed_line[0],
            "movie a has no products": not products(out, "a"),
            "b and c keep their route": routes.get("b") == kind and routes.get("c") == kind,
            "no CUDA error or fallback in b and c":
                "CUDA Error" not in later_logs and "Falling back" not in later_logs
                and "failed recoverably" not in later_logs,
            "b and c products identical to b alone":
                products(out, "b") == refs[kind] and products(out, "c") == refs[kind],
        }
        bad = [k for k, v in checks.items() if not v]
        print(f"[{'PASS' if not bad else 'FAIL'}] {kind:<8} --ingest {ingest:<7} rc={rc} "
              f"routes={routes}" + (f"  failed: {bad}" if bad else ""))
        if bad:
            fails.append(label)
            for line in text.splitlines():
                if "[alignfault]" in line or "CUDA Error" in line or "ingest" in line.lower():
                    print("   ", line[:160])

    print()
    if fails:
        print(f"FAIL: {fails}")
        return 1
    print("PASS: a genuine handled allocation failure leaves the next movies on their "
          "route with identical products")
    return 0


if __name__ == "__main__":
    sys.exit(main())
