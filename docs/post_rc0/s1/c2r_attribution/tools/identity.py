#!/usr/bin/env python3
"""Product identity between two run dirs: MRC core header (bytes 0-223) + payload, and per-movie STAR bytes.
The verdict excludes MRC labels (224-1023, which carry a run timestamp) and the extended header; both are
reported separately. It does not compare logs, PDF/EPS or the output inventory."""
import hashlib, json, struct, sys
from pathlib import Path


def mrc_parts(p):
    b = open(p, "rb").read()
    nsymbt = struct.unpack_from("<i", b, 92)[0]
    return b[:224], b[1024 + nsymbt:], b[224:1024], b[1024:1024 + nsymbt]


def main(a, b):
    a, b = Path(a), Path(b)
    out = {"a": str(a), "b": str(b)}
    ma, mb = next((a / "Movies").glob("*.mrc")), next((b / "Movies").glob("*.mrc"))
    ha, pa, la, ea = mrc_parts(ma); hb, pb, lb, eb = mrc_parts(mb)
    out["mrc_labels_identical_unmasked_not_in_verdict"] = la == lb
    out["mrc_ext_header_identical_not_in_verdict"] = ea == eb
    out["mrc_core_header_identical"] = ha == hb
    out["mrc_payload_identical"] = pa == pb
    out["mrc_payload_sha256"] = [hashlib.sha256(pa).hexdigest(), hashlib.sha256(pb).hexdigest()]
    sa, sb = next((a / "Movies").glob("*.star")), next((b / "Movies").glob("*.star"))
    out["star_identical"] = open(sa, "rb").read() == open(sb, "rb").read()
    out["star_sha256"] = [hashlib.sha256(open(sa, "rb").read()).hexdigest(), hashlib.sha256(open(sb, "rb").read()).hexdigest()]
    out["identical"] = out["mrc_core_header_identical"] and out["mrc_payload_identical"] and out["star_identical"]
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    res = [main(sys.argv[i], sys.argv[i + 1]) for i in range(1, len(sys.argv) - 1, 2)]
    sys.exit(0 if all(r["identical"] for r in res) else 1)
