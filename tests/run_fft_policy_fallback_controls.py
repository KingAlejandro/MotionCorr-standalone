#!/usr/bin/env python3
"""--fft_size_policy fast: the CPU fallbacks receive exact-size spectra.

A padded session holds frame spectra on the padded grid. When the resident
inverse FFT or the resident dose weighting fails recoverably, the runner
downloads those spectra and continues on the CPU, which expects the movie's
own grid; exactSpectraFromPadded converts them (docs/fft_size_policy.md).

Uses the test-only motioncorr_faultinject binary (injected status codes, no
real device fault) on a 62 x 46 fixture, which pads to 64 x 48. Each fault
run must witness its injection and the fallback, finish, and write products
of the movie's own size. Without the conversion the run aborts in the
dose weighting (MEASURED, docs/fft_size_policy.md).

Oracles (values MEASURED on 4GPUs A100):
  - noDW sum: frames reconstructed from the converted spectra equal the
    healthy fast run's (relRMSE 6e-7); bound 1e-5.
  - DW sum: both fallbacks weight on the exact grid, through different code
    (CUDA non-session after the inverse fault, CPU after the DW fault); they
    agree (7e-7, bound 1e-5). They differ from the healthy fast run, which
    weights on the padded grid, by 0.0042; that must stay below the
    fast-versus-exact policy difference of the same movie (0.051). A frame
    offset by one pixel is 0.61.
"""
import argparse
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile

NX, NY, NFRAMES = 62, 46, 8


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def frames(seed=7):
    state = seed
    def rnd():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    base = [int(rnd() * 50 + 100) for _ in range(NX * NY)]
    out = []
    for n in range(NFRAMES):
        f = list(base)
        cx, cy = NX // 2 + n // 2, NY // 2 + n % 3
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                x, y = (cx + dx) % NX, (cy + dy) % NY
                f[y * NX + x] += int(600 / (1 + dx * dx + dy * dy))
        out.append(f)
    return out


def write_tiff(path, movie):
    chunks = [struct.pack("<" + "H" * (NX * NY), *f) for f in movie]
    tags = 10
    ifd = 2 + 12 * tags + 4
    first = 8 + len(movie) * ifd
    raw = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    for i, chunk in enumerate(chunks):
        values = [(256, 4, NX), (257, 4, NY), (258, 3, 16), (259, 3, 1), (262, 3, 1),
                  (273, 4, first + i * len(chunk)), (277, 3, 1), (278, 4, NY),
                  (279, 4, len(chunk)), (284, 3, 1)]
        raw += struct.pack("<H", tags)
        for tag, kind, value in values:
            raw += struct.pack("<HHII", tag, kind, 1, value)
        raw += struct.pack("<I", 8 + (i + 1) * ifd if i + 1 < len(movie) else 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw + b"".join(chunks))


def read_mrc(path):
    data = path.read_bytes()
    nx, ny, nz, mode = struct.unpack_from("<4i", data)
    require(mode == 2, f"{path}: MRC mode {mode}")
    return (nx, ny, nz), struct.unpack_from("<%df" % (nx * ny), data, 1024)


def rel_rmse(a, b):
    num = sum((x - y) ** 2 for x, y in zip(a, b))
    mean = sum(a) / len(a)
    den = sum((x - mean) ** 2 for x in a)
    return math.sqrt(num / den)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--workdir", type=Path)
    args = ap.parse_args()
    work = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-fft-fallback-"))
    data = work / "input"
    write_tiff(data / "Movies/m.tiff", frames())
    (data / "movies.star").write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
        "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n_rlnSphericalAberration #5\n"
        "_rlnAmplitudeContrast #6\nopticsGroup1 1 1.0 300 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        "Movies/m.tiff 1\n")

    def run(name, fault, policy="fast"):
        out = work / name
        out.mkdir(parents=True)
        cmd = [str(args.binary.resolve()), "--i", "movies.star", "--o", str(out) + "/", "--use_own",
               "--gpu", "0", "--j", "2", "--patch_x", "1", "--patch_y", "1", "--bfactor", "150",
               "--seed", "1", "--angpix", "1.0", "--voltage", "300", "--skip_defect",
               "--dose_weighting", "--dose_per_frame", "1", "--save_noDW", "--fft_size_policy", policy]
        env = {k: v for k, v in os.environ.items() if not k.startswith("MC_")}
        env["MC_PREPROCESS_FAULT"] = fault
        p = subprocess.run(cmd, cwd=data, env=env, capture_output=True, text=True, timeout=120)
        log = (out / "Movies/m.log").read_text() if (out / "Movies/m.log").exists() else ""
        text = p.stdout + p.stderr + log
        (work / (name + ".txt")).write_text(text)
        require(p.returncode == 0, f"{name}: exit {p.returncode}: {text[-2000:]}")
        require("remaining-owned=0 stale-releases=0" in p.stderr, f"{name}: CUDA allocations left owned")
        if policy == "fast":
            require(f"FFT size policy fast: frame {NX}x{NY} transformed at 64x48" in text,
                    f"{name}: the session did not pad")
        products = {}
        for kind in ("m.mrc", "m_noDW.mrc"):
            shape, pixels = read_mrc(out / "Movies" / kind)
            require(shape == (NX, NY, 1), f"{name}: {kind} has shape {shape}")
            products[kind] = pixels
        return text, products

    # fast fails the backend gate, so the option must stay out of --help.
    usage = subprocess.run([str(args.binary.resolve()), "--use_own", "--help"], capture_output=True, text=True, timeout=60)
    require("--ingest" in usage.stdout, "--help printed no usage")
    require("fft_size_policy" not in usage.stdout, "--fft_size_policy is listed in --help")
    _, healthy = run("healthy", "none")
    _, exact = run("healthy_exact", "none", policy="exact")
    policy_dw = rel_rmse(healthy["m.mrc"], exact["m.mrc"])
    print(f"healthy exact vs fast m.mrc: relRMSE {policy_dw:.3g}")
    cases = (("ifft-crop-recoverable", "computeGlobalInverseFFT"),
             ("dw-alloc-recoverable", "cudaDoseWeightAndInterpolateDevice"))
    fallback_dw = []
    for fault, boundary in cases:
        text, got = run(fault, fault)
        require(f"at {boundary}; pending slot cleared" in text,
                f"{fault}: injection witness missing")
        require("Refusing CPU fallback" not in text, f"{fault}: recoverable fault was refused")
        nodw = rel_rmse(healthy["m_noDW.mrc"], got["m_noDW.mrc"])
        dw = rel_rmse(healthy["m.mrc"], got["m.mrc"])
        print(f"{fault}: relRMSE vs healthy fast noDW {nodw:.3g} DW {dw:.3g}")
        require(nodw < 1e-5, f"{fault}: noDW relRMSE {nodw:.3g} vs healthy fast run")
        require(dw < policy_dw, f"{fault}: DW relRMSE {dw:.3g} not below the policy difference {policy_dw:.3g}")
        fallback_dw.append(got["m.mrc"])
    agree = rel_rmse(*fallback_dw)
    print(f"fallback DW products agree: relRMSE {agree:.3g}")
    require(agree < 1e-5, f"the two fallback DW products differ: relRMSE {agree:.3g}")
    print(f"PASS fft_size_policy fast CPU fallbacks; artifacts: {work}")
    print("Injected status codes only; genuine device faults remain untested.")


if __name__ == "__main__":
    main()
