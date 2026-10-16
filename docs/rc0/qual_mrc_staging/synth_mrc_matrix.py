#!/usr/bin/env python3
"""W-MRC-Q synthetic fixtures for raw integer MRC staging (#194/#195).

Generates small MRC movies in every mode rwMRC.h reads (0, 1, 2, 6, 12, 101, plus the
refused 3 and 4), with extreme sample values, odd geometry, frame selection, gain on/off
and swapped byte order, and runs each through `motioncorr --use_own` under
--ingest auto / compact / float. Section `compressed` and `errors` cover .xz/.zst/.bz2
movies, damaged streams and truncated or short-header raw MRC.

Identity is tools/profiling/lib/identity.py (header, extended header, payload and every
non-log, non-pdf file; inventories must match). Results go to a JSON file; nothing here
changes a tolerance. Needs numpy and a motioncorr binary.

    synth_mrc_matrix.py --binary B --gpu 3 --work DIR --out results.json --section all
    synth_mrc_matrix.py --binary B --cpu --work DIR --out results.json --section matrix
"""
import argparse
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "test-data"))
sys.path.insert(0, str(ROOT / "tools" / "profiling"))
import generate_synthetic_fixture as gen  # noqa: E402
from lib import identity  # noqa: E402

STAR_HEAD = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.000 300.0 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
"""

EXTREMES = {  # values forced into the fixture so the claimed range is really present
    0: (-128, 127, 0, -1, 1),
    1: (-32768, 32767, 0, -1, 1),
    6: (0, 65535, 32768, 32767, 1),
    2: (-1.0e4, 1.0e4, 0.0, 65535.0, -32768.0),
    12: (-60000.0, 60000.0, 0.0, 65504.0, -65504.0),
}


# ---------------------------------------------------------------- fixtures
def base_stack(nx, ny, nz, seed=20260923):
    """Float movie with known motion (generator in test-data/), centred on 0."""
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / ("mrcgen-%d-%d-%d" % (nx, ny, nz))
    tmp.mkdir(parents=True, exist_ok=True)
    path, _, _ = gen.generate_movie(tmp / "f.mrcs", nx=nx, ny=ny, nframes=nz, seed=seed)
    stack = np.fromfile(path, dtype="<f4", offset=1024).reshape(nz, ny, nx)
    shutil.rmtree(tmp, ignore_errors=True)
    return stack - 100.0  # signal about -3 .. +60, noise sigma 1


def encode(mode, nx, ny, nz):
    """Return the stack as the on-disk dtype for `mode`, with EXTREMES planted in every frame."""
    s = base_stack(nx, ny, nz)
    if mode == 0:
        a = np.clip(np.rint(s * 2.0), -128, 127).astype("<i1")
    elif mode == 1:
        a = np.clip(np.rint(s * 500.0), -32768, 32767).astype("<i2")
    elif mode == 6:
        a = np.clip(np.rint(s * 500.0 + 30000.0), 0, 65535).astype("<u2")
    elif mode == 2:
        a = (s * 1.0).astype("<f4")
    elif mode == 12:
        a = (s * 100.0).astype("<f2")
    else:
        raise ValueError(mode)
    if mode in EXTREMES:
        for f in range(nz):
            for k, v in enumerate(EXTREMES[mode]):
                a[f, 2 + k, 3 + f % max(1, nx - 4)] = v
        a[:, 0, 0] = EXTREMES[mode][0]       # first and last sample in memory order
        a[:, -1, -1] = EXTREMES[mode][1]
    return a


def nibbles(nx, ny, nz):
    rng = np.random.default_rng(7)
    return rng.integers(0, 16, size=(nz, ny * nx), dtype=np.uint8)


def write_mrc(path, mode, stack=None, nx=None, ny=None, nz=None, big_endian=False, nsymbt=0,
              claim_nz=None):
    """1024-byte MRC2014 header + payload. `claim_nz` overrides the header's nz only."""
    if stack is not None:
        nz, ny, nx = stack.shape
    endian = ">" if big_endian else "<"
    header = bytearray(1024)
    hz = claim_nz if claim_nz is not None else nz
    struct.pack_into(endian + "4i", header, 0, nx, ny, hz, mode)
    struct.pack_into(endian + "3i", header, 28, nx, ny, hz)
    struct.pack_into(endian + "3f", header, 40, float(nx), float(ny), float(hz))
    struct.pack_into(endian + "3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into(endian + "3i", header, 64, 1, 2, 3)
    struct.pack_into(endian + "i", header, 92, nsymbt)
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x11, 0x11, 0, 0)) if big_endian else bytes((0x44, 0x41, 0, 0))
    with open(path, "wb") as f:
        f.write(header)
        f.write(b"\x5a" * nsymbt)
        if mode in (3, 4):
            f.write(np.zeros((nz, ny, nx, 2), "<f4").tobytes())
        else:
            a = stack
            if big_endian and a.dtype.itemsize > 1:
                a = a.astype(a.dtype.newbyteorder(">"))
            f.write(a.tobytes())


def write_gain(path, nx, ny):
    rng = np.random.default_rng(11)
    g = (1.0 + 0.1 * rng.standard_normal((ny, nx))).clip(0.5, 1.5).astype("<f4")
    write_mrc(path, 2, g.reshape(1, ny, nx))


# ------------------------------------------------------------------ runner
def run_motioncorr(binary, work, label, movie_name, writer, ingest, gpu, cpu, gain=None,
                   extra=(), env_path=None, expected_frames=None, timeout=900):
    """One arm. `writer(path)` creates the movie file inside the arm's data dir."""
    arm = Path(work) / label
    data, out = arm / "data", arm / "out"
    if arm.exists():
        shutil.rmtree(arm)
    data.mkdir(parents=True)
    out.mkdir()
    writer(data / movie_name)
    (data / "movies.star").write_text(STAR_HEAD + "%s 1\n" % movie_name)
    if gain:
        shutil.copy(gain, data / "gain.mrc")
    witness = arm / "witness.txt"
    cmd = [str(binary), "--i", "movies.star", "--o", str(out) + "/", "--use_own", "--j", "2",
           "--dose_weighting", "--dose_per_frame", "1.0", "--voltage", "300", "--angpix", "1.0",
           "--patch_x", "3", "--patch_y", "3", "--bfactor", "150", "--seed", "1"]
    if not cpu:
        cmd += ["--gpu", str(gpu)]
        if ingest:
            cmd += ["--ingest", ingest, "--ingest_witness", str(witness)]
    if gain:
        cmd += ["--gainref", "gain.mrc"]
    if expected_frames:
        cmd += ["--expected_frames", str(expected_frames)]
    cmd += list(extra)
    env = dict(os.environ)
    if env_path:
        env["PATH"] = env_path + ":" + env["PATH"]
    res = subprocess.run(cmd, cwd=data, capture_output=True, text=True, env=env, timeout=timeout)
    text = res.stdout + res.stderr
    (arm / "stdout_stderr.txt").write_text(text)
    wit = [l.split()[-1] for l in witness.read_text().split("\n") if l] if witness.exists() else []
    products = sorted(os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs)
    return {"label": label, "rc": res.returncode, "witness": wit, "out": str(out),
            "products": products, "completion_star": [p for p in products if p.endswith(".star")],
            "mrc_products": [p for p in products if p.endswith(".mrc")],
            "text": text, "cmd": " ".join(cmd)}


def err_msg(text):
    """First 'in: file, line N' + message pair of the runner's error output, without the backtrace."""
    lines = text.split("\n")
    out = []
    for i, l in enumerate(lines):
        if l.startswith("in: ") and ", line " in l:
            out.append(l.strip() + " :: " + " ".join(x.strip() for x in lines[i + 1:i + 4]
                                                      if x.strip() and not x.startswith("ERROR")
                                                      and not x.startswith("===")))
    return " || ".join(out[:2]) if out else text[-300:].replace("\n", " ")


def brief(a):
    return {k: a[k] for k in ("label", "rc", "witness", "completion_star", "mrc_products")}


def compare(a, b):
    r = identity.compare_trees(a["out"], b["out"])
    return {"identical": r["identical"], "problems": r["problems"], "mrc_compared": r["mrc_compared"],
            "compared": r["compared"], "differences": r["differences"][:3],
            "only_a": r["only_a"], "only_b": r["only_b"]}


# ------------------------------------------------------------------ matrix
def cases():
    """(name, mode, nx, ny, nz, gain, extra options, big_endian, expected auto route)."""
    c = []
    for mode, route in ((0, "compact"), (1, "compact"), (6, "compact"), (2, "float"),
                        (12, "float"), (101, "float")):
        c.append(dict(name="m%d_even" % mode, mode=mode, nx=128, ny=128, nz=8, route=route))
    for mode, route in ((0, "compact"), (1, "compact"), (6, "compact"), (2, "float")):
        c.append(dict(name="m%d_odd_gain" % mode, mode=mode, nx=134, ny=98, nz=9, gain=True, route=route))
        c.append(dict(name="m%d_20fr" % mode, mode=mode, nx=96, ny=112, nz=20, route=route))
        c.append(dict(name="m%d_framesel" % mode, mode=mode, nx=128, ny=128, nz=12, route=route,
                      extra=["--first_frame_sum", "3", "--last_frame_sum", "10"], frames_expected=None))
        c.append(dict(name="m%d_swapped" % mode, mode=mode, nx=120 if mode == 0 else 128, ny=128, nz=8,
                      route=route, big=True))
        c.append(dict(name="m%d_nsymbt" % mode, mode=mode, nx=128, ny=128, nz=8, route=route, nsymbt=1024))
    # Alignment needs even frame dimensions on every route (global alignment uses the whole frame), so an odd
    # nx/ny must fail identically everywhere: odd x with even y, and odd x with odd y (mode 101 refuses at the reader).
    for mode, route in ((1, "compact"), (0, "compact"), (6, "compact"), (2, "float"), (101, "float")):
        c.append(dict(name="m%d_odd_nx133_expected_fail" % mode, mode=mode, nx=133, ny=96, nz=8, route=route,
                      expect_fail=True))
    c.append(dict(name="m1_odd_ny97_expected_fail", mode=1, nx=132, ny=97, nz=8, route="compact", expect_fail=True))
    c.append(dict(name="m101_both_odd_expected_fail", mode=101, nx=133, ny=97, nz=8, route="float", expect_fail=True))
    # Known inherited limit (src/rwMRC.h parseMRCHeader): a big-endian mode-0 header with nx == 128 reads
    # as INT_MIN, abs(INT_MIN) is negative, so no swap is detected. Must fail identically on every route.
    c.append(dict(name="m0_swapped_nx128_inherited", mode=0, nx=128, ny=128, nz=8, route="compact",
                  big=True, expect_fail=True))
    c.append(dict(name="m12_odd_gain", mode=12, nx=134, ny=98, nz=9, gain=True, route="float"))
    c.append(dict(name="m101_gain", mode=101, nx=128, ny=128, nz=8, gain=True, route="float"))
    return c


def make_writer(case):
    mode, nx, ny, nz = case["mode"], case["nx"], case["ny"], case["nz"]
    if mode == 101:
        flat = nibbles(nx, ny, nz)
        return (lambda p: _write_101(p, flat, nx, ny, nz)), flat
    stack = encode(mode, nx, ny, nz)
    return (lambda p: write_mrc(p, mode, stack, big_endian=case.get("big", False),
                                nsymbt=case.get("nsymbt", 0))), stack


def _write_101(path, flat, nx, ny, nz):
    """SerialEM 4-bit packing: two samples per byte, low nibble first, along the flattened frame."""
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, nz, 101)
    struct.pack_into("<3i", header, 28, nx, ny, nz)
    struct.pack_into("<3f", header, 40, float(nx), float(ny), float(nz))
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x44, 0x41, 0, 0))
    with open(path, "wb") as f:
        f.write(header)
        if flat.shape[1] % 2:
            flat = np.pad(flat, ((0, 0), (0, 1)))
        f.write(((flat[:, 0::2] & 0xF) | (flat[:, 1::2] << 4)).astype(np.uint8).tobytes())


def section_matrix(args, results):
    work = Path(args.work) / "matrix"
    for case in cases():
        nx, ny = case["nx"], case["ny"]
        gain = None
        if case.get("gain"):
            gain = work / ("gain_%dx%d.mrc" % (nx, ny))
            if not gain.exists():
                work.mkdir(parents=True, exist_ok=True)
                write_gain(gain, nx, ny)
        writer, stack = make_writer(case)
        extra = case.get("extra", [])
        efr = None if extra else case["nz"]
        arms = {}
        order = ["float", "auto"] + (["compact"] if case["route"] == "compact" else [])
        if args.cpu:
            order = ["cpu"]
        for ingest in order:
            arms[ingest] = run_motioncorr(args.binary, work, "%s-%s" % (case["name"], ingest),
                                          "movie.mrcs", writer, None if args.cpu else ingest,
                                          args.gpu, args.cpu, gain=gain, extra=extra,
                                          expected_frames=efr)
        rec = {"case": {k: v for k, v in case.items()}, "arms": {k: brief(v) for k, v in arms.items()}}
        if case.get("expect_fail") and not args.cpu:
            rec["pass"] = all(a["rc"] != 0 and not a["mrc_products"] and not a["completion_star"]
                              for a in arms.values())
            rec["expected_failure"] = True
            msgs = {err_msg(v["text"]) for v in arms.values()}
            rec["same_error_on_every_route"] = len(msgs) == 1
            rec["error"] = sorted(msgs)[0][:300]
            rec["pass"] = rec["pass"] and rec["same_error_on_every_route"]
            rec["fail_tail"] = {k: [l for l in v["text"].split("\n") if "frame count" in l or "unsupported" in l][:1]
                                for k, v in arms.items()}
        elif not args.cpu:
            rec["expected_route"] = case["route"]
            rec["routes_ok"] = (arms["float"]["witness"] == ["float"]
                                and arms["auto"]["witness"] == [case["route"]]
                                and ("compact" not in arms or arms["compact"]["witness"] == ["compact"]))
            rec["all_rc0"] = all(a["rc"] == 0 for a in arms.values())
            rec["auto_vs_float"] = compare(arms["float"], arms["auto"]) if rec["all_rc0"] else None
            if "compact" in arms and rec["all_rc0"]:
                rec["compact_vs_float"] = compare(arms["float"], arms["compact"])
            else:
                if not rec["all_rc0"]:
                    rec["fail_text"] = {k: err_msg(v["text"]) for k, v in arms.items() if v["rc"]}
            # one-line status
            ok = rec["all_rc0"] and rec["routes_ok"] and rec["auto_vs_float"]["identical"] and \
                rec.get("compact_vs_float", {"identical": True})["identical"]
            rec["pass"] = bool(ok)
            if case["route"] == "float":
                # pinned compact must refuse and publish no products
                pin = run_motioncorr(args.binary, work, "%s-pinned" % case["name"], "movie.mrcs", writer,
                                     "compact", args.gpu, args.cpu, gain=gain, extra=extra,
                                     expected_frames=efr)
                rec["pinned_compact"] = dict(brief(pin), refused=("--ingest compact was requested" in pin["text"]
                                                                  and not pin["mrc_products"]
                                                                  and not pin["completion_star"]))
                rec["pass"] = rec["pass"] and rec["pinned_compact"]["refused"]
        else:
            rec["rc0"] = arms["cpu"]["rc"] == 0
            rec["out"] = arms["cpu"]["out"]
        results["matrix"].append(rec)
        print(("PASS " if rec.get("pass", rec.get("rc0")) else "FAIL ") + case["name"], flush=True)
        if not args.cpu and not args.keep_outputs:
            for a in arms.values():
                shutil.rmtree(Path(a["out"]), ignore_errors=True)


OPTION_SETS = {  # name -> (options, expected auto route, resident session expected)
    "late_bin2": (["--no_early_binning", "--bin_factor", "2"], "compact", True),
    "early_bin2_default": (["--bin_factor", "2"], "float", False),
    "early_bin2_explicit": (["--early_binning", "--bin_factor", "2"], "float", False),
    "noDW_evenodd": (["--save_noDW", "--even_odd_split"], "compact", True),
    "ps_group4": (["--grouping_for_ps", "4"], "compact", True),
}


def section_options(args, results):
    """Coordinator steer: binning, noDW/even-odd and power-spectrum options on signed MRC (modes 0, 1)."""
    work = Path(args.work) / "options"
    for mode in (0, 1):
        for name, (opts, route, session) in OPTION_SETS.items():
            # The power spectrum is resized to a fixed size, so it needs a frame of at least ~540 px at 1.0 A/px
            # (192 px fails identically on every route with "Invalid size given to cropInFourierSpace").
            side = 768 if name == "ps_group4" else 192
            case = dict(mode=mode, nx=side, ny=side, nz=12)
            writer, _ = make_writer(case)
            raw = {i: run_motioncorr(args.binary, work, "o-m%d-%s-%s" % (mode, name, i), "movie.mrcs", writer, i,
                                     args.gpu, False, extra=opts, expected_frames=12) for i in ("float", "auto")}
            rec = {"mode": mode, "option_set": name, "options": opts, "expected_route": route, "side_px": side,
                   "arms": {k: brief(v) for k, v in raw.items()}}
            rec["routes_ok"] = raw["float"]["witness"] == ["float"] and raw["auto"]["witness"] == [route]
            rec["resident_session_used"] = {
                k: "Computing full-frame Fourier transforms (CUDA in-VRAM)" in
                "".join(p.read_text() for p in Path(v["out"]).rglob("*.log")) for k, v in raw.items()}
            rec["session_ok"] = rec["resident_session_used"]["auto"] == session
            ok = all(v["rc"] == 0 for v in raw.values())
            rec["identity"] = compare(raw["float"], raw["auto"]) if ok else {"identical": False, "problems": ["rc"]}
            rec["products"] = sorted({Path(p).name for p in raw["auto"]["products"] if p.endswith(".mrc")})
            if not ok:
                rec["fail_text"] = {k: err_msg(v["text"]) for k, v in raw.items() if v["rc"]}
            if route == "float":
                pin = run_motioncorr(args.binary, work, "o-m%d-%s-pinned" % (mode, name), "movie.mrcs", writer,
                                     "compact", args.gpu, False, extra=opts, expected_frames=12)
                rec["pinned_compact"] = dict(brief(pin), refused="--ingest compact was requested" in pin["text"]
                                             and not pin["mrc_products"] and not pin["completion_star"])
            rec["pass"] = bool(ok and rec["routes_ok"] and rec["session_ok"] and rec["identity"]["identical"]
                               and rec.get("pinned_compact", {"refused": True})["refused"])
            results["options"].append(rec)
            print(("PASS " if rec["pass"] else "FAIL ") + "options m%d %s: routes %s/%s session %s identity %s" % (
                mode, name, raw["float"]["witness"], raw["auto"]["witness"], rec["resident_session_used"]["auto"],
                rec["identity"]["identical"]), flush=True)
            if not args.keep_outputs:
                for v in raw.values():
                    shutil.rmtree(Path(v["out"]), ignore_errors=True)


def section_refuse(args, results):
    """Modes 3 and 4 refuse explicitly under every ingest, with no products."""
    work = Path(args.work) / "refuse"
    for mode in (3, 4):
        recs = {}
        for ingest in (["float", "auto", "compact"] if not args.cpu else ["cpu"]):
            a = run_motioncorr(args.binary, work, "m%d-%s" % (mode, ingest), "movie.mrcs",
                               lambda p, m=mode: write_mrc(p, m, nx=64, ny=64, nz=8), None if args.cpu else ingest,
                               args.gpu, args.cpu)
            recs[ingest] = dict(brief(a), message=[l for l in a["text"].split("\n")
                                                    if "only real-space" in l or "unsupported MRC mode" in l][:1])
        results["refuse"].append({"mode": mode, "arms": recs})
        ok = all(r["rc"] != 0 and not r["mrc_products"] and not r["completion_star"] and r["message"]
                 for r in recs.values())
        print(("PASS " if ok else "FAIL ") + "mode %d refused explicitly under every route" % mode, flush=True)
        results["refuse"][-1]["pass"] = ok


# ------------------------------------------------------------- compressed
def compress(src, dst, codec, extra=()):
    with open(dst, "wb") as f:
        subprocess.run({"xz": ["xz", "-c", "-k", "-T1"], "zst": ["zstd", "-c", "-q"],
                        "bz2": ["bzip2", "-c", "-k"]}[codec] + list(extra) + [str(src)],
                       stdout=f, check=True)


def shim_dir(path, name, body):
    d = Path(path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(d)


def section_compressed(args, results):
    work = Path(args.work) / "compressed"
    work.mkdir(parents=True, exist_ok=True)
    nz = 8
    for mode, mname in ((1, "int16"), (0, "int8"), (6, "uint16"), (2, "float32")):
        case = dict(mode=mode, nx=128, ny=128, nz=nz)
        writer, _ = make_writer(case)
        raw = work / ("src_m%d.mrc" % mode)
        writer(raw)
        ref = run_motioncorr(args.binary, work, "ref-m%d" % mode, "movie.mrcs", writer, "float", args.gpu,
                             args.cpu, expected_frames=nz)
        for codec in ("xz", "zst", "bz2"):
            if codec == "bz2" and mode != 1:
                continue
            comp = work / ("src_m%d.mrc.%s" % (mode, codec))
            compress(raw, comp, codec)
            # bz2: pbzip2 is what the reader calls; absent on this host, so run it twice.
            variants = [("native", None)]
            if codec == "bz2":
                variants.append(("pbzip2-shim", shim_dir(work / "shim-bz2", "pbzip2", 'exec bzip2 -cd "${@: -1}"\n')))
            for vname, envp in variants:
                for ingest in (["auto", "float"] if not args.cpu else ["cpu"]):
                    a = run_motioncorr(args.binary, work, "c-m%d-%s-%s-%s" % (mode, codec, vname, ingest),
                                       "movie.mrc." + codec, lambda p, c=comp: shutil.copy(c, p),
                                       None if args.cpu else ingest, args.gpu, args.cpu, env_path=envp,
                                       expected_frames=nz)
                    rec = dict(mode=mode, codec=codec, decompressor=vname, ingest=ingest, **brief(a))
                    if a["rc"] == 0:
                        rec["vs_uncompressed"] = compare_named(ref, a)
                    else:
                        rec["fail_text"] = err_msg(a["text"])
                    expect_ok = not (codec == "bz2" and vname == "native")
                    rec["route_ok"] = args.cpu or (a["witness"] == ["float"] if a["rc"] == 0 else not a["witness"] or True)
                    rec["pass"] = (a["rc"] == 0 and rec["vs_uncompressed"]["identical"] and rec["route_ok"]) \
                        if expect_ok else (a["rc"] != 0 and not a["completion_star"] and not a["mrc_products"])
                    results["compressed"].append(rec)
                    print(("PASS " if rec["pass"] else "FAIL ") +
                          "compressed m%d %s [%s] ingest=%s" % (mode, codec, vname, ingest), flush=True)
            if not args.cpu and mode in (1, 2) and codec in ("xz", "zst"):
                a = run_motioncorr(args.binary, work, "c-pinned-m%d-%s" % (mode, codec), "movie.mrc." + codec,
                                   lambda p, c=comp: shutil.copy(c, p), "compact", args.gpu, args.cpu,
                                   expected_frames=nz)
                rec = dict(mode=mode, codec=codec, ingest="compact", **brief(a),
                           refused="--ingest compact was requested" in a["text"])
                rec["pass"] = a["rc"] != 0 and rec["refused"] and not a["mrc_products"] and not a["completion_star"]
                results["compressed"].append(rec)
                print(("PASS " if rec["pass"] else "FAIL ") + "pinned compact refuses compressed m%d %s" % (mode, codec),
                      flush=True)
        if mode == 2 and not args.cpu:
            a = run_motioncorr(args.binary, work, "pinned-float32-raw", "movie.mrcs", writer, "compact", args.gpu,
                               args.cpu, expected_frames=nz)
            rec = dict(mode=2, codec="none", ingest="compact", **brief(a),
                       refused="--ingest compact was requested" in a["text"])
            rec["pass"] = a["rc"] != 0 and rec["refused"] and not a["mrc_products"] and not a["completion_star"]
            results["compressed"].append(rec)
            print(("PASS " if rec["pass"] else "FAIL ") + "pinned compact refuses raw float32 MRC", flush=True)

    # damaged streams, mode 1
    case = dict(mode=1, nx=128, ny=128, nz=nz)
    writer, _ = make_writer(case)
    raw = work / "src_m1.mrc"
    for codec in ("xz", "zst"):
        comp = work / ("src_m1.mrc.%s" % codec)
        data = comp.read_bytes()
        damaged = {
            "truncated-60pct": data[: int(len(data) * 0.6)],
            "truncated-tail1": data[:-1],
            "truncated-header-only": data[:300],
        }
        # corrupt only the trailing integrity field: payload is delivered in full, decoder exits nonzero
        flip = bytearray(data)
        if codec == "zst":
            flip[-1] ^= 0xFF           # xxh32 content checksum
        else:
            flip[-13] ^= 0xFF          # a byte of the stream footer's CRC32 (xz format section 2.1.1.2)
        damaged["trailer-corrupt"] = bytes(flip)
        # corrupt a byte in the middle of the compressed payload
        mid = bytearray(data)
        mid[len(mid) // 2] ^= 0x55
        damaged["midstream-corrupt"] = bytes(mid)
        for dname, blob in damaged.items():
            for ingest in (["auto", "float"] if not args.cpu else ["cpu"]):
                a = run_motioncorr(args.binary, work, "d-%s-%s-%s" % (codec, dname, ingest), "movie.mrc." + codec,
                                   lambda p, b=blob: p.write_bytes(b), None if args.cpu else ingest, args.gpu,
                                   args.cpu, expected_frames=nz)
                # decompressor alone, for ground truth
                chk = work / ("d-%s-%s.chk" % (codec, dname))
                chk.write_bytes(blob)
                dec = subprocess.run(["xz" if codec == "xz" else "zstd", "-cd", str(chk)],
                                     capture_output=True)
                rec = dict(codec=codec, damage=dname, ingest=ingest, decoder_rc=dec.returncode,
                           decoder_bytes=len(dec.stdout), expected_bytes=1024 + 8 * 128 * 128 * 2, **brief(a))
                rec["failed_explicitly"] = a["rc"] != 0 or "failed" in a["text"].lower()
                rec["pass"] = rec["failed_explicitly"] and not a["completion_star"] and not a["mrc_products"]
                rec["fail_text"] = err_msg(a["text"])
                results["damaged"].append(rec)
                print(("PASS " if rec["pass"] else "FAIL ") +
                      "damaged %s %s ingest=%s (decoder rc=%d, %d/%d bytes out, motioncorr rc=%d, completion star=%s)"
                      % (codec, dname, ingest, dec.returncode, len(dec.stdout), rec["expected_bytes"], a["rc"],
                         bool(a["completion_star"])), flush=True)

    # nonzero decompressor exit after a complete, correct byte stream (shim stands in for xz/zstd)
    for codec, tool in (("xz", "xz"), ("zst", "zstd")):
        comp = work / ("src_m1.mrc.%s" % codec)
        sd = shim_dir(work / ("shim-exit-" + codec), tool,
                      'f="${@: -1}"; /usr/bin/%s -cd "$f"; exit 3\n' % tool)
        # positive control: the same shim exiting 0 must give a normal, complete run, so the exit-3 arm below
        # can only differ through the decoder's exit status
        sd0 = shim_dir(work / ("shim-exit0-" + codec), tool,
                       'f="${@: -1}"; exec /usr/bin/%s -cd "$f"\n' % tool)
        a0 = run_motioncorr(args.binary, work, "d-shim-exit0-%s" % codec, "movie.mrc." + codec,
                            lambda p, c=comp: shutil.copy(c, p), None if args.cpu else "auto", args.gpu, args.cpu,
                            env_path=sd0, expected_frames=nz)
        rec0 = dict(codec=codec, damage="shim-control-exit-0", ingest="auto", **brief(a0))
        rec0["pass"] = a0["rc"] == 0 and bool(a0["mrc_products"])
        results["damaged"].append(rec0)
        print(("PASS " if rec0["pass"] else "FAIL ") + "shim control exits 0 (%s): rc=%d" % (codec, a0["rc"]), flush=True)
        a = run_motioncorr(args.binary, work, "d-shim-exit3-%s" % codec, "movie.mrc." + codec,
                           lambda p, c=comp: shutil.copy(c, p), None if args.cpu else "auto", args.gpu, args.cpu,
                           env_path=sd, expected_frames=nz)
        rec = dict(codec=codec, damage="decoder-exit-3-after-complete-stream", ingest="auto", **brief(a),
                   failed_explicitly=a["rc"] != 0)
        rec["pass"] = rec["failed_explicitly"] and not a["completion_star"] and not a["mrc_products"]
        rec["fail_text"] = err_msg(a["text"])
        results["damaged"].append(rec)
        print(("PASS " if rec["pass"] else "FAIL ") + "decoder exits 3 after full stream (%s): rc=%d completion star=%s"
              % (codec, a["rc"], bool(a["completion_star"])), flush=True)


def _ref_to_comp(rel):
    """Product names for movie.mrcs vs movie.mrc.<codec>: the writer names outputs from the input name."""
    if rel == "movie_shifts.eps":
        return "movie.mrc_shifts.eps"
    if rel.startswith("movie.") and rel.split(".")[-1] in ("mrc", "star", "log"):
        return "movie_mrc." + rel.split(".")[-1]
    return rel


def _norm(data, root, collapse_ws=True):
    for r in sorted({root.rstrip("/"), os.path.realpath(root).rstrip("/")}, key=len, reverse=True):
        data = data.replace(r.encode(), b"<ROOT>")
    for pat in (b"movie.mrc.zst", b"movie.mrc.bz2", b"movie.mrc.xz", b"movie_mrc", b"movie.mrcs", b"movie.mrc"):
        data = data.replace(pat, b"movie")
    return re.sub(rb"[ \t]+", b" ", data) if collapse_ws else data  # STAR columns are padded to the longest name


def compare_named(ref, a, collapse_ws=True):
    """Plain vs compressed movie: MRC products strict (header, payload); STAR/EPS after root and movie-name
    normalisation; .log and .pdf are inventoried only, as in tools/profiling/lib/identity.py."""
    ra, rb = Path(ref["out"]), Path(a["out"])
    inv_a, inv_b = identity.inventory(str(ra)), identity.inventory(str(rb))
    problems, diffs = [], []
    mapped = sorted(_ref_to_comp(r) for r in inv_a)
    if mapped != sorted(inv_b):
        problems.append("inventories differ after name mapping: %s" % sorted(set(mapped) ^ set(inv_b)))
    n_mrc = 0
    for rel in inv_a:
        other = _ref_to_comp(rel)
        if other not in inv_b or rel.endswith((".log", ".pdf")):
            continue
        pa, pb = ra / rel, rb / other
        if rel.endswith(".mrc"):
            n_mrc += 1
            d = identity.compare_mrc(str(pa), str(pb))
        else:
            d = None if _norm(pa.read_bytes(), str(ra), collapse_ws) == _norm(pb.read_bytes(), str(rb), collapse_ws) \
                else "differs after normalisation"
        if d:
            diffs.append({"file": "%s vs %s" % (rel, other), "difference": d})
    if diffs:
        problems.append("%d file(s) differ" % len(diffs))
    if n_mrc == 0:
        problems.append("no MRC products compared")
    return {"identical": not problems, "problems": problems, "differences": diffs[:3], "mrc_compared": n_mrc}


# ------------------------------------------------------------------ errors
def error_record(args, mode, variant, raw):
    """Outcome per route. `pass` = every route failed explicitly and published nothing (what a damaged raw movie
    should do); `route_consistent` = same exit class and publication on every route (the #195 requirement);
    `products_identical` = float vs auto trees identical when all routes published."""
    arms = {k: dict(brief(v), tail=err_msg(v["text"]) if v["rc"] else "") for k, v in raw.items()}
    published = {k: bool(v["completion_star"] or v["mrc_products"]) for k, v in raw.items()}
    rec = {"mode": mode, "variant": variant, "arms": arms,
           "route_consistent": len({(v["rc"] != 0, published[k]) for k, v in raw.items()}) == 1,
           "all_failed_explicitly": all(v["rc"] != 0 for v in raw.values()),
           "any_published": any(published.values())}
    if all(v["rc"] == 0 for v in raw.values()) and "float" in raw and "auto" in raw:
        rec["products_identical_float_vs_auto"] = compare(raw["float"], raw["auto"])["identical"]
        rec["unaligned_sum_mean"] = {}
        for k, v in raw.items():
            log = Path(v["out"]) / "movie.log"
            if log.exists():
                m = [l for l in log.read_text().split("\n") if "In unaligned sum" in l]
                rec["unaligned_sum_mean"][k] = m[0].split("Mean =")[1].split("Std")[0].strip() if m else None
    rec["pass"] = rec["all_failed_explicitly"] and not rec["any_published"]
    return rec


def section_errors(args, results):
    work = Path(args.work) / "errors"
    work.mkdir(parents=True, exist_ok=True)
    nx = ny = 128
    nz = 8
    for mode in (1, 0, 6, 2):
        case = dict(mode=mode, nx=nx, ny=ny, nz=nz)
        writer, stack = make_writer(case)
        full = work / ("full_m%d.mrc" % mode)
        writer(full)
        blob = full.read_bytes()
        routes = (["float", "auto"] + (["compact"] if mode != 2 else [])) if not args.cpu else ["cpu"]
        variants = {
            "truncated-mid-frame": blob[: 1024 + (nz * nx * ny * stack.dtype.itemsize) // 2 + 7],
            "truncated-one-byte": blob[:-1],
            "truncated-header": blob[:600],
            "header-only": blob[:1024],
        }
        for vname, vb in variants.items():
            raw = {i: run_motioncorr(args.binary, work, "e-m%d-%s-%s" % (mode, vname, i), "movie.mrcs",
                                     lambda p, b=vb: p.write_bytes(b), None if args.cpu else i, args.gpu, args.cpu,
                                     expected_frames=nz) for i in routes}
            rec = error_record(args, mode, vname, raw)
            results["errors"].append(rec)
            print(("PASS " if rec["pass"] else "FAIL ") + "error m%d %s: rc=%s published=%s consistent=%s ident=%s" % (
                mode, vname, {k: v["rc"] for k, v in rec["arms"].items()}, rec["any_published"],
                rec["route_consistent"], rec.get("products_identical_float_vs_auto")), flush=True)
        # header claims more frames than the file holds (no --expected_frames: the header is the only source)
        for claim in (nz + 4, nz * 3):
            raw = {i: run_motioncorr(args.binary, work, "e-m%d-claim%d-%s" % (mode, claim, i), "movie.mrcs",
                                     lambda p, c=claim: write_mrc(p, mode, stack, claim_nz=c),
                                     None if args.cpu else i, args.gpu, args.cpu) for i in routes}
            rec = error_record(args, mode, "claims-%d-frames-has-%d" % (claim, nz), raw)
            results["errors"].append(rec)
            print(("PASS " if rec["pass"] else "FAIL ") + "error m%d claims %d frames: rc=%s published=%s consistent=%s "
                  "ident=%s" % (mode, claim, {k: v["rc"] for k, v in rec["arms"].items()}, rec["any_published"],
                                rec["route_consistent"], rec.get("products_identical_float_vs_auto")), flush=True)
        # a STAR/--expected_frames count that disagrees with the header must fail
        if mode in (1, 2):
            raw = {i: run_motioncorr(args.binary, work, "e-m%d-expect-wrong-%s" % (mode, i), "movie.mrcs", writer,
                                     None if args.cpu else i, args.gpu, args.cpu, expected_frames=nz + 3)
                   for i in routes}
            rec = error_record(args, mode, "expected_frames-mismatch", raw)
            results["errors"].append(rec)
            print(("PASS " if rec["pass"] else "FAIL ") + "error m%d expected_frames mismatch: rc=%s" % (
                mode, {k: v["rc"] for k, v in rec["arms"].items()}), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--cpu", action="store_true", help="CPU-only binary: single arm, no --ingest")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--section", default="all", choices=("all", "matrix", "refuse", "compressed", "errors", "options"))
    ap.add_argument("--keep-outputs", action="store_true")
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    results = {"binary": str(args.binary), "cpu": args.cpu, "matrix": [], "refuse": [], "compressed": [],
               "damaged": [], "errors": [], "options": []}
    todo = ("matrix", "refuse", "compressed", "errors", "options") if args.section == "all" else (args.section,)
    for s in todo:
        {"matrix": section_matrix, "refuse": section_refuse, "compressed": section_compressed,
         "errors": section_errors, "options": section_options}[s](args, results)
    for k in ("matrix", "refuse", "compressed", "damaged", "errors", "options"):
        for r in results[k]:
            r.pop("text", None)
    args.out.write_text(json.dumps(results, indent=1, default=str))
    bad = [r for k in ("matrix", "refuse", "compressed", "damaged", "errors", "options") for r in results[k]
           if not r.get("pass", r.get("rc0", True))]
    print("\n%d records, %d not passing" % (sum(len(results[k]) for k in
                                                ("matrix", "refuse", "compressed", "damaged", "errors", "options")), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
