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
#
# These invoke envelope_report.main() on a synthetic series and assert on the JSON it
# emits. An earlier version loaded the module and then re-implemented the predicate it
# claimed to verify, so reverting the production code would have left them green -- the
# same defect these controls exist to prevent.

def _mk_run(tag, arm_id, wall, pair, order, exit_code=0, products=1, star="movies.star",
            gpu=None, binary="/b/motioncorr", **kw):
    r = {"tag": tag, "arm_id": arm_id, "rep": 1, "pair_index": pair, "order_in_pair": order,
         "wall_s": wall, "exit_code": exit_code, "product_count": products,
         "binary": binary, "resource_usage": {}, "memory": {},
         "products": [{"path": "out.star", "bytes": 4, "sha256": "deadbeef"}],
         "sampling": {"foreign_cpu_pct": {"n": 1, "mean": 0, "max": 0},
                      "foreign_threads_inside_mask": {"n": 1, "mean": 0, "max": 0},
                      "device_vram_mib_sampled": {"n": 0}},
         "requested": {"gpu_ordinal": gpu},
         "command": ["taskset", "-c", "0", "/usr/bin/time", "-v", binary, "--i", star],
         "effective": {"j": 8, "io_threads": 8}}
    r.update(kw)
    return r


def _run_report(series, args_extra):
    """Invoke the real main() and return its exit code plus the emitted JSON."""
    import json, subprocess, sys, tempfile
    d = pathlib.Path(tempfile.mkdtemp(prefix="envelope-report-ctl-"))
    (d / "series.json").write_text(json.dumps(series))
    out = d / "report.json"
    rc = subprocess.run(
        [sys.executable, str(HERE / "envelope_report.py"), "--series", str(d / "series.json"),
         "--json-out", str(out)] + args_extra,
        capture_output=True, text=True)
    data = json.loads(out.read_text()) if out.exists() else None
    return rc.returncode, data, rc.stdout


def control_failed_runs_excluded_from_timing():
    """A run that died early must not lower its arm's median, via main()'s own output."""
    bad = []
    healthy = _mk_run("ok1", "arm", 30.0, 1, 0)
    for name, broken in (
            ("non-zero exit", _mk_run("x", "arm", 2.0, 2, 0, exit_code=1)),
            ("timed out", _mk_run("x", "arm", 2.0, 2, 0, timed_out=True)),
            ("quarantined", _mk_run("x", "arm", 2.0, 2, 0, quarantined=True)),
            ("cleanup unconfirmed", _mk_run("x", "arm", 2.0, 2, 0, cleanup_unconfirmed=True)),
            ("no products", _mk_run("x", "arm", 2.0, 2, 0, products=0))):
        series = {"plan_name": "ctl", "runs": [healthy, _mk_run("ok2", "arm", 30.0, 3, 0), broken],
                  "arms": [{"id": "arm", "input_star": "movies.star", "gpu": None,
                            "binary": "/b/motioncorr"}]}
        rc, data, _ = _run_report(series, ["--reference-arm", "arm"])
        med = (data or {}).get("timing", {}).get("arm", {}).get("median_s")
        n = (data or {}).get("timing", {}).get("arm", {}).get("n")
        ok = med is not None and abs(med - 30.0) < 1e-9 and n == 2
        print(f"  {'PASS' if ok else 'FAIL'}  main() keeps a {name} run out of the median: "
              f"median={med} n={n} (2.0s run must not appear)")
        if not ok:
            bad.append(name)
    return bad


def control_reference_keys_distinguish_backend():
    """Two references sharing an input STAR but differing in backend must not collide."""
    bad = []
    series = {"plan_name": "ctl",
              "arms": [{"id": "cpu_a", "input_star": "movies.star", "gpu": None,
                        "binary": "/b/cpu/motioncorr"},
                       {"id": "gpu_a", "input_star": "movies.star", "gpu": 0,
                        "binary": "/b/cuda/motioncorr"}],
              "runs": [_mk_run("c", "cpu_a", 10.0, 1, 0, binary="/b/cpu/motioncorr"),
                       _mk_run("g", "gpu_a", 10.0, 2, 0, gpu=0, binary="/b/cuda/motioncorr")]}
    rc, data, out = _run_report(series, ["--reference-arm", "cpu_a", "--reference-arm", "gpu_a"])
    ok = rc == 0 and data is not None
    print(f"  {'PASS' if ok else 'FAIL'}  main() accepts two references that differ only by "
          f"backend: rc={rc}")
    bad += [] if ok else ["distinct backends rejected"]

    rc2, _, out2 = _run_report(series, ["--reference-arm", "cpu_a", "--reference-arm", "cpu_a"])
    ok2 = rc2 == 2 and "Ambiguous references are rejected" in out2
    print(f"  {'PASS' if ok2 else 'FAIL'}  main() rejects a duplicate reference: rc={rc2} "
          f"(expected 2)")
    bad += [] if ok2 else ["duplicate not rejected"]

    # Discriminating: with only the CPU reference named, the CUDA arm must be left unscored
    # rather than silently scored against the CPU baseline.
    rc3, _, out3 = _run_report(series, ["--reference-arm", "cpu_a"])
    ok3 = "gpu_a" in out3 and "no same-input, same-backend reference" in out3
    print(f"  {'PASS' if ok3 else 'FAIL'}  a CUDA arm is NOT scored against a CPU reference "
          f"(left unscored)")
    bad += [] if ok3 else ["cross-backend scoring"]
    return bad



if __name__ == "__main__":
    sys.exit(main())
