#!/usr/bin/env python3
"""Ordered-pixel identity of the decoded movie buffer, main head vs PR #90 head.

Review on PR #90 records that the in-tree TIFF check compares per-row sums, and
that row sums cannot prove ordered-pixel or packed-nibble layout. This driver
compares the decoded buffers themselves, element by element, in memory order.

It reuses the fixture writer from tests/test_tiff_read.py unchanged, so the
geometries under test are the ones the repository already declares, including
the packed 4-bit case whose row stride is only observable when a strip holds
several rows.

Three controls run against every comparison, because a comparator that cannot
fail proves nothing:

  perm   two pixels swapped within one row of the reference dump. Row sums are
         unchanged by construction -- the check asserts that -- so this is the
         exact defect the in-tree row-sum test is blind to.
  bitflip one float perturbed in the reference dump.
  missing the reference dump deleted.

Each control must be reported as detected. Emits JSON on stdout and to --json.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

CHUNK_FLOATS = 1 << 22  # 16 MiB of float32 per streaming step


def load_fixture_writer(repo: Path):
    """Import tests/test_tiff_read.py as a module and reuse its TIFF writer."""
    path = repo / "tests" / "test_tiff_read.py"
    spec = importlib.util.spec_from_file_location("in_tree_tiff_read", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_dims(path: Path):
    with path.open("rb") as stream:
        return struct.unpack("<3q", stream.read(24))


def compare_dumps(ref: Path, test: Path) -> dict:
    """Stream both dumps and count matching float32 elements, in order."""
    if not ref.is_file():
        return {"comparable": False, "reason": f"missing reference dump {ref.name}"}
    if not test.is_file():
        return {"comparable": False, "reason": f"missing test dump {test.name}"}

    ref_dims, test_dims = read_dims(ref), read_dims(test)
    if ref_dims != test_dims:
        return {"comparable": False, "reason": f"dims differ {ref_dims} vs {test_dims}",
                "ref_dims": list(ref_dims), "test_dims": list(test_dims)}

    expected = ref_dims[0] * ref_dims[1] * ref_dims[2]
    if ref.stat().st_size != 24 + expected * 4 or test.stat().st_size != 24 + expected * 4:
        return {"comparable": False, "reason": "dump size does not match declared dims"}

    matched = 0
    first_bad = None
    max_abs = 0.0
    index = 0
    with ref.open("rb") as rs, test.open("rb") as ts:
        rs.seek(24)
        ts.seek(24)
        while True:
            a = np.frombuffer(rs.read(CHUNK_FLOATS * 4), dtype="<f4")
            b = np.frombuffer(ts.read(CHUNK_FLOATS * 4), dtype="<f4")
            if a.size == 0 and b.size == 0:
                break
            if a.size != b.size:
                return {"comparable": False, "reason": "truncated dump"}
            # Bitwise element identity, not a tolerance: same backend, same input.
            same = a.view("<u4") == b.view("<u4")
            matched += int(same.sum())
            if first_bad is None and not same.all():
                first_bad = index + int(np.argmin(same))
            diff = np.abs(a.astype(np.float64) - b.astype(np.float64))
            if diff.size:
                max_abs = max(max_abs, float(diff.max()))
            index += a.size

    return {
        "comparable": True,
        "dims": list(ref_dims),
        "pixels_compared": expected,
        "pixels_matched": matched,
        "pixels_differing": expected - matched,
        "identical": matched == expected and expected > 0,
        "first_differing_index": first_bad,
        "max_abs_difference": max_abs,
    }


def row_sums(path: Path, nx: int, ny: int, nn: int) -> np.ndarray:
    data = np.fromfile(path, dtype="<f4", offset=24, count=nx * ny * nn)
    return data.reshape(nn * ny, nx).astype(np.float64).sum(axis=1)


def make_controls(ref: Path, work: Path, dims) -> dict:
    """Build the three tampered references and report whether each is detected."""
    nx, ny, nn = dims
    out = {}

    # perm: swap two pixels inside one row. Row sums are invariant under this,
    # which the check below asserts rather than assumes.
    perm = work / (ref.stem + ".perm.bin")
    shutil.copyfile(ref, perm)
    if nx >= 2:
        with perm.open("r+b") as stream:
            mid_row = (nn * ny) // 2
            base = 24 + (mid_row * nx) * 4
            stream.seek(base)
            first = stream.read(4)
            stream.seek(base + (nx - 1) * 4)
            last = stream.read(4)
            stream.seek(base)
            stream.write(last)
            stream.seek(base + (nx - 1) * 4)
            stream.write(first)
        sums_before = row_sums(ref, nx, ny, nn)
        sums_after = row_sums(perm, nx, ny, nn)
        out["perm_row_sums_unchanged"] = bool(np.array_equal(sums_before, sums_after))
        out["perm_bytes_changed"] = sha256(perm) != sha256(ref)
        out["perm"] = compare_dumps(perm, ref)
        out["perm_detected"] = out["perm"].get("identical") is False
    else:
        out["perm_detected"] = None
        out["perm_skipped"] = "row shorter than 2 pixels"

    # bitflip: perturb one float.
    flip = work / (ref.stem + ".bitflip.bin")
    shutil.copyfile(ref, flip)
    with flip.open("r+b") as stream:
        offset = 24 + (nx * ny * nn // 3) * 4
        stream.seek(offset)
        value = struct.unpack("<f", stream.read(4))[0]
        stream.seek(offset)
        stream.write(struct.pack("<f", value + 1.0 if value == value else 1.0))
    out["bitflip"] = compare_dumps(flip, ref)
    out["bitflip_detected"] = out["bitflip"].get("identical") is False

    # missing: reference absent entirely.
    absent = work / (ref.stem + ".absent.bin")
    absent.unlink(missing_ok=True)
    out["missing"] = compare_dumps(absent, ref)
    out["missing_detected"] = out["missing"].get("comparable") is False

    perm.unlink(missing_ok=True)
    flip.unlink(missing_ok=True)
    return out


def dump(binary: Path, movie: Path, out: Path) -> dict:
    proc = subprocess.run([str(binary), str(movie), str(out)],
                          capture_output=True, text=True)
    return {
        "binary": str(binary),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip()[:400],
        "stderr": proc.stderr.strip()[:800],
    }


def synthetic_cases(module, tmp: Path) -> list:
    """The geometries tests/test_tiff_read.py declares, written by its own writer."""
    rng = random.Random(7)
    cases = []

    w, h = 29, 37
    frames = [[rng.randbytes(w * 2) for _ in range(h)] for _ in range(3)]
    path = tmp / "u16_deflate_rps1.tif"
    module.write_tiff(str(path), frames, 16, 8, 1, w)
    cases.append(("u16_deflate_rps1", path))

    w, h = 16, 50
    frames = [[rng.randbytes(w * 2) for _ in range(h)] for _ in range(2)]
    path = tmp / "u16_raw_rps7.tif"
    module.write_tiff(str(path), frames, 16, 1, 7, w)
    cases.append(("u16_raw_rps7", path))

    # Packed 4-bit at the recognised super-resolution geometry, several rows per
    # strip and not dividing the height: the only layout in which a wrong row
    # stride inside a strip is visible at all.
    file_w, h = 3710, 7676
    frames = [[rng.randbytes(file_w) for _ in range(h)]]
    path = tmp / "packed4bit_k2sr.tif"
    module.write_tiff(str(path), frames, 4, 1, 7, file_w * 2)
    cases.append(("packed4bit_k2sr", path))

    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path,
                        help="source tree supplying tests/test_tiff_read.py")
    parser.add_argument("--ref-dumper", required=True, type=Path)
    parser.add_argument("--test-dumper", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--real-movie", type=Path, action="append", default=[],
                        help="real movie to decode as well; repeatable")
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    module = load_fixture_writer(args.repo)

    report = {
        "what": "decoded movie buffer, ordered-pixel identity between two builds",
        "ref_dumper": str(args.ref_dumper),
        "ref_dumper_sha256": sha256(args.ref_dumper),
        "test_dumper": str(args.test_dumper),
        "test_dumper_sha256": sha256(args.test_dumper),
        "fixture_writer": str(args.repo / "tests" / "test_tiff_read.py"),
        "fixture_writer_sha256": sha256(args.repo / "tests" / "test_tiff_read.py"),
        "cases": [],
    }

    with tempfile.TemporaryDirectory(dir=args.work) as tmpname:
        tmp = Path(tmpname)
        cases = synthetic_cases(module, tmp)
        cases += [(f"real:{p.stem}", p) for p in args.real_movie]

        for name, movie in cases:
            entry = {"case": name, "movie": str(movie)}
            if not movie.is_file():
                entry["status"] = "UNRUN"
                entry["reason"] = "input movie not present"
                report["cases"].append(entry)
                continue
            entry["movie_sha256"] = sha256(movie)
            entry["movie_bytes"] = movie.stat().st_size

            ref_bin = tmp / f"{Path(name).name.replace(':', '_')}.ref.bin"
            test_bin = tmp / f"{Path(name).name.replace(':', '_')}.test.bin"
            entry["ref_run"] = dump(args.ref_dumper, movie, ref_bin)
            entry["test_run"] = dump(args.test_dumper, movie, test_bin)

            if entry["ref_run"]["exit_code"] != 0 or entry["test_run"]["exit_code"] != 0:
                entry["status"] = "FAIL"
                entry["reason"] = "a dumper exited nonzero"
                report["cases"].append(entry)
                ref_bin.unlink(missing_ok=True)
                test_bin.unlink(missing_ok=True)
                continue

            entry["ref_dump_sha256"] = sha256(ref_bin)
            entry["test_dump_sha256"] = sha256(test_bin)
            entry["comparison"] = compare_dumps(ref_bin, test_bin)
            entry["controls"] = make_controls(ref_bin, tmp, read_dims(ref_bin))

            controls_ok = (entry["controls"].get("perm_detected") is not False
                           and entry["controls"].get("bitflip_detected") is True
                           and entry["controls"].get("missing_detected") is True
                           and entry["controls"].get("perm_row_sums_unchanged") is not False)
            entry["controls_ok"] = controls_ok
            entry["status"] = ("PASS" if entry["comparison"].get("identical") and controls_ok
                               else "FAIL")

            ref_bin.unlink(missing_ok=True)
            test_bin.unlink(missing_ok=True)
            report["cases"].append(entry)

    statuses = [c["status"] for c in report["cases"]]
    report["summary"] = {
        "cases": len(statuses),
        "pass": statuses.count("PASS"),
        "fail": statuses.count("FAIL"),
        "unrun": statuses.count("UNRUN"),
        "total_pixels_matched": sum(c.get("comparison", {}).get("pixels_matched", 0)
                                    for c in report["cases"]),
        "total_pixels_compared": sum(c.get("comparison", {}).get("pixels_compared", 0)
                                     for c in report["cases"]),
    }
    report["overall"] = ("PASS" if statuses and statuses.count("PASS") == len(statuses)
                         and report["summary"]["total_pixels_matched"] > 0 else "FAIL")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    print("overall:", report["overall"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
