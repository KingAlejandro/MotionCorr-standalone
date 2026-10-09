#!/usr/bin/env python3
"""Native production-runner controls for preprocessing session disposal.

Uses the existing test-only fault executable; no real context is poisoned. A
small deterministic TIFF is generated here, so the test needs no tutorial data.
Optional --mutant-binary proves the guards discriminate against a checked build
with only discard_preprocessing_session's fatal refusal disabled.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from test_gain_cache import NX, NY, synthetic_frames, write_star


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tiff(path, frames, floating=False):
    """Minimal little-endian, single-strip-per-page TIFF; no codec dependency."""
    bits, fmt = (32, 3) if floating else (16, 1)
    sample = "f" if floating else "H"
    chunks = [struct.pack("<" + sample * (NX * NY), *frame) for frame in frames]
    tags = 11
    ifd_size = 2 + 12 * tags + 4
    first_pixels = 8 + len(frames) * ifd_size
    raw = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    for i, chunk in enumerate(chunks):
        values = [(256, 4, NX), (257, 4, NY), (258, 3, bits), (259, 3, 1),
                  (262, 3, 1), (273, 4, first_pixels + i * len(chunk)),
                  (277, 3, 1), (278, 4, NY), (279, 4, len(chunk)),
                  (284, 3, 1), (339, 3, fmt)]
        raw += struct.pack("<H", tags)
        for tag, kind, value in values:
            raw += struct.pack("<HHII", tag, kind, 1, value)
        raw += struct.pack("<I", 8 + (i + 1) * ifd_size if i + 1 < len(frames) else 0)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw + b"".join(chunks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--mutant-binary", type=Path)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--float-host", action="store_true",
                        help="test the shared disposal boundary without compact U16 host staging")
    args = parser.parse_args()
    binary = args.binary.resolve()
    work = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-preprocessing-"))
    if args.workdir:
        work.mkdir(parents=True, exist_ok=False)
    require(binary.is_file(), f"missing binary: {binary}")

    source = Path(__file__).resolve().parents[1]
    comparator_path = source / ("docs/issue69/evidence/ownership-20260929/compare-native.py"
                                if args.float_host else "docs/issue85_laneC/compare_output_trees.py")
    spec = importlib.util.spec_from_file_location("preprocessing_comparator", comparator_path)
    comparator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = comparator
    spec.loader.exec_module(comparator)
    frames = [[int(value) for value in frame] for frame in synthetic_frames()]
    manifest = {"movies": ["Movies/control.tiff"], "expected_shape_xyz": [NX, NY, 1],
                "joint_star": "corrected_micrographs.star"}
    def validate_products(out):
        if not args.float_host:
            comparator.validate_tree(out, manifest)
            return
        expected = {Path("Movies/control.mrc"), Path("Movies/control.star"),
                    Path("corrected_micrographs.star")}
        actual = {p.relative_to(out) for p in out.rglob("*") if p.suffix in (".mrc", ".star")}
        require(actual == expected, f"unexpected product inventory: {actual}")
        image = out / "Movies/control.mrc"
        require(struct.unpack_from("<3i", image.read_bytes()) == (NX, NY, 1),
                "unexpected image dimensions")
        comparator.compare(out, out, 1, 2)

    def compare_products(reference, candidate):
        if not args.float_host:
            return comparator.compare_trees(reference, candidate, manifest, compare_auxiliary=False)
        validate_products(reference)
        validate_products(candidate)
        return dict(status="PASS", **comparator.compare(reference, candidate, 1, 2))

    data = {}
    records = []
    for kind in ("u16", "float"):
        root = work / ("input-" + kind)
        write_tiff(root / "Movies/control.tiff", frames, kind == "float")
        write_star(root / "movies.star", manifest["movies"])
        (root / "defects.txt").write_text("10 12 1 1\n")
        data[kind] = root

    def run(name, kind="u16", fault="none", executable=binary, extra=()):
        out = work / name / "out"
        out.mkdir(parents=True)
        cmd = [str(executable), "--i", "movies.star", "--o", str(out) + "/",
               "--use_own", "--gpu", "0", "--j", "4", "--max_io_threads", "2",
               "--patch_x", "2", "--patch_y", "2", "--max_iter", "1", "--bfactor", "150",
               "--seed", "1", "--angpix", "1.0", "--voltage", "300",
               "--defect_file", "defects.txt", *extra]
        env = dict(os.environ)
        for key in ("MC_FAULT_ORDINAL", "MC_FAULT_CODE", "MC_FAULT_TRACE", "MC_U16_FAULT", "MC_U16_STAGE_BYTES",
                    "MC_COUNT_FAULT_ORDINAL", "MC_COUNT_FAULT_CODE"):
            env.pop(key, None)
        env["MC_PREPROCESS_FAULT"] = fault
        env["OMP_NUM_THREADS"] = "4"
        process = subprocess.Popen(cmd, cwd=data[kind], env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        proc = Path("/proc") / str(process.pid)
        identity = {"pid": process.pid, "executable": os.readlink(proc / "exe"),
                    "start_ticks": (proc / "stat").read_text().rsplit(")", 1)[1].split()[19],
                    "cpus": sorted(os.sched_getaffinity(process.pid)),
                    "status": (proc / "status").read_text(),
                    "numa_maps_initial": (proc / "numa_maps").read_text()}
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError(f"{name}: owned test process exceeded 120 seconds")
        (out.parent / "stdout.txt").write_text(stdout)
        (out.parent / "stderr.txt").write_text(stderr)
        text = stdout + stderr + "\n".join(p.read_text() for p in out.rglob("*.log"))
        records.append({"case": name, "command": cmd, "cwd": str(data[kind]), "fault": fault,
                        "exit_code": process.returncode, "binary_sha256": digest(executable),
                        "payload_identity": identity})
        (work / "runs.json").write_text(json.dumps(records, indent=2) + "\n")
        require("remaining-owned=0 stale-releases=0" in stderr,
                f"{name}: owned CUDA allocation cleanup was not complete")
        return out, process.returncode, text

    healthy = {}
    for kind in data:
        out, rc, text = run("healthy-" + kind, kind)
        require(rc == 0, f"healthy {kind} failed: {text[-2000:]}")
        validate_products(out)
        require("injected" not in text, "healthy run unexpectedly injected a fault")
        healthy[kind] = out
    require(args.float_host or "Released native uint16 host staging" in (work / "healthy-u16/out/Movies/control.log").read_text(),
            "healthy U16 run did not reach the staging-release boundary")

    out, rc, text = run("sparse-recoverable", fault="sparse-recoverable")
    require(rc == 0, "recoverable sparse update did not complete")
    require("injected cudaErrorMemoryAllocation at updateDefectPixels" in text,
            "sparse recoverable injection did not reach its production helper")
    require(args.float_host or "Materialized native uint16 frames as float" in text,
            "sparse recoverable path did not materialize raw host frames")
    report = compare_products(healthy["u16"], out)
    require(report["status"] == "PASS", "recoverable sparse output differs from healthy output")
    (work / "recoverable-products.json").write_text(json.dumps(report, indent=2) + "\n")

    cases = [("init-fatal", "u16", "initialize"),
             ("sparse-fatal", "u16", "updateDefectPixels"),
             ("sparse-release-fatal", "u16", "updateDefectPixels"),
             ("float-gain-fatal", "float", "applyGainDefectsAndSum"),
             ("forward-fatal", "u16", "computeGlobalForwardFFT")]
    # --save_noDW keeps the dose-weighting scratch a separate allocation: without
    # it the scratch is carved from the consumed real-space movie
    # (docs/vram_live_ranges.md) and there is no reconstruction cudaFree to fault.
    dose_weighted = ("--dose_weighting", "--dose_per_frame", "1", "--save_noDW")
    cases = [(fault, kind, stage, ()) for fault, kind, stage in cases]
    cases += [("unweighted-release-fatal", "u16", "cudaRealSpaceInterpolationDevice", ()),
              ("dw-release-fatal", "u16", "cudaDoseWeightAndInterpolateDevice", dose_weighted)]
    for fault, kind, stage, extra in cases:
        out, rc, text = run(fault, kind, fault, extra=extra)
        require("at " + stage + "; pending slot cleared" in text,
                f"{fault}: missing exact production injection witness")
        require(rc != 0, f"{fault}: fatal status was reported as success")
        require("Refusing CPU fallback after a fatal device error." in text,
                f"{fault}: preprocessing refusal did not fire")
        require(not list(out.rglob("*.mrc")) and not list(out.rglob("*.star")),
                f"{fault}: failed movie published an image or STAR")
        require("Materialized native uint16 frames as float" not in text,
                f"{fault}: fatal path materialized host frames")
        require("[preprocessfault] later cudaMalloc" not in text,
                f"{fault}: CUDA allocation redispatch occurred after the fatal operation")
        if fault == "sparse-release-fatal":
            require("injected cudaErrorMemoryAllocation at updateDefectPixels" in text and
                    "injected cudaErrorIllegalAddress after real session cudaFree" in text and
                    "recorded at releaseBuffer:" in text and "First failure at updateDefectPixels:" in text,
                    "release fatal did not retain both operation and cleanup attribution")
        if fault in ("unweighted-release-fatal", "dw-release-fatal"):
            require("reconstruction for" in text and "recorded at scoped cudaFree:" in text,
                    f"{fault}: reconstruction cleanup status was not retained by the session")

    if args.mutant_binary:
        mutant = args.mutant_binary.resolve()
        for fault, kind in (("sparse-fatal", "u16"), ("sparse-release-fatal", "u16"),
                            ("float-gain-fatal", "float")):
            out, rc, text = run("mutant-" + fault, kind, fault, mutant)
            require(rc == 0 and "Refusing CPU fallback after a fatal device error." not in text,
                    f"mutant {fault} did not complete normally without the refusal")
            require("[preprocessfault] later cudaMalloc" in text,
                    f"mutant {fault} did not witness forbidden GPU redispatch")
            report = compare_products(healthy[kind], out)
            require(report["status"] == "PASS", f"mutant {fault} did not produce complete expected products")
        print("PASS three disabled-guard mutants complete and redispatch; fixed binary refuses")
    provenance = {"host_storage": "float" if args.float_host else "compact uint16",
                  "input_sha256": {kind: {str(p.relative_to(root)): digest(p)
                                         for p in root.rglob("*") if p.is_file()}
                                    for kind, root in data.items()},
                  "comparator_sha256": digest(comparator_path), "runs": records}
    (work / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"PASS preprocessing failure controls; artifacts: {work}")
    print("Injected status codes only; genuine device poisoning remains untested.")


if __name__ == "__main__":
    main()
