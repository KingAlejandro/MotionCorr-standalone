#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""New scratch attempt; reuse only verified binaries/source from completed a01."""
import hashlib
import json
import os
from pathlib import Path
import socket

import run_native as n

BUILT = Path("/mnt/clathrin/motioncorr-215-native-20261022-409be643-a01")


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
    binaries = json.loads((BUILT / "binaries.json").read_text())
    for path, digest in binaries.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    n.save("reuse-verification.json", dict(status="PASS", source_head=n.HEAD,
           source_files=len(source), canonical_files_sha256=expected["canonical_files_sha256"],
           generated_python_bytecode=generated,
           binaries=binaries, previous_exit=json.loads((BUILT / "exit.json").read_text())))
    n.command("host-controls", [n.PYTHON, str(BUILT / "src/tests/test_tiff_identity_later_chunk.py"),
              "--host-binary", str(BUILT / "build/tiff_identity_host_control")], timeout=60)
    gpulock = n.lock("/tmp/motioncorr-gpu2-correctness.lock")
    try:
        probe = n.lock("/tmp/motioncorr-bench.lock")
        n.unlock(probe)
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
            n.health("post", require_idle=True)
        n.save("native-verdict.json", dict(later_exit=rc, early_exit=early))
        assert rc == 0 and early == 0, "native controls failed"
        for path, digest in binaries.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    finally:
        n.unlock(gpulock)


if __name__ == "__main__":
    status = "FAIL"
    try:
        main()
        status = "PASS"
    finally:
        n.save("exit.json", dict(utc=n.utc(), status=status, pid=os.getpid()))
