#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic movies in every container, sample type and codec MotionCorr reads.

One integer-valued movie (counts 0..15) is written in each encoding. Every value
is exactly representable in every sample type here (int8 to float32, float16,
4-bit packed, EER electron counts), so each accepted encoding must decode to the
same array, and a motion-correction run on it must produce the same products as
the float32 MRC reference. tests/test_input_formats.py checks both.

Groups
  small   192 x 160 x 8; MRC modes, TIFF sample types and codecs, compressed MRC,
          gain and defect inputs, rejections and characterisation cases
  eer     2048^2 and 4096^2 EER (65000, 65001, 65002, legacy), EER gain
  heavy   K2 super-resolution geometry for IMOD packed 4-bit TIFF (opt-in)

Each case in manifest.json says how it is checked:
  decode  the decoded movie (tests/test_runner_numerics read_tiff_raw/render_eer)
          must equal expected/<id>.npy (or the sparse EER form) exactly
  e2e     products of a motioncorr batch must be byte-identical (pixel payload
          and shift tables) to those of the named reference case
  reject  motioncorr must exit non-zero, name the movie and print the substring,
          and write no product for it
  characterise  pins current (upstream-inherited) behaviour that differs from the
          producer's convention; the note says what and why

Deterministic: NumPy RNG with fixed seeds and pure-Python encoders; manifest.json
records the SHA-256 of every file. Usage:
  python3 test-data/generate_format_fixtures.py --outdir DIR [--include-heavy]
"""
import argparse
import bz2
import hashlib
import json
import lzma
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "formats"))
import encoders as E  # noqa: E402

GENERATOR_VERSION = 1
NX, NY, NF = 192, 160, 8
DRIFT = (0.6, -0.4)
EER_GROUP = 10
EER_GROUPS = 3
EER_TAIL = 7            # extra raw fractions that grouping must drop


# ----------------------------------------------------------------- base content

def blob_movie(nx, ny, nf, seed, peak=6.0, maxval=15, n_blobs=None, sigma=2.2, background=0.8):
    """Poisson counts of drifting Gaussian blobs, clipped to maxval."""
    rng = np.random.default_rng(seed)
    n_blobs = n_blobs or max(12, nx * ny // 900)
    cx = rng.uniform(0, nx, n_blobs)
    cy = rng.uniform(0, ny, n_blobs)
    amp = rng.uniform(0.5, 1.0, n_blobs)
    yy, xx = np.mgrid[0:ny, 0:nx]
    out = np.empty((nf, ny, nx), dtype=np.float64)
    for f in range(nf):
        lam = np.full((ny, nx), background)
        for x0, y0, a in zip(cx, cy, amp):
            x1, y1 = x0 + DRIFT[0] * f, y0 + DRIFT[1] * f
            r = int(4 * sigma) + 1
            xs = slice(max(0, int(x1) - r), min(nx, int(x1) + r + 1))
            ys = slice(max(0, int(y1) - r), min(ny, int(y1) + r + 1))
            lam[ys, xs] += peak * a * np.exp(-((xx[ys, xs] - x1) ** 2 + (yy[ys, xs] - y1) ** 2)
                                            / (2 * sigma ** 2))
        out[f] = np.minimum(rng.poisson(lam), maxval)
    return out


def small_movie():
    m = blob_movie(NX, NY, NF, seed=20261016)
    # Pin the extremes so every encoding is exercised at 0 and 15.
    m[:, 0, 0] = 0
    m[:, 0, 1] = 15
    return m


def small_gain():
    """Integer gain 1..4: exact in every sample type, including float16 and int8."""
    rng = np.random.default_rng(7)
    return rng.integers(1, 5, size=(NY, NX)).astype(np.float64)


DEFECT_RECTS = [(10, 12, 3, 2), (100, 40, 1, 5), (150, 120, 4, 4)]   # x y w h


def defect_map():
    m = np.zeros((NY, NX))
    for x, y, w, h in DEFECT_RECTS:
        m[y:y + h, x:x + w] = 1
    return m


def eer_fractions(size, n_groups, group, tail, seed, blobs_per_mpx, sym_bits):
    """Electron events whose grouped counts form a drifting-blob movie.

    A pixel holds at most one electron per fraction, so a group's count is at
    most `group`; each count c is spread over c distinct fractions of the group.
    Returns (fractions, grouped counts at detector resolution, all events).
    """
    rng = np.random.default_rng(seed)
    counts = blob_movie(size, size, n_groups, seed + 1, peak=2.5, maxval=group,
                        n_blobs=max(4, int(blobs_per_mpx * size * size / 1e6)), sigma=5.0,
                        background=0.01)
    fractions = []
    for g in range(n_groups + (1 if tail else 0)):
        nfr = group if g < n_groups else tail
        per = [[] for _ in range(nfr)]
        if g < n_groups:
            flat = counts[g].ravel().astype(np.int64)
            idx = np.flatnonzero(flat)
            # c distinct fractions per pixel: the first c of a random permutation
            order = np.argsort(rng.random((idx.size, nfr)), axis=1)
            take = np.arange(nfr)[None, :] < flat[idx][:, None]
            pix = np.broadcast_to(idx[:, None], order.shape)[take]
            frac = order[take]
            for f in range(nfr):
                per[f] = pix[frac == f]
        else:
            for f in range(nfr):
                per[f] = np.unique(rng.integers(0, size * size, size * 4)).tolist()
        for f in range(nfr):
            pos = np.sort(np.asarray(per[f], dtype=np.int64))
            sym = rng.integers(0, 1 << sym_bits, pos.size).astype(np.int64)
            fractions.append((pos, sym))
    return fractions, counts


def render_expected(fractions, size, group, n_groups, upsampling, sym_bits):
    """Grouped counts as the EER format defines them (x subpixel in the low half
    of the symbol, y in the high half; upsampling keeps the top bits)."""
    hb = sym_bits // 2
    out = []
    for g in range(n_groups):
        acc = {}
        for pos, sym in fractions[g * group:(g + 1) * group]:
            y, x = pos // size, pos % size
            if upsampling == -1:
                X, Y, w = x >> 1, y >> 1, size >> 1
            else:
                k = upsampling - 1
                xs, ys = sym & ((1 << hb) - 1), sym >> hb
                X = (x << k) | (xs >> (hb - k)) if k else x
                Y = (y << k) | (ys >> (hb - k)) if k else y
                w = size << k
            lin = Y * w + X
            u, c = np.unique(lin, return_counts=True)
            for a, b in zip(u.tolist(), c.tolist()):
                acc[a] = acc.get(a, 0) + b
        keys = np.array(sorted(acc), dtype=np.int64)
        out.append((keys, np.array([acc[k] for k in keys.tolist()], dtype=np.int64)))
    return out


# --------------------------------------------------------------------- the cases

class Builder:
    def __init__(self, outdir, include_heavy):
        self.out = Path(outdir)
        self.heavy = include_heavy
        self.cases = []
        self.expected = {}

    def path(self, rel):
        p = self.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def expect(self, key, arr):
        p = self.path("expected/%s.npy" % key)
        np.save(p, np.asarray(arr, dtype=np.float32))
        self.expected[key] = str(p.relative_to(self.out))

    def add(self, **case):
        case.setdefault("kind", "accept")
        case.setdefault("requires", [])
        case.setdefault("heavy", False)
        self.cases.append(case)


def build_small(b):
    m = small_movie()
    b.expect("small", m)
    star_opts = {"angpix": 1.0, "voltage": 300}
    ref = "mrc_mode2_f32"

    def mrc(name, fname, mode, note, **kw):
        b.path("small/" + fname).write_bytes(E.mrc_bytes(kw.pop("movie", m), mode, **kw))
        b.add(name=name, group="small", file="small/" + fname, note=note,
              decode={"reader": "image", "expected": kw.get("expected", "small")},
              e2e={"batch": "small", "reference": ref})

    mrc(ref, "mrc_mode2_f32.mrcs", 2, "float32 MRC: the reference every other encoding must match")
    mrc("mrc_mode0_s8", "mrc_mode0_s8.mrcs", 0, "8-bit MRC (EMPIAR-10164); compact signed 8-bit staging on CUDA")
    mrc("mrc_mode1_s16", "mrc_mode1_s16.mrcs", 1, "int16 MRC (EMPIAR-10216, EPU Fractions)")
    mrc("mrc_mode6_u16", "mrc_mode6_u16.mrcs", 6, "uint16 MRC (Leginon K2, EPU Falcon with FEI headers)")
    mrc("mrc_mode12_f16", "mrc_mode12_f16.mrcs", 12, "float16 MRC")
    mrc("mrc_mode101_4bit", "mrc_mode101_4bit.mrcs", 101, "SerialEM 4-bit packed MRC (EMPIAR-10374)")
    mrc("mrc_mode2_f32_bigendian", "mrc_mode2_f32_be.mrcs", 2, "big-endian float32 MRC", endian=">")
    mrc("mrc_mode1_s16_bigendian", "mrc_mode1_s16_be.mrcs", 1, "big-endian int16 MRC", endian=">")
    mrc("mrc_mode6_u16_fei2", "mrc_mode6_u16_fei2.mrcs", 6, "uint16 MRC with an FEI2 extended header (EPU)",
        ext_header=bytes(range(256)) * 12, exttyp=b"FEI2")
    mrc("mrc_mode1_s16_seri", "mrc_mode1_s16_seri.mrcs", 1, "int16 MRC with a SERI extended header (SerialEM)",
        ext_header=b"\x01" * 1024, exttyp=b"SERI", imod_flags=1)

    raw = (b.out / "small/mrc_mode2_f32.mrcs").read_bytes()
    for suffix, req, data in (("xz", "xz", lzma.compress(raw)), ("bz2", "pbzip2", bz2.compress(raw)),
                              ("zst", "zstd", None)):
        fname = "small/mrc_mode2_f32_%s.mrcs.%s" % (suffix, suffix)
        if data is None:
            if shutil.which("zstd") is None:
                b.add(name="mrc_compressed_zst", group="small", file=fname, kind="unbuilt",
                      requires=["zstd"], note="zstd not available to build the fixture")
                continue
            p = b.path(fname)
            subprocess.run(["zstd", "-q", "-19", "-f", "--no-progress", "-o", str(p), "-"],
                           input=raw, check=True)
        else:
            b.path(fname).write_bytes(data)
        b.add(name="mrc_compressed_" + suffix, group="small", file=fname, requires=[req],
              note="compressed MRC, decoded through an external %s pipe (Leginon .frames.mrc.bz2, EMPIAR-10202 .zst); "
                   "the harness copies it rather than linking it" % req,
              e2e={"batch": "small", "reference": ref, "copy": True})
        if suffix == "zst":
            b.add(name="mrc_compressed_zst_symlink", group="small", file=fname, requires=[req],
                  kind="known_failure", known={"current": "refused", "correct": "accepted"},
                  note="the reader pipes 'zstd -cdk FILE'; zstd ignores a symbolic-link input without -f, so "
                       "a symlinked .mrc.zst movie fails with 'error in reading header'. RELION projects and "
                       "the corpus run directories link movies. xz accepts links. Upstream uses the same command.")

    def tif(name, fname, dtype, note, values=None, decode=True, **kw):
        E.write_tiff_movie(b.path("small/" + fname), m if values is None else values, dtype, **kw)
        b.add(name=name, group="small", file="small/" + fname, note=note,
              decode={"reader": "image", "expected": "small"} if decode else None,
              e2e={"batch": "small", "reference": ref})

    tif("tiff_u8_none", "tiff_u8_none.tif", np.uint8, "8-bit TIFF, uncompressed")
    tif("tiff_u8_lzw", "tiff_u8_lzw.tif", np.uint8, "8-bit LZW TIFF (most EMPIAR K2/K3 TIFF)", compression=5, rows_per_strip=3)
    tif("tiff_u8_lzw_pred2", "tiff_u8_lzw_p2.tif", np.uint8, "8-bit LZW TIFF, horizontal predictor", compression=5, predictor=2, rows_per_strip=8)
    tif("tiff_u8_deflate", "tiff_u8_deflate.tif", np.uint8, "8-bit Deflate TIFF", compression=8, rows_per_strip=1)
    tif("tiff_u8_packbits", "tiff_u8_packbits.tif", np.uint8, "8-bit PackBits TIFF", compression=32773, rows_per_strip=16)
    tif("tiff_u8_bigtiff_lzw", "tiff_u8_bigtiff_lzw.tif", np.uint8, "8-bit LZW BigTIFF (EMPIAR-10361/10441/10641)", compression=5, rows_per_strip=2, bigtiff=True)
    tif("tiff_u16_none", "tiff_u16_none.tif", np.uint16, "16-bit TIFF, uncompressed")
    tif("tiff_u16_deflate_rps1", "tiff_u16_deflate_rps1.tif", np.uint16, "16-bit Deflate TIFF, one row per strip: the tutorial layout, nvCOMP-eligible on CUDA", compression=8, rows_per_strip=1)
    tif("tiff_u16_deflate_rps16", "tiff_u16_deflate_rps16.tif", np.uint16, "16-bit Deflate TIFF, 16 rows per strip (not nvCOMP-eligible)", compression=8, rows_per_strip=16)
    tif("tiff_u16_deflate_pred2", "tiff_u16_deflate_p2.tif", np.uint16, "16-bit Deflate TIFF, horizontal predictor (not nvCOMP-eligible)", compression=8, predictor=2, rows_per_strip=1)
    tif("tiff_u16_deflate_old", "tiff_u16_deflate_32946.tif", np.uint16, "16-bit Deflate TIFF, old compression code 32946", compression=32946, rows_per_strip=1)
    tif("tiff_u16_lzw", "tiff_u16_lzw.tif", np.uint16, "16-bit LZW TIFF", compression=5, rows_per_strip=4)
    tif("tiff_u16_lzw_pred2", "tiff_u16_lzw_p2.tif", np.uint16, "16-bit LZW TIFF, horizontal predictor", compression=5, predictor=2, rows_per_strip=4)
    tif("tiff_u16_packbits", "tiff_u16_packbits.tif", np.uint16, "16-bit PackBits TIFF", compression=32773, rows_per_strip=8)
    tif("tiff_u16_bigendian", "tiff_u16_be.tif", np.uint16, "big-endian 16-bit TIFF", endian=">")
    tif("tiff_u16_bigendian_deflate", "tiff_u16_be_deflate.tif", np.uint16, "big-endian 16-bit Deflate TIFF, one row per strip (byte-swapped: not nvCOMP-eligible)", compression=8, rows_per_strip=1, endian=">")
    tif("tiff_u16_bigtiff_deflate", "tiff_u16_bigtiff_deflate.tif", np.uint16, "16-bit Deflate BigTIFF", compression=8, rows_per_strip=1, bigtiff=True)
    tif("tiff_s8", "tiff_s8.tif", np.int8, "signed 8-bit TIFF")
    tif("tiff_s16", "tiff_s16.tif", np.int16, "signed 16-bit TIFF")
    tif("tiff_s16_lzw", "tiff_s16_lzw.tif", np.int16, "signed 16-bit LZW TIFF", compression=5, rows_per_strip=4)
    tif("tiff_f32", "tiff_f32.tif", np.float32, "float32 TIFF")
    tif("tiff_f32_lzw_pred3", "tiff_f32_lzw_p3.tif", np.float32, "float32 LZW TIFF, floating-point predictor", compression=5, predictor=3, rows_per_strip=4)
    tif("tiff_f32_deflate", "tiff_f32_deflate.tif", np.float32, "float32 Deflate TIFF", compression=8, rows_per_strip=8)
    tif("tiff_u8_orientation2", "tiff_u8_orient2.tif", np.uint8,
        "orientation tag 2 (EPU EER and .gain files carry 2, 4, 5, 6): the reader ignores it, as upstream",
        extra_tags=[(274, E.SHORT, [2])])

    # ---- characterisation: behaviour that differs from a producer's convention
    u = np.where(m > 0, m + 120, 0)                       # 0 or 121..135: crosses 127
    b.path("small/mrc_mode0_unsigned.mrcs").write_bytes(E.mrc_bytes(u, 0, imod_flags=0))
    wrapped = np.where(u > 127, u - 256, u)
    b.expect("small_mode0_wrapped", wrapped)
    b.path("small/mrc_mode2_wrapped_ref.mrcs").write_bytes(E.mrc_bytes(wrapped, 2))
    b.add(name="mrc_mode2_wrapped_ref", group="small", file="small/mrc_mode2_wrapped_ref.mrcs",
          decode={"reader": "image", "expected": "small_mode0_wrapped"},
          e2e={"batch": "small", "reference": "mrc_mode2_wrapped_ref"},
          note="float32 reference for the mode-0 characterisation")
    b.add(name="mrc_mode0_unsigned_bytes", group="small", file="small/mrc_mode0_unsigned.mrcs", kind="characterise",
          decode={"reader": "image", "expected": "small_mode0_wrapped"},
          e2e={"batch": "small", "reference": "mrc_mode2_wrapped_ref"},
          note="IMOD writes mode 0 unsigned unless imodFlags bit 1 is set (here unset). rwMRC.h reads every "
               "mode-0 file as signed (RELION 3.1 change, MRC2014 standard), so 128..255 become negative. "
               "Upstream behaviour, pinned. Real 8-bit counting movies stay below 128.")

    odd = blob_movie(NX - 1, NY, 2, seed=11)              # odd width, even height
    row_bytes = []
    for f in odd:
        for r in f:
            padded = np.concatenate([r, [0]]).astype(np.uint8)
            row_bytes.append(E.pack_nibbles(padded))
    b.path("small/mrc_mode101_oddwidth.mrcs").write_bytes(
        E.mrc_bytes(odd, 101, payload=b"".join(row_bytes)))
    b.expect("small_oddwidth", odd)
    b.add(name="mrc_mode101_odd_width", group="small", file="small/mrc_mode101_oddwidth.mrcs", kind="characterise",
          decode={"reader": "image", "expected": "small_oddwidth", "expect_equal": False},
          note="IMOD pads each 4-bit row to (nx+1)/2 bytes when nx is odd (mrc_format.txt). rwMRC.h reads the "
               "nibbles contiguously and rejects only odd nx AND odd ny, so an odd-width, even-height file "
               "decodes shifted. Pinned as a known divergence; no real file of this shape was found.")

    # ---- gain inputs: every encoding of the same gain must give the same products
    g = small_gain()
    b.path("small/gain_f32.mrc").write_bytes(E.mrc_bytes(g[None], 2))
    gains = [("gain_mrc_f32", "gain_f32.mrc", None),
             ("gain_mrc_f16", "gain_f16.mrc", ("mrc", 12)), ("gain_mrc_s16", "gain_s16.mrc", ("mrc", 1)),
             ("gain_mrc_u16", "gain_u16.mrc", ("mrc", 6)), ("gain_mrc_s8", "gain_s8.mrc", ("mrc", 0)),
             ("gain_tiff_f32", "gain_f32.tif", ("tif", np.float32)), ("gain_tiff_u16", "gain_u16.tif", ("tif", np.uint16)),
             ("gain_tiff_u8_lzw", "gain_u8_lzw.tif", ("tif", np.uint8))]
    for name, fname, how in gains:
        if how and how[0] == "mrc":
            b.path("small/" + fname).write_bytes(E.mrc_bytes(g[None], how[1]))
        elif how:
            E.write_tiff_movie(b.path("small/" + fname), g[None], how[1],
                               compression=5 if "lzw" in fname else 1, rows_per_strip=8)
        b.add(name=name, group="small", file="small/mrc_mode2_f32.mrcs", note="gain reference stored as " + fname,
              e2e={"batch": "gain:" + fname, "reference": "gain_mrc_f32", "options": ["--gainref", fname]})

    # ---- defect inputs: one set of bad pixels as a text file and as maps
    d = defect_map()
    b.path("small/defect.txt").write_text("".join("%d %d %d %d\n" % r for r in DEFECT_RECTS))
    defects = [("defect_txt", "defect.txt", None), ("defect_mrc_f32", "defect_f32.mrc", ("mrc", 2)),
               ("defect_mrc_s8", "defect_s8.mrc", ("mrc", 0)), ("defect_mrc_u16", "defect_u16.mrc", ("mrc", 6)),
               ("defect_tiff_u8", "defect_u8.tif", ("tif", np.uint8))]
    for name, fname, how in defects:
        if how and how[0] == "mrc":
            b.path("small/" + fname).write_bytes(E.mrc_bytes(d[None], how[1]))
        elif how:
            E.write_tiff_movie(b.path("small/" + fname), d[None], how[1], rows_per_strip=16)
        b.add(name=name, group="small", file="small/mrc_mode2_f32.mrcs", note="defects given as " + fname,
              e2e={"batch": "defect:" + fname, "reference": "defect_txt", "options": ["--defect_file", fname],
                   "no_skip_defect": True})
    b.path("small/defect_serialem.txt").write_text(
        "CameraSizeX 192 CameraSizeY 160\nRotationAndFlip 0\nK2Type 0\nBadColumns 10 100\n"
        "PartialBadColumn 150 120 124\nBadPixels 12 13 40 41\n")
    b.add(name="defect_serialem_text", group="small", file="small/mrc_mode2_f32.mrcs", kind="reject",
          reject={"substring": "SerialEM", "options": ["--defect_file", "defect_serialem.txt"], "no_skip_defect": True,
                  "names_movie": False},
          note="SerialEM defect lists use a different text format and must be refused")

    # ---- rejections
    def rej(name, fname, data_or_fn, substring, note):
        p = b.path("small/" + fname)
        if callable(data_or_fn):
            data_or_fn(p)
        else:
            p.write_bytes(data_or_fn)
        b.add(name=name, group="small", file="small/" + fname, kind="reject",
              reject={"substring": substring}, note=note)

    rej("mrc_mode3_complex16", "mrc_mode3.mrcs", E.mrc_bytes(m, 3, payload=b"\0" * (m.size * 4)),
        "only real-space images", "complex MRC (mode 3)")
    rej("mrc_mode4_complex32", "mrc_mode4.mrcs", E.mrc_bytes(m, 4, payload=b"\0" * (m.size * 8)),
        "only real-space images", "complex MRC (mode 4)")
    rej("mrc_mode5", "mrc_mode5.mrcs", E.mrc_bytes(m, 5, payload=m.astype(np.uint8).tobytes()),
        "unsupported MRC mode 5", "non-standard mode 5, seen in EMPIAR-10287")
    rej("mrc_mode101_odd_odd", "mrc_mode101_oddodd.mrcs",
        E.mrc_bytes(np.zeros((2, 159, 191)), 101, payload=b"\0" * (2 * 80 * 191)),
        "4-bit MRC (mode 101) only when", "4-bit MRC with odd width and height")
    b.path("small/mrc_mode0_imodflag16.mrcs").write_bytes(
        E.mrc_bytes(m, 0, imod_flags=16, payload=E.pack_nibbles(m)))
    b.add(name="mrc_mode0_imod_4bit_flag", group="small", file="small/mrc_mode0_imodflag16.mrcs",
          kind="known_failure", known={"current": "accepted", "correct": "refused"},
          note="IMOD flag 16 marks 4-bit data stored as mode 0. rwMRC.h ignores the flag and reads nx*ny "
               "bytes per frame, so the second half of the movie is past end of file. The short read "
               "returns -2 from Image::readData, the runner ignores it, and the movie is corrected from "
               "reinterpreted nibbles plus whatever the frame buffers held. Should be refused.")
    full = E.mrc_bytes(m, 2)
    b.path("small/mrc_truncated.mrcs").write_bytes(full[:1024 + (len(full) - 1024) * 6 // 10])
    b.add(name="mrc_truncated_payload", group="small", file="small/mrc_truncated.mrcs",
          kind="known_failure", known={"current": "accepted", "correct": "refused"},
          note="float32 MRC cut to 60% of its payload (an interrupted copy). Every MRC mode behaves the "
               "same: Image::readData returns -2 on the short fread, MotioncorrRunner ignores the return "
               "value of Image::read, the job exits 0, and the missing frames hold stale pooled-buffer "
               "contents, so the product depends on the movie processed before it. Upstream ignores the "
               "return value too. TIFF truncation is refused (#92).")
    rej("tiff_u32", "tiff_u32.tif", lambda p: E.write_tiff_movie(p, m, np.uint32),
        "Unsupported TIFF format", "32-bit unsigned integer TIFF")
    rej("tiff_f64", "tiff_f64.tif", lambda p: E.write_tiff_movie(p, m, np.float64),
        "Unsupported TIFF format", "float64 TIFF")
    rej("tiff_f16", "tiff_f16.tif", lambda p: write_tiff_f16(p, m),
        "Unsupported TIFF format", "float16 TIFF (EMPIAR lists two such imagesets)")
    rej("tiff_tiled", "tiff_u16_tiled.tif",
        lambda p: E.write_tiff_movie(p, m, np.uint16, compression=8, tile=(64, 64)),
        "tiled", "tiled TIFF: LibTIFF refuses scanline reads of tiled images")
    rej("tiff_rgb", "tiff_u8_rgb.tif", lambda p: E.write_tiff_movie(p, m, np.uint8, spp=3, rows_per_strip=16),
        "", "3 samples per pixel (RGB); EMPIAR has annotation mosaics like this")
    rej("tiff_mixed_frame_size", "tiff_u8_mixed.tif", write_mixed_tiff(m), "",
        "frames of different sizes in one TIFF")
    return m


def write_tiff_f16(path, m):
    """16-bit IEEE float samples: bits 16 with sample format 3."""
    w = E.TiffWriter(path)
    for f in m:
        rows = f[::-1].astype("<f2")
        w.write_page(NX, NY, [rows.tobytes()], 16, 3, 1, rows_per_strip=NY)
    w.close()


def write_mixed_tiff(m):
    def fn(path):
        w = E.TiffWriter(path)
        for i, f in enumerate(m[:3]):
            rows = (f if i != 1 else f[:, :-8])[::-1].astype(np.uint8)
            w.write_page(rows.shape[1], rows.shape[0], [rows.tobytes()], 8, 1, 1, rows_per_strip=rows.shape[0])
        w.close()
    return fn


def build_eer(b):
    group, ngroups, tail = EER_GROUP, EER_GROUPS, EER_TAIL
    for size, comps in ((2048, (65000, 65001, 65002)), (4096, (65001, 65002))):
        for comp in comps:
            sym_bits = 2 if comp == 65002 else 4
            fr, counts = eer_fractions(size, ngroups, group, tail, seed=size + comp,
                                       blobs_per_mpx=40 if size == 2048 else 8, sym_bits=sym_bits)
            tag = "eer_%dk_%d" % (size // 1024, comp)
            fname = "eer/%s.eer" % tag
            E.write_eer(b.path(fname), fr, size, comp)
            # 2K files with 4-bit symbols are rendered at upsampling 1 only: render2K_to_4K
            # assumes 2-bit symbols and would index rows past the frame (see the note case).
            if size == 2048:
                ups = [1, 2] if sym_bits == 2 else [1]
            else:
                ups = [1, 2, -1] if sym_bits == 4 else [1, 2]
            for up in ups:
                exp = render_expected(fr, size, group, ngroups, up, sym_bits)
                key = "%s_up%d" % (tag, up)
                p = b.path("expected/%s.npz" % key)
                np.savez_compressed(p, **{"idx%d" % i: e[0] for i, e in enumerate(exp)},
                                    **{"val%d" % i: e[1] for i, e in enumerate(exp)})
                b.expected[key] = str(p.relative_to(b.out))
                known = None
                if size == 4096 and comp == 65002 and up == 2:
                    known = ("renderEER.cpp renders 4K 65002 (1+1 subpixel bits) at --eer_upsampling 2 with the "
                             "4-bit symbol masks of render4K_to_8K, so the y subpixel is always 0 and x takes "
                             "the y bit. Upstream ver5.1 and master are identical. No real 4K 65002 file was found "
                             "in the EMPIAR census, so this is a latent divergence.")
                b.add(name="%s_render_up%d" % (tag, up), group="eer", file=fname,
                      kind="characterise" if known else "accept",
                      decode={"reader": "eer", "upsampling": up, "grouping": group, "groups": ngroups,
                              "expected": key, "expect_equal": known is None},
                      note=known or ("EER %d at %d^2, rendered at --eer_upsampling %d; %d trailing fractions "
                                     "must be dropped" % (comp, size, up, tail)))
            if size == 2048:
                ref = "eer/%s_ref.mrcs" % tag
                # int8 keeps this 13 MB instead of 50; counts are <= grouping (10), and the
                # small group shows mode 0 decodes and corrects exactly like float32.
                b.path(ref).write_bytes(E.mrc_bytes(counts, 0))
                b.add(name=tag + "_ref", group="eer", file=ref,
                      note="int8 MRC of the grouped counts (reference for the EER run)",
                      e2e={"batch": "eer:" + tag, "reference": tag + "_ref"})
                b.add(name=tag + "_motioncorr", group="eer", file=fname,
                      note="EER %d through the runner at upsampling 1 must match its float32 reference" % comp,
                      e2e={"batch": "eer:" + tag, "reference": tag + "_ref",
                           "options": ["--eer_grouping", str(group), "--eer_upsampling", "1"]})

    # EER gain: an EPU .gain is multiplicative; any other gain is a count reference and is inverted.
    tag = "eer_2k_65001"
    rng = np.random.default_rng(99)
    g = rng.integers(1, 5, size=(2048, 2048)).astype(np.float64)
    gain_tif = b.path("eer/eer_gain.gain")
    w = E.TiffWriter(gain_tif)                    # EPU: float32 LZW, orientation tag present
    rows = g.astype("<f4")                        # loadEERGain undoes the TIFF reader's flip
    w.write_page(2048, 2048, E.tiff_segments(rows, np.float32, 5, 1, 2048), 32, 3, 5,
                 rows_per_strip=2048, extra_tags=[(274, E.SHORT, [2])])
    w.close()
    b.path("eer/eer_gain_mult.mrc").write_bytes(E.mrc_bytes(g[None], 0))      # 1..4, exact in int8
    # Count-reference gain h with mean exactly 2, so mean/h = 2/h is exact.
    h = np.ones((2048, 2048))
    cells = rng.permutation(2048 * 2048)
    n8 = 2048 * 2048 // 8
    h.ravel()[cells[:n8]] = 4
    h.ravel()[cells[n8:n8 + 2 * n8]] = 1
    h.ravel()[cells[3 * n8:]] = 2
    assert h.mean() == 2.0
    b.path("eer/eer_gain_counts.mrc").write_bytes(E.mrc_bytes(h[None], 0))     # 1, 2, 4
    b.path("eer/eer_gain_inverted.mrc").write_bytes(E.mrc_bytes((2.0 / h)[None], 12))  # 2, 1, 0.5
    eo = ["--eer_grouping", str(EER_GROUP), "--eer_upsampling", "1"]
    ref = "eer/%s_ref.mrcs" % tag
    b.add(name="eer_gain_ref_mult", group="eer", file=ref, note="float32 movie with the multiplicative gain as MRC",
          e2e={"batch": "eergain:mult", "reference": "eer_gain_ref_mult", "options": ["--gainref", "eer_gain_mult.mrc"]})
    b.add(name="eer_gain_epu_gain_file", group="eer", file="eer/%s.eer" % tag,
          note="EPU .gain (float32 LZW TIFF, multiplicative, orientation tag ignored) must act as the same gain",
          e2e={"batch": "eergain:mult", "reference": "eer_gain_ref_mult", "options": eo + ["--gainref", "eer_gain.gain"]})
    b.add(name="eer_gain_ref_inverted", group="eer", file=ref, note="float32 movie with gain 2/h",
          e2e={"batch": "eergain:inv", "reference": "eer_gain_ref_inverted",
               "options": ["--gainref", "eer_gain_inverted.mrc"]})
    b.add(name="eer_gain_count_reference", group="eer", file="eer/%s.eer" % tag,
          note="a non-.gain EER gain is a count reference: loadEERGain uses mean/h, here exactly 2/h",
          e2e={"batch": "eergain:inv", "reference": "eer_gain_ref_inverted",
               "options": eo + ["--gainref", "eer_gain_counts.mrc"]})

    # EER rejections
    fr, _ = eer_fractions(2048, 1, 2, 0, seed=5, blobs_per_mpx=10, sym_bits=4)

    def eer_rej(name, fname, writer, substring, note, options=()):
        writer(b.path(fname))
        b.add(name=name, group="eer", file=fname, kind="reject",
              reject={"substring": substring, "options": list(options) or ["--eer_grouping", "1"]}, note=note)

    eer_rej("eer_size_3072", "eer/eer_3k.eer",
            lambda p: E.write_eer(p, eer_fractions(3072, 1, 2, 0, 6, 5, 4)[0], 3072, 65001),
            "4096x4096 or 2048x2048", "EER sizes other than 4K and 2K are refused")
    eer_rej("eer_unknown_compression", "eer/eer_65003.eer", lambda p: write_eer_code(p, fr, 65003),
            "Unknown compression scheme for EER", "unknown EER compression code")
    eer_rej("eer_65002_rle8", "eer/eer_65002_rle8.eer", lambda p: write_eer_code(p, fr, 65002, rle=8),
            "Unsupported compression scheme", "65002 with an 8-bit run length is refused")
    eer_rej("eer_grouping_exceeds_fractions", "eer/eer_2fractions.eer",
            lambda p: E.write_eer(p, fr, 2048, 65001), "",
            "grouping larger than the fraction count leaves no frames", options=["--eer_grouping", "10"])

    b.add(name="eer_4k_65002_upsampling_minus1", group="eer", file="eer/eer_4k_65002.eer", kind="reject",
          reject={"substring": "must be 1 or 2", "options": ["--eer_grouping", str(EER_GROUP), "--eer_upsampling", "-1"]},
          note="65002 (1+1 subpixel bits) refuses --eer_upsampling -1 and 3")
    b.add(name="eer_2k_4bit_symbols_upsampling2", group="eer", file="eer/eer_2k_65001.eer", kind="not_run",
          note="render2K_to_4K takes x from symbol bit 0 and y from symbol >> 1, which is right for 2-bit "
               "symbols only. A 2K file with 4-bit symbols (65000/65001) at --eer_upsampling 2 would place "
               "y subpixels 0..7 and write past the last row of the 4096^2 frame. read() guards 2-bit symbols "
               "against -1 and 3 but nothing guards this case. Not run because it writes out of bounds; "
               "upstream ver5.1/master are the same. No real 2K EER file was found in the EMPIAR census.")

    # Legacy (pre-TIFF) EER: written, not run. renderEER.cpp leaves width, height, rle_bits,
    # subpixel_bits and total_pixels uninitialised on this path (RELION 3.1 fixed them at 4K 8-bit).
    lfr, _ = eer_fractions(4096, 1, 2, 0, seed=8, blobs_per_mpx=2, sym_bits=4)
    E.write_eer(b.path("eer/eer_legacy_4k.eer"), lfr, 4096, 65000, legacy=True)
    b.add(name="eer_legacy_container", group="eer", file="eer/eer_legacy_4k.eer", kind="not_run",
          note="pre-TIFF EER container (Falcon 3 prototypes). renderEER.cpp's legacy path never sets width, "
               "height, rle_bits, subpixel_bits or total_pixels, so rendering reads uninitialised members "
               "(undefined behaviour); upstream ver5.1/master are the same. RELION 3.1 assumed 4K with "
               "8-bit codes. Kept as a fixture for a fix; no legacy file was found in the EMPIAR census.")


def write_eer_code(path, fractions, code, rle=7):
    w = E.TiffWriter(path, "<", bigtiff=True)
    extra = [(65007, E.SHORT, [rle]), (65008, E.SHORT, [1]), (65009, E.SHORT, [1])] if code == 65002 else []
    for pos, sym in fractions:
        data = E.eer_encode_7bit(pos, sym, 2048 * 2048, 4)
        w.write_page(2048, 2048, [data], 1, 1, code, rows_per_strip=2048, extra_tags=extra,
                     write_sampleformat=False, minimal=True)
    w.close()


def build_heavy(b):
    """IMOD packed 4-bit TIFF at K2 super-resolution, the only geometry rwTIFF.h recognises."""
    nx, ny, nf = 7420, 7676, 3          # the runner needs at least 3 frames
    m = blob_movie(nx, ny, nf, seed=31, n_blobs=4000)
    E.write_packed4_tiff(b.path("heavy/tiff_4bit_k2.tif"), m)
    b.path("heavy/k2_ref.mrcs").write_bytes(E.mrc_bytes(m, 0))
    b.expect("heavy_k2", m)
    b.add(name="heavy_k2_ref", group="heavy", file="heavy/k2_ref.mrcs", heavy=True,
          note="8-bit MRC reference at 7420 x 7676 (the small group shows mode 0 == float32)",
          decode={"reader": "image", "expected": "heavy_k2", "max_rows": 64},
          e2e={"batch": "heavy", "reference": "heavy_k2_ref"})
    b.add(name="tiff_4bit_packed_k2", group="heavy", file="heavy/tiff_4bit_k2.tif", heavy=True,
          note="IMOD packed 4-bit TIFF (SerialEM K2 super-resolution); recognised by geometry only",
          decode={"reader": "image", "expected": "heavy_k2", "max_rows": 64},
          e2e={"batch": "heavy", "reference": "heavy_k2_ref"})


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--include-heavy", action="store_true",
                    help="also write the K2 super-resolution packed 4-bit TIFF and its reference (about 260 MB)")
    ap.add_argument("--groups", default="small,eer", help="comma list of groups to build (small, eer)")
    a = ap.parse_args()
    if a.outdir.exists():
        shutil.rmtree(a.outdir)
    a.outdir.mkdir(parents=True)
    b = Builder(a.outdir, a.include_heavy)
    groups = set(a.groups.split(","))
    if "small" in groups:
        build_small(b)
    if "eer" in groups:
        build_eer(b)
    if a.include_heavy:
        build_heavy(b)
    files = sorted(p for p in a.outdir.rglob("*") if p.is_file())
    manifest = {
        "generator": "generate_format_fixtures.py", "generator_version": GENERATOR_VERSION,
        "numpy": np.__version__, "geometry": {"small": [NX, NY, NF], "eer_grouping": EER_GROUP,
                                             "eer_groups": EER_GROUPS, "eer_tail": EER_TAIL},
        "cases": b.cases, "expected": b.expected,
        "files": {str(p.relative_to(a.outdir)): sha256(p) for p in files},
    }
    (a.outdir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    kinds = {}
    for c in b.cases:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print("wrote %d files, %d cases %s to %s" % (len(files), len(b.cases), kinds, a.outdir))


if __name__ == "__main__":
    main()
