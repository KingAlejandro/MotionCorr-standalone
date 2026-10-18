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

Products are compared strictly. Every movie that must have products has exactly its
corrected MRC and its motion STAR, and a failed job has no joint STAR. Each MRC goes
through docs/issue85_laneC/compare_output_trees.validate_mrc, so the whole header
(only the established "Relion    <date>" writer timestamp masked), the extended header
and the payload are compared, together with the MRC's structure. The STAR is compared
byte for byte, apart from its own movie name. Before any fault row, the comparison is
shown to reject a changed header byte, a changed payload byte and a missing STAR (in
the tested tree alone, and in both the reference and the tested tree), and to accept a
timestamp-only difference.
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gain_cache import NX, NY, synthetic_frames, write_star  # noqa: E402
from run_nvcomp_reconstruction_controls import write_deflate_tiff  # noqa: E402
from run_preprocessing_failure_controls import write_tiff  # noqa: E402

MOVIES = ("a", "b", "c")
PRODUCTS = (".mrc", ".star")
JOINT_STAR = Path("corrected_micrographs.star")

_spec = importlib.util.spec_from_file_location(
    "stale_cuda_comparator",
    Path(__file__).resolve().parents[1] / "docs/issue85_laneC/compare_output_trees.py")
comparator = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = comparator
_spec.loader.exec_module(comparator)


def products(out: Path, movie: str) -> tuple[dict, list[str]]:
    """Comparable digests of one movie's corrected MRC and motion STAR, and problems.

    A missing product is a problem, not an absent key that could compare equal."""
    found, problems = {}, []
    for suffix in PRODUCTS:
        path = out / "Movies" / (movie + suffix)
        if not path.is_file():
            problems.append(f"{movie}{suffix} missing")
        elif suffix == ".mrc":
            try:
                found[suffix] = comparator.validate_mrc(path, (NX, NY, 1))
            except comparator.ValidationError as exc:
                problems.append(str(exc))
        else:
            # The STAR names its own movie; nothing else in it may differ.
            found[suffix] = path.read_bytes().replace(
                f"Movies/{movie}.".encode(), b"Movies/MOVIE.")
    return found, problems


def inventory(out: Path) -> set[Path]:
    return {p.relative_to(out) for p in out.rglob("*") if p.suffix in PRODUCTS}


def compare_movie(out: Path, movie: str, ref: dict) -> list[str]:
    got, problems = products(out, movie)
    for suffix in PRODUCTS:
        if suffix in got and got[suffix] != ref.get(suffix):
            problems.append(f"{movie}{suffix} differs from the standalone reference")
    return problems


def check_reference(out: Path) -> tuple[dict, list[str]]:
    ref, problems = products(out, "b")
    expected = {Path("Movies/b.mrc"), Path("Movies/b.star"), JOINT_STAR}
    if inventory(out) != expected:
        problems.append(f"reference inventory {sorted(map(str, inventory(out)))}, "
                        f"expected {sorted(map(str, expected))}")
    return ref, problems


def comparison_self_tests(ref_out: Path, scratch: Path) -> list[str]:
    """The comparison must be able to fail for the defects it claims to see."""
    def mutated(name, change):
        tree = scratch / name
        shutil.rmtree(tree, ignore_errors=True)
        shutil.copytree(ref_out, tree)
        change(tree)
        return tree

    def poke(offset):
        def change(tree):
            path = tree / "Movies/b.mrc"
            data = bytearray(path.read_bytes())
            data[offset] ^= 0x01
            path.write_bytes(bytes(data))
        return change

    def retime(tree):
        path = tree / "Movies/b.mrc"
        data = path.read_bytes()
        stamp = comparator.TIMESTAMP.search(data[:1024])
        if not stamp:
            raise RuntimeError("the writer label has no timestamp to mask")
        path.write_bytes(data[:stamp.start()] + b"01-Jan-99  00:00:00" + data[stamp.end():])

    ref, problems = check_reference(ref_out)
    if problems:
        return [f"reference not usable: {problems}"]
    failures = []
    cases = [
        ("identical tree accepted", ref_out, False),
        ("timestamp-only difference accepted", mutated("retimed", retime), False),
        ("header byte 40 (cell dimension) rejected", mutated("header", poke(40)), True),
        ("payload byte rejected", mutated("payload", poke(2048)), True),
        ("missing STAR rejected", mutated("nostar", lambda t: (t / "Movies/b.star").unlink()), True),
    ]
    for what, tree, must_fail in cases:
        if bool(compare_movie(tree, "b", ref)) != must_fail:
            failures.append(what)
    both = mutated("nostar-both", lambda t: (t / "Movies/b.star").unlink())
    if not check_reference(both)[1] or not compare_movie(both, "b", products(both, "b")[0]):
        failures.append("STAR missing from reference and tested tree rejected")
    return failures


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


def controls(a: argparse.Namespace, root: Path) -> int:
    binary = a.binary.resolve()
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
        refs[kind], problems = check_reference(out)
        ok = rc == 0 and routes.get("b") == kind and not problems
        print(f"[{'PASS' if ok else 'FAIL'}] reference {kind:<8} rc={rc} route={routes.get('b')} "
              f"inventory={sorted(map(str, inventory(out)))}" + (f"  {problems}" if problems else ""))
        if not ok:
            print("  the fixture does not take its route with complete products when healthy; "
                  "every row below would be vacuous")
            return 1
        bad = comparison_self_tests(out, root / "selftest" / kind)
        print(f"[{'PASS' if not bad else 'FAIL'}] comparison self-tests on the {kind} reference"
              + (f"  failed: {bad}" if bad else ""))
        if bad:
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
        # REPORT_ERROR prints the job-level message twice; count distinct lines.
        failed_line = sorted({l for l in text.splitlines() if "Motion correction failed for" in l})
        checks = {
            "genuine fault set the runtime slot":
                "returned=cudaErrorMemoryAllocation pending-after=cudaErrorMemoryAllocation"
                in text,
            "job fails for movie a only":
                rc != 0 and len(failed_line) == 1
                and "failed for 1 movie(s): Movies/a" in failed_line[0],
            "product inventory is b and c only, no joint STAR":
                inventory(out) == {Path(f"Movies/{m}{x}") for m in MOVIES[1:] for x in PRODUCTS},
            "b and c keep their route": routes.get("b") == kind and routes.get("c") == kind,
            "no CUDA error or fallback in b and c":
                "CUDA Error" not in later_logs and "Falling back" not in later_logs
                and "failed recoverably" not in later_logs,
            "b and c products identical to b alone":
                not compare_movie(out, "b", refs[kind]) and not compare_movie(out, "c", refs[kind]),
            "no device allocation left at exit":
                "[faultinject] remaining-owned=0 stale-releases=0" in text,
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True,
                    help="motioncorr_faultinject from the build under test")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--cpus", default=None, help="optional taskset CPU list")
    ap.add_argument("--no-nvcomp", action="store_true",
                    help="build without nvCOMP: run only the compact row")
    a = ap.parse_args()
    if a.workdir:
        return controls(a, a.workdir.resolve())
    # No --workdir: the scratch tree (movies, products, logs) is removed whatever
    # the outcome; controls() prints every failing check before returning.
    root = Path(tempfile.mkdtemp(prefix="mc-stale-cuda-"))
    try:
        return controls(a, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
