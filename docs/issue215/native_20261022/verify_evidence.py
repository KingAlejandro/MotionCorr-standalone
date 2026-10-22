#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independently verify downloaded temporary archives against committed receipts."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent
verified = []
for attempt in ("01", "02", "03"):
    compact = root / ("attempt" + attempt)
    receipt = json.loads((compact / "archive.json").read_text())
    local = Path("/tmp/issue215-attempt" + attempt + "-raw.tar.gz")
    assert local.stat().st_size == receipt["bytes"]
    assert hashlib.sha256(local.read_bytes()).hexdigest() == receipt["sha256"]
    index = json.loads((compact / "raw-index.json").read_text())
    assert len(index) == receipt["indexed_members"]
    with tarfile.open(local) as archive:
        assert len(archive.getmembers()) == len(index) + 1
        assert json.loads(archive.extractfile("raw-index.json").read()) == index
        for name, expected in index.items():
            data = archive.extractfile(name).read()
            assert len(data) == expected["bytes"]
            assert hashlib.sha256(data).hexdigest() == expected["sha256"]
        compact_count = 0
        for path in compact.rglob("*"):
            if not path.is_file() or path.name in ("raw-index.json", "archive.json"):
                continue
            name = str(path.relative_to(compact))
            assert hashlib.sha256(path.read_bytes()).hexdigest() == index[name]["sha256"]
            compact_count += 1
        if attempt == "03":
            later = json.loads(archive.extractfile("later-controls/result.json").read())
            early = json.loads(archive.extractfile("early-controls/result.json").read())
            assert len(later) == 8 and all(row["passed"] for row in later)
            assert len(early) == 9 and all(row["passed"] for row in early)
            witnesses = []
            for row in later:
                name = "later-controls/" + row["label"] + "/process.log"
                text = archive.extractfile(name).read().decode()
                witnesses.append(row["label"] + ":")
                witnesses.extend(line for line in text.splitlines() if "[tiffidentity]" in line)
                name = "later-controls/" + row["label"] + "/output/Movies/control.log"
                text = archive.extractfile(name).read().decode()
                witnesses.extend(line for line in text.splitlines() if "identity changed" in line)
            (root / "native-witnesses.log").write_text("\n".join(witnesses) + "\n")
    verified.append(dict(attempt=attempt, archive_sha256=receipt["sha256"],
                         verified_members=len(index), verified_compact_files=compact_count, status="PASS"))
for path in root.rglob("*.json"):
    json.loads(path.read_text())
for path in root.rglob("*.jsonl"):
    for line in path.read_text().splitlines():
        json.loads(line)
(root / "archive-verification.json").write_text(json.dumps(verified, indent=2) + "\n")
print("PASS: all three archive hashes, all indexed members, compact receipts, and JSON syntax; native 8+9 row verdicts")
