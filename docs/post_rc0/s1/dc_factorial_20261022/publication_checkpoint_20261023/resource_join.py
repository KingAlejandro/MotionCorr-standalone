#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Join recorded resource-conflict IDs to frozen evaluation IDs, without extraction."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent.parent
overlap = root / "resource_stop_20261022/gpu2-foreign-overlap.json"
snapshot = root / "analysis_B_pass3_20261023/frozen/snapshot.tgz"
resource = json.loads(overlap.read_bytes())
rows = resource["affected_records"]
affected = [row["id"] for row in rows]
assert len(affected) == len(set(affected)) == 54
assert all(row["exit"] == 0 and row["resource_status"] == "FOREIGN_OBSERVED" for row in rows)
with tarfile.open(snapshot) as archive:
    evaluated = [Path(member.name).stem for member in archive.getmembers()
                 if member.isfile() and member.name.startswith("eval/B/") and member.name.endswith(".json")]
assert len(evaluated) == len(set(evaluated)) == 736
assert all(item.startswith("B-") for item in evaluated)
intersection = sorted(set(affected) & set(evaluated))
assert not intersection
print(json.dumps({
    "schema": "dc262-recorded-resource-id-join/1",
    "inputs_sha256": {
        str(overlap.relative_to(root)): hashlib.sha256(overlap.read_bytes()).hexdigest(),
        str(snapshot.relative_to(root)): hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "resource_join.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "recorded_foreign_overlap_ids": sorted(affected),
    "affected_tiers": dict(Counter(item.split("-", 1)[0] for item in affected)),
    "frozen_evaluation_ids": sorted(evaluated),
    "frozen_record_count": len(evaluated),
    "intersection": intersection,
    "scope": "Recorded before/after foreign-overlap ID set only; not continuous occupancy or timing qualification.",
}, indent=2, sort_keys=True))
