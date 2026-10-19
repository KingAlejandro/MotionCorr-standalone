#!/usr/bin/env python3
"""Inventory EER files: TIFF container, compression tag, fraction count, geometry.

Walks the IFD chain with struct only (no libtiff), so it is independent of the
renderer it is auditing. Usage: eer_inventory.py FILE...  (prints JSON).
"""
import hashlib, json, os, struct, sys

def inventory(path, want_sha=True):
    out = {"file": os.path.basename(path), "bytes": os.path.getsize(path)}
    with open(path, "rb") as f:
        head = f.read(16)
        if head[:2] == b"II":
            e = "<"
        elif head[:2] == b"MM":
            e = ">"
        else:
            out["container"] = "not TIFF (legacy EER?)"
            return out
        ver = struct.unpack(e + "H", head[2:4])[0]
        big = ver == 43
        out["container"] = "BigTIFF" if big else "TIFF"
        off = struct.unpack(e + "Q", head[8:16])[0] if big else struct.unpack(e + "I", head[4:8])[0]
        n = 0; first = None; comps = set(); shapes = set(); strips = set()
        while off:
            f.seek(off)
            cnt = struct.unpack(e + ("Q" if big else "H"), f.read(8 if big else 2))[0]
            esz = 20 if big else 12
            raw = f.read(cnt * esz)
            tags = {}
            for i in range(cnt):
                ent = raw[i * esz:(i + 1) * esz]
                tag, typ = struct.unpack(e + "HH", ent[:4])
                if big:
                    val = ent[12:20]
                else:
                    val = ent[8:12]
                fmt = {3: "H", 4: "I", 16: "Q", 8: "h", 1: "B", 2: "B"}.get(typ, "I")
                tags[tag] = struct.unpack(e + fmt, val[:struct.calcsize(fmt)])[0]
            n += 1
            comps.add(tags.get(259)); shapes.add((tags.get(256), tags.get(257)))
            strips.add(tags.get(278))
            if first is None:
                first = {t: tags.get(t) for t in (256, 257, 258, 259, 277, 278, 65007, 65008, 65009)}
            nxt = f.read(8 if big else 4)
            off = struct.unpack(e + ("Q" if big else "I"), nxt)[0]
    out.update(directories=n, first_dir_tags=first, compression_tags=sorted(c for c in comps if c is not None),
               shapes=sorted(shapes), rows_per_strip=sorted(s for s in strips if s is not None))
    if want_sha:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(1 << 24), b""):
                h.update(blk)
        out["sha256"] = h.hexdigest()
    return out

if __name__ == "__main__":
    json.dump([inventory(p) for p in sys.argv[1:]], sys.stdout, indent=1)
    print()
