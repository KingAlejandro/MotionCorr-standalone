#!/usr/bin/env python3
"""Issue 61: provenance capture for the three consumed motion-correction arms.

MRC headers carry a strftime label and are not byte-reproducible, so the pixel
payload (bytes 1024+) and the core header (bytes 0-223) are digested separately.
"""
import hashlib, json, os, struct, sys

RESULTS = "/home/alex/MotionCorr-issue36-full24/results"
ARMS = ["cpu", "default", "allfftw"]
MOVIES = sorted(os.listdir(os.path.join(RESULTS, "default")))


def digests(path):
    core = hashlib.sha256()
    label = hashlib.sha256()
    payload = hashlib.sha256()
    with open(path, "rb") as fh:
        head = fh.read(1024)
        core.update(head[0:224])
        label.update(head[224:1024])
        while True:
            chunk = fh.read(1 << 22)
            if not chunk:
                break
            payload.update(chunk)
    nx, ny, nz, mode = struct.unpack("<4i", head[0:16])
    mx, my, mz = struct.unpack("<3i", head[28:40])
    xl = struct.unpack("<f", head[40:44])[0]
    amin, amax, amean = struct.unpack("<3f", head[76:88])
    arms_ = struct.unpack("<f", head[216:220])[0]
    return {
        "core_header_sha256": core.hexdigest(),
        "label_sha256": label.hexdigest(),
        "pixel_payload_sha256": payload.hexdigest(),
        "nx": nx, "ny": ny, "nz": nz, "mode": mode,
        "angpix": xl / mx,
        "amin": amin, "amax": amax, "amean": amean, "arms": arms_,
        "bytes": os.path.getsize(path),
    }


out = {"results_root": RESULTS, "movies": MOVIES, "arms": {}}
for arm in ARMS:
    out["arms"][arm] = {}
    for mid in MOVIES:
        p = f"{RESULTS}/{arm}/{mid}/output/Movies/20170629_{mid}_frameImage.mrc"
        if not os.path.exists(p):
            out["arms"][arm][mid] = {"MISSING": p}
            continue
        out["arms"][arm][mid] = digests(p)

# cross-arm sanity: geometry must be identical everywhere
geom = set()
for arm in ARMS:
    for mid in MOVIES:
        d = out["arms"][arm][mid]
        if "MISSING" in d:
            continue
        geom.add((d["nx"], d["ny"], d["nz"], d["mode"], round(d["angpix"], 6)))
out["geometry_unique"] = sorted(str(g) for g in geom)

# payload identity check between arms (expected: all different)
ident = {}
for a in ("default", "allfftw"):
    same = sum(1 for m in MOVIES
               if out["arms"][a][m].get("pixel_payload_sha256")
               == out["arms"]["cpu"][m].get("pixel_payload_sha256"))
    ident[f"{a}_payload_identical_to_cpu"] = same
out["payload_identity_vs_cpu"] = ident
json.dump(out, sys.stdout, indent=1, sort_keys=True)
