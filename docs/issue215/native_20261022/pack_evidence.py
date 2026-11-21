#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Archive finished scratch receipts/products, retaining binaries on host only."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent
assert (root / "exit.json").is_file(), "run has no exit receipt"
files = [p for p in root.iterdir() if p.is_file() and
         p.suffix in (".json", ".jsonl", ".log", ".py", ".sha256", ".pid") and
         p.name not in ("archive.json", "raw-index.json")]
for name in ("later-controls", "early-controls"):
    if (root / name).exists():
        files.extend(p for p in (root / name).rglob("*") if p.is_file())
build = root / "build"
files.extend(p for p in build.rglob("*") if p.is_file() and (
    p.name in ("flags.make", "link.txt", "CMakeCache.txt", "LastTest.log", "CTestTestfile.cmake") or
    p.name == "cuda_movie_session_identity_first_chunk.cu"))
index = {str(p.relative_to(root)): dict(bytes=p.stat().st_size,
         sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(set(files))}
assert index
(root / "raw-index.json").write_text(json.dumps(index, indent=2) + "\n")
archive = root / "raw-evidence.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    for name in index:
        tar.add(root / name, arcname=name, recursive=False)
    tar.add(root / "raw-index.json", arcname="raw-index.json")
with tarfile.open(archive, "r:gz") as tar:
    assert len(tar.getmembers()) == len(index) + 1
    for name, item in index.items():
        data = tar.extractfile(name).read()
        assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
receipt = dict(path=str(archive), bytes=archive.stat().st_size,
               sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
               indexed_members=len(index), status="PASS", verification="all archived bytes rehashed")
(root / "archive.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
