"""Product identity between two MotionCorr output trees (docs/profiling.md).

* MRC (.mrc, .mrcs): the complete 1024-byte header (including all ten labels),
  extended header and payload must be byte-identical. Only the known Relion
  writer timestamp at the end of the first label is normalised. The version,
  remaining label text, padding and other labels are compared.
* Every other file except those below: byte-identical after the tree's own
  absolute root is replaced by a placeholder. STAR and EPS files embed the
  output path; nothing else is normalised.
* .log: excluded, they carry timing values. .pdf: inventoried only,
  Ghostscript embeds a creation date and a time-derived /ID.
* Both trees must hold the same file inventory and at least one MRC.
  An empty comparison is a failure, not a pass.
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
from typing import Dict, List, Optional

MRC_EXT = (".mrc", ".mrcs")
LABEL_START, HEADER_LEN = 224, 1024
EXCLUDED = {".log": "timing values in per-movie logs",
            ".pdf": "Ghostscript creation date and /ID"}
CHUNK = 8 << 20
WRITER_LABEL = re.compile(
    rb"(Relion [\x20-\x7e]*   )"
    rb"((?:0[1-9]|[12][0-9]|3[01])-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-[0-9]{2}  "
    rb"(?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60))(\x00*)")


def normalise_mrc_header(header: bytes) -> bytes:
    """Mask the known first-label writer clock, leaving every other byte."""
    # nlabl is itself compared in the core header. Do not reinterpret unused
    # label bytes as a writer clock on files without a declared first label.
    if struct.unpack("<i", header[220:224])[0] < 1:
        return header
    match = WRITER_LABEL.fullmatch(header[LABEL_START:LABEL_START + 80])
    if not match:
        return header
    begin, end = match.span(2)
    return header[:LABEL_START + begin] + b"0" * (end - begin) + header[LABEL_START + end:]


def inventory(root: str) -> List[str]:
    out = []
    for d, _, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(out)


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def compare_mrc(a: str, b: str) -> Optional[str]:
    """None when complete headers/extended headers/payloads match after the clock mask."""
    sa, sb = os.path.getsize(a), os.path.getsize(b)
    with open(a, "rb") as fa, open(b, "rb") as fb:
        ha, hb = fa.read(HEADER_LEN), fb.read(HEADER_LEN)
        if len(ha) < HEADER_LEN or len(hb) < HEADER_LEN:
            return "shorter than an MRC header"
        if ha[:LABEL_START] != hb[:LABEL_START]:
            off = next(i for i in range(LABEL_START) if ha[i] != hb[i])
            return "core header differs at byte %d" % off
        na, nb = normalise_mrc_header(ha), normalise_mrc_header(hb)
        if na[LABEL_START:] != nb[LABEL_START:]:
            off = next(i for i in range(LABEL_START, HEADER_LEN) if na[i] != nb[i])
            return "label header differs at byte %d" % off
        if sa != sb:
            return "size differs (%d vs %d bytes)" % (sa, sb)
        nsymbt = struct.unpack("<i", ha[92:96])[0]
        if nsymbt < 0 or HEADER_LEN + nsymbt > sa:
            return "invalid extended header length %d" % nsymbt
        if fa.read(nsymbt) != fb.read(nsymbt):
            return "extended header differs"
        off = HEADER_LEN + nsymbt
        while True:
            ca, cb = fa.read(CHUNK), fb.read(CHUNK)
            if ca != cb:
                i = next((k for k in range(min(len(ca), len(cb))) if ca[k] != cb[k]), min(len(ca), len(cb)))
                return "payload differs at byte %d" % (off + i)
            if not ca:
                return None
            off += len(ca)


def normalise(data: bytes, root: str) -> bytes:
    for r in sorted({root.rstrip("/"), os.path.realpath(root).rstrip("/")}, key=len, reverse=True):
        data = data.replace(r.encode(), b"<ROOT>")
    return data


def compare_trees(root_a: str, root_b: str, expect_mrc: Optional[int] = None) -> Dict:
    inv_a, inv_b = inventory(root_a), inventory(root_b)
    sa, sb = set(inv_a), set(inv_b)
    res: Dict = {"root_a": root_a, "root_b": root_b, "only_a": sorted(sa - sb), "only_b": sorted(sb - sa),
                 "compared": 0, "mrc_compared": 0, "excluded": [], "differences": []}
    for rel in sorted(sa & sb):
        ext = _ext(rel)
        pa, pb = os.path.join(root_a, rel), os.path.join(root_b, rel)
        if ext in EXCLUDED:
            res["excluded"].append({"file": rel, "reason": EXCLUDED[ext]})
            continue
        if ext in MRC_EXT:
            diff = compare_mrc(pa, pb)
            res["mrc_compared"] += 1
        else:
            with open(pa, "rb") as f:
                da = normalise(f.read(), root_a)
            with open(pb, "rb") as f:
                db = normalise(f.read(), root_b)
            diff = None if da == db else "differs after root normalisation (sha256 %s vs %s)" % (
                hashlib.sha256(da).hexdigest()[:12], hashlib.sha256(db).hexdigest()[:12])
        res["compared"] += 1
        if diff:
            res["differences"].append({"file": rel, "difference": diff})
    problems = []
    if res["only_a"] or res["only_b"]:
        problems.append("file inventories differ")
    if res["differences"]:
        problems.append("%d file(s) differ" % len(res["differences"]))
    if res["mrc_compared"] == 0:
        problems.append("no MRC products compared")
    if expect_mrc is not None:
        for side, inv in (("a", inv_a), ("b", inv_b)):
            n = sum(1 for p in inv if _ext(p) in MRC_EXT)
            if n != expect_mrc:
                problems.append("tree %s has %d MRC products, expected %d" % (side, n, expect_mrc))
    res["problems"] = problems
    res["identical"] = not problems
    return res
