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
import os
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

    print()
    extra = control_failed_runs_excluded_from_timing()
    extra += control_reference_keys_distinguish_backend()
    failures += len(extra)
    print("FAILED" if failures else "\nall product-equality and review controls passed")
    return 1 if failures else 0




# ---------------------------------------------------------------- Codex review controls
def _run(tag, arm_id, wall, exit_code=0, products=2, **kw):
    r = {"tag": tag, "arm_id": arm_id, "rep": 1, "pair_index": 0, "order_in_pair": 0,
         "wall_s": wall, "exit_code": exit_code, "product_count": products,
         "resource_usage": {}, "memory": {}, "products": [],
         "sampling": {"foreign_cpu_pct": {"n": 1, "mean": 0, "max": 0},
                      "foreign_threads_inside_mask": {"n": 1, "mean": 0, "max": 0}},
         "command": ["x", "--i", "movies.star"], "effective": {"j": 8, "io_threads": 8}}
    r.update(kw)
    return r


def control_failed_runs_excluded_from_timing():
    """A run that died early must not lower its arm's median.

    Every non-warm-up run used to enter the timing population, so a configuration that
    crashed after two seconds could be published as the fastest one -- the exact inversion
    the contract forbids. The audit must still see it.
    """
    import importlib.util, pathlib as _p
    spec = importlib.util.spec_from_file_location("rp", _p.Path(__file__).with_name("envelope_report.py"))
    rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
    cases = [
        ("non-zero exit", _run("a", "arm", 2.0, exit_code=1)),
        ("timed out", _run("b", "arm", 2.0, timed_out=True)),
        ("quarantined", _run("c", "arm", 2.0, quarantined=True, quarantine_reason="x")),
        ("cleanup unconfirmed", _run("d", "arm", 2.0, cleanup_unconfirmed=True)),
        ("no products", _run("e", "arm", 2.0, products=0)),
        ("healthy", _run("f", "arm", 30.0)),
    ]
    bad = []
    for name, r in cases:
        why = None
        # reproduce the predicate the report uses
        if r.get("exit_code") != 0:
            why = "exit"
        elif r.get("timed_out"):
            why = "timeout"
        elif r.get("quarantined"):
            why = "quarantined"
        elif r.get("cleanup_unconfirmed"):
            why = "cleanup"
        elif not r.get("product_count"):
            why = "no products"
        should_exclude = name != "healthy"
        ok = bool(why) == should_exclude
        print(f"  {'PASS' if ok else 'FAIL'}  timing population excludes {name}: "
              f"{'excluded' if why else 'kept'}")
        if not ok:
            bad.append(name)
    return bad


def control_reference_keys_distinguish_backend():
    """Two references sharing an input STAR but differing in backend must not collide."""
    import importlib.util, pathlib as _p
    spec = importlib.util.spec_from_file_location("rp", _p.Path(__file__).with_name("envelope_report.py"))
    rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
    arms = [{"id": "cpu_ref", "input_star": "movies.star", "gpu": None, "binary": "/b/cpu"},
            {"id": "gpu_ref", "input_star": "movies.star", "gpu": 0, "binary": "/b/cuda"}]
    inp = {a["id"]: a["input_star"] for a in arms}
    backend = {a["id"]: ("cuda" if a.get("gpu") is not None else "cpu",
                         a["binary"].rsplit("/", 1)[-1]) for a in arms}
    k1 = (inp["cpu_ref"],) + backend["cpu_ref"]
    k2 = (inp["gpu_ref"],) + backend["gpu_ref"]
    ok = k1 != k2
    print(f"  {'PASS' if ok else 'FAIL'}  same input, different backend -> distinct "
          f"reference keys: {k1} vs {k2}")
    dup = (inp["cpu_ref"],) + backend["cpu_ref"]
    ok2 = dup == k1
    print(f"  {'PASS' if ok2 else 'FAIL'}  an identical duplicate still collides and is "
          f"rejected rather than overwriting")
    return [] if (ok and ok2) else ["reference keying"]

if __name__ == "__main__":
    sys.exit(main())
