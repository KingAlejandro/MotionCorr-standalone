#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the cut-down real movies and real_cutdown_manifest.json.

For each item of test-data/real_cutdown_plan.json: cut the source with
tools/cut_down_movie.py, copy side files (gain, defect list), and record SHA-256
and size. Decoded-sample checksums come from runner_numerics, i.e. from
MotionCorr's own readers: the SHA-256 of the decoded float32 samples
(read_tiff_raw), or of the sparse grouped EER render at upsampling 1. Decoding
is exact, so the checksum is portable across platforms. Compressed MRC is
decompressed first, since the helper reads plain MRC.

Usage: make_real_cutdown.py PLAN.json DATA_ROOT OUT_DIR MANIFEST.json --helper runner_numerics
"""
import argparse, bz2, hashlib, json, lzma, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def plain_copy(path, tmp):
    """A plain MRC the helper can read, decompressing .bz2/.xz/.zst."""
    n = path.name
    if n.endswith(".bz2"):
        data = bz2.decompress(path.read_bytes())
    elif n.endswith(".xz"):
        data = lzma.decompress(path.read_bytes())
    elif n.endswith(".zst"):
        data = subprocess.run(["zstd", "-dc", "--", str(path)], check=True, capture_output=True).stdout
    else:
        return path
    out = Path(tmp) / (n.rsplit(".", 1)[0])
    out.write_bytes(data)
    return out


def decoded_checksums(helper, path, item, tmp):
    """SHA-256 of MotionCorr's decoded samples: decoding is exact, so this is portable."""
    dump = Path(tmp) / "dump.bin"
    if path.name.endswith(".eer"):
        subprocess.run([str(helper), "render_eer", str(path), str(dump), "1", str(item["eer_grouping"])], check=True)
        nx, ny, n = struct.unpack("<qqq", dump.read_bytes()[:24])
        kind = "render_eer upsampling 1 grouping %d (sparse dump)" % item["eer_grouping"]
    else:
        subprocess.run([str(helper), "read_tiff_raw", str(plain_copy(path, tmp)), str(dump)], check=True)
        nx, ny, n = struct.unpack("<qqq", dump.read_bytes()[:24])
        kind = "read_tiff_raw (float32 samples)"
    return {"kind": kind, "nx": nx, "ny": ny, "n": n, "sha256": sha256(dump)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path)
    ap.add_argument("data", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--helper", type=Path, required=True)
    a = ap.parse_args()
    plan = json.loads(a.plan.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    items = []
    with tempfile.TemporaryDirectory() as tmp:
        for it in plan["items"]:
            src = a.data / it["source"]
            name = src.name
            if name.endswith(".mrc"):
                name = name[:-4] + ".mrcs"          # MRC stacks need .mrcs
            dst = a.out / it["id"] / name
            cmd = [sys.executable, str(HERE / "cut_down_movie.py"), str(src), str(dst), "--frames", str(it["frames"])]
            if it.get("crop"):
                cmd += ["--crop"] + [str(v) for v in it["crop"]]
            subprocess.run(cmd, check=True)
            files = [{"path": "%s/%s" % (it["id"], name), "sha256": sha256(dst), "bytes": dst.stat().st_size}]
            for side in it.get("side", []):
                s = a.data / side
                shutil.copyfile(s, a.out / it["id"] / s.name)
                files.append({"path": "%s/%s" % (it["id"], s.name), "sha256": sha256(s), "bytes": s.stat().st_size})
            rec = {k: v for k, v in it.items() if k not in ("side",)}
            rec.update(files=files, movie=files[0]["path"], source_sha256=sha256(src),
                       decoded=decoded_checksums(a.helper, dst, it, tmp))
            items.append(rec)
            print("%-28s %8.1f MB  %dx%dx%d" % (it["id"], files[0]["bytes"] / 1e6, rec["decoded"]["nx"],
                                                 rec["decoded"]["ny"], rec["decoded"]["n"]), flush=True)
    manifest = {"plan_sha256": sha256(a.plan), "cut_tool_sha256": sha256(HERE / "cut_down_movie.py"),
                "items": items, "total_bytes": sum(f["bytes"] for i in items for f in i["files"])}
    a.manifest.write_text(json.dumps(manifest, indent=1) + "\n")
    print("total %.1f MB in %d items" % (manifest["total_bytes"] / 1e6, len(items)))


if __name__ == "__main__":
    main()
