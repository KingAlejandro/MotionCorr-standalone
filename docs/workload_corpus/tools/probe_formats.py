#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the actual on-disk encoding of EMPIAR movie files with HTTP range requests.

EMPIAR's imageset metadata (data_format, voxel_type) is self-reported and often wrong
(EMPIAR-10216 says unsigned 16-bit; its header is MRC mode 1). This tool lists an
imageset directory, picks movie files, and parses only their headers:

  MRC   1024-byte header: mode, nx/ny/nz, nsymbt, exttyp, machine stamp / byte order
  TIFF  classic or BigTIFF header and the first IFD (second IFD on request):
        bits, sample format, compression, predictor, rows per strip, tiling,
        samples per pixel, byte order, orientation, EER tags 65007-65009
  EER   legacy (non-TIFF) files are reported as such
  compressed MRC (.bz2/.xz/.zst) are reported by suffix; their MRC header is not read

Standard library only. Output: one JSON object per probed file.
"""
import argparse, concurrent.futures as cf, html.parser, json, re, struct, sys, time, urllib.parse, urllib.request

BASE = "https://ftp.ebi.ac.uk/empiar/world_availability/"
MOVIE_EXT = (".tif", ".tiff", ".eer", ".mrc", ".mrcs", ".mrc.bz2", ".mrcs.bz2", ".mrc.xz",
             ".mrcs.xz", ".mrc.zst", ".mrcs.zst", ".gain", ".bz2", ".xz", ".zst", ".tif.bz2")
UA = {"User-Agent": "MotionCorr-corpus-probe/1 (format census; range requests only)"}


def fetch(url, start=None, length=None, timeout=40):
    hdr = dict(UA)
    if start is not None:
        hdr["Range"] = "bytes=%d-%d" % (start, start + length - 1)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
                total = None
                cr = r.headers.get("Content-Range")
                if cr and "/" in cr:
                    total = int(cr.split("/")[-1])
                elif r.headers.get("Content-Length") and start is None:
                    total = int(r.headers["Content-Length"])
                return r.read(), total
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 416):
                raise
            time.sleep(2 + 3 * attempt)
        except Exception:
            time.sleep(2 + 3 * attempt)
    raise RuntimeError("fetch failed: " + url)


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            h = dict(attrs).get("href")
            if h and not h.startswith(("?", "/", "http", "#", "..")):
                self.links.append(h)


def listdir(url):
    data, _ = fetch(url)
    p = Links(); p.feed(data.decode("utf-8", "replace"))
    sizes = {}
    # Apache-style index rows carry a size column; keep it when present.
    for m in re.finditer(r'href="([^"]+)".*?</td><td[^>]*>\s*([0-9.]+[KMGT]?)\s*<', data.decode("utf-8", "replace")):
        sizes[m.group(1)] = m.group(2)
    return [(l, sizes.get(l)) for l in p.links]


def find_movies(url, depth=3, want=2):
    """Breadth-first: return up to `want` movie-like files under url."""
    found, queue = [], [(url, 0)]
    while queue and len(found) < want:
        u, d = queue.pop(0)
        try:
            entries = listdir(u)
        except Exception as e:
            continue
        files = [l for l, _ in entries if not l.endswith("/") and l.lower().endswith(MOVIE_EXT)]
        # Prefer real movies over gain/defect references, but report a gain when that is all there is.
        files.sort(key=lambda l: (("gain" in l.lower()) or ("ref" in l.lower()), l))
        for f in files[:want - len(found)]:
            found.append(u + f)
        if d < depth:
            queue += [(u + l, d + 1) for l, _ in entries if l.endswith("/")][:6]
    return found


TAGS = {256: "width", 257: "length", 258: "bits", 259: "compression", 262: "photometric",
        266: "fillorder", 274: "orientation", 277: "spp", 278: "rps", 284: "planar",
        317: "predictor", 322: "tile_w", 323: "tile_l", 339: "sampleformat", 32997: "imagedepth",
        65007: "eer_rle_depth", 65008: "eer_subpix_h", 65009: "eer_subpix_v", 273: "_stripoffs", 279: "_stripbytes",
        324: "_tileoffs", 325: "_tilebytes"}
TSIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 16: 8, 17: 8, 18: 8}
TFMT = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 16: "Q", 17: "q", 18: "Q"}


def parse_ifd(url, off, e, big):
    n_sz, ent_sz, cnt_fmt = (8, 20, "Q") if big else (2, 12, "H")
    head, _ = fetch(url, off, n_sz)
    n = struct.unpack(e + cnt_fmt, head)[0]
    if n > 4096:
        raise ValueError("implausible IFD entry count %d" % n)
    body, _ = fetch(url, off + n_sz, n * ent_sz + (8 if big else 4))
    tags = {}
    for i in range(n):
        ent = body[i * ent_sz:(i + 1) * ent_sz]
        if big:
            tag, typ, count = struct.unpack(e + "HHQ", ent[:12]); val = ent[12:20]
        else:
            tag, typ, count = struct.unpack(e + "HHI", ent[:8]); val = ent[8:12]
        if tag not in TAGS:
            continue
        name = TAGS[tag]
        if name.startswith("_"):
            tags[name[1:] + "_count"] = count
            continue
        sz = TSIZE.get(typ, 1) * count
        if typ in TFMT and sz <= len(val):
            vals = struct.unpack(e + TFMT[typ] * count, val[:sz])
        elif typ in TFMT and count < 64:
            ptr = struct.unpack(e + ("Q" if big else "I"), val)[0]
            raw, _ = fetch(url, ptr, sz)
            vals = struct.unpack(e + TFMT[typ] * count, raw)
        else:
            vals = ("type%d x%d" % (typ, count),)
        tags[name] = vals[0] if len(vals) == 1 else list(vals)
    nxt = struct.unpack(e + ("Q" if big else "I"), body[n * ent_sz:n * ent_sz + (8 if big else 4)])[0]
    return tags, nxt


def probe_tiff(url, head, total, second=False):
    e = "<" if head[:2] == b"II" else ">"
    magic = struct.unpack(e + "H", head[2:4])[0]
    big = magic == 43
    off = struct.unpack(e + "Q", head[8:16])[0] if big else struct.unpack(e + "I", head[4:8])[0]
    tags, nxt = parse_ifd(url, off, e, big)
    out = dict(container="BigTIFF" if big else "TIFF", byteorder="big" if e == ">" else "little",
               ifd0_offset=off, **tags)
    if second and nxt:
        t2, _ = parse_ifd(url, nxt, e, big)
        out["ifd1_differs"] = {k: v for k, v in t2.items() if tags.get(k) != v}
    return out


MODES = {0: "int8", 1: "int16", 2: "float32", 3: "complex int16", 4: "complex float32", 6: "uint16",
         12: "float16", 101: "4-bit packed"}


def probe_mrc(head, total):
    out = {}
    for e in ("<", ">"):
        nx, ny, nz, mode = struct.unpack(e + "4i", head[:16])
        if 0 < nx < 100000 and 0 < ny < 100000 and -1 <= mode < 1000:
            break
    else:
        return dict(container="MRC?", error="unparseable header")
    nsymbt = struct.unpack(e + "i", head[92:96])[0]
    exttyp = head[104:108].decode("latin-1")
    stamp = head[212:216].hex()
    nversion = struct.unpack(e + "i", head[108:112])[0]
    imodstamp, imodflags = struct.unpack(e + "ii", head[152:160])
    out = dict(container="MRC", byteorder="big" if e == ">" else "little", mode=mode,
               mode_name=MODES.get(mode, "unknown"), nx=nx, ny=ny, nz=nz, nsymbt=nsymbt,
               exttyp=exttyp.strip("\0"), machst=stamp, nversion=nversion,
               imod_stamp=imodstamp, imod_flags=imodflags)
    if total:
        bpp = {0: 1, 1: 2, 2: 4, 6: 2, 12: 2, 101: 0.5}.get(mode)
        if bpp:
            out["payload_matches_size"] = (1024 + nsymbt + int(nx * ny * nz * bpp)) == total
    return out


def probe_file(url, second=False):
    rec = dict(url=url, file=urllib.parse.unquote(url.split("/")[-1]))
    low = rec["file"].lower()
    try:
        if low.endswith((".bz2", ".xz", ".zst")):
            head, total = fetch(url, 0, 16)
            rec.update(container="compressed:" + low.rsplit(".", 1)[1], bytes=total, magic=head[:6].hex())
            return rec
        head, total = fetch(url, 0, 1024)
        rec["bytes"] = total
        if head[:4] in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"):
            rec.update(probe_tiff(url, head, total, second))
        elif low.endswith(".eer"):
            rec.update(container="EER legacy (non-TIFF)", magic=head[:16].hex())
        else:
            rec.update(probe_mrc(head, total))
    except Exception as ex:
        rec["error"] = "%s: %s" % (type(ex).__name__, ex)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalogue", help="JSON from the EMPIAR API census (entry -> imagesets)")
    ap.add_argument("--select", default="all", help="python expression over (fmt, voxel, cat) deciding which imagesets to probe")
    ap.add_argument("--per-imageset", type=int, default=1)
    ap.add_argument("--second-ifd", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="probe at most N imagesets (0 = all)")
    ap.add_argument("--entries", default="", help="comma list of entry ids to restrict to")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    cat = json.load(open(a.catalogue))
    only = set(a.entries.split(",")) if a.entries else None
    jobs = []
    for eid, e in sorted(cat.items(), key=lambda kv: int(kv[0])):
        if e == "ERR" or (only and eid not in only):
            continue
        for s in e["imagesets"]:
            fmt, vox, c = s.get("data_format") or "", s.get("voxel_type") or "", s.get("category") or ""
            if a.select != "all" and not eval(a.select, {}, dict(fmt=fmt, voxel=vox, cat=c)):
                continue
            if not s.get("directory"):
                continue
            jobs.append((eid, s))
    if a.limit:
        jobs = jobs[:a.limit]
    print("probing %d imagesets" % len(jobs), file=sys.stderr)

    def work(job):
        eid, s = job
        url = BASE + eid + "/" + urllib.parse.quote(s["directory"].strip("/")) + "/"
        recs = []
        for f in find_movies(url, want=a.per_imageset):
            r = probe_file(f, a.second_ifd)
            r.update(entry=eid, imageset=s.get("name"), meta_format=s.get("data_format"),
                     meta_voxel=s.get("voxel_type"), meta_category=s.get("category"),
                     meta_size=[s.get("image_width"), s.get("image_height")], meta_frames=s.get("frames_per_image"))
            recs.append(r)
        if not recs:
            recs.append(dict(entry=eid, imageset=s.get("name"), dir=url, error="no movie files found",
                             meta_format=s.get("data_format"), meta_voxel=s.get("voxel_type")))
        return recs

    with open(a.out, "w") as fh, cf.ThreadPoolExecutor(a.workers) as ex:
        for i, recs in enumerate(ex.map(work, jobs)):
            for r in recs:
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            if i % 25 == 0:
                print("  %d/%d" % (i, len(jobs)), file=sys.stderr)


if __name__ == "__main__":
    main()
