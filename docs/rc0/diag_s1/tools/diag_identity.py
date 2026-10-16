#!/usr/bin/env python3
"""Product identity between two run dirs: MRC core header (bytes 0-223) + payload, and STAR bytes.
MRC labels (224-1023) carry a run timestamp and are excluded."""
import hashlib, json, struct, sys
from pathlib import Path


def mrc_parts(p):
    b = open(p, "rb").read()
    nsymbt = struct.unpack_from("<i", b, 92)[0]
    return b[:224], b[1024 + nsymbt:]


def main(a, b):
    a, b = Path(a), Path(b)
    out = {"a": str(a), "b": str(b)}
    ma, mb = next((a / "Movies").glob("*.mrc")), next((b / "Movies").glob("*.mrc"))
    ha, pa = mrc_parts(ma); hb, pb = mrc_parts(mb)
    out["mrc_core_header_identical"] = ha == hb
    out["mrc_payload_identical"] = pa == pb
    out["mrc_payload_sha256"] = [hashlib.sha256(pa).hexdigest(), hashlib.sha256(pb).hexdigest()]
    sa, sb = next((a / "Movies").glob("*.star")), next((b / "Movies").glob("*.star"))
    out["star_identical"] = open(sa, "rb").read() == open(sb, "rb").read()
    out["identical"] = out["mrc_core_header_identical"] and out["mrc_payload_identical"] and out["star_identical"]
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    res = [main(sys.argv[i], sys.argv[i + 1]) for i in range(1, len(sys.argv) - 1, 2)]
    sys.exit(0 if all(r["identical"] for r in res) else 1)
