#!/usr/bin/env python3
"""Controls for the issue #26 product-equality checker.

A comparison that reports EQUAL is only worth something if it would have reported DIFFERS
for the changes it claims to detect. These cases pin both directions:

  clock stamp only   -> EQUAL        the RELION timestamp in the first 80-byte MRC label is
                                     masked, as docs/gate_contract.md requires
  label provenance   -> DIFFERS      a real change elsewhere in labels 224-1023 is caught,
                                     so masking the stamp did not amount to dropping labels
  pixel payload      -> DIFFERS      a one-byte pixel change is caught
  truncated file     -> UNPARSEABLE  a file that cannot be parsed is reported as such and
                                     not as an ordinary pixel mismatch

The last case is the one worth keeping. An earlier version returned None on a parse failure
and fell through to a whole-file digest, which includes the timestamped label block and
therefore always differs -- so a truncated output was indistinguishable from a genuine
numerical regression.

Run: python3 tools/test_envelope_report.py
"""

import hashlib
import importlib.util
import pathlib
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


er = _load("envelope_runner", HERE / "envelope_runner.py")
rep = _load("envelope_report", HERE / "envelope_report.py")

STAMP_A = b"RELION   27-Sep-26  23:58:01"
STAMP_B = b"RELION   28-Sep-26  04:11:47"


def _mrc(label: bytes, payload: bytes = b"\0" * 64, short: int = 0) -> bytes:
    h = bytearray(1024)
    for off, val in ((0, 4), (4, 4), (8, 1), (12, 2)):      # nx, ny, nz, mode=float32
        h[off:off + 4] = struct.pack("<i", val)
    h[92:96] = struct.pack("<i", 0)                          # nsymbt
    h[224:1024] = label.ljust(800, b" ")
    return bytes(h) + payload[:len(payload) - short]


def main() -> int:
    root = pathlib.Path(tempfile.mkdtemp(prefix="envelope-report-controls-"))

    def case(tag, label, payload=b"\0" * 64, short=0):
        d = root / tag / "out"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "a.mrc"
        f.write_bytes(_mrc(label, payload, short))
        run = {"tag": tag, "products": [{
            "path": "a.mrc", "bytes": f.stat().st_size,
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "mrc": er.mrc_split_digests(f)}]}
        return rep.product_key(run, root)

    ref = case("ref", STAMP_A)
    cases = [
        ("clock stamp only", case("clock", STAMP_B), "EQUAL"),
        ("label provenance", case("prov", STAMP_A + b" EXTRA-PROVENANCE"), "DIFFERS"),
        ("pixel payload", case("pix", STAMP_A, payload=b"\1" * 64), "DIFFERS"),
        ("truncated file", case("trunc", STAMP_A, short=8), "UNPARSEABLE"),
    ]

    failures = 0
    for name, key, want in cases:
        got = rep.compare_products(ref, key)
        ok = got["verdict"] == want
        failures += not ok
        via = ""
        if got["verdict"] == "DIFFERS":
            via = " via " + ",".join(f for f in ("payloads", "core_headers", "labels")
                                     if not got[f]["equal"])
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<18} expected {want:<12} "
              f"got {got['verdict']}{via}")

    print("FAILED" if failures else "\nall product-equality controls passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
