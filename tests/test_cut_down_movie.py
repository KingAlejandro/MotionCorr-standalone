#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""tools/cut_down_movie.py must keep exactly the requested frames, in any container.

Inputs are written with test-data/formats/encoders.py, cut, and decoded with
MotionCorr's own readers (runner_numerics read_tiff_raw / render_eer); the result
must equal the corresponding subset (and crop) of the source array. Covers classic
TIFF and BigTIFF (whose directories must stay 8-byte aligned), EER 65001/65002,
MRC in both byte orders with and without an extended header, a big-endian 256x256
movie whose dimensions are plausible in either byte order, 4-bit and uint16 MRC
crops, xz/zstd-compressed MRC, and a refused inconsistent header.
"""
import argparse, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "test-data" / "formats"))
sys.path.insert(0, str(ROOT / "test-data"))
import encoders as E  # noqa: E402
import generate_format_fixtures as G  # noqa: E402

CUT = ROOT / "tools" / "cut_down_movie.py"


def cut(src, dst, frames, first=0, crop=None):
    cmd = [sys.executable, str(CUT), str(src), str(dst), "--frames", str(frames), "--first", str(first)]
    if crop:
        cmd += ["--crop"] + [str(v) for v in crop]
    return subprocess.run(cmd, capture_output=True, text=True)


MAX_SAMPLES = 50_000_000   # every fixture here is far smaller


def declared_samples(path):
    """Samples the MRC reader will believe the header declares (TIFF: None).

    Mirrors parseMRCHeader in src/rwMRC.h: the header is read little-endian and
    byte-swapped when |mode| or |nx| exceeds SWAPTRIG (65535, src/image.h). Any
    other rule can approve a header the reader then interprets as 2^48 samples.
    """
    with open(path, "rb") as f:
        h = f.read(1024)
    if len(h) < 1024 or h[:4] in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"):
        return None
    nx, ny, nz, mode = struct.unpack("<4i", h[:16])
    if abs(mode) > 65535 or abs(nx) > 65535:
        nx, ny, nz, mode = struct.unpack(">4i", h[:16])
    if nx <= 0 or ny <= 0 or nz <= 0:
        return 0
    return nx * ny * nz


def decode(helper, path, tmp):
    """Decoded movie, or an empty array when the reader refuses the file (reported as a mismatch).

    A corrupt header can claim terabytes; such files are not handed to the reader,
    whose raw dump would otherwise fill the disk.
    """
    dump = Path(tmp) / "d.bin"
    if not Path(path).exists():
        return np.zeros((0, 0, 0), np.float32)
    n = declared_samples(path)
    if n is not None and (n == 0 or n > MAX_SAMPLES):
        return np.zeros((0, 0, 0), np.float32)
    if subprocess.run([str(helper), "read_tiff_raw", str(path), str(dump)],
                                                 capture_output=True).returncode != 0:
        return np.zeros((0, 0, 0), np.float32)
    d = dump.read_bytes()
    nx, ny, nn = struct.unpack("<qqq", d[:24])
    return np.frombuffer(d[24:], "<f4").reshape(nn, ny, nx)


def eer_groups(helper, path, tmp, up, grouping):
    dump = Path(tmp) / "e.bin"
    if subprocess.run([str(helper), "render_eer", str(path), str(dump), str(up), str(grouping)],
                      capture_output=True).returncode != 0:
        return (0, 0), []
    d = dump.read_bytes()
    nx, ny, g = struct.unpack("<qqq", d[:24])
    off, out = 24, []
    for _ in range(g):
        n = struct.unpack("<q", d[off:off + 8])[0]
        off += 8
        i = np.frombuffer(d[off:off + 8 * n], "<i8")
        off += 8 * n
        v = np.frombuffer(d[off:off + 4 * n], "<f4")
        off += 4 * n
        out.append((i, v))
    return (nx, ny), out


def bigtiff_aligned(path):
    with open(path, "rb") as f:
        h = f.read(16)
        if h[:4] != b"II+\0":
            return None
        off = struct.unpack("<Q", h[8:16])[0]
        while off:
            if off % 8:
                return False
            f.seek(off)
            n = struct.unpack("<Q", f.read(8))[0]
            f.seek(off + 8 + 20 * n)
            off = struct.unpack("<Q", f.read(8))[0]
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--helper", type=Path, required=True)
    a = ap.parse_args()
    failures = []

    def check(name, ok, detail=""):
        print("  %-36s %s %s" % (name, "PASS" if ok else "FAIL", detail))
        if not ok:
            failures.append(name)

    rng = np.random.default_rng(5)
    m = rng.integers(0, 16, size=(6, 64, 80)).astype(np.float64)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        # TIFF, classic and BigTIFF
        for name, kw in [("tiff_u16_deflate_p2", dict(compression=8, predictor=2, rows_per_strip=1)),
                         ("bigtiff_u8_lzw", dict(compression=5, rows_per_strip=3, bigtiff=True))]:
            dt = np.uint16 if "u16" in name else np.uint8
            E.write_tiff_movie(t / (name + ".tif"), m, dt, **kw)
            r = cut(t / (name + ".tif"), t / (name + "_cut.tif"), 3, first=2)
            ok = r.returncode == 0 and np.array_equal(decode(a.helper, t / (name + "_cut.tif"), tmp), m[2:5])
            if kw.get("bigtiff"):
                ok = ok and bigtiff_aligned(t / (name + "_cut.tif"))
            check(name + " frames 2-4", ok, r.stderr.strip()[-120:])
        # EER: 30 fractions of a 37-fraction file, grouped by 10
        for comp, sym in ((65001, 4), (65002, 2)):
            fr, _ = G.eer_fractions(2048, 3, 10, 7, seed=comp, blobs_per_mpx=10, sym_bits=sym)
            src, dst = t / ("e%d.eer" % comp), t / ("e%d_cut.eer" % comp)
            E.write_eer(src, fr, 2048, comp)
            r = cut(src, dst, 20)
            up = 2 if sym == 2 else 1
            ok = r.returncode == 0 and bigtiff_aligned(dst)
            if ok:
                (d1, g1), (d2, g2) = eer_groups(a.helper, dst, tmp, up, 10), eer_groups(a.helper, src, tmp, up, 10)
                ok = d1 == d2 and len(g1) == 2 and all(np.array_equal(x[0], y[0]) and np.array_equal(x[1], y[1])
                                                       for x, y in zip(g1, g2[:2]))
            check("eer %d first 20 fractions" % comp, ok, r.stderr.strip()[-120:])
        # MRC in both byte orders; the 256 x 256 big-endian movie reads as 65536 x 65536
        # little-endian, so dimension plausibility cannot pick the byte order.
        sq = rng.integers(0, 16, size=(3, 256, 256)).astype(np.float64)
        cases = [("mrc_le_mode2_fei2", m, dict(mode=2, ext_header=b"\x07" * 2048, exttyp=b"FEI2")),
                 ("mrc_be_mode2", m, dict(mode=2, endian=">")),
                 ("mrc_be_mode0_256", sq, dict(mode=0, endian=">")),
                 ("mrc_be_mode1_256", sq, dict(mode=1, endian=">"))]
        for name, mov, kw in cases:
            src, dst = t / (name + ".mrcs"), t / (name + "_cut.mrcs")
            src.write_bytes(E.mrc_bytes(mov, kw.pop("mode"), **kw))
            r = cut(src, dst, 2, first=1)
            ok = r.returncode == 0 and np.array_equal(decode(a.helper, dst, tmp), mov[1:3])
            check(name + " frames 1-2", ok, r.stderr.strip()[-120:])
        # Unstamped big-endian header: the payload-size check must still pick the order.
        raw = bytearray(E.mrc_bytes(sq, 1, endian=">"))
        raw[212:216] = b"\0\0\0\0"
        (t / "mrc_be_nostamp.mrcs").write_bytes(bytes(raw))
        r = cut(t / "mrc_be_nostamp.mrcs", t / "mrc_be_nostamp_cut.mrcs", 2)
        ok = r.returncode == 0 and np.array_equal(decode(a.helper, t / "mrc_be_nostamp_cut.mrcs", tmp), sq[:2])
        check("mrc_be_mode1 without machine stamp", ok, r.stderr.strip()[-120:])
        # Crops (raw samples only)
        for name, mode in (("mrc_mode101_crop", 101), ("mrc_mode6_crop", 6)):
            src, dst = t / (name + ".mrcs"), t / (name + "_cut.mrcs")
            src.write_bytes(E.mrc_bytes(m, mode))
            r = cut(src, dst, 3, crop=(10, 6, 40, 30))
            ok = r.returncode == 0 and np.array_equal(decode(a.helper, dst, tmp), m[:3, 6:36, 10:50])
            check(name, ok, r.stderr.strip()[-120:])
        # Compressed MRC: recompressed with the same codec
        raw = E.mrc_bytes(m, 1)
        import lzma
        (t / "c.mrcs.xz").write_bytes(lzma.compress(raw))
        r = cut(t / "c.mrcs.xz", t / "c_cut.mrcs.xz", 3)
        ok = r.returncode == 0
        if ok:
            (t / "c_cut.mrcs").write_bytes(lzma.decompress((t / "c_cut.mrcs.xz").read_bytes()))
            ok = np.array_equal(decode(a.helper, t / "c_cut.mrcs", tmp), m[:3])
        check("mrc xz frames 0-2", ok, r.stderr.strip()[-120:])
        if shutil.which("zstd"):
            subprocess.run(["zstd", "-q", "-o", str(t / "c.mrcs.zst"), "-"], input=raw, check=True)
            r = cut(t / "c.mrcs.zst", t / "c_cut.mrcs.zst", 3)
            ok = r.returncode == 0
            if ok:
                plain = subprocess.run(["zstd", "-dc", str(t / "c_cut.mrcs.zst")], capture_output=True, check=True).stdout
                (t / "c_cut2.mrcs").write_bytes(plain)
                ok = np.array_equal(decode(a.helper, t / "c_cut2.mrcs", tmp), m[:3])
            check("mrc zst frames 0-2", ok, r.stderr.strip()[-120:])
        # The guard must use the reader's byte-order rule: this little-endian header
        # (65536, 256, 1, mode 0) is modest read as written, but rwMRC.h swaps it
        # (nx > 65535) and sees 256 x 65536 x 16777216 = 2^48 samples. The helper path
        # does not exist, so the check fails loudly if the guard lets the file through.
        g = bytearray(1024 + 4096)
        struct.pack_into("<4i", g, 0, 65536, 256, 1, 0)
        (t / "guard.mrcs").write_bytes(bytes(g))
        try:
            refused = decode(Path("/nonexistent/runner_numerics"), t / "guard.mrcs", tmp).size == 0
        except OSError:
            refused = False
        check("oversized header not decoded", refused and declared_samples(t / "guard.mrcs") == 1 << 48)
        # An inconsistent header (more frames than the file holds) is refused, not cut.
        bad = bytearray(E.mrc_bytes(m, 2))
        struct.pack_into("<i", bad, 8, 60)
        (t / "bad.mrcs").write_bytes(bytes(bad))
        r = cut(t / "bad.mrcs", t / "bad_cut.mrcs", 2)
        check("inconsistent header refused", r.returncode != 0 and not (t / "bad_cut.mrcs").exists(), r.stderr.strip()[-80:])
    print("cut_down_movie: %d failure(s)" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
