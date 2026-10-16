#!/usr/bin/env python3
"""Failure controls for the resident non-converged patch retry (#197).

Drives the real runner linked with two test-only shims: cuda_retry_caller_shim.cpp
reports the first patch as a completed, non-converged resident attempt, and
cuda_fault_inject_shim.cpp (MC_PREPROCESS_FAULT=resident-retry-*) fails the first
cudaMalloc inside CudaMovieSession::downloadPatchSpectra, which builds the retry input.
No GPU is poisoned; the fault is an injected error code at that allocation.

  healthy      resident retry preparation runs and succeeds; reference products
  recoverable  WARNING, the movie is re-read from the device, products identical
  fatal        poisoned-context refusal, no products, non-zero exit

"Identical" means the complete MRC header and extended header (only the run timestamp in
the label is masked, as in docs/issue85_laneC/compare_output_trees.py), every pixel, and
the per-movie STAR with the output root spelled away. Before it is used on the arms the
comparison is shown to reject a header, a pixel and a STAR difference.
"""
import argparse
import os
import random
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

NX = NY = 512
NFRAMES = 12


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def synthetic_frames():
    """Periodic structure with a 1 px/frame drift (roll) and per-frame noise."""
    rng = random.Random(20261016)

    def profile():
        values, v = [], 0.0
        for _ in range(NX):
            v = 0.9 * v + rng.gauss(0, 1)
            values.append(v)
        return values

    terms = [(profile(), profile()) for _ in range(8)]
    base = [[sum(a[x] * b[y] for a, b in terms) for x in range(NX)] for y in range(NY)]
    lo = min(map(min, base))
    hi = max(map(max, base))
    scale = 3000.0 / (hi - lo)
    frames = []
    for k in range(NFRAMES):
        dx, dy = k, -(k // 2)
        frame = []
        for y in range(NY):
            row = base[(y - dy) % NY]
            frame.extend(min(65535, max(0, int((row[(x - dx) % NX] - lo) * scale
                                                  + 500 + rng.gauss(0, 120))))
                         for x in range(NX))
        frames.append(frame)
    return frames


def write_tiff(path, frames):
    """Minimal little-endian uint16 TIFF, one strip per page."""
    tags = 11
    ifd_size = 2 + 12 * tags + 4
    first_pixels = 8 + len(frames) * ifd_size
    chunks = [struct.pack("<%dH" % (NX * NY), *f) for f in frames]
    raw = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    for i, chunk in enumerate(chunks):
        values = [(256, 4, NX), (257, 4, NY), (258, 3, 16), (259, 3, 1), (262, 3, 1),
                  (273, 4, first_pixels + i * len(chunk)), (277, 3, 1), (278, 4, NY),
                  (279, 4, len(chunk)), (284, 3, 1), (339, 3, 1)]
        raw += struct.pack("<H", tags)
        for tag, kind, value in values:
            raw += struct.pack("<HHII", tag, kind, 1, value)
        raw += struct.pack("<I", 8 + (i + 1) * ifd_size if i + 1 < len(frames) else 0)
    path.parent.mkdir(parents=True)
    path.write_bytes(bytes(raw) + b"".join(chunks))


def write_star(path):
    path.write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n"
        "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n_rlnMicrographOriginalPixelSize #3\n"
        "_rlnVoltage #4\n_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
        "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n"
        "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\nMovies/control.tiff 1\n")


TIMESTAMP = re.compile(rb"(?<=Relion    )[0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}")


def mrc_parts(path):
    """(header + extended header with the run timestamp masked, pixel bytes)."""
    data = path.read_bytes()
    nx, ny, nz, mode = struct.unpack("<4i", data[:16])
    require(mode == 2 and (nx, ny, nz) == (NX, NY, 1), f"unexpected MRC {path}: {nx}x{ny}x{nz} mode {mode}")
    header_size = 1024 + struct.unpack_from("<i", data, 92)[0]
    require(len(data) == header_size + nx * ny * nz * 4, f"unexpected MRC size {path}")
    return TIMESTAMP.sub(b"00-XXX-00  00:00:00", data[:header_size]), data[header_size:]


def star_text(out):
    """Per-movie STAR content with the output root spelled away."""
    return (out / "Movies/control.star").read_bytes().replace(str(out).encode(), b"<ROOT>")


def differences(reference, candidate):
    found = []
    header_a, pixels_a = mrc_parts(reference / "Movies/control.mrc")
    header_b, pixels_b = mrc_parts(candidate / "Movies/control.mrc")
    if header_a != header_b:
        found.append("MRC header")
    if pixels_a != pixels_b:
        found.append("MRC pixels")
    if star_text(reference) != star_text(candidate):
        found.append("per-movie STAR")
    return found


def comparison_discriminates(reference, work):
    """The comparison must reject a header, a pixel and a STAR difference."""
    for what, edit in (("MRC header", lambda d: patch_bytes(d / "Movies/control.mrc", 40, b"\x00\x00\x80\x3f")),
                       ("MRC pixels", lambda d: patch_bytes(d / "Movies/control.mrc", -4, b"\x00\x00\x80\x3f")),
                       ("per-movie STAR", lambda d: edit_star(d / "Movies/control.star"))):
        copy = work / ("tampered-" + what.replace(" ", "-"))
        shutil.copytree(reference, copy)
        star = copy / "Movies/control.star"  # a relocated tree records its own root
        star.write_bytes(star.read_bytes().replace(str(reference).encode(), str(copy).encode()))
        require(not differences(reference, copy), "an unmodified copy must compare identical")
        edit(copy)
        found = differences(reference, copy)
        require(found == [what], f"comparison did not isolate a {what} difference: {found}")


def patch_bytes(path, offset, value):
    data = bytearray(path.read_bytes())
    start = offset if offset >= 0 else len(data) + offset
    require(bytes(data[start:start + len(value)]) != value, "tamper would not change the file")
    data[start:start + len(value)] = value
    path.write_bytes(bytes(data))


def edit_star(path):
    text = path.read_text()
    edited = re.sub(r"(?m)^(\S+\s+)(-?[0-9]+\.[0-9]+)", lambda m: m.group(1) + "9" + m.group(2), text, count=1)
    require(edited != text, "STAR tamper found nothing to change")
    path.write_text(edited)


def products(out):
    return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.suffix in (".mrc", ".star"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    require(binary.is_file(), f"missing binary: {binary}")
    work = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-resident-retry-"))
    if args.workdir:
        work.mkdir(parents=True, exist_ok=False)
    data = work / "input"
    write_tiff(data / "Movies/control.tiff", synthetic_frames())
    write_star(data / "movies.star")

    def run(name, fault):
        out = work / name
        out.mkdir()
        cmd = [str(binary), "--i", "movies.star", "--o", str(out) + "/", "--use_own", "--gpu", "0",
               "--j", "4", "--max_io_threads", "2", "--patch_x", "3", "--patch_y", "3",
               "--max_iter", "5", "--bfactor", "150", "--seed", "1", "--angpix", "1.0",
               "--voltage", "300"]
        env = dict(os.environ, OMP_NUM_THREADS="4", MC_RETRY_CALLER="1", MC_PREPROCESS_FAULT=fault,
                   MC_RESIDENT_RETRY_COUNT="1")
        r = subprocess.run(cmd, cwd=data, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=180)
        text = r.stdout + r.stderr + "\n".join(p.read_text() for p in out.rglob("*.log"))
        (work / (name + ".txt")).write_text(text)
        require("[retry-caller] injected nonconvergence" in text,
                f"{name}: no completed non-converged resident attempt was produced")
        require("remaining-owned=0 stale-releases=0" in r.stderr,
                f"{name}: owned CUDA allocation cleanup was not complete")
        witness = re.findall(r"resident-retry-preparations=(\d+) failed=(\d+) spectra-copied=(\d+)", r.stderr)
        require(len(witness) == 1, f"{name}: missing resident retry witness")
        return out, r.returncode, text, tuple(int(v) for v in witness[0])

    healthy, rc, text, (prepared, failed, copied) = run("healthy", "none")
    require(rc == 0, f"healthy run failed:\n{text[-2000:]}")
    require("second native alignment succeeded" in text, "healthy run did not converge on the retry")
    # Positive witness: a downloadPatchSpectra invocation finished with every one of its
    # NFRAMES spectrum copies (one group per frame) returning success.
    require((prepared, failed, copied) == (1, 0, NFRAMES),
            f"healthy: resident retry preparation did not succeed once (prepared={prepared} "
            f"failed={failed} spectra copied={copied}, expected 1, 0, {NFRAMES})")
    require("WARNING:" not in text and "[preprocessfault]" not in text and "CUDA Error in" not in text,
            "healthy run took the download path or logged a CUDA error")
    require(set(p for p in products(healthy) if p.endswith(".mrc")) == {"Movies/control.mrc"},
            f"healthy inventory: {products(healthy)}")
    comparison_discriminates(healthy, work)
    print("PASS healthy: resident retry preparation succeeded, retry converged, comparison rejects "
          "header, pixel and STAR differences")

    out, rc, text, (prepared, failed, copied) = run("recoverable", "resident-retry-recoverable")
    require("injected cudaErrorMemoryAllocation at downloadPatchSpectra; pending slot cleared" in text,
            "recoverable: injection did not reach downloadPatchSpectra")
    require(rc == 0, f"recoverable: movie was lost:\n{text[-2000:]}")
    require("WARNING: resident retry preparation did not complete for patch" in text and
            "retrying from the downloaded frames" in text, "recoverable: missing runner WARNING")
    require("Refusing to retry" not in text, "recoverable: classified as fatal")
    require((prepared, failed, copied) == (0, 0, 0),
            f"recoverable: a resident retry preparation ran past the fault ({prepared}, {failed}, {copied})")
    require(products(out) == products(healthy), f"recoverable inventory: {products(out)}")
    found = differences(healthy, out)
    require(not found, f"recoverable: products differ from the resident-retry products: {found}")
    print("PASS recoverable: WARNING, download path taken, MRC header and pixels and STAR identical")

    out, rc, text, _ = run("fatal", "resident-retry-fatal")
    require("injected cudaErrorIllegalAddress at downloadPatchSpectra; pending slot cleared" in text,
            "fatal: injection did not reach downloadPatchSpectra")
    require(rc != 0, "fatal: a poisoned context was reported as success")
    require("Refusing to retry alignment on a poisoned context" in text, "fatal: refusal missing")
    require(not products(out), f"fatal: failed movie published {products(out)}")
    require("[preprocessfault] later cudaMalloc" not in text,
            "fatal: CUDA allocation redispatch occurred after the fatal operation")
    print("PASS fatal: refused, non-zero exit, no products")
    print("RESIDENT_RETRY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
