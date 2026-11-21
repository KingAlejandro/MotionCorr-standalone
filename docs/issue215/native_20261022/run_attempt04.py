#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Attempt04: unchanged a01 binaries, bounded read-only post-run idle policy."""
import hashlib
import json
import os
from pathlib import Path
import socket

import run_native as n
from postrun_idle import postrun_health

BUILT = Path("/mnt/clathrin/motioncorr-215-native-20261022-409be643-a01")


def verify_reuse(label):
    expected = json.loads((n.ROOT / "expected-source.json").read_text())
    original_files = json.loads((BUILT / "source-files.json").read_text())["files"]
    actual = {str(p.relative_to(BUILT / "src")): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((BUILT / "src").rglob("*")) if p.is_file()}
    source = {name: actual[name] for name in original_files}
    assert source == original_files, "archive source changed after build"
    generated = {name: digest for name, digest in actual.items() if name not in original_files}
    assert all("__pycache__" in Path(name).parts and Path(name).suffix == ".pyc"
               for name in generated), generated
    digest = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == expected["canonical_files_sha256"] and len(source) == expected["file_count"]
    assert n.HEAD == expected["source_head"]
    archive = BUILT / "issue215-fc1c8e6f-source.tar"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected["archive_sha256"]
    historical = json.loads((n.ROOT / "historical-archives.json").read_text())
    for path, item in historical.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == item["sha256"]
    binaries = json.loads((BUILT / "binaries.json").read_text())
    for path, digest in binaries.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    n.save(label + "-reuse-verification.json", dict(status="PASS", utc=n.utc(), source_head=n.HEAD,
           source_files=len(source), canonical_files_sha256=expected["canonical_files_sha256"],
           generated_python_bytecode=generated, binaries=binaries,
           source_archive_sha256=expected["archive_sha256"], historical_archives=historical))
    return binaries


def main():
    fd = os.open(n.ROOT / "started.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w") as out:
        json.dump(dict(utc=n.utc(), pid=os.getpid(), host=socket.gethostname(), source_head=n.HEAD,
                       build_reused=str(BUILT), cpu_affinity=sorted(os.sched_getaffinity(0)),
                       env={k: n.ENV[k] for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                            "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "CUDA_VISIBLE_DEVICES",
                            "PATH", "LD_LIBRARY_PATH")}), out, indent=2)
    assert sorted(os.sched_getaffinity(0)) == [8, 9]
    assert json.loads((BUILT / "exit.json").read_text())["status"] == "FAIL"
    identities = {name: hashlib.sha256((n.ROOT / name).read_bytes()).hexdigest()
                  for name in ("run_attempt04.py", "postrun_idle.py", "run_native.py",
                               "test_postrun_idle.py", "test_receipt_health.py")}
    n.save("driver-identity.json", dict(policy="two consecutive idle samples; 1s spacing; <10s monotonic",
           implementation_base="698cddea4faad612cf397f6c7a08c861ca55fef2", files=identities,
           compiled_source=n.HEAD, recompiled=False))
    verify_reuse("pre")
    n.command("idle-host-controls", [n.PYTHON, str(n.ROOT / "test_postrun_idle.py")], timeout=60)
    n.command("health-parser-controls", [n.PYTHON, str(n.ROOT / "test_receipt_health.py")], timeout=60)
    n.command("host-controls", [n.PYTHON, str(BUILT / "src/tests/test_tiff_identity_later_chunk.py"),
              "--host-binary", str(BUILT / "build/tiff_identity_host_control")], timeout=60)
    gpulock = n.lock("/tmp/motioncorr-gpu2-correctness.lock")
    try:
        probe = n.lock("/tmp/motioncorr-bench.lock")
        n.unlock(probe)
        n.command("occupancy", ["ps", "-eo", "pid,psr,pcpu,pmem,args"])
        n.command("scratch-space", ["df", "-h", "/mnt/clathrin"])
        n.health("pre", require_idle=True)
        try:
            rc = n.command("later-controls", [n.PYTHON, str(BUILT / "src/tests/run_tiff_identity_later_chunk_controls.py"),
                    "--binary", str(BUILT / "build/motioncorr_tiff_identity_later"),
                    "--mutant-binary", str(BUILT / "build/motioncorr_tiff_identity_first_chunk"),
                    "--workdir", str(n.ROOT / "later-controls"), "--cpus", "8-9"], timeout=1500, required=False)
            if rc == 0:
                n.ENV["MC_TIFF_CONVERSION_EXPECTED"] = str(n.ROOT / "later-controls/first-chunk-floats.bin")
                early = n.command("early-controls", [n.PYTHON, str(BUILT / "src/tests/run_tiff_identity_controls.py"),
                     "--binary", str(BUILT / "build/motioncorr_tiff_identity_later"),
                     "--workdir", str(n.ROOT / "early-controls")], timeout=1500, required=False)
            else:
                early = None
        finally:
            postrun_health()
        later_rows = json.loads((n.ROOT / "later-controls/result.json").read_text())
        early_rows = json.loads((n.ROOT / "early-controls/result.json").read_text()) if early is not None else []
        assert len(later_rows) == 8 and all(row["passed"] for row in later_rows)
        assert len(early_rows) == 9 and all(row["passed"] for row in early_rows)
        assert all(row["fixed_acceptance"] is True for row in later_rows
                   if row["label"].startswith("fixed-later-"))
        assert all(row["fixed_acceptance"] is False for row in later_rows
                   if row["label"].startswith("mutant-later-"))
        n.save("native-verdict.json", dict(later_exit=rc, early_exit=early,
               later_rows_passed=len(later_rows), early_rows_passed=len(early_rows)))
        assert rc == 0 and early == 0, "native controls failed"
    finally:
        n.unlock(gpulock)
        verify_reuse("post")
        for name, digest in identities.items():
            assert hashlib.sha256((n.ROOT / name).read_bytes()).hexdigest() == digest
        n.save("driver-post-verification.json", dict(status="PASS", files=identities))


if __name__ == "__main__":
    status = "FAIL"
    try:
        main()
        status = "PASS"
    finally:
        n.save("exit.json", dict(utc=n.utc(), status=status, pid=os.getpid()))
