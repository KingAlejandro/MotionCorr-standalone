#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read historical archives; verify attempt04 without changing old evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile

root = Path(__file__).resolve().parent
local = Path(sys.argv[1])
verified = []
for attempt in ("01", "02", "03", "04"):
    compact = root / ("attempt" + attempt)
    receipt = json.loads((compact / "archive.json").read_text())
    archive = local / ("attempt" + attempt + ".tar.gz")
    assert archive.stat().st_size == receipt["bytes"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == receipt["sha256"]
    index = json.loads((compact / "raw-index.json").read_text())
    assert len(index) == receipt["indexed_members"]
    with tarfile.open(archive) as tar:
        assert len(tar.getmembers()) == len(index) + 1
        assert json.loads(tar.extractfile("raw-index.json").read()) == index
        for name, expected in index.items():
            data = tar.extractfile(name).read()
            assert len(data) == expected["bytes"]
            assert hashlib.sha256(data).hexdigest() == expected["sha256"]
        count = 0
        for path in compact.rglob("*"):
            if not path.is_file() or path.name in ("raw-index.json", "archive.json"):
                continue
            name = str(path.relative_to(compact))
            assert hashlib.sha256(path.read_bytes()).hexdigest() == index[name]["sha256"]
            count += 1
        exit_status = json.loads(tar.extractfile("exit.json").read())["status"]
        assert exit_status == ("PASS" if attempt == "04" else "FAIL")
        if attempt == "04":
            later = json.loads(tar.extractfile("later-controls/result.json").read())
            early = json.loads(tar.extractfile("early-controls/result.json").read())
            assert len(later) == 8 and all(row["passed"] for row in later)
            assert len(early) == 9 and all(row["passed"] for row in early)
            assert [row["fixed_acceptance"] for row in later
                    if row["label"].startswith("fixed-later-")] == [True, True]
            assert [row["fixed_acceptance"] for row in later
                    if row["label"].startswith("mutant-later-")] == [False, False]
            for phase in ("pre", "post"):
                reuse = json.loads(tar.extractfile(phase + "-reuse-verification.json").read())
                assert reuse["status"] == "PASS" and reuse["source_files"] == 7260
            driver = json.loads(tar.extractfile("driver-identity.json").read())
            post = json.loads(tar.extractfile("driver-post-verification.json").read())
            assert post["status"] == "PASS" and post["files"] == driver["files"]
            for name, digest in driver["files"].items():
                assert hashlib.sha256(tar.extractfile(name).read()).hexdigest() == digest
                assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
            settle = json.loads(tar.extractfile("post-settle.json").read())
            assert settle["status"] == "PASS" and settle["consecutive_idle"] == 2
            assert settle["elapsed_seconds"] < 10
            samples = [json.loads(line) for line in tar.extractfile("post-samples.jsonl").read().splitlines()]
            assert len(samples) == settle["samples"]
            from postrun_idle import validate
            for row in samples:
                validate(row)
            assert all(row["utilization"] == 0 for row in samples[-2:])
            assert all(b["elapsed_seconds"] - a["elapsed_seconds"] >= 1
                       for a, b in zip(samples, samples[1:]))
            witnesses = []
            for row in later:
                witnesses.append(row["label"] + ":")
                for name in ("process.log", "output/Movies/control.log"):
                    text = tar.extractfile("later-controls/" + row["label"] + "/" + name).read().decode()
                    witnesses.extend(line for line in text.splitlines()
                                     if "[tiffidentity]" in line or "identity changed" in line)
            (root / "attempt04-native-witnesses.log").write_text("\n".join(witnesses) + "\n")
    verified.append(dict(attempt=attempt, archive_sha256=receipt["sha256"],
                         verified_members=len(index), verified_compact_files=count,
                         driver_verdict=exit_status, verification="PASS"))
(root / "attempt04-archive-verification.json").write_text(json.dumps(verified, indent=2) + "\n")
print("PASS: four immutable archive hashes, every indexed member and compact receipt; old FAILs retained; attempt04 8+9 rows, driver identities and idle/health PASS")
